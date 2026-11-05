//! Finite execution binding and invocation-local instruction rendering.
use crate::{executor_brief_profile::BriefProfile, executor_target_policy::PolicyFailure};
use serde_json::Value;
use std::path::Path;

fn failure(message: impl Into<String>) -> PolicyFailure {
    PolicyFailure {
        kind: "ValueError".into(),
        message: message.into(),
        stderr: None,
    }
}
fn strings(value: &Value) -> impl Iterator<Item = &str> {
    value
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(Value::as_str)
}
fn covers(owned: &str, requested: &str) -> bool {
    let owned = owned
        .strip_prefix("./")
        .unwrap_or(owned)
        .trim_end_matches('/');
    let requested = requested
        .strip_prefix("./")
        .unwrap_or(requested)
        .trim_end_matches('/');
    let prefix = owned.strip_suffix("/**").unwrap_or(owned);
    requested == prefix || requested.starts_with(&format!("{prefix}/"))
}
pub(crate) fn bind(
    profile: &BriefProfile,
    root: &Path,
    cwd: &Path,
    args: &Value,
) -> Result<(), PolicyFailure> {
    let raw = crate::executor_execute::value_path(&args["dispatch_brief"], cwd);
    let path = crate::executor_admission::resolved(&raw, cwd)
        .map_err(|e| crate::executor_brief_profile::io_failure(e, &raw))?;
    let result = (|| {
        let brief = profile.load(&path)?;
        let expected = root.join(brief["resume_state_ref"].as_str().unwrap_or_default());
        let expected = crate::executor_admission::resolved(&expected, cwd)
            .map_err(|e| crate::executor_brief_profile::io_failure(e, &expected))?;
        if path != expected {
            return Err(failure(
                "DispatchBrief path must match its resume_state_ref",
            ));
        }
        let agent = brief["target_agent"].as_str().unwrap_or_default();
        if !root
            .join(".claude/agents")
            .join(format!("{agent}.md"))
            .is_file()
        {
            return Err(failure(format!(
                "DispatchBrief target_agent profile is missing: {agent}"
            )));
        }
        if let Some(change) = args["change_id"].as_str()
            && !strings(&brief["tdd_change_refs"]).any(|s| s == format!("tasks/tdd.json#{change}"))
        {
            return Err(failure(
                "DispatchBrief does not bind the requested TDD change",
            ));
        }
        for requested in strings(&args["allow_paths"]) {
            if !strings(&brief["owned_scope"]).any(|owned| covers(owned, requested)) {
                return Err(failure(format!(
                    "allow path is outside DispatchBrief owned_scope: {requested}"
                )));
            }
        }
        let config = crate::executor_local::LocalConfig::load(root).map_err(|e| PolicyFailure {
            kind: e.kind().into(),
            message: e.to_string(),
            stderr: None,
        })?;
        let declared: Vec<_> = strings(&brief["verification_commands"])
            .map(crate::stop_tools::shell_words)
            .collect();
        let undeclared: Vec<_> = strings(&args["verify_cmds"])
            .filter(|command| {
                !strings(&brief["verification_commands"]).any(|c| c == *command)
                    && !config.raw()["verifiers"]
                        .get(*command)
                        .and_then(Value::as_array)
                        .is_some_and(|argv| {
                            let argv: Option<Vec<String>> =
                                argv.iter().map(|v| v.as_str().map(str::to_owned)).collect();
                            argv.is_some() && declared.contains(&argv)
                        })
            })
            .collect();
        if !undeclared.is_empty() {
            return Err(failure(format!(
                "verification command is not declared by DispatchBrief: {}",
                undeclared.join(", ")
            )));
        }
        Ok(())
    })();
    result.map_err(|error: PolicyFailure| {
        if error.kind == "TypeError" {
            error
        } else {
            failure(format!("DispatchBrief error: {}", error.message))
        }
    })
}

pub(crate) fn render(brief: &Value, instruction: Option<&str>) -> Result<String, String> {
    // Preserve model declaration order using the existing Python JSON layout writer.
    const ORDER: &str = r#"{"version":null,"task_id":null,"phase_id":null,"slice_id":null,"target_agent":null,"user_intent":null,"expanded_goal":null,"owned_scope":[],"out_of_scope":[],"verification_commands":[],"stop_conditions":[],"handoff_refs":[],"tdd_change_refs":[],"resume_state_ref":null,"source_refs":{"task_spec":null,"plan":null,"phase":null}}"#;
    let payload = crate::executor_ledger_json::render(ORDER, brief)?;
    let instruction =
        instruction.unwrap_or_else(|| brief["expanded_goal"].as_str().unwrap_or_default());
    Ok(format!(
        "# DispatchBrief\n\nTarget profile: `{}`\n\n## Active step instruction\n\n{}\n\n## Typed execution contract\n\n```json\n{}```\n",
        brief["target_agent"].as_str().unwrap_or_default(),
        instruction.trim_matches(crate::executor_brief_authority::python_space),
        payload
    ))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::executor_target_policy::NativePolicy;
    use serde_json::json;
    use std::fs;

    fn substitute(value: &mut Value, root: &str) {
        match value {
            Value::String(text) => *text = text.replace("<root>", root),
            Value::Array(values) => values.iter_mut().for_each(|v| substitute(v, root)),
            Value::Object(values) => values.values_mut().for_each(|v| substitute(v, root)),
            _ => (),
        }
    }

    #[test]
    fn captured_binding_patches_errors_and_render_bytes() {
        let fixture: Value = serde_json::from_str(include_str!(
            "../tests/fixtures/executor_smd_binding_render.json"
        ))
        .unwrap();
        let root = Path::new(env!("CARGO_MANIFEST_DIR")).join(format!(
            ".scratch-execution-{}",
            crate::executor_execute::unique_id()
        ));
        fs::create_dir_all(root.join("config")).unwrap();
        let root = fs::canonicalize(root).unwrap();
        fs::write(
            root.join("config/mir-executor.local.json"),
            fixture["config_raw"].as_str().unwrap(),
        )
        .unwrap();
        let policy = NativePolicy::parse(&json!({
            "version": 1, "brief_profile": {"name": "execution_v1"},
            "brief_controls": {"mode": "execution_subset"},
            "verifier_aliases": {"configuration_root": "target"},
            "target_admission": {"family": {
                "mode":"alias_map", "aliases":{},
                "unknown":{"kind":"ValueError", "message":"Unknown family slug: {family_repr}. {key_error}"},
                "unknown_key_error":"unknown family",
                "root_conflict":{"kind":"ValueError", "message":"--family {family_repr} resolves to {family_root}, not {requested_root}"}
            }}
        }))
        .unwrap();
        let profile = BriefProfile::parse(&json!({"name":"execution_v1"})).unwrap();
        for case in fixture["cases"].as_array().unwrap() {
            let name = case["name"].as_str().unwrap();
            // Invocation argv failures occur after the policy binding boundary.
            if [
                "malformed_instruction",
                "conflicting_instruction",
                "missing_instruction",
            ]
            .contains(&name)
            {
                continue;
            }
            let mut args = case["args"].clone();
            substitute(&mut args, root.to_str().unwrap());
            let path = args["dispatch_brief"].as_str().map(Path::new);
            if let Some(path) = path {
                fs::create_dir_all(path.parent().unwrap()).unwrap();
                fs::write(path, case["raw"].as_str().unwrap()).unwrap();
                if name == "missing_file" {
                    fs::remove_file(path).unwrap();
                }
            }
            let agent = root.join(".claude/agents/offline-agent.md");
            fs::create_dir_all(agent.parent().unwrap()).unwrap();
            fs::write(&agent, "Offline profile.\n").unwrap();
            if ["missing_agent", "multiple_binding_errors"].contains(&name) {
                fs::remove_file(agent).unwrap();
            }
            let result = policy.pre_execute(&root, &root, &root, &mut args, &Default::default());
            // Error text carries the path raw and as a Python repr (backslashes doubled on Windows).
            let repr_root = root.to_str().unwrap().replace('\\', "\\\\");
            let normalize = |value: &str| {
                value
                    .replace(&repr_root, "<root>")
                    .replace(root.to_str().unwrap(), "<root>")
            };
            match case.get("message").and_then(Value::as_str) {
                Some(expected) => {
                    let error = result.unwrap_err();
                    assert_eq!(error.kind, case["kind"].as_str().unwrap(), "{name}");
                    assert_eq!(normalize(&error.message), expected, "{name}");
                }
                None => result.unwrap(),
            }
            let mut patch = case["patch"].clone();
            substitute(&mut patch, root.to_str().unwrap());
            assert_eq!(args, patch, "{name}");
            if let Some(expected) = case.get("rendered") {
                let brief = profile
                    .validate_bytes(case["raw"].as_str().unwrap().as_bytes())
                    .unwrap();
                let marker = "## Active step instruction\n\n";
                let expected = expected.as_str().unwrap();
                let instruction = expected
                    .split_once(marker)
                    .unwrap()
                    .1
                    .split_once("\n\n## Typed execution contract")
                    .unwrap()
                    .0;
                assert_eq!(
                    render(&brief, Some(instruction)).unwrap().as_bytes(),
                    expected.as_bytes(),
                    "{name}"
                );
                assert_eq!(
                    render(&brief, None).unwrap(),
                    case["rendered_again"].as_str().unwrap(),
                    "{name}"
                );
            }
        }
        fs::remove_dir_all(root).unwrap();
    }
}
