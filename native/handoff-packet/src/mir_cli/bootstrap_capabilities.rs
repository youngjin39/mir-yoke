//! Library-only bootstrap capability selection, activation and lock evidence.
#![forbid(unsafe_code)]
use super::authored::{io_error, json_text, python_str, read_text, value_error};
use super::content::truthy;
use super::{Error, Host, release};
use crate::executor_execute::repr;
use crate::mir_cli::bootstrap_adoption::wire;
use crate::plugin_scripts::ontology_check::{Doc, object};
use crate::python_json::{self as py, Object, Text, Value as PyValue};
use serde_json::{Value, json};
use std::{collections::BTreeSet, fs, path::Path};

pub const CATALOG_TEMPLATE_BY_PROFILE: [(&str, &str); 4] = [
    ("code_app", "code_app"),
    ("hybrid_pipeline", "hybrid_pipeline"),
    ("infra_runtime", "infra_runtime"),
    ("content_workspace", "ontology_content"),
];

/// stdout/stderr are separate because finalize redirects stdout only.
pub struct CapabilityOutput {
    pub code: i32,
    pub stdout: Text,
    pub stderr: Text,
}
impl CapabilityOutput {
    /// Reuse the library CLI with an explicitly supplied provider; no provider discovery.
    pub fn run(
        argv: &[String],
        manager: &mut impl crate::mir_cli::capability::Manager,
    ) -> Result<Self, Error> {
        let argv: Vec<_> = argv.iter().map(String::as_str).collect();
        let (code, stdout, stderr) = crate::mir_cli::capability::main(&argv, manager)?;
        Ok(Self {
            code,
            stdout: Text::from_wtf8(&stdout).map_err(super::authored::adopt_error)?,
            stderr: Text::from_wtf8(&stderr).map_err(super::authored::adopt_error)?,
        })
    }
}
pub fn load_capability_sources(root: &Path, profile: &str) -> Result<Value, Error> {
    let path = root.join("config/capability-sources.json");
    if !path.is_file() {
        return Err(value_error(
            "tracked config/capability-sources.json is missing",
        ));
    }
    let raw = json_text(&path).map_err(|e| {
        if e.class == "UnicodeDecodeError" {
            e
        } else {
            value_error(format!("invalid config/capability-sources.json: {e}"))
        }
    })?;
    if !raw.is_object() || !truthy(&raw) {
        return Err(value_error(
            "config/capability-sources.json must be a non-empty JSON object",
        ));
    }
    if !raw["source"].is_object()
        || !truthy(&raw["source"]["url"])
        || !truthy(&raw["source"]["ref"])
    {
        return Err(value_error(
            "capability source must declare source.url and source.ref",
        ));
    }
    let profiles = &raw["profiles"];
    if !profiles.is_object() || !truthy(profiles) {
        return Err(value_error(
            "capability source must declare non-empty profiles",
        ));
    }
    let selected = profiles["aliases"].get(profile).unwrap_or(&Value::Null);
    let selected = if profiles["aliases"].is_object() && !selected.is_null() {
        python_str(selected)
    } else {
        profile.into()
    };
    if !profiles["packs"].is_object() || profiles["packs"].get(&selected).is_none() {
        return Err(value_error(format!(
            "capability source has no pack for profile {}",
            repr(profile)
        )));
    }
    Ok(raw)
}
fn failed(reason: impl Into<Text>) -> (String, PyValue) {
    let mut fields = Object::default();
    fields.insert("reason".into(), PyValue::String(reason.into()));
    ("failed".into(), PyValue::Object(fields))
}
/// Temporary scalar-only main/validator boundary; never flatten Python strings.
pub fn scalar_evidence(value: &PyValue) -> Result<Value, Error> {
    serde_json::from_str(&value.json_sorted(false))
        .map_err(|e| value_error(format!("scalar-only bootstrap boundary: {e}")))
}
fn import(host: &mut impl Host) -> Result<Option<(String, PyValue)>, Error> {
    match host.capability_import() {
        Ok(()) => Ok(None),
        Err(e) if ["ImportError", "ModuleNotFoundError"].contains(&e.class.as_str()) => {
            Ok(Some(failed(format!("capability CLI unavailable: {e}"))))
        }
        Err(e) => Err(e),
    }
}
pub fn activate_capabilities(
    root: &Path,
    profile: &str,
    host: &mut impl Host,
) -> Result<(String, PyValue), Error> {
    if let Some(result) = import(host)? {
        return Ok(result);
    }
    let argv = [
        "sync",
        "--profile",
        profile,
        "--project-root",
        &wire(root),
        "--apply",
        "--json",
    ]
    .map(str::to_owned);
    let output = host.capability_main(&argv)?;
    if output.code != 0 {
        let text = output.stdout.concat(&output.stderr);
        let text = text.strip();
        return Ok(failed(if text.is_empty() {
            Text::from(format!("capability sync exited {}", output.code))
        } else {
            text
        }));
    }
    capability_lock_evidence(root, host)
}

/// Keep the configuration loader injectable while defaulting to the Rust validator.
pub(super) fn capability_config_plugins(path: &Path) -> Result<Value, Error> {
    super::capability_config::plugins(path)
}
pub fn capability_lock_evidence(
    root: &Path,
    host: &mut impl Host,
) -> Result<(String, PyValue), Error> {
    let path = root.join(".mir/capability-lock.json");
    if !path.is_file() {
        return Ok(failed(
            "capability sync did not write .mir/capability-lock.json",
        ));
    }
    let lock = match read_text(&path)
        .and_then(|s| py::parse(&s).map_err(|e| Error::new(e.exception, e.to_string())))
    {
        Ok(value) => value,
        Err(e) if e.class == "UnicodeDecodeError" => return Err(e),
        Err(e) => return Ok(failed(format!("invalid capability lock: {e}"))),
    };
    if !lock.is_object() {
        return Ok(failed("capability lock must be a JSON object"));
    }
    if let Some(artifacts) = lock.get("native_artifacts") {
        let mut validate = || -> Result<(), Error> {
            let config = root.join("config/capability-sources.json");
            let plugins = if config.is_file() {
                host.capability_config_plugins(&config)?
            } else {
                scalar_evidence(&lock["plugins"])?
            };
            host.validate_artifacts(&scalar_evidence(artifacts)?, &plugins)
        };
        match validate() {
            Ok(()) => (),
            Err(e) if ["ValueError", "CapabilityConfigError"].contains(&e.class.as_str()) => {
                return Ok(failed(format!("invalid capability lock: {e}")));
            }
            Err(e) => return Err(e),
        }
    }
    let source = &lock["source"];
    let commit = source
        .get("commit")
        .map(PyValue::py_str)
        .unwrap_or_default();
    if !source.is_object()
        || commit.len() != 40
        || !commit
            .bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
        || !lock["plugins"].is_object()
        || !lock["plugins"].truthy()
    {
        return Ok(failed(
            "capability lock requires source.commit and non-empty plugins",
        ));
    }
    let hash = crate::digest::sha256(&fs::read(&path).map_err(|e| io_error(&path, e))?);
    let mut plugins: Vec<_> = lock["plugins"]
        .as_object()
        .into_iter()
        .flat_map(|m| m.keys().cloned())
        .collect();
    plugins.sort_by(|a, b| a.codepoints.cmp(&b.codepoints));
    let agents = python_sorted(
        lock.get("agents")
            .unwrap_or(&PyValue::Object(Object::default())),
    )?;
    let mut evidence = Object::default();
    for (key, value) in [
        (
            "lock_path",
            PyValue::String(".mir/capability-lock.json".into()),
        ),
        ("lock_sha256", PyValue::String(hash.into())),
        (
            "selected_plugins",
            PyValue::Array(plugins.into_iter().map(PyValue::String).collect()),
        ),
        ("selected_agents", PyValue::Array(agents)),
        ("lock_version", lock["schema_version"].clone()),
        ("source_commit", source["commit"].clone()),
        ("profile", lock["profile"].clone()),
        ("registration", lock["registration"].clone()),
    ] {
        evidence.insert(key.into(), value);
    }
    Ok(("ready".into(), PyValue::Object(evidence)))
}
/// Python `sorted(value)` for the shapes a lock can hold: dict keys, a string list, or a string.
fn python_sorted(value: &PyValue) -> Result<Vec<PyValue>, Error> {
    let mut items: Vec<PyValue> = match value {
        PyValue::Object(map) => map.keys().map(|k| PyValue::String(k.clone())).collect(),
        PyValue::String(text) => text
            .codepoints
            .iter()
            .map(|c| PyValue::String(Text::new(vec![*c])))
            .collect(),
        PyValue::Array(items) if items.iter().all(|v| v.as_text().is_some()) => items.clone(),
        // Python also raises TypeError for non-string items; its exact message is not mirrored.
        PyValue::Array(_) => {
            return Err(Error::new(
                "TypeError",
                "'<' not supported between instances of agent list items",
            ));
        }
        other => {
            return Err(Error::new(
                "TypeError",
                format!("'{}' object is not iterable", other.type_name()),
            ));
        }
    };
    items.sort_by(|a, b| {
        a.as_text()
            .map(|s| &s.codepoints)
            .cmp(&b.as_text().map(|s| &s.codepoints))
    });
    Ok(items)
}
pub fn finalize_capabilities(
    root: &Path,
    prior: Option<&Value>,
    host: &mut impl Host,
) -> Result<(String, PyValue), Error> {
    if !prior.is_some_and(|p| truthy(p) && p["status"] == "restart_required") {
        return Ok(failed(
            "--finalize requires a prior restart_required bootstrap receipt",
        ));
    }
    if let Some(result) = import(host)? {
        return Ok(result);
    }
    let argv = [
        "finalize",
        "--project-root",
        &wire(root),
        "--apply",
        "--after-restart",
        "--json",
    ]
    .map(str::to_owned);
    let output = host.capability_main(&argv)?;
    if output.code != 0 {
        let text = output.stdout.strip();
        return Ok(failed(if text.is_empty() {
            Text::from(format!("capability status exited {}", output.code))
        } else {
            text
        }));
    }
    let (status, evidence) = capability_lock_evidence(root, host)?;
    if !evidence["registration"].is_object()
        || evidence["registration"]["status"].as_str() != Some("active")
    {
        return Ok(failed("capability activation lock is not active"));
    }
    Ok((status, evidence))
}

fn is_object(doc: &Doc) -> bool {
    matches!(doc, Doc::Object(_))
}
fn selected(doc: &Doc, names: &BTreeSet<String>) -> Doc {
    Doc::Object(
        doc.items()
            .iter()
            .filter(|(k, v)| names.contains(k) && is_object(v))
            .cloned()
            .collect(),
    )
}
fn missing(names: &BTreeSet<String>, selected: &Doc, kind: &str) -> Result<(), Error> {
    let missing: Vec<_> = names
        .iter()
        .filter(|k| !selected.has(k))
        .map(|s| repr(s))
        .collect();
    if !missing.is_empty() {
        return Err(value_error(format!(
            "repository agent catalog is missing selected {kind}: [{}]",
            missing.join(", ")
        )));
    }
    Ok(())
}
fn filter_skills(doc: &mut Doc, skills: &Doc) {
    if let Doc::Array(values) = doc {
        values.retain(|v| v.text().is_some_and(|s| skills.has(s)));
    }
}
pub fn compile_adopter_agent_catalog(root: &Path, profile: &str) -> Result<Vec<String>, Error> {
    let relative = "config/repo-agent-management.json";
    let path = root.join(relative);
    let digests = release::release_payload_digests(root)?;
    let Some(expected) = digests.get(relative).filter(|s| !s.is_empty()) else {
        return Ok(vec![]);
    };
    if !release::is_safe_existing_project_file(root, &path)
        || crate::digest::sha256(&fs::read(&path).map_err(|e| io_error(&path, e))?) != *expected
    {
        return Ok(vec![]);
    }
    // First use the shared Python-compatible JSON diagnostics, then retain source order.
    let raw = json_text(&path).map_err(|e| {
        if e.class == "UnicodeDecodeError" {
            e
        } else {
            value_error(format!("invalid repository agent catalog: {e}"))
        }
    })?;
    if !raw.is_object() {
        return Err(value_error(
            "repository agent catalog must be a JSON object",
        ));
    }
    let mut catalog: Doc = serde_json::from_str(&read_text(&path)?)
        .map_err(|e| value_error(format!("invalid repository agent catalog: {e}")))?;
    let capabilities = load_capability_sources(root, profile)?;
    let profiles = &capabilities["profiles"];
    let selected_profile = profiles["aliases"]
        .get(profile)
        .and_then(Value::as_str)
        .unwrap_or(profile);
    let pack = &profiles["packs"][selected_profile];
    let plugins = &capabilities["plugins"];
    if !pack.is_object() || !plugins.is_object() {
        return Err(value_error(format!(
            "capability source has no usable pack for profile {}",
            repr(profile)
        )));
    }
    let agent_names = pack["agents"]
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(Value::as_str)
        .map(|p| {
            // Python Path.stem keeps a trailing dot; handle it independently of Rust's stem.
            let p = p.trim_end_matches('/').rsplit('/').next().unwrap_or("");
            let p = if cfg!(windows) {
                p.rsplit('\\').next().unwrap_or("")
            } else {
                p
            };
            p.rsplit_once('.')
                .filter(|(stem, ext)| !stem.is_empty() && !ext.is_empty())
                .map_or(p, |(stem, _)| stem)
                .to_owned()
        })
        .collect();
    let skill_names = pack["plugins"]
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(Value::as_str)
        .flat_map(|p| plugins[p]["skills"].as_array().into_iter().flatten())
        .filter_map(Value::as_str)
        .map(str::to_owned)
        .collect();
    let mut inventory = catalog.get("catalog").clone();
    let templates = catalog.get("templates");
    let template_name = CATALOG_TEMPLATE_BY_PROFILE
        .iter()
        .find(|(p, _)| *p == profile)
        .map(|(_, t)| *t)
        .ok_or_else(|| Error::new("KeyError", repr(profile)))?;
    if !is_object(&inventory) || !is_object(templates) {
        return Err(value_error(
            "repository agent catalog is missing catalog or templates",
        ));
    }
    let mut template = templates.get(template_name).clone();
    if !is_object(inventory.get("agents"))
        || !is_object(inventory.get("skills"))
        || !is_object(&template)
    {
        return Err(value_error(format!(
            "repository agent catalog has no template for {}",
            repr(profile)
        )));
    }
    let mut agents = selected(inventory.get("agents"), &agent_names);
    missing(&agent_names, &agents, "agents")?;
    let mut skills = selected(inventory.get("skills"), &skill_names);
    if let Doc::Object(entries) = &mut skills {
        for (_, metadata) in entries {
            metadata.set("status", Doc::from(json!("external")));
            metadata.set("source_path", Doc::from(json!("external")));
        }
    }
    missing(&skill_names, &skills, "skills")?;
    if let Doc::Object(entries) = &mut agents {
        for (_, metadata) in entries {
            if let Doc::Object(fields) = metadata {
                for (key, value) in fields {
                    if key == "recommended_skills" {
                        filter_skills(value, &skills);
                    }
                }
            }
        }
    }
    let roles: Vec<Vec<Doc>> = ["control_plane", "execution", "review", "specialist"]
        .iter()
        .map(|role| {
            agents
                .items()
                .iter()
                .filter(|(_, m)| m.get("role").text() == Some(role))
                .map(|(slug, _)| Doc::from(json!(slug)))
                .collect()
        })
        .collect();
    if roles[0].len() != 1 || roles[1].len() > 1 {
        return Err(value_error(
            "selected adopter catalog requires one orchestrator and at most one executor",
        ));
    }
    let mut agent_pack = object(vec![
        ("orchestrator", roles[0][0].clone()),
        ("reviewers", Doc::Array(roles[2].clone())),
        ("specialists", Doc::Array(roles[3].clone())),
    ]);
    if !roles[1].is_empty() {
        agent_pack.set("executor", roles[1][0].clone());
    }
    template.set("default_agent_pack", agent_pack);
    if let Doc::Object(fields) = &mut template {
        for (key, field) in fields {
            if key == "default_skill_pack" {
                if let Doc::Object(buckets) = field {
                    for (bucket, values) in buckets {
                        if ["core", "code", "domain"].contains(&bucket.as_str()) {
                            filter_skills(values, &skills);
                        }
                    }
                }
            } else if key == "tracked_paths"
                && let Doc::Object(paths) = field
            {
                for (name, values) in paths {
                    if let Doc::Array(values) = values {
                        values.retain(|v| !v.text().is_some_and(|s| s.starts_with("plugins/")));
                        if name == "harness_structure" {
                            for path in [
                                "config/capability-sources.json",
                                ".mir/capability-lock.json",
                            ] {
                                let path = Doc::from(json!(path));
                                if !values.contains(&path) {
                                    values.push(path);
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    inventory.set("agents", agents);
    inventory.set("skills", skills);
    catalog.set("catalog", inventory);
    catalog.set("templates", object(vec![(profile, template)]));
    catalog.remove("repositories_dir");
    catalog.set("repositories", Doc::Array(vec![]));
    catalog.set(
        "purpose",
        Doc::from(json!(concat!(
            "Repository-local adopter catalog; reusable skills are supplied by pinned external ",
            "Mir capabilities."
        ))),
    );
    release::rewrite_release_matched(
        root,
        &[(relative.into(), catalog.dump(false, Some(2)) + "\n")],
    )
}
