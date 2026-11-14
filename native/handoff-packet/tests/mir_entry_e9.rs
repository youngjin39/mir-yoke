use serde_json::Value;
use std::{fs, process::Command};

#[test]
fn frozen_context_parser_and_removed_cwd() {
    let records: Vec<Value> = serde_json::from_str(include_str!("fixtures/y-e9.json")).unwrap();
    let mut failures = Vec::new();
    for r in records {
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path().canonicalize().unwrap();
        let gone = root.join("gone");
        fs::create_dir(&gone).unwrap();
        fs::write(root.join("bad.db"), b"not a database").unwrap();
        if r["argv"]
            .as_array()
            .unwrap()
            .iter()
            .any(|v| v == "valid.db")
        {
            use handoff_packet::mir_core::memory::store;
            let c = store::connect(
                &root.join("valid.db"),
                store::ConnectOptions {
                    timeout: None,
                    vec_loading: store::VecLoading::Bundled,
                },
            )
            .unwrap();
            store::apply_migrations(&c.conn).unwrap();
        }
        let mut command = if r["removed"] == true {
            if !cfg!(unix) {
                continue;
            }
            let mut shell = Command::new("/bin/sh");
            shell.args(["-c", "cd gone && rmdir ../gone && exec \"$@\"", "seam"]);
            shell.arg(env!("CARGO_BIN_EXE_mir"));
            shell
        } else {
            Command::new(env!("CARGO_BIN_EXE_mir"))
        };
        let out = command
            .args(
                r["argv"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .map(|v| v.as_str().unwrap()),
            )
            .env_clear()
            .env("HOME", &root)
            .current_dir(&root)
            .output()
            .unwrap();
        let actual = serde_json::json!({"exit":out.status.code(),
            "stdout":String::from_utf8(out.stdout).unwrap(),
            "stderr":String::from_utf8(out.stderr).unwrap()});
        if actual["exit"] != r["exit"]
            || actual["stdout"] != r["stdout"]
            || actual["stderr"] != r["stderr"]
        {
            failures.push(format!(
                "argv={} removed={}: {actual} != {r}",
                r["argv"], r["removed"]
            ));
        }
    }
    assert!(failures.is_empty(), "{}", failures.join("\n"));
}
