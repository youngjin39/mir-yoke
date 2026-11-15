use serde_json::Value;
use std::{fs, process::Command};

#[test]
fn frozen_bootstrap_adoption_public() {
    let records: Vec<Value> = serde_json::from_str(include_str!("fixtures/y-e14.json")).unwrap();
    let mut failures = Vec::new();
    let temporary_name = regex::Regex::new(r"\.bootstrap-receipt\.json\.[^']+").unwrap();
    for r in records {
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path().canonicalize().unwrap();
        for (name, body) in r["files"].as_object().unwrap() {
            let path = root.join(name);
            fs::create_dir_all(path.parent().unwrap()).unwrap();
            fs::write(path, body.as_str().unwrap()).unwrap();
        }
        let receipt = root.join(".mir/bootstrap-receipt.json");
        if let Some(sql) = r["sql"].as_str().filter(|s| !s.is_empty()) {
            rusqlite::Connection::open(root.join(".mir/memory.db"))
                .unwrap()
                .execute_batch(sql)
                .unwrap();
        }
        if r["mode"] == "memory-bad" {
            fs::write(root.join(".mir/memory.db"), b"bad database").unwrap();
        }
        if r["mode"] == "receipt-dir" {
            fs::remove_file(&receipt).unwrap();
            fs::create_dir(&receipt).unwrap();
        }
        let command = |name: &str| {
            let mut c = Command::new(name);
            c.env_clear()
                .env("HOME", &root)
                .env("PATH", "/usr/bin:/bin")
                .env(
                    "MIR_CAPABILITY_NATIVE_ARTIFACTS",
                    if r["mode"] == "local" { "1" } else { "0" },
                )
                .env("GIT_CONFIG_NOSYSTEM", "1")
                .env("GIT_CONFIG_GLOBAL", "/dev/null")
                .current_dir(&root);
            c
        };
        assert!(
            command("git")
                .args(["init", "-q"])
                .status()
                .unwrap()
                .success()
        );
        if r["mode"] != "untracked" {
            assert!(
                command("git")
                    .args(["add", "."])
                    .status()
                    .unwrap()
                    .success()
            );
        }
        let out = command(env!("CARGO_BIN_EXE_mir"))
            .args(
                r["argv"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .map(|v| v.as_str().unwrap()),
            )
            .output()
            .unwrap();
        let actual = serde_json::json!({"exit":out.status.code(),
            "stdout":String::from_utf8(out.stdout).unwrap().replace(root.to_str().unwrap(), "{ROOT}"),
            "stderr":temporary_name.replace_all(&String::from_utf8(out.stderr).unwrap().replace(root.to_str().unwrap(), "{ROOT}"), ".bootstrap-receipt.json.<TEMP>"),
            "receipt":fs::read_to_string(&receipt).ok()});
        for field in ["exit", "stdout", "stderr", "receipt"] {
            if actual[field] != r[field] {
                failures.push(format!(
                    "{} {} {field}: {} != {}",
                    r["mode"], r["argv"], actual[field], r[field]
                ));
            }
        }
    }
    assert!(failures.is_empty(), "{}", failures.join("\n"));
}

#[cfg(unix)]
#[test]
fn receipt_parent_substitution_fails_closed() {
    use handoff_packet::mir_cli::bootstrap_adoption::write_receipt_with;
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().canonicalize().unwrap();
    let parent = root.join("project");
    let outside = root.join("outside");
    fs::create_dir(&parent).unwrap();
    fs::create_dir(&outside).unwrap();
    let receipt = parent.join("receipt.json");
    let sentinel = outside.join("receipt.json");
    fs::write(&sentinel, "preserve").unwrap();
    let result = write_receipt_with(&receipt, &serde_json::json!({"ready":true}), |source, _| {
        fs::copy(source, outside.join(source.file_name().unwrap()))?;
        fs::rename(&parent, root.join("saved"))?;
        std::os::unix::fs::symlink(&outside, &parent)
    });
    assert!(result.is_err());
    assert_eq!(fs::read_to_string(sentinel).unwrap(), "preserve");
    assert_eq!(fs::read_dir(outside).unwrap().count(), 2);
}
