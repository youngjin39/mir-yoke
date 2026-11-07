//! Library-only bootstrap architecture evidence and installed-surface validation.
#![forbid(unsafe_code)]
use super::authored::{attribute_error, io_error, json_text, read_text};
use super::{Error, Host};
use crate::mir_cli::bootstrap_adoption::phase2::load_yaml;
use serde_json::{Map, Value, json};
use std::{fs, path::Path};

pub const ARCHITECTURE_OUTPUTS: [&str; 4] = [
    "spec/STATE.md",
    "spec/index.yaml",
    "spec/graph.yaml",
    "spec/gaps.yaml",
];
pub const ARCHITECTURE_SEQUENCE: [&str; 2] = ["mir-core:design", "mir-core:spec-architect"];
type Validation = Result<(Vec<String>, Value), Error>;

// Python bool is an int, including for coverage counters and equality checks.
fn integer(value: &Value) -> Option<i128> {
    match value {
        Value::Bool(value) => Some(i128::from(*value)),
        Value::Number(value) => value
            .as_i64()
            .map(i128::from)
            .or_else(|| value.as_u64().map(i128::from)),
        _ => None,
    }
}
fn equals_int(value: &Value, expected: i128) -> bool {
    integer(value) == Some(expected) || value.as_f64() == Some(expected as f64)
}
fn nonnegative(value: &Value) -> Option<i128> {
    integer(value).filter(|value| *value >= 0)
}
fn invalid_document(path: &Path) -> Result<Value, Error> {
    load_yaml(&read_text(path)?).map_err(|e| Error::new("YAMLError", e))
}
pub fn validate_architecture_evidence(root: &Path) -> Validation {
    let evidence_path = root.join("spec/bootstrap-evidence.json");
    let lock_path = root.join(".mir/capability-lock.json");
    let mut errors = Vec::new();
    if evidence_path.is_symlink() || !evidence_path.is_file() {
        return Ok((
            vec!["architecture evidence is missing: spec/bootstrap-evidence.json".into()],
            json!({}),
        ));
    }
    let documents = json_text(&evidence_path)
        .and_then(|evidence| json_text(&lock_path).map(|lock| (evidence, lock)));
    let (mut evidence, lock) = match documents {
        Ok(documents) => documents,
        Err(e) if e.class != "UnicodeDecodeError" => {
            return Ok((
                vec![format!(
                    "architecture evidence or capability lock is invalid: {e}"
                )],
                json!({}),
            ));
        }
        Err(e) => return Err(e),
    };
    if !evidence.is_object() || !equals_int(&evidence["schema_version"], 2) {
        errors.push("architecture evidence schema_version must be 2".into());
        evidence = json!({});
    }
    if evidence["sequence"] != json!(ARCHITECTURE_SEQUENCE) {
        errors.push("architecture evidence must record design then spec-architect".into());
    }
    let locked_commit = lock
        .get("source")
        .and_then(|source| source.get("commit"))
        .filter(|_| lock["source"].is_object())
        .cloned()
        .unwrap_or(Value::Null);
    if evidence["capability_commit"] != locked_commit || !locked_commit.is_string() {
        errors.push("architecture evidence capability_commit does not match the lock".into());
    }
    if evidence["outputs"] != json!(ARCHITECTURE_OUTPUTS) {
        errors.push("architecture evidence must list the required spec outputs".into());
    }
    let mut coverage = evidence["coverage"].clone();
    if !coverage.is_object() {
        errors.push("architecture evidence must contain four-layer spec coverage".into());
        coverage = json!({});
    }
    for (layer, exact) in [
        ("l1", None),
        ("l2", None),
        ("l3", Some(9)),
        ("l4", Some(10)),
    ] {
        let row = &coverage[layer];
        if !row.is_object() {
            errors.push(format!("architecture coverage is missing {layer}"));
            continue;
        }
        let counts: Option<Vec<_>> = ["total", "filled", "derived", "na", "tbd"]
            .iter()
            .map(|key| nonnegative(&row[*key]))
            .collect();
        let Some(counts) = counts else {
            errors.push(format!(
                "architecture coverage {layer} counts must be non-negative integers"
            ));
            continue;
        };
        let total = counts[0];
        if total == 0 || exact.is_some_and(|exact| total != exact) {
            let expected = exact
                .map(|n| format!("exactly {n}"))
                .unwrap_or_else(|| "greater than zero".into());
            errors.push(format!(
                "architecture coverage {layer}.total must be {expected}"
            ));
        }
        if counts[1..].iter().sum::<i128>() != total {
            errors.push(format!(
                "architecture coverage {layer} counts do not sum to total"
            ));
        }
        if counts[4] != 0 {
            errors.push(format!(
                "architecture coverage {layer} still contains TBD requirements"
            ));
        }
    }
    let ai_ready = &coverage["ai_ready"];
    let l1_total = coverage["l1"].get("total").cloned().unwrap_or(Value::Null);
    if !ai_ready.is_object()
        || ["ready", "incomplete", "blocked"]
            .iter()
            .any(|key| nonnegative(&ai_ready[*key]).is_none())
    {
        errors.push("architecture coverage ai_ready counts are missing or invalid".into());
    } else if equals_int(&ai_ready["ready"], 0)
        || !integer(&ai_ready["ready"]).is_some_and(|n| equals_int(&l1_total, n))
        || !equals_int(&ai_ready["incomplete"], 0)
        || !equals_int(&ai_ready["blocked"], 0)
    {
        errors.push("all requirements must be AI-ready with no incomplete or blocked items".into());
    }
    let full_review = &evidence["full_review"];
    if !full_review.is_object()
        || [
            "project_structure",
            "memory",
            "discoverability",
            "requirements",
            "organization",
        ]
        .iter()
        .any(|key| full_review[*key] != "pass")
    {
        errors.push("architecture evidence must record a passing full project review".into());
    }
    // Python word boundaries exclude combining marks; re.I also folds dotted/dotless i.
    let placeholder = regex::Regex::new(concat!(
        r"(?i)(?:^|[^\p{L}\p{N}_])",
        r"(?:de[s\u{017f}]cr[i\u{0130}\u{0131}]be|placeholder|replace[ -]?me|tbd|todo|unknown)",
        r"(?:$|[^\p{L}\p{N}_])",
    ))
    .map_err(|e| Error::new("ValueError", e.to_string()))?;
    let mut output_hashes = Map::new();
    for relative in ARCHITECTURE_OUTPUTS {
        let path = root.join(relative);
        if path.is_symlink() || !path.is_file() {
            errors.push(format!(
                "architecture output is missing or linked: {relative}"
            ));
            continue;
        }
        let body = fs::read(&path).map_err(|e| io_error(&path, e))?;
        if body.iter().all(|b| b" \t\n\r\x0b\x0c".contains(b)) {
            errors.push(format!("architecture output is empty: {relative}"));
            continue;
        }
        if placeholder.is_match(&String::from_utf8_lossy(&body)) {
            errors.push(format!(
                "architecture output contains placeholder text: {relative}"
            ));
        }
        output_hashes.insert(relative.into(), json!(crate::digest::sha256(&body)));
    }
    let mut open_gaps = -1i128;
    match invalid_document(&root.join("spec/gaps.yaml")) {
        Err(e) => errors.push(format!("spec/gaps.yaml is invalid: {e}")),
        Ok(doc) => match doc
            .get("gaps")
            .and_then(Value::as_array)
            .filter(|_| doc.is_object())
        {
            None => errors.push("spec/gaps.yaml must contain a gaps list".into()),
            Some(gaps) => {
                open_gaps = gaps
                    .iter()
                    .filter(|gap| {
                        !gap.is_object()
                            || !["resolved", "dismissed", "na"]
                                .iter()
                                .any(|status| gap["status"] == *status)
                    })
                    .count() as i128;
                if open_gaps != 0 {
                    errors.push(format!("spec/gaps.yaml contains {open_gaps} open gap(s)"));
                }
            }
        },
    }
    if !equals_int(&evidence["open_gaps"], open_gaps) || open_gaps != 0 {
        errors.push(
            "architecture evidence open_gaps must match spec/gaps.yaml and equal zero".into(),
        );
    }
    for name in ["index.yaml", "graph.yaml"] {
        let doc = match invalid_document(&root.join("spec").join(name)) {
            Ok(doc) => doc,
            Err(e) => {
                errors.push(format!("spec/{name} is invalid: {e}"));
                continue;
            }
        };
        if !doc.is_object() {
            errors.push(format!("spec/{name} must be a mapping"));
        } else if name == "index.yaml" {
            match doc["requirements"].as_array() {
                None => errors.push("spec/index.yaml must contain a requirements list".into()),
                Some(requirements)
                    if !equals_int(&l1_total, requirements.len() as i128)
                        || requirements
                            .iter()
                            .any(|r| !r.is_object() || r["status"] != "ready") =>
                {
                    errors.push(
                        concat!(
                            "spec/index.yaml requirements must match L1 total ",
                            "and all be ready"
                        )
                        .into(),
                    );
                }
                Some(_) => {}
            }
        } else if doc["nodes"].as_array().is_none_or(Vec::is_empty) || !doc["edges"].is_array() {
            errors.push("spec/graph.yaml must contain non-empty nodes and an edges list".into());
        }
    }
    Ok((
        errors,
        json!({"path":"spec/bootstrap-evidence.json",
        "sequence":ARCHITECTURE_SEQUENCE,"capability_commit":locked_commit,
        "coverage":coverage,"open_gaps":open_gaps,"full_review":full_review,
        "output_hashes":output_hashes}),
    ))
}

pub fn validate_json_file(path: &Path) -> Result<Option<String>, Error> {
    match json_text(path) {
        Ok(_) => Ok(None),
        Err(e) if e.class == "UnicodeDecodeError" => Err(e),
        Err(e) => Ok(Some(format!(
            "invalid JSON surface {}: {e}",
            path.display()
        ))),
    }
}
fn registry(root: &Path, directory: &str, extension: &str) -> bool {
    fs::read_dir(root.join(directory)).is_ok_and(|entries| {
        entries
            .filter_map(Result::ok)
            .any(|entry| entry.path().extension().is_some_and(|ext| ext == extension))
    })
}
pub fn validate_surfaces(root: &Path, host: &mut impl Host) -> Validation {
    let mut errors = Vec::new();
    const JSON: [&str; 6] = [
        ".claude/settings.json",
        ".codex/hooks.json",
        "config/sub-agent-policy.json",
        "config/capability-sources.json",
        "config/adopter-boundary.json",
        "config/adopter-payload.json",
    ];
    for relative in [
        "CLAUDE.md",
        "AGENTS.md",
        ".claude/settings.json",
        ".codex/config.toml",
        ".codex/hooks.json",
        ".ai-harness/deny-list.yaml",
        ".claude/agents/main-orchestrator.md",
        ".codex/agents/main-orchestrator.toml",
        "config/sub-agent-policy.json",
        "config/capability-sources.json",
        "config/adopter-boundary.json",
        "config/adopter-payload.json",
    ] {
        if !root.join(relative).is_file() {
            errors.push(format!("required harness surface is missing: {relative}"));
        }
    }
    for relative in JSON {
        let path = root.join(relative);
        if path.is_file()
            && let Some(error) = validate_json_file(&path)?
        {
            errors.push(error);
        }
    }
    for (directory, extension, message) in [
        (".claude/agents", "md", "Claude sub-agent registry is empty"),
        (".codex/agents", "toml", "Codex sub-agent registry is empty"),
        (".claude/hooks", "sh", "Claude hook registry is empty"),
    ] {
        if !registry(root, directory, extension) {
            errors.push(message.into());
        }
    }
    let settings_path = root.join(".claude/settings.json");
    if settings_path.is_file() {
        match json_text(&settings_path) {
            Ok(settings) if !settings.is_object() => return Err(attribute_error(&settings, "get")),
            Ok(settings) => {
                if settings["hooks"].as_object().is_none_or(Map::is_empty) {
                    errors.push(".claude/settings.json has no active hooks".into());
                }
            }
            Err(e) if e.class == "UnicodeDecodeError" => return Err(e),
            Err(_) => {}
        }
    }
    let config = root.join(".codex/config.toml");
    if config.is_file() {
        let parsed = read_text(&config).and_then(|body| {
            toml::from_str::<toml::Value>(&body).map_err(|e| {
                Error::new(
                    "TOMLDecodeError",
                    crate::mir_core::tomllib::tomllib_error(&e, &body),
                )
            })
        });
        match parsed {
            Err(e) if e.class == "UnicodeDecodeError" => return Err(e),
            Err(e) => errors.push(format!("invalid TOML surface {}: {e}", config.display())),
            Ok(doc) => {
                if ["sandbox_mode", "sandbox_workspace_write"]
                    .iter()
                    .any(|key| doc.get(key).is_some())
                    && ["default_permissions", "permissions"]
                        .iter()
                        .any(|key| doc.get(key).is_some())
                {
                    errors.push(
                        concat!(
                            ".codex/config.toml mixes legacy sandbox settings ",
                            "with permission profiles"
                        )
                        .into(),
                    );
                }
            }
        }
    }
    let bash = host.which("bash").map(|path| path.display().to_string());
    let jq = host.which("jq").map(|path| path.display().to_string());
    if jq.is_none() {
        errors.push("hook runtime requires jq on PATH for JSON payload parsing".into());
    }
    Ok((
        errors,
        json!({"kind":"bash","bash":bash.unwrap_or_else(||
        "not_required_for_bootstrap".into()),"jq":jq.unwrap_or_else(|| "missing".into()),
        "syntax":"not_required"}),
    ))
}
