//! Explicit capability profile authorization and exact Markdown rendering.
use crate::executor_target_policy::PolicyFailure;
use serde_json::Value;
use std::{collections::BTreeSet, fs, path::Path};

fn fail(message: impl Into<String>) -> PolicyFailure {
    PolicyFailure {
        kind: "DispatchBriefPolicyError".into(),
        message: message.into(),
        stderr: None,
    }
}
fn strings(
    value: Option<&toml::Value>,
    label: &str,
    nonempty: bool,
) -> Result<Vec<String>, PolicyFailure> {
    let Some(items) = value
        .and_then(toml::Value::as_array)
        .filter(|items| !nonempty || !items.is_empty())
    else {
        return Err(fail(format!(
            "repository profile {label}{}",
            if nonempty {
                " must be non-empty"
            } else {
                " must be a list"
            }
        )));
    };
    items
        .iter()
        .map(|item| {
            item.as_str()
                .filter(|s| !s.trim_matches(python_space).is_empty())
                .map(str::to_owned)
                .ok_or_else(|| {
                    fail(format!(
                        "repository profile {label} must contain non-empty strings"
                    ))
                })
        })
        .collect()
}
fn python_space(c: char) -> bool {
    c.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&c)
}
fn prefix(pattern: &str) -> Vec<&str> {
    pattern
        .split('/')
        .filter(|s| !s.is_empty() && *s != ".")
        .take_while(|s| !s.contains(['*', '?', '[']))
        .collect()
}
fn validate(pattern: &str, name_only: bool) -> Result<(), PolicyFailure> {
    if pattern.is_empty()
        || pattern.trim_matches(python_space) != pattern
        || pattern.starts_with('/')
        || pattern.split('/').any(|s| s == "..")
        || [".", "./"].contains(&pattern)
        || pattern.contains('\\')
    {
        return Err(fail(
            "dispatch path must be a safe repository-relative pattern",
        ));
    }
    if prefix(pattern).is_empty() && !(name_only && !pattern.contains('/')) {
        return Err(fail("dispatch path must have a concrete path prefix"));
    }
    Ok(())
}
fn items<'a>(brief: &'a Value, key: &str) -> Vec<&'a str> {
    brief[key]
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(Value::as_str)
        .collect()
}
pub fn authorize(root: &Path, brief: &Value) -> Result<(), PolicyFailure> {
    if brief["expanded_goal"]
        .as_str()
        .unwrap_or_default()
        .trim_matches(python_space)
        .is_empty()
    {
        return Err(PolicyFailure {
            kind: "ValueError".into(),
            message: "DispatchBrief expanded_goal must be non-empty".into(),
            stderr: None,
        });
    }
    let profile = fs::read_to_string(root.join(".mir/repo-profile.toml"))
        .ok()
        .and_then(|text| text.parse::<toml::Value>().ok())
        .ok_or_else(|| fail("repository profile is missing or invalid"))?;
    let paths = profile.get("paths").and_then(toml::Value::as_table);
    let execution = profile.get("execution").and_then(toml::Value::as_table);
    let (Some(paths), Some(execution)) = (paths, execution) else {
        return Err(fail(
            "repository profile paths and execution sections are required",
        ));
    };
    let empty = toml::Value::Array(vec![]);
    let allowed = strings(paths.get("code_paths"), "paths.code_paths", true)?;
    let protected = strings(
        Some(paths.get("protected_paths").unwrap_or(&empty)),
        "paths.protected_paths",
        false,
    )?;
    let allowed_caps = strings(
        execution.get("codex_allowed_modes"),
        "execution.codex_allowed_modes",
        true,
    )?;
    let blocked_caps = strings(
        Some(execution.get("codex_blocked_modes").unwrap_or(&empty)),
        "execution.codex_blocked_modes",
        false,
    )?;
    let owned = items(brief, "owned_scope");
    for pattern in allowed
        .iter()
        .map(String::as_str)
        .chain(owned.iter().copied())
    {
        validate(pattern, false)?;
    }
    for pattern in &protected {
        validate(pattern, true)?;
    }
    for scope in owned {
        let scope_prefix = prefix(scope);
        for pattern in &protected {
            let protected_prefix = prefix(pattern);
            let mut basename = false;
            if !pattern.contains('/') {
                for part in &scope_prefix {
                    basename |= crate::executor_verifier::matches(pattern, part)
                        .map_err(|error| fail(error.to_string()))?;
                }
            }
            let shortest = scope_prefix.len().min(protected_prefix.len());
            if basename
                || (!protected_prefix.is_empty()
                    && scope_prefix[..shortest] == protected_prefix[..shortest])
            {
                return Err(fail(format!(
                    "owned_scope intersects protected path: {scope}"
                )));
            }
        }
        if !allowed
            .iter()
            .any(|pattern| scope_prefix.starts_with(&prefix(pattern)))
        {
            return Err(fail(format!(
                "owned_scope is not delegable by repository profile: {scope}"
            )));
        }
    }
    let caps = items(brief, "capabilities")
        .into_iter()
        .collect::<BTreeSet<_>>();
    let blocked = caps
        .iter()
        .filter(|cap| blocked_caps.iter().any(|s| s == **cap))
        .copied()
        .collect::<Vec<_>>();
    let unknown = caps
        .iter()
        .filter(|cap| !allowed_caps.iter().any(|s| s == **cap))
        .copied()
        .collect::<Vec<_>>();
    if !blocked.is_empty() {
        return Err(fail(format!(
            "blocked dispatch capabilities: {}",
            blocked.join(", ")
        )));
    }
    if !unknown.is_empty() {
        return Err(fail(format!(
            "unapproved dispatch capabilities: {}",
            unknown.join(", ")
        )));
    }
    Ok(())
}
pub fn render(brief: &Value) -> String {
    let text = |key: &str| brief[key].as_str().unwrap_or_default();
    let mut lines = vec![
        "# Dispatch Brief".into(),
        String::new(),
        format!("Task: {}", text("task_id")),
        format!("Slice: {}", text("slice_id")),
        format!("Target agent: {}", text("target_agent")),
        String::new(),
        "## Goal".into(),
        String::new(),
        text("expanded_goal").into(),
    ];
    for (key, label, quoted) in [
        ("owned_scope", "Owned scope", true),
        ("capabilities", "Capabilities", true),
        ("out_of_scope", "Out of scope", false),
        ("verification_commands", "Verification", true),
        ("stop_conditions", "Stop conditions", false),
    ] {
        lines.extend([String::new(), format!("## {label}"), String::new()]);
        lines.extend(items(brief, key).iter().map(|item| {
            if quoted {
                format!("- `{item}`")
            } else {
                format!("- {item}")
            }
        }));
    }
    lines.extend([String::new(), "## Sources".into(), String::new()]);
    for (key, label) in [
        ("task_spec", "Task spec"),
        ("plan", "Plan"),
        ("phase", "Phase"),
    ] {
        lines.push(format!(
            "- {label}: `{}`",
            brief["source_refs"][key].as_str().unwrap_or_default()
        ));
    }
    lines.push(String::new());
    lines.join("\n")
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{
        executor_brief_profile::BriefProfile, executor_job_identity::JobIdentity,
        executor_target_policy::NativePolicy,
    };
    use serde_json::json;

    #[test]
    fn captured_profile_controls_render_and_identity() {
        let golden: Value = serde_json::from_str(include_str!(
            "../../../tests/fixtures/executor_home_profile.json"
        ))
        .unwrap();
        let root = std::env::var_os("MIR_NATIVE_TEST_SCRATCH")
            .map(std::path::PathBuf::from)
            .unwrap_or_else(|| Path::new(env!("CARGO_MANIFEST_DIR")).join("../../.scratch"))
            .join(format!("authority-{}", std::process::id()));
        fs::create_dir_all(root.join(".mir")).unwrap();
        fs::create_dir_all(root.join("config")).unwrap();
        fs::write(
            root.join("config/mir-executor.local.json"),
            golden["config_raw"].as_str().unwrap(),
        )
        .unwrap();
        let profile = BriefProfile::parse(&json!({"name":"capability_v1"})).unwrap();
        let policy = NativePolicy::parse(&json!({"version":1,"brief_profile":{"name":"capability_v1"},"brief_controls":{"mode":"authorized_exact"},"verifier_aliases":{"configuration_root":"initial"}})).unwrap();
        let identity = JobIdentity::parse(&json!({"name":"scope_capabilities_v1"})).unwrap();
        for case in golden["cases"].as_array().unwrap() {
            let path = root.join(".mir/repo-profile.toml");
            let _ = fs::remove_file(&path);
            if let Some(text) = case["profile"].as_str() {
                fs::write(&path, text).unwrap();
            }
            let result = profile
                .validate_bytes(case["raw"].as_str().unwrap().as_bytes())
                .and_then(|brief| {
                    authorize(&root, &brief)?;
                    Ok(brief)
                });
            if case["kind"].is_string() {
                let error = result.unwrap_err();
                assert_eq!(error.kind, case["kind"], "{}", case["name"]);
                assert_eq!(error.message, case["message"], "{}", case["name"]);
            } else {
                let brief = result.unwrap();
                assert_eq!(brief, case["value"]);
                assert_eq!(render(&brief), case["rendered"]);
            }
        }
        for case in golden["controls"].as_array().unwrap() {
            let path = root.join(".mir/repo-profile.toml");
            let _ = fs::remove_file(&path);
            if let Some(text) = case["profile"].as_str() {
                fs::write(&path, text).unwrap();
            }
            fs::write(root.join("brief.json"), case["raw"].as_str().unwrap()).unwrap();
            // Substitute the root as JSON string content: Windows paths carry backslashes.
            let escaped = json!(root.to_string_lossy()).to_string();
            let escaped = &escaped[1..escaped.len() - 1];
            let mut args: Value =
                serde_json::from_str(&case["args"].to_string().replace("<root>", escaped)).unwrap();
            let result = policy.pre_execute(&root, &root, &root, &mut args, &Default::default());
            if case["kind"].is_string() {
                let error = result.unwrap_err();
                assert_eq!(error.kind, case["kind"], "{}", case["name"]);
                assert_eq!(error.message, case["message"], "{}", case["name"]);
            } else {
                result.unwrap();
            }
            assert_eq!(
                serde_json::from_str::<Value>(&args.to_string().replace(escaped, "<root>"))
                    .unwrap(),
                case["patch"],
                "{}",
                case["name"]
            );
            assert_eq!(
                identity.render_scope(&args).unwrap(),
                case["identity"],
                "{}",
                case["name"]
            );
        }
        fs::remove_dir_all(root).unwrap();
    }
}
