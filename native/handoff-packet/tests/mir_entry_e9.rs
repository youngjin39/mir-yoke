use serde_json::Value;
use std::{fs, process::Command};

#[test]
fn frozen_context_parser_and_removed_cwd() {
    let mut records: Vec<Value> = serde_json::from_str(include_str!("fixtures/y-e9.json")).unwrap();
    records
        .extend(serde_json::from_str::<Vec<Value>>(include_str!("fixtures/y-e10.json")).unwrap());
    records.extend(
        serde_json::from_str::<Vec<Value>>(include_str!("fixtures/e10_constructor.json")).unwrap(),
    );
    let mut failures = Vec::new();
    for r in records {
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path().canonicalize().unwrap();
        let gone = root.join("gone");
        fs::create_dir(&gone).unwrap();
        fs::write(root.join("bad.db"), b"not a database").unwrap();
        if let Some(config) = r["config"].as_str() {
            fs::create_dir(root.join("notes")).unwrap();
            fs::write(root.join("harness_a.toml"), config).unwrap();
        }
        if r["config"].is_string()
            || r["argv"]
                .as_array()
                .unwrap()
                .iter()
                .any(|v| v == "valid.db")
        {
            use handoff_packet::mir_core::memory::store;
            let c = store::connect(
                &root.join(if r["config"].is_string() {
                    "memory.db"
                } else {
                    "valid.db"
                }),
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
        command
            .args(
                r["argv"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .map(|v| v.as_str().unwrap()),
            )
            .env_clear()
            .env("HOME", &root)
            .current_dir(&root);
        if let Some(key) = r["key"].as_str() {
            command.env("FAKE_KEY", key);
        }
        if let Some(env) = r["env"].as_object() {
            command.envs(env.iter().map(|(k, v)| (k, v.as_str().unwrap())));
        }
        let out = command.output().unwrap();
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
