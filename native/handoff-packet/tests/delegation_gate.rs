use serde_json::{Value, json};
use std::{
    fs,
    io::Write,
    process::{Command, Stdio},
};

#[test]
fn decision_fixtures() {
    let cases: Vec<Value> =
        serde_json::from_str(include_str!("fixtures/delegation-gate.json")).unwrap();
    for (index, case) in cases.iter().enumerate() {
        let root =
            std::env::temp_dir().join(format!("delegation-gate-{}-{index}", std::process::id()));
        fs::create_dir_all(root.join("config")).unwrap();
        let mode = &case["mode"];
        let source = case["source"].as_str().unwrap_or("lock");
        if !mode.is_null() && case["no_policy"] != true {
            let (file, data) = match source {
                "local" => ("sub-agent-policy.json", json!({"delegation":{"mode":mode}})),
                "flat" => ("sub-agent-policy.json", json!({"mode":mode})),
                _ => (
                    "model-routing.lock.json",
                    json!({"policy":{"delegation":{"mode":mode}}}),
                ),
            };
            fs::write(root.join("config").join(file), data.to_string()).unwrap();
        }
        if let Some(local) = case.get("local_mode") {
            fs::write(
                root.join("config/sub-agent-policy.json"),
                json!({"mode":local}).to_string(),
            )
            .unwrap();
        }
        if let Some(raw) = case["raw_policy"].as_str() {
            fs::write(root.join("config/model-routing.lock.json"), raw).unwrap();
        }
        let lock = root.join("config/model-routing.lock.json");
        if case["broken_policy"] == true {
            fs::remove_file(&lock).unwrap();
        }
        if case["directory_lock"] == true {
            fs::remove_file(&lock).unwrap();
            fs::create_dir(&lock).unwrap();
        }
        let overlay = root.join("overlay.json");
        if let Some(data) = case.get("overlay") {
            fs::write(&overlay, data.to_string()).unwrap();
        }
        if let Some(raw) = case["raw_overlay"].as_str() {
            fs::write(&overlay, raw).unwrap();
        }
        let mut child = Command::new(env!("CARGO_BIN_EXE_delegation-gate"))
            .current_dir(&root)
            .env_remove("CLAUDE_PROJECT_DIR")
            .env("MIR_SUB_AGENT_POLICY", &overlay)
            .env("MIR_R3_FALLBACK", case["r3"].as_str().unwrap_or("0"))
            .env(
                "MIR_CODEX_MAIN",
                if case["main"] == true { "1" } else { "0" },
            )
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .unwrap();
        let input = case["raw"]
            .as_str()
            .map(str::to_owned)
            .unwrap_or_else(|| case["payload"].to_string());
        child
            .stdin
            .take()
            .unwrap()
            .write_all(input.as_bytes())
            .unwrap();
        let output = child.wait_with_output().unwrap();
        fs::remove_dir_all(root).unwrap();
        assert_eq!(
            output.status.code(),
            Some(case["code"].as_i64().unwrap() as i32),
            "{}: {:?}",
            case["name"],
            output
        );
        assert!(output.stdout.is_empty());
        let error = String::from_utf8(output.stderr).unwrap();
        if let Some(hint) = case["expected_hint"].as_str() {
            assert!(error.contains(hint), "{error}");
        }
        if case["advisory"] == true {
            assert_eq!(
                error,
                "[mir ADVISORY] force_codex Agent/Task escape via MIR_R3_FALLBACK=1\n"
            );
        } else if case["code"] == 0 {
            assert!(error.is_empty(), "{error}");
        } else if case["malformed"] == true {
            assert!(error.contains("Malformed PreToolUse payload"), "{error}");
        } else {
            assert!(error.starts_with("[mir BLOCKED]"), "{error}");
        }
    }
}
