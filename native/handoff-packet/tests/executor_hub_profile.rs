use handoff_packet::{executor_brief_profile::BriefProfile, executor_job_identity::JobIdentity};
use serde_json::{Value, json};
use std::{fs, path::PathBuf};

fn golden() -> Value {
    serde_json::from_str(include_str!(
        "../../../tests/fixtures/executor_hub_profile.json"
    ))
    .unwrap()
}

#[test]
fn owner_identity_golden_preserves_exact_prompt_and_json_bytes() {
    for case in golden()["identity_cases"].as_array().unwrap() {
        let identity = JobIdentity::parse(&json!({
            "name": "codex_mcp_v1", "package": "mir-agent-hub",
            "package_version": case["version"]
        }))
        .unwrap();
        assert!(identity.enabled());
        assert_eq!(
            identity.render(
                case["dispatch"].as_bool().unwrap(),
                case["prompt"].as_str().unwrap(),
                case["model"].as_str()
            ),
            case["value"].as_str().unwrap(),
            "{case}"
        );
    }
}

#[test]
fn owner_goal_bounds_and_schema_errors_match_golden() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join(format!(".hub-golden-{}", std::process::id()));
    fs::create_dir_all(root.join("config")).unwrap();
    let profile = BriefProfile::parse(&json!({
        "name": "base_v1", "input_bound": "expanded_goal"
    }))
    .unwrap();
    for case in golden()["brief_cases"].as_array().unwrap() {
        let configuration = if case["name"] == "limit_missing" {
            json!({})
        } else {
            json!({"input_limit_bytes": case["limit"]})
        };
        fs::write(
            root.join("config/mir-executor.local.json"),
            serde_json::to_vec(&configuration).unwrap(),
        )
        .unwrap();
        let outcome = if case["payload"].is_null() {
            profile
                .bound_text(case["text"].as_str().unwrap(), &root)
                .map(|()| Value::Null)
        } else {
            let path = root.join("brief.json");
            fs::write(&path, case["payload_text"].as_str().unwrap()).unwrap();
            profile.load(&path).and_then(|value| {
                profile.bound_text(value["expanded_goal"].as_str().unwrap(), &root)?;
                Ok(value)
            })
        };
        let actual = match outcome {
            Ok(value) => json!({"value": value}),
            Err(error) => json!({"kind": error.kind, "message": error.message}),
        };
        let expected = if case.get("kind").is_some() {
            json!({"kind": case["kind"], "message": case["message"]})
        } else {
            json!({"value": case["value"]})
        };
        assert_eq!(actual, expected, "{}", case["name"]);
    }
    fs::remove_dir_all(root).unwrap();
}
