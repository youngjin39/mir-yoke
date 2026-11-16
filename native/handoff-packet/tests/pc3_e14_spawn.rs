use handoff_packet::mir_cli::bootstrap_adoption::{Host, evidence_digest};
use serde_json::Value;
use std::{env, fs, path::PathBuf, process::Command};

struct Local;
impl Host for Local {}

#[test]
fn missing_jq_child() {
    let Some(root) = env::var_os("PC3_SPAWN_ROOT").map(PathBuf::from) else {
        return;
    };
    assert_eq!(env::current_dir().unwrap(), root);
    assert_eq!(env::var_os("HOME").unwrap(), root);
    let error = evidence_digest(
        ".claude/settings.json",
        &root.join("settings.json"),
        &mut Local,
    )
    .unwrap_err();
    assert_eq!(error.class(), "AdoptionError");
    let message = error.to_string();
    if cfg!(windows) {
        let records: Value = serde_json::from_slice(
            &fs::read(
                PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/y-e14-windows.json"),
            )
            .unwrap(),
        )
        .unwrap();
        let record = records
            .as_array()
            .unwrap()
            .iter()
            .find(|r| r["mode"] == "settings")
            .unwrap();
        let report: Value = serde_json::from_str(record["stdout"].as_str().unwrap()).unwrap();
        assert!(
            report["errors"]
                .as_array()
                .unwrap()
                .contains(&Value::String(message))
        );
    } else {
        let os_error = Command::new("jq").output().unwrap_err();
        assert_eq!(
            message,
            format!("cannot digest settings hook evidence: {os_error}")
        );
    }
}

#[test]
fn missing_jq_in_synthetic_path() {
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().canonicalize().unwrap();
    fs::write(
        root.join("settings.json"),
        r#"{"hooks":{"SessionStart":[]}}"#,
    )
    .unwrap();
    let mut child = Command::new(env::current_exe().unwrap());
    child
        .env_clear()
        .env("HOME", &root)
        .env("USERPROFILE", &root)
        .env("PATH", &root)
        .env("PC3_SPAWN_ROOT", &root)
        .current_dir(&root)
        .args(["--exact", "missing_jq_child", "--nocapture"]);
    #[cfg(windows)]
    for key in ["SystemRoot", "WINDIR"] {
        if let Some(value) = env::var_os(key) {
            child.env(key, value);
        }
    }
    let output = child.output().unwrap();
    assert!(
        output.status.success(),
        "{}{}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
}
