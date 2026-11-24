//! Replay the unmodified shell's frozen enforcement and instruction bytes.
#![cfg(unix)]
#[allow(dead_code)] // Shared full-envelope helper also serves other hook tests.
#[path = "support/replay.rs"]
mod frozen;
use serde_json::Value;
use std::{
    fs,
    io::Write,
    process::{Command, Stdio},
};
#[path = "../src/digest.rs"]
mod digest;

#[test]
fn frozen_bootstrap_enforcement_and_instructions() {
    let fixture: Value = serde_json::from_str(include_str!(
        "../../../tests/fixtures/bootstrap-enforce.json"
    ))
    .unwrap();
    assert_eq!(
        digest::sha256(
            &fs::read(concat!(
                env!("CARGO_MANIFEST_DIR"),
                "/../../.claude/hooks/_lib/bootstrap-gate.sh"
            ))
            .unwrap()
        ),
        fixture["source"]["sha256"]
    );
    let mut retired = 0;
    for record in fixture["records"].as_array().unwrap() {
        if record["retired_branch"] == true {
            assert!(
                String::from_utf8(frozen::decode(&record["expected"]["stderr"]))
                    .unwrap()
                    .contains("jq is required")
            );
            retired += 1;
            continue;
        }
        let dir = tempfile::tempdir_in(std::env::temp_dir().canonicalize().unwrap()).unwrap();
        // Frozen bare-provider commands require whitespace in the unquoted root.
        // Keep its truncated path inside this private directory, away from host files.
        let replay_root = dir.path().join("replay with spaces");
        let root = replay_root.as_path();
        let isolation = frozen::prepare(root);
        let mut setup = fixture["scenarios"][record["scenario"].as_str().unwrap()]["setup"]
            .as_object()
            .unwrap()
            .clone();
        setup.extend(record["setup"].as_object().unwrap().clone());
        frozen::install(&Value::Object(setup), root);
        let before = frozen::snapshot(&root.join("project"));
        let mut command = Command::new(env!("CARGO_BIN_EXE_bootstrap-gate"));
        command
            .env_clear()
            .envs(isolation.get_envs().filter_map(|(k, v)| v.map(|v| (k, v))))
            .current_dir(root.join("project"))
            .args([record["operation"].as_str().unwrap(), "--protocol", "1"]);
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
        if record["operation"] == "instructions" {
            command.arg(record["state"].as_str().unwrap());
        }
        // Preload the exact input bytes so early refusal cannot race the writer.
        let input = frozen::transform(frozen::decode(&record["stdin"]), root, true);
        assert!(input.len() <= 4096, "frozen stdin exceeds one pipe buffer");
        let (reader, mut writer) = std::io::pipe().unwrap();
        writer.write_all(&input).unwrap();
        drop(writer);
        command
            .arg(root.join("project"))
            .stdin(reader)
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        let child = command.spawn().unwrap();
        let result = child.wait_with_output().unwrap();
        assert_eq!(
            result.status.code(),
            Some(record["expected"]["exit"].as_i64().unwrap() as i32),
            "{}",
            record["id"]
        );
        for (stream, bytes) in [("stdout", result.stdout), ("stderr", result.stderr)] {
            assert_eq!(
                frozen::transform(bytes, root, false),
                frozen::decode(&record["expected"][stream]),
                "{} {stream}",
                record["id"]
            );
        }
        assert_eq!(
            before,
            frozen::snapshot(&root.join("project")),
            "{}",
            record["id"]
        );
    }
    assert_eq!(retired, 2);
}
