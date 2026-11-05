//! Frozen own-bootstrap state replay; command/path enforcement belongs to Y6b.
#![cfg(unix)]
// This shared envelope module also serves project-hooks event replay.
#[allow(dead_code)]
#[path = "support/replay.rs"]
mod frozen;
use serde_json::{Value, json};
use std::{fs, process::Command};
#[path = "../src/digest.rs"]
mod digest;

fn protocol(state: &Value, mode: &Value, code: &Value, supported: bool) -> Vec<u8> {
    let mut out = serde_json::to_vec(&json!({"schema":"mir.bootstrap-state@1",
        "supported":supported,"state":state,"mode":mode,"shell_exit":code}))
    .unwrap();
    out.push(b'\n');
    out
}
fn replay(record: &Value, expected: &Value) {
    let dir = tempfile::tempdir().unwrap();
    let root = dir.path();
    let isolation = frozen::prepare(root);
    frozen::install(&record["setup"], root);
    let before = frozen::snapshot(&root.join("project"));
    let mut command = Command::new(env!("CARGO_BIN_EXE_bootstrap-gate"));
    command
        .env_clear()
        .envs(isolation.get_envs().filter_map(|(k, v)| v.map(|v| (k, v))))
        .current_dir(root.join("project"));
    for (key, value) in record["env"].as_object().unwrap() {
        command.env(
            key,
            String::from_utf8(frozen::transform(
                value.as_str().unwrap().as_bytes().to_vec(),
                root,
                true,
            ))
            .unwrap(),
        );
    }
    let result = command
        .args(["state", "--protocol", "1"])
        .arg(root.join("project"))
        .output()
        .unwrap();
    let unsupported = record["unsupported"] == true;
    let code = if unsupported {
        64
    } else {
        record["expected"]["exit"].as_i64().unwrap()
    };
    let wanted = if unsupported {
        protocol(&Value::Null, &Value::Null, &Value::Null, false)
    } else {
        protocol(&expected["state"], &expected["mode"], &json!(code), true)
    };
    assert_eq!(result.status.code(), Some(code as i32), "{}", record["id"]);
    assert_eq!(result.stdout, wanted, "{}", record["id"]);
    assert!(
        result.stderr.is_empty(),
        "{}: {:?}",
        record["id"],
        result.stderr
    );
    assert_eq!(
        before,
        frozen::snapshot(&root.join("project")),
        "state evaluation wrote files: {}",
        record["id"]
    );
}
#[test]
fn frozen_own_bootstrap_states() {
    let records: Vec<Value> =
        serde_json::from_str(include_str!("fixtures/w1/records.json")).unwrap();
    let map: Value = serde_json::from_str(include_str!("fixtures/bootstrap-state.json")).unwrap();
    assert_eq!(map["reused"].as_array().unwrap().len(), 43);
    for row in map["reused"].as_array().unwrap() {
        let record = records.iter().find(|r| r["id"] == row["id"]).unwrap();
        assert_eq!(
            frozen::decode(&record["expected"]["stdout"]),
            format!("{}\n", row["state"].as_str().unwrap()).as_bytes()
        );
        assert_eq!(record["expected"]["exit"], row["shell_exit"]);
        replay(record, row);
    }
    assert_eq!(map["legacy_native"].as_array().unwrap().len(), 42);
    for row in map["legacy_native"].as_array().unwrap() {
        assert!(records.iter().any(|r| r["id"] == row["id"]));
        assert!(
            map["reused"]
                .as_array()
                .unwrap()
                .iter()
                .any(|r| r["id"] == row["state_record"])
        );
    }
}
#[test]
fn captured_shell_states_and_protocol_deviations() {
    let map: Value = serde_json::from_str(include_str!("fixtures/bootstrap-state.json")).unwrap();
    assert_eq!(map["new"].as_array().unwrap().len(), 46);
    for record in map["new"].as_array().unwrap() {
        assert_eq!(
            frozen::decode(&record["expected"]["stdout"]),
            format!("{}\n", record["state"].as_str().unwrap()).as_bytes()
        );
        replay(record, record);
    }
}
#[test]
fn state_capability_and_unsupported_inputs() {
    let bin = env!("CARGO_BIN_EXE_bootstrap-gate");
    let result = Command::new(bin).arg("--capabilities").output().unwrap();
    assert_eq!(result.status.code(), Some(0));
    assert_eq!(
        result.stdout,
        b"{\"protocols\":[\"mir.bootstrap-state@1\",\"mir.bootstrap-enforce@1\",\"mir.bootstrap-instructions@1\"]}\n"
    );
    assert!(result.stderr.is_empty());
    for path in ["C:\\repo", "C:/repo", "\\\\server\\share"] {
        let result = Command::new(bin)
            .args(["state", "--protocol", "1", path])
            .output()
            .unwrap();
        assert_eq!(result.status.code(), Some(64));
        assert_eq!(
            result.stdout,
            protocol(&Value::Null, &Value::Null, &Value::Null, false)
        );
        assert!(result.stderr.is_empty());
    }
    for args in [
        vec!["state"],
        vec!["state", "--protocol", "2", "."],
        vec!["state", "--protocol", "1", ".", "extra"],
    ] {
        let result = Command::new(bin).args(args).output().unwrap();
        assert_eq!(result.status.code(), Some(64));
        assert!(result.stdout.is_empty() && result.stderr.is_empty());
    }
    // The shell source pin is checked without loading a mutable oracle at runtime.

    let map: Value = serde_json::from_str(include_str!("fixtures/bootstrap-state.json")).unwrap();
    assert_eq!(
        digest::sha256(
            &fs::read(concat!(
                env!("CARGO_MANIFEST_DIR"),
                "/../../.claude/hooks/_lib/bootstrap-gate.sh"
            ))
            .unwrap()
        ),
        map["source"]["sha256"]
    );
}
