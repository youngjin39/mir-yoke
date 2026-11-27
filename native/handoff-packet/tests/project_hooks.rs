//! The probe and warmup must finish while the caller still owns open stdin.
use std::{
    process::{Command, Stdio},
    thread,
    time::{Duration, Instant},
};

#[cfg(unix)]
use frozen::executable;

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
        b"mir-project-hooks-v1\nmir-project-hooks-compact-v1\nmir-project-hooks-tdd-v1\nmir-project-hooks-post-edit-v1\nmir-project-hooks-prompt-v1\nmir-project-hooks-stop-v1\nmir-project-hooks-session-start-v1\nmir-project-hooks-session-start-v2\nmir-project-hooks-post-edit-memory-sync-v1\nmir-project-hooks-pre-commit-v1\nmir-project-hooks-pre-tool-use-v1\nmir-project-hooks-tool-contract-v1\n",
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

    fn payload(template: &str, root: &str) -> String {
        fn expand(value: &mut Value, root: &str) {
            match value {
                Value::String(text) => *text = text.replace("@PROJECT@", root),
                Value::Array(items) => items.iter_mut().for_each(|v| expand(v, root)),
                Value::Object(fields) => fields.values_mut().for_each(|v| expand(v, root)),
                _ => {}
            }
        }
        // Malformed-input records intentionally exercise the advisory parse failure.
        let Ok(mut value) = serde_json::from_str::<Value>(template) else {
            return template.to_owned();
        };
        expand(&mut value, root);
        serde_json::to_string(&value).unwrap()
    }

    #[test]
    fn payload_expansion_preserves_json_strings() {
        let template = r#"{"tool_input":{"file_path":"@PROJECT@/app.ts","patch":"*** Update File: @PROJECT@/app.ts\n"}}"#;
        for root in [
            r"C:\scratch\project",
            r"\\?\C:\scratch\project",
            "/scratch/quote\"root",
        ] {
            let input: Value = serde_json::from_str(&payload(template, root)).unwrap();
            assert_eq!(input["tool_input"]["file_path"], format!("{root}/app.ts"));
            assert_eq!(
                input["tool_input"]["patch"],
                format!("*** Update File: {root}/app.ts\n")
            );
        }
        assert_eq!(payload("no json", "root"), "no json");
        assert_eq!(payload("", "root"), "");
    }

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
            .write_all(
                payload(record["stdin"].as_str().unwrap(), root.to_str().unwrap()).as_bytes(),
            )
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
        let record = json!({"setup":{"app.ts":{"text":"console.log('sk-aaaaaaaaaaaaaaaaaaaa');\n"}},"stdin":json!({"tool_input":{"file_path":"app.ts"}}).to_string(),"env":{}});
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

#[cfg(unix)]
#[path = "../src/stop_audit.rs"]
#[allow(dead_code)] // The replay suite also exercises deterministic filename collisions.
mod stop_audit_impl;

#[cfg(unix)]
mod stop_audit {
    use super::{executable, frozen, stop_audit_impl as audit};
    use regex::Regex;
    use serde_json::{Value, json};
    use std::{collections::BTreeMap, fs, io::Write, os::unix::fs::PermissionsExt, process::Stdio};

    fn normalized(name: &str, entry: &Value) -> (String, Value) {
        let filename =
            Regex::new(r"stop(-failure)?-([0-9]{8}T[0-9]{6}Z)-([1-9][0-9]*)-([0-9a-f]{6})\.log")
                .unwrap();
        let utc = Regex::new(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}\+00:00").unwrap();
        let name = filename
            .replace_all(name, "stop${1}-@TIME@-@PID@-@RANDOM@.log")
            .into_owned();
        if entry.get("base64").is_none() {
            return (name, entry.clone());
        }
        let raw = String::from_utf8(frozen::decode(&entry["base64"])).unwrap();
        let mut raw = filename
            .replace_all(&raw, "stop${1}-@TIME@-@PID@-@RANDOM@.log")
            .into_owned();
        if name.ends_with("-@RANDOM@.log") && raw != "sentinel\n" {
            if !raw.contains("@UTC@") {
                assert_eq!(utc.find_iter(&raw).count(), 1, "{name}");
            }
            raw = utc.replace_all(&raw, "@UTC@").into_owned();
        }
        if name == "review-argv.json" {
            raw = Regex::new(r"auto-review-\d{8}T\d{6}Z-")
                .unwrap()
                .replace_all(&raw, "auto-review-@TIME@-")
                .into_owned();
        }
        (name, json!({"text":raw,"mode":entry["mode"]}))
    }

    fn records() -> Vec<Value> {
        let mut records: Vec<Value> =
            serde_json::from_str(include_str!("fixtures/w1-stop-audit/records.json")).unwrap();
        let old: Vec<Value> =
            serde_json::from_str(include_str!("fixtures/w1/records.json")).unwrap();
        records.extend(old.into_iter().filter(|r| {
            matches!(
                r["family"].as_str(),
                Some(".claude/hooks/mir-stop.sh" | ".claude/hooks/stop-failure-audit.sh")
            )
        }));
        assert_eq!(records.len(), 53);
        records
    }

    fn replay(record: &Value) {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path().canonicalize().unwrap(); // macOS temp paths may be symlinks.
        let mut command = frozen::prepare(&root);
        // New records store target-relative setup; W1 stores root-relative setup.
        let new = record.get("retired").is_some();
        let project = root.join("project");
        frozen::install(&record["setup"], if new { &project } else { &root });
        let stop = record["family"] == ".claude/hooks/mir-stop.sh";
        command.arg(if stop {
            "stop-audit"
        } else {
            "stop-failure-audit"
        });
        for (key, value) in record["env"].as_object().unwrap() {
            command.env(
                key,
                String::from_utf8(frozen::transform(
                    value.as_str().unwrap().as_bytes().to_vec(),
                    &root,
                    true,
                ))
                .unwrap(),
            );
        }
        if record["case"] == "review" {
            let adapter = root.join("tools/review-adapter");
            executable::write(&adapter, "#!/bin/sh\n[ \"$1\" = -m ] && [ \"$2\" = tools.mir_executor ] || exit 2\nshift 2\n{ printf '['; sep=''; for arg do printf '%s\"%s\"' \"$sep\" \"$arg\"; sep=', '; done; printf ']'; } > review-argv.json\necho ignored >&2\nexit 9\n").unwrap();
            fs::set_permissions(&adapter, fs::Permissions::from_mode(0o755)).unwrap();
            command.env("MIR_STOP_REVIEW_ADAPTER", adapter);
        }
        let before = frozen::snapshot(&root.join("project"));
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
            .write_all(&frozen::transform(
                frozen::decode(&record["stdin"]),
                &root,
                true,
            ))
            .unwrap();
        let result = child.wait_with_output().unwrap();
        let after = frozen::snapshot(&root.join("project"));
        let delta: BTreeMap<_, _> = after
            .iter()
            .filter(|(name, value)| before.get(*name) != Some(*value))
            .map(|(name, value)| normalized(name, value))
            .collect();
        let deleted: Vec<_> = before
            .keys()
            .filter(|name| !after.contains_key(*name))
            .collect();
        let expected = &record["expected"];
        let mut want: BTreeMap<_, _> = expected["delta"]
            .as_object()
            .unwrap()
            .iter()
            .map(|(k, v)| normalized(k, v))
            .collect();
        let mut stderr = String::from_utf8(frozen::decode(&expected["stderr"])).unwrap();
        let case = record["case"].as_str().unwrap();
        if case == "malformed" {
            // Retire CPython JSONDecodeError wording, retaining the parse-failure file.
            for entry in want.values_mut() {
                if let Some(text) = entry.get_mut("text") {
                    let raw = text.as_str().unwrap();
                    let re = if stop {
                        r"parse_error: .*\n"
                    } else {
                        r#""parse_error": ".*",\n"#
                    };
                    *text = Regex::new(re)
                        .unwrap()
                        .replace(
                            raw,
                            if stop {
                                "parse_error: 'invalid JSON'\n"
                            } else {
                                "\"parse_error\": \"invalid JSON\",\n"
                            },
                        )
                        .into_owned()
                        .into();
                }
            }
        } else if matches!(case, "list" | "null" | "scalar" | "string-root") {
            // Retire CPython AttributeError traceback; retain mkdir effects and no log.
            assert!(stderr.contains("AttributeError"));
            assert!(!record["retired"].as_str().unwrap().is_empty());
            stderr.clear();
        }
        let actual_stderr = frozen::transform(result.stderr, &root, false);
        let actual_stderr =
            normalized("stderr", &json!({"base64":encode(&actual_stderr),"mode":0})).1["text"]
                .as_str()
                .unwrap()
                .to_owned();
        let expected_stderr = normalized(
            "stderr",
            &json!({"base64":encode(stderr.as_bytes()),"mode":0}),
        )
        .1["text"]
            .as_str()
            .unwrap()
            .to_owned();
        if case == "unwritable" {
            fs::set_permissions(
                root.join("project/tasks/sessions"),
                fs::Permissions::from_mode(0o755),
            )
            .unwrap();
        }
        assert_eq!(result.status.code(), Some(0), "{}", record["id"]);
        assert_eq!(
            frozen::transform(result.stdout, &root, false),
            frozen::decode(&expected["stdout"]),
            "{}",
            record["id"]
        );
        assert_eq!(actual_stderr, expected_stderr, "{}", record["id"]);
        assert_eq!(delta, want, "{}", record["id"]);
        assert_eq!(json!(deleted), expected["deleted"], "{}", record["id"]);
    }

    fn encode(bytes: &[u8]) -> String {
        let alphabet = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
        let mut out = String::new();
        for chunk in bytes.chunks(3) {
            let n =
                chunk.iter().fold(0u32, |n, b| (n << 8) | u32::from(*b)) << (8 * (3 - chunk.len()));
            for i in 0..4 {
                out.push(if i > chunk.len() {
                    '='
                } else {
                    alphabet[((n >> (18 - i * 6)) & 63) as usize] as char
                });
            }
        }
        out
    }

    #[test]
    fn stop_audit_frozen_records() {
        for r in records() {
            replay(&r);
        }
    }
    #[test]
    fn stop_audit_unwritable() {
        for r in records().iter().filter(|r| r["case"] == "unwritable") {
            replay(r);
        }
    }
    #[test]
    fn stop_audit_snippet_500() {
        for r in records()
            .iter()
            .filter(|r| r["case"] == "type-11" || r["case"] == "type-12")
        {
            replay(r);
        }
    }
    #[test]
    fn stop_audit_review_adapter() {
        for r in records().iter().filter(|r| r["case"] == "review") {
            replay(r);
        }
    }

    #[test]
    fn stop_audit_existing_collision() {
        let dir = tempfile::tempdir().unwrap();
        let ts = "20000101T000000Z";
        let existing = dir
            .path()
            .join(format!("stop-{ts}-{}-010203.log", std::process::id()));
        fs::write(&existing, "sentinel\n").unwrap();
        let mut calls = 0;
        let (mut log, path) = audit::create_log(dir.path(), "stop", ts, || {
            calls += 1;
            Ok(if calls == 1 { [1, 2, 3] } else { [4, 5, 6] })
        })
        .unwrap();
        log.write_all(b"new log\n").unwrap();
        assert_eq!(fs::read_to_string(&existing).unwrap(), "sentinel\n");
        assert_eq!(calls, 2);
        assert_ne!(path, existing);
        assert_eq!(fs::read_to_string(path).unwrap(), "new log\n");
        assert!(audit::create_log(dir.path(), "stop", ts, || Ok([1, 2, 3])).is_err());
    }
}
