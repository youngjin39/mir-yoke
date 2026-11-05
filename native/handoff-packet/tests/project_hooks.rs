//! The probe and warmup must finish while the caller still owns open stdin.
use std::{
    process::{Command, Stdio},
    thread,
    time::{Duration, Instant},
};

fn run(args: &[&str], code: i32, stdout: &[u8], stderr: &[u8]) {
    let mut child = Command::new(env!("CARGO_BIN_EXE_project-hooks"))
        .args(args)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    let input = child.stdin.take().unwrap();
    let deadline = Instant::now() + Duration::from_secs(5);
    loop {
        if child.try_wait().unwrap().is_some() {
            break;
        }
        if Instant::now() >= deadline {
            child.kill().unwrap();
            child.wait().unwrap();
            panic!("project-hooks waited for stdin");
        }
        thread::sleep(Duration::from_millis(10));
    }
    let output = child.wait_with_output().unwrap();
    drop(input);
    assert_eq!(output.status.code(), Some(code));
    assert_eq!(output.stdout, stdout);
    assert_eq!(output.stderr, stderr);
}

#[test]
fn capabilities() {
    run(
        &["capabilities"],
        0,
        b"mir-project-hooks-v1\nmir-project-hooks-compact-v1\nmir-project-hooks-tdd-v1\nmir-project-hooks-post-edit-v1\nmir-project-hooks-prompt-v1\n",
        b"",
    );
}

#[test]
fn warmup() {
    run(&["--mir-warmup"], 0, b"", b"");
}

#[test]
fn unknown_subcommand() {
    for args in [vec![], vec!["unknown"], vec!["capabilities", "extra"]] {
        run(&args, 64, b"", b"project-hooks: unknown subcommand\n");
    }
}

mod post_edit_check {
    //! Native replay of the unmodified Yoke advisory scanner; no interpreter required.
    use serde_json::{Value, json};
    use std::{
        fs,
        io::Write,
        process::{Command, Stdio},
    };

    fn snapshot(root: &std::path::Path) -> Vec<(std::path::PathBuf, u64, bool)> {
        let mut out = Vec::new();
        for entry in fs::read_dir(root).unwrap() {
            let path = entry.unwrap().path();
            let meta = fs::metadata(&path).unwrap();
            out.push((path.clone(), meta.len(), meta.is_dir()));
            if meta.is_dir() {
                out.extend(snapshot(&path));
            }
        }
        out.sort();
        out
    }
    fn invoke(record: &Value) -> Value {
        let dir = tempfile::tempdir().unwrap();
        let root = fs::canonicalize(dir.path()).unwrap();
        let expand = |s: &str| s.replace("@PROJECT@", root.to_str().unwrap());
        for (name, entry) in record["setup"].as_object().unwrap() {
            let path = root.join(name);
            fs::create_dir_all(path.parent().unwrap()).unwrap();
            if entry["directory"] == true {
                fs::create_dir_all(path).unwrap();
            } else {
                fs::write(&path, entry["text"].as_str().unwrap()).unwrap();
                #[cfg(unix)]
                {
                    use std::os::unix::fs::PermissionsExt;
                    fs::set_permissions(
                        path,
                        fs::Permissions::from_mode(entry["mode"].as_u64().unwrap_or(0o644) as u32),
                    )
                    .unwrap();
                }
            }
        }
        let before = snapshot(&root);
        let mut command = Command::new(env!("CARGO_BIN_EXE_project-hooks"));
        command
            .arg("post-edit-check")
            .env_clear()
            .env("CLAUDE_PROJECT_DIR", &root)
            .current_dir(&root);
        for (key, value) in record["env"].as_object().unwrap() {
            command.env(key, value.as_str().unwrap());
        }
        let mut child = command
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .unwrap();
        child
            .stdin
            .take()
            .unwrap()
            .write_all(expand(record["stdin"].as_str().unwrap()).as_bytes())
            .unwrap();
        let result = child.wait_with_output().unwrap();
        assert_eq!(snapshot(&root), before);
        let normalize = |data: Vec<u8>| {
            String::from_utf8(data)
                .unwrap()
                .replace(root.to_str().unwrap(), "@PROJECT@")
        };
        // This command is read-only; compare every readable file and its original mode.
        for (name, entry) in record["setup"].as_object().unwrap() {
            let path = root.join(name);
            if entry["directory"] == true {
                assert!(path.is_dir());
                continue;
            }
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                assert_eq!(
                    fs::metadata(&path).unwrap().permissions().mode() & 0o777,
                    entry["mode"].as_u64().unwrap_or(0o644) as u32
                );
                fs::set_permissions(&path, fs::Permissions::from_mode(0o644)).unwrap();
            }
            assert_eq!(
                fs::read_to_string(path).unwrap(),
                entry["text"].as_str().unwrap()
            );
        }
        json!({"exit":result.status.code(),"stdout":normalize(result.stdout),"stderr":normalize(result.stderr),"delta":{},"deleted":[]})
    }

    #[test]
    fn frozen_post_edit_branches() {
        let fixture: Value =
            serde_json::from_str(include_str!("fixtures/w1/post-edit-check.json")).unwrap();
        let records = fixture["records"].as_array().unwrap();
        assert_eq!(records.len(), 55);
        for record in records {
            #[cfg(not(unix))]
            if record["id"] == "unreadable" {
                continue;
            }
            assert_eq!(invoke(record), record["expected"], "{}", record["id"]);
        }
    }

    #[test]
    fn redaction_and_warnings_remain_advisory() {
        let record = json!({"setup":{"app.ts":{"text":"console.log('sk-aaaaaaaaaaaaaaaaaaaa');\n"}},"stdin":"{\"tool_input\":{\"file_path\":\"app.ts\"}}","env":{}});
        let result = invoke(&record);
        assert_eq!(result["exit"], 0, "warnings must never block");
        let stdout = result["stdout"].as_str().unwrap();
        assert!(stdout.contains("[WARNING]") && stdout.contains("[CRITICAL]"));
        assert!(
            !format!("{}{}", stdout, result["stderr"]).contains("sk-aaaaaaaaaaaaaaaaaaaa"),
            "matched secret line must never be echoed"
        );
    }

    #[test]
    fn legacy_capture_environment_artefacts_are_preserved() {
        let records: Vec<Value> =
            serde_json::from_str(include_str!("fixtures/w1/records.json")).unwrap();
        let legacy: Vec<_> = records
            .iter()
            .filter(|r| r["family"] == ".claude/hooks/post-edit-check.sh")
            .collect();
        assert_eq!(legacy.len(), 3);
        for r in legacy {
            // W1-Y1 omitted paste from PATH. These are capture-environment artefacts,
            // not scanner behavior to reproduce in Rust; normal-tool records above replace replay.
            assert_eq!(r["expected"]["exit"], 0);
            assert_eq!(r["expected"]["stdout"], "");
            let alphabet = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
            let (mut bits, mut buffer) = (0, 0u32);
            let mut decoded = Vec::new();
            for b in r["expected"]["stderr"]
                .as_str()
                .unwrap()
                .bytes()
                .take_while(|b| *b != b'=')
            {
                buffer = (buffer << 6) | alphabet.iter().position(|c| *c == b).unwrap() as u32;
                bits += 6;
                if bits >= 8 {
                    bits -= 8;
                    decoded.push((buffer >> bits) as u8);
                }
            }
            let stderr = String::from_utf8(decoded).unwrap();
            assert_eq!(stderr.lines().count(), 2);
            assert!(
                stderr
                    .lines()
                    .all(|line| line.ends_with("paste: command not found"))
            );
        }
    }
}

// Immutable W1 own-hook replay; subprocesses have no interpreter on PATH.
#[cfg(unix)]
// Only envelope primitives are needed; the shared dispatcher uses shell filenames.
#[allow(dead_code)]
#[path = "support/replay.rs"]
mod frozen;

#[cfg(unix)]
mod prompt_submit {
    use super::frozen;
    use serde_json::{Value, json};
    use std::{fs, io::Write, process::Stdio};

    fn check(record: &Value) {
        let dir = tempfile::tempdir().unwrap();
        let root = fs::canonicalize(dir.path()).unwrap();
        let mut cmd = frozen::prepare(&root);
        cmd.arg("prompt-submit");
        let unreadable = record["case"] == "unreadable-stdin";
        if unreadable {
            cmd.stdin(fs::File::open(&root).unwrap());
        } else {
            cmd.stdin(Stdio::piped());
        }
        let before = frozen::snapshot(&root.join("project"));
        let mut child = cmd
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .unwrap();
        if !unreadable {
            child
                .stdin
                .take()
                .unwrap()
                .write_all(&frozen::decode(&record["stdin"]))
                .unwrap();
        }
        let output = child.wait_with_output().unwrap();
        assert_eq!(
            output.status.code(),
            record["expected"]["exit"].as_i64().map(|n| n as i32),
            "{} status",
            record["case"]
        );
        assert_eq!(
            output.stdout,
            frozen::decode(&record["expected"]["stdout"]),
            "{} stdout",
            record["case"]
        );
        assert_eq!(
            output.stderr,
            frozen::decode(&record["expected"]["stderr"]),
            "{} stderr",
            record["case"]
        );
        assert_eq!(
            frozen::snapshot(&root.join("project")),
            before,
            "{} filesystem",
            record["case"]
        );
        assert_eq!(record["expected"]["delta"], json!({}));
        assert_eq!(record["expected"]["deleted"], json!([]));
    }

    fn new_records() -> Value {
        serde_json::from_str(include_str!("fixtures/w1/prompt-submit.json")).unwrap()
    }

    #[test]
    fn reused_w1_records() {
        let records: Vec<Value> =
            serde_json::from_str(include_str!("fixtures/w1/records.json")).unwrap();
        let own: Vec<_> = records
            .iter()
            .filter(|r| r["family"] == ".claude/hooks/user-prompt-submit.sh")
            .collect();
        assert_eq!(own.len(), 5);
        for row in own {
            check(row);
        }
    }

    #[test]
    fn added_frozen_records() {
        let data = new_records();
        let rows = data["records"].as_array().unwrap();
        assert_eq!(rows.len(), 28);
        assert_eq!(data["locale"], "en_US.UTF-8");
        let mut retired = Vec::new();
        for row in rows {
            if let Some(reason) = row["retired_branch"].as_str() {
                // Native code has no interpreter: retain observations, never emulate failures.
                retired.push((row["case"].as_str().unwrap(), reason));
            } else {
                check(row);
            }
        }
        assert_eq!(
            retired.iter().map(|r| r.0).collect::<Vec<_>>(),
            ["python-unavailable", "tokenizer-unavailable"]
        );
        assert!(retired.iter().all(|r| !r.1.is_empty()));
    }

    fn named(case: &str) {
        let data = new_records();
        check(
            data["records"]
                .as_array()
                .unwrap()
                .iter()
                .find(|r| r["case"] == case)
                .unwrap(),
        );
    }

    #[test]
    fn underscore_splits_tokens() {
        named("punctuation-underscore");
    }
    #[test]
    fn counts_characters_not_bytes() {
        named("unicode-39");
        named("unicode-40");
    }
    #[test]
    fn invalid_payload_stays_advisory() {
        named("non-object");
        named("invalid-utf8");
    }
}
