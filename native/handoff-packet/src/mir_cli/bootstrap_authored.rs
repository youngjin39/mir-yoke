//! Library-only authored files and profile validation; no live caller is connected.
use super::authored_text::code_paths;
use super::{Error, Host, release};
use crate::executor_execute::repr;
use crate::mir_cli::bootstrap_adoption::{self as adoption, is_python_space, wire};
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    fs,
    io::Write,
    path::{Path, PathBuf},
};

/// subprocess.run's exact bootstrap boundary. No environment overrides are made here.
pub struct CommandRequest {
    pub argv: Vec<String>,
    pub cwd: PathBuf,
    pub environment: BTreeMap<String, String>,
    pub stdin_null: bool,
    pub capture_output: bool,
    pub text: bool,
    pub check: bool,
}
pub struct CommandOutput {
    pub returncode: i32,
    pub stdout: Vec<u8>,
    pub stderr: Vec<u8>,
}
pub(super) fn run(
    root: &Path,
    argv: &[&str],
    text: bool,
    host: &mut impl Host,
) -> Result<CommandOutput, Error> {
    host.run(&CommandRequest {
        argv: argv.iter().map(|v| (*v).into()).collect(),
        cwd: root.into(),
        environment: BTreeMap::new(),
        stdin_null: true,
        capture_output: true,
        text,
        check: false,
    })
}
pub(super) fn value_error(message: impl Into<String>) -> Error {
    Error::new("ValueError", message)
}
pub(super) fn adopt_error(e: adoption::Error) -> Error {
    Error::new(e.class(), e.to_string())
}
pub(super) fn io_error(path: &Path, e: std::io::Error) -> Error {
    adopt_error(adoption::io_error(path, e))
}
pub(super) fn read_error(path: &Path, e: std::io::Error) -> Error {
    adopt_error(adoption::read_error(path, e))
}
pub(super) fn decode(bytes: Vec<u8>) -> Result<String, Error> {
    adoption::decode(bytes)
        .map(|s| s.replace("\r\n", "\n").replace('\r', "\n"))
        .map_err(adopt_error)
}
pub(super) fn read_text(path: &Path) -> Result<String, Error> {
    decode(fs::read(path).map_err(|e| read_error(path, e))?)
}
pub(super) fn json_text(path: &Path) -> Result<Value, Error> {
    adoption::json_text(&read_text(path)?).map_err(adopt_error)
}
pub(super) fn python_str(value: &Value) -> String {
    value
        .as_str()
        .map(str::to_owned)
        .unwrap_or_else(|| crate::executor_brief_render::python_value_repr(value))
}
pub(super) fn attribute_error(value: &Value, name: &str) -> Error {
    let class = match value {
        Value::Null => "NoneType",
        Value::Bool(_) => "bool",
        Value::Number(n) => {
            if n.is_f64() {
                "float"
            } else {
                "int"
            }
        }
        Value::String(_) => "str",
        Value::Array(_) => "list",
        Value::Object(_) => "dict",
    };
    Error::new(
        "AttributeError",
        format!("'{class}' object has no attribute '{name}'"),
    )
}
/// json.dumps with the default separators and ensure_ascii=False.
pub(super) fn json_spaces(value: &Value) -> String {
    match value {
        Value::Array(v) => format!(
            "[{}]",
            v.iter().map(json_spaces).collect::<Vec<_>>().join(", ")
        ),
        Value::Object(v) => format!(
            "{{{}}}",
            v.iter()
                .map(|(k, v)| format!("{}: {}", json!(k), json_spaces(v)))
                .collect::<Vec<_>>()
                .join(", ")
        ),
        _ => value.to_string(),
    }
}
pub(super) fn ascii(text: String) -> String {
    text.chars()
        .map(|c| {
            if c.is_ascii() {
                c.to_string()
            } else {
                c.encode_utf16(&mut [0; 2])
                    .iter()
                    .map(|u| format!("\\u{u:04x}"))
                    .collect()
            }
        })
        .collect()
}
pub(super) fn pretty(value: &Value, ensure_ascii: bool) -> Result<String, Error> {
    // sort_keys=True, including when preserve_order is enabled by another crate feature.
    fn sorted(value: &Value) -> Value {
        match value {
            Value::Object(v) => {
                let fields: BTreeMap<_, _> = v.iter().collect();
                Value::Object(
                    fields
                        .into_iter()
                        .map(|(k, v)| (k.clone(), sorted(v)))
                        .collect(),
                )
            }
            Value::Array(v) => Value::Array(v.iter().map(sorted).collect()),
            _ => value.clone(),
        }
    }
    let text = serde_json::to_string_pretty(&sorted(value))
        .map_err(|e| Error::new("TypeError", e.to_string()))?;
    Ok(if ensure_ascii { ascii(text) } else { text })
}
pub(super) fn atomic_write_text(path: &Path, body: &str) -> Result<(), Error> {
    atomic_write(path, body, false)
}
fn atomic_write(path: &Path, body: &str, sync: bool) -> Result<(), Error> {
    atomic_write_with(path, body, sync, |source, destination| {
        tempfile::TempPath::try_from_path(source)
            .and_then(|p| p.persist(destination).map_err(|e| e.error))
            .map_err(|e| io_error(destination, e))
    })
}
pub(super) fn atomic_write_with(
    path: &Path,
    body: &str,
    sync: bool,
    replace: impl FnOnce(&Path, &Path) -> Result<(), Error>,
) -> Result<(), Error> {
    let parent = path.parent().unwrap_or(Path::new("."));
    fs::create_dir_all(parent).map_err(|e| io_error(parent, e))?;
    let mut temp = tempfile::Builder::new()
        .prefix(&format!(
            ".{}.",
            path.file_name().unwrap_or_default().to_string_lossy()
        ))
        .tempfile_in(parent)
        .map_err(|e| io_error(parent, e))?;
    #[cfg(windows)]
    let body = body.replace('\n', "\r\n");
    temp.write_all(body.as_bytes())
        .map_err(|e| io_error(temp.path(), e))?;
    if sync {
        temp.as_file()
            .sync_all()
            .map_err(|e| io_error(temp.path(), e))?;
    }
    replace(temp.path(), path)?;
    #[cfg(unix)]
    if sync {
        fs::File::open(parent)
            .and_then(|f| f.sync_all())
            .map_err(|e| io_error(parent, e))?;
    }
    Ok(())
}
pub fn validate_existing_profile(path: &Path, expected_profile: &str) -> Result<Value, Error> {
    let body = read_text(path).map_err(|e| {
        if e.class.ends_with("Error") && e.class != "UnicodeDecodeError" {
            value_error(format!("invalid existing .mir/repo-profile.toml: {e}"))
        } else {
            e
        }
    })?;
    let raw: toml::Value = toml::from_str(&body).map_err(|e| {
        value_error(format!(
            "invalid existing .mir/repo-profile.toml: {}",
            crate::mir_core::tomllib::tomllib_error(&e, &body)
        ))
    })?;
    let raw = serde_json::to_value(raw).map_err(|e| value_error(e.to_string()))?;
    let purpose = raw["repo"]["purpose"].as_str();
    let stack: Vec<_> = raw["repo"]["technology_stack"]
        .as_array()
        .into_iter()
        .flatten()
        .map(python_str)
        .collect();
    let identity_errors = super::validate_project_identity(purpose, &stack);
    if !identity_errors.is_empty() {
        return Err(value_error(format!(
            "existing .mir/repo-profile.toml has incomplete project identity: {}",
            identity_errors.join("; ")
        )));
    }
    if raw["execution"]["non_code_profile"] != expected_profile {
        return Err(value_error(format!(
            "existing .mir/repo-profile.toml profile does not match --profile {}",
            repr(expected_profile)
        )));
    }
    let gates = raw.get("gates").cloned().unwrap_or_else(|| json!({}));
    if !gates.is_object() {
        return Err(attribute_error(&gates, "get"));
    }
    if gates["requires_memory_store"] != true || gates["requires_global_capabilities"] != true {
        return Err(value_error(concat!(
            "existing .mir/repo-profile.toml must explicitly set ",
            "[gates].requires_memory_store=true and requires_global_capabilities=true; ",
            "bootstrap will not overwrite authored policy"
        )));
    }
    Ok(raw)
}
pub(super) fn valid_commit(candidate: &str) -> bool {
    (40..=64).contains(&candidate.len())
        && candidate
            .bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
}
// Parameters mirror the Python library boundary without inventing a configuration object.
#[allow(clippy::too_many_arguments)]
pub fn ensure_authored_files(
    root: &Path,
    slug: &str,
    profile: &str,
    purpose: &str,
    stack: &[String],
    onboarding: Option<&Value>,
    definition_body: Option<&str>,
    replace_provider_profile: bool,
    host: &mut impl Host,
) -> Result<(), Error> {
    let directories = [".mir", "docs", "tasks", ".ai-harness"];
    for name in directories {
        let path = root.join(name);
        if path.is_symlink() || path.exists() && !path.is_dir() {
            return Err(value_error(format!(
                "bootstrap authored directory is unsafe: {name}"
            )));
        }
    }
    for name in directories {
        let path = root.join(name);
        fs::create_dir_all(&path).map_err(|e| io_error(&path, e))?;
    }
    let harness = root.join("harness_a.toml");
    if !harness.exists() {
        atomic_write_text(
            &harness,
            &super::memory_config_text(slug, profile, onboarding)?,
        )?;
    }
    let path = root.join(".mir/repo-profile.toml");
    if !path.exists() || replace_provider_profile {
        let output = run(root, &["git", "rev-parse", "HEAD"], true, host)?;
        let stdout = decode(output.stdout)?;
        let candidate = stdout.trim_matches(is_python_space);
        let base = if output.returncode == 0 && valid_commit(candidate) {
            candidate
        } else {
            "unverified"
        };
        atomic_write_text(
            &path,
            &super::repo_profile_text(root, slug, profile, purpose, stack, base, host)?,
        )?;
    }
    if profile == "content_workspace" {
        let (Some(onboarding), Some(definition_body)) = (onboarding, definition_body) else {
            return Err(Error::new("AssertionError", ""));
        };
        let path = root.join("config/content-onboarding.json");
        let parent = path.parent().unwrap_or(root);
        fs::create_dir_all(parent).map_err(|e| io_error(parent, e))?;
        if path.exists() {
            super::load_content_onboarding(&path)?;
        }
        atomic_write(&path, &(pretty(onboarding, true)? + "\n"), true)?;
        let definition = root.join("docs/project-purpose.md");
        if !definition.exists() {
            atomic_write_text(&definition, definition_body)?;
        }
    }
    if replace_provider_profile {
        reset_provider_contract_state(root, slug, profile, purpose, host)?;
        reset_provider_task_state(root, purpose)?;
    }
    for (relative, body) in [
        (
            "tasks/tdd.json",
            "{\n  \"version\": 1,\n  \"changes\": []\n}\n",
        ),
        ("tasks/plan.md", "# Plan\n\nNo active work.\n"),
    ] {
        let path = root.join(relative);
        if !path.exists() {
            atomic_write_text(&path, body)?;
        }
    }
    Ok(())
}
pub fn reset_provider_contract_state(
    root: &Path,
    slug: &str,
    profile: &str,
    purpose: &str,
    host: &mut impl Host,
) -> Result<(), Error> {
    let paths = code_paths(profile)?.join(", ");
    let updates = [
        (
            "CLAUDE.md".into(),
            super::product_contract_text(slug, profile, purpose),
        ),
        (
            ".ai-harness/bluebricks.md".into(),
            format!(
                concat!(
                    "# Product Bluebricks\n\nPurpose: {purpose}\n\n",
                    "Phase 2 design owns the product module map. Keep dependencies directed, ",
                    "interfaces explicit, and verification proportional to the changed boundary.\n"
                ),
                purpose = purpose
            ),
        ),
        (
            ".mir/boundary.md".into(),
            format!(
                concat!(
                    "# Boundary: {slug}\n\nAllowed product code roots: {paths}.\n",
                    "Protected paths and external-service boundaries are canonical in ",
                    "`.mir/repo-profile.toml`.\n\n",
                    "Blocked: Mir Yoke provider source, maintainer tests, local plugin copies, ",
                    "credentials, and undeclared external writes.\n"
                ),
                slug = slug,
                paths = paths
            ),
        ),
    ];
    let mut changed = release::rewrite_release_matched(root, &updates)?;
    changed.extend(host.compile_adopter_agent_catalog(root, profile)?);
    let generator = root.join("scripts/generate_codex_derivatives.sh");
    if changed.is_empty() || !generator.is_file() {
        return Ok(());
    }
    let generator = wire(&generator);
    let output = run(root, &["bash", &generator], true, host)?;
    if output.returncode != 0 {
        let stderr = decode(output.stderr)?;
        let stdout = decode(output.stdout)?;
        let detail = [
            stderr.trim_matches(is_python_space),
            stdout.trim_matches(is_python_space),
        ]
        .into_iter()
        .find(|s| !s.is_empty())
        .unwrap_or("unknown error");
        return Err(value_error(format!(
            "product contract derivative generation failed: {detail}"
        )));
    }
    Ok(())
}
pub fn reset_provider_task_state(root: &Path, purpose: &str) -> Result<(), Error> {
    // This JSON uses Python's insertion order (not the sorted receipt writer).
    let purpose = json!(purpose).to_string();
    let intent = format!(
        concat!(
            "{{\n  \"goal\": {purpose},\n  \"goal_type\": \"product\",\n",
            "  \"scope\": \"local\",\n  \"priority\": \"normal\",\n  \"history\": []\n}}\n"
        ),
        purpose = purpose
    );
    let updates = [
        (
            "tasks/change_log.md".into(),
            "# Change log\n\nOne bullet per non-trivial product change.\n".into(),
        ),
        (
            "tasks/checklist.md".into(),
            "# Checklist\n\n- [ ] Define the first product outcome.\n".into(),
        ),
        (
            "tasks/handoffs/session-handoff-LATEST.md".into(),
            "# Session Handoff\n\nNo product handoff has been recorded.\n".into(),
        ),
        ("tasks/intent.json".into(), intent),
        ("tasks/plan.md".into(), "# Plan\n\nNo active work.\n".into()),
        (
            "tasks/tdd.json".into(),
            "{\n  \"version\": 1,\n  \"changes\": []\n}\n".into(),
        ),
    ];
    release::rewrite_release_matched(root, &updates).map(|_| ())
}
