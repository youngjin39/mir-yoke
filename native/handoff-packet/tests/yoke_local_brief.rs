use handoff_packet::{executor_command_hooks::CommandHooks, local_bridge::BridgeConfig};
use serde_json::{Value, json};
use std::{collections::BTreeMap, fs, path::PathBuf, time::Duration};

mod path_records {
    include!("support/path_records.rs");
}

#[test]
fn disabled_parser_extensions_do_not_control_execute_or_resume() {
    let scratch = std::env::var_os("MIR_NATIVE_TEST_SCRATCH")
        .map(PathBuf::from)
        .unwrap_or_else(std::env::temp_dir);
    let root = tempfile::tempdir_in(scratch).unwrap();
    fs::create_dir(root.path().join("config")).unwrap();
    fs::create_dir_all(root.path().join("tools/mir_executor")).unwrap();
    fs::write(
        root.path().join("tools/mir_executor/local.py"),
        "# register_execute_options\nraise AssertionError('inactive module imported')\n",
    )
    .unwrap();
    // Host temp roots may use an alias (e.g. /var versus /private/var).
    // Keep this deterministic even when scratch has no aliased ancestors.
    #[cfg(unix)]
    let invoking_home = root.path().join("home-alias");
    #[cfg(unix)]
    std::os::unix::fs::symlink(root.path(), &invoking_home).unwrap();
    #[cfg(not(unix))]
    let invoking_home = root.path().to_path_buf();
    let db = root.path().join("tasks/jobs.db");
    drop(handoff_packet::executor_registry::JobRegistry::open(&db).unwrap());
    let before = fs::read(&db).unwrap();
    let cases: &[(&[&str], &[u8])] = &[
        (
            &["execute", "--codex-args", r#"["exec", "prompt"]"#],
            b"[mir_executor] --change-id and --category are required outside --dispatch\n",
        ),
        (
            &["resume", "--job-id", "absent"],
            b"[mir_executor] resume requires an existing job with a dispatch_brief_path\n",
        ),
    ];
    for disabled in [true, false] {
        fs::write(
            root.path().join("config/mir-executor.local.json"),
            json!({"python_local_hooks":!disabled,"native_policy":{
                "version":1,"brief_profile":{"name":"base_v1"}
            }})
            .to_string(),
        )
        .unwrap();
        for (arguments, expected) in cases {
            let trace = root
                .path()
                .join(format!("{}-{disabled}.trace", arguments[0]));
            let output = std::process::Command::new(env!("CARGO_BIN_EXE_executor-query"))
                .arg("--home-root")
                .arg(&invoking_home)
                .args(*arguments)
                .arg("--repo-root")
                .arg(root.path())
                .current_dir(root.path())
                .env("HOME", root.path())
                .env("PATH", "")
                .env("MIR_EXECUTOR_DECLINE_TRACE", &trace)
                .output()
                .unwrap();
            assert!(output.stdout.is_empty(), "{arguments:?}: {output:?}");
            if disabled {
                assert_eq!(output.status.code(), Some(1), "{arguments:?}: {output:?}");
                let expected = if cfg!(windows) {
                    String::from_utf8(expected.to_vec())
                        .unwrap()
                        .replace('\n', "\r\n")
                        .into_bytes()
                } else {
                    expected.to_vec()
                };
                assert_eq!(output.stderr, expected, "{arguments:?}: {output:?}");
                assert!(!trace.exists(), "{arguments:?}: unexpected decline");
            } else {
                assert_eq!(output.status.code(), Some(64), "{arguments:?}: {output:?}");
                assert!(output.stderr.is_empty(), "{arguments:?}: {output:?}");
                assert!(
                    fs::read_to_string(trace)
                        .unwrap()
                        .contains("local parser extension"),
                    "{arguments:?}: missing parser-extension decline"
                );
            }
            assert_eq!(
                fs::read(&db).unwrap(),
                before,
                "{arguments:?}: registry changed"
            );
            for suffix in ["-journal", "-wal", "-shm"] {
                assert!(!db.with_file_name(format!("jobs.db{suffix}")).exists());
            }
        }
    }
}

#[test]
fn yoke_local_brief_frozen_hook_parity_without_python() {
    let fixture: Value = serde_json::from_str(include_str!(
        "../../../tests/fixtures/yoke_local_brief.json"
    ))
    .unwrap();
    let scratch = std::env::var_os("MIR_NATIVE_TEST_SCRATCH")
        .map(PathBuf::from)
        .unwrap_or_else(std::env::temp_dir);
    let root = tempfile::tempdir_in(scratch).unwrap();
    fs::create_dir(root.path().join("config")).unwrap();
    fs::write(
        root.path().join("config/mir-executor.local.json"),
        include_bytes!("../../../config/mir-executor.local.json"),
    )
    .unwrap();
    fs::create_dir_all(root.path().join("tools/mir_executor")).unwrap();
    fs::write(
        root.path().join("tools/mir_executor/local.py"),
        include_bytes!("../../../tools/mir_executor/local.py"),
    )
    .unwrap();
    assert_eq!(fixture["cases"].as_array().unwrap().len(), 93);
    // These paths cannot launch a process. Every case must use the native route.
    let mut hooks = CommandHooks::start_in(
        BridgeConfig {
            interpreter: root.path().join("missing-python"),
            target_root: root.path().to_path_buf(),
            bridge_script: root.path().join("missing-bridge.py"),
            environment: BTreeMap::new(),
            timeout: Duration::from_secs(1),
        },
        root.path(),
    )
    .unwrap()
    .unwrap();
    assert!(!hooks.python_exports("validate_brief"));
    // Native status must also ignore the inactive module, with no PATH lookup.
    let status = std::process::Command::new(env!("CARGO_BIN_EXE_executor-query"))
        .arg("--home-root")
        .arg(root.path())
        .arg("status")
        .arg("--help")
        .current_dir(root.path())
        .env("HOME", root.path())
        .env("PATH", "")
        .output()
        .unwrap();
    assert_eq!(status.status.code(), Some(2), "{status:?}");
    assert!(status.stdout.is_empty());
    assert!(status.stderr.starts_with(b"usage:"));
    assert!(String::from_utf8_lossy(&status.stderr).contains("required: --job-id"));
    assert!(!root.path().join("tasks/jobs.db").exists());
    let path = root.path().join("brief.json");
    let root_argument = json!({"$type":"path","value":root.path()});
    let mut mismatches = Vec::new();
    for case in fixture["cases"].as_array().unwrap() {
        #[cfg(not(unix))]
        if case["path_kind"] == "unreadable" {
            continue;
        }
        if path.is_dir() {
            fs::remove_dir(&path).unwrap();
        } else if path.exists() {
            fs::remove_file(&path).unwrap();
        }
        let argument = if case["input_kind"] == "text" {
            case["text"].clone()
        } else {
            match case["path_kind"].as_str() {
                Some("missing") => (),
                Some("directory") => fs::create_dir(&path).unwrap(),
                #[cfg(unix)]
                Some("unreadable") => {
                    use std::os::unix::fs::PermissionsExt;
                    fs::write(&path, b"{}").unwrap();
                    fs::set_permissions(&path, fs::Permissions::from_mode(0o0)).unwrap();
                }
                _ => {
                    let hex = case["bytes_hex"].as_str().unwrap();
                    let bytes = hex
                        .as_bytes()
                        .as_chunks::<2>()
                        .0
                        .iter()
                        .map(|pair| {
                            u8::from_str_radix(std::str::from_utf8(pair).unwrap(), 16).unwrap()
                        })
                        .collect::<Vec<_>>();
                    fs::write(&path, bytes).unwrap();
                }
            }
            json!({"$type":"path","value":path})
        };
        let reply = hooks
            .call(
                "validate_brief",
                vec![argument, root_argument.clone()],
                json!({}),
            )
            .unwrap();
        #[cfg(unix)]
        if case["path_kind"] == "unreadable" {
            use std::os::unix::fs::PermissionsExt;
            fs::set_permissions(&path, fs::Permissions::from_mode(0o600)).unwrap();
        }
        // The Python bridge retains BaseModel results as opaque handles. A
        // successful model containing lone surrogates has no JSON value on that
        // wire; compare its admission decision, retaining the raw oracle dump.
        if case["decision_only"] == true {
            assert_eq!(reply["ok"], true, "{}: {reply}", case["name"]);
            continue;
        }
        let actual = if reply["ok"] == true {
            json!({"value":reply["result"]})
        } else {
            json!({"kind":reply["error"]["type"],"message":reply["error"]["message"]
                .as_str().map(|s| path_records::root_token(s, root.path(), "<ROOT>")).unwrap()})
        };
        let expected = if case.get("kind").is_some() {
            json!({"kind":case["kind"],"message":case["message"]})
        } else {
            json!({"value":case["value"]})
        };
        #[cfg(windows)]
        let expected = if matches!(case["name"].as_str(), Some("missing_file" | "directory")) {
            let name = case["name"].as_str().unwrap();
            let record = path_records::record(&format!("yoke_local_brief.{name}"));
            json!({"kind":record["error"]["kind"],"message":record["error"]["message"]
                .as_str().unwrap().replace(&format!("{{ROOT}}\\\\{name}"), "<ROOT>")})
        } else {
            expected
        };
        if actual != expected {
            mismatches.push(format!(
                "{}\nactual: {actual}\nexpected: {expected}",
                case["name"]
            ));
        }
    }
    assert!(mismatches.is_empty(), "{}", mismatches.join("\n\n"));
    // Unrelated valid JSON must not turn an explicit opt-out back into a
    // Python module (serde_json's default recursion cap is too shallow).
    let deep = format!(
        "{{\"python_local_hooks\":false,\"ignored\":{}0{}}}",
        "[".repeat(130),
        "]".repeat(130)
    );
    fs::write(root.path().join("config/mir-executor.local.json"), deep).unwrap();
    assert!(
        CommandHooks::start_in(
            BridgeConfig {
                interpreter: root.path().join("missing-python"),
                target_root: root.path().to_path_buf(),
                bridge_script: root.path().join("missing-bridge.py"),
                environment: BTreeMap::new(),
                timeout: Duration::from_secs(1),
            },
            root.path()
        )
        .unwrap()
        .is_none()
    );
}

#[test]
fn invalid_hook_selection_is_a_final_refusal_for_every_command() {
    let scratch = std::env::var_os("MIR_NATIVE_TEST_SCRATCH")
        .map(PathBuf::from)
        .unwrap_or_else(std::env::temp_dir);
    let root = tempfile::tempdir_in(scratch).unwrap();
    fs::create_dir(root.path().join("config")).unwrap();
    fs::create_dir_all(root.path().join("tools/mir_executor")).unwrap();
    let db = root.path().join("tasks/jobs.db");
    drop(handoff_packet::executor_registry::JobRegistry::open(&db).unwrap());
    let before = fs::read(&db).unwrap();
    let commands: &[&[&str]] = &[
        &["status", "--job-id", "missing"],
        &["result", "--job-id", "missing"],
        &["list-jobs"],
        &["cancel", "--job-id", "missing"],
        &["execute", "--codex-args", "[]"],
        &["execute", "--dispatch", "--dispatch-brief", "missing.json"],
        &["resume", "--job-id", "missing"],
        &["sweep"],
    ];
    // New key contract: a present selector is boolean and names a retained module.
    // These literal cases are policy tests, not a Python-reference oracle.
    for local in [false, true] {
        let module = root.path().join("tools/mir_executor/local.py");
        if local {
            fs::write(&module, "raise AssertionError('must not import')\n").unwrap();
        }
        for value in [
            json!(null),
            json!(0),
            json!(1),
            json!("false"),
            json!("unknown"),
            json!([]),
            json!({}),
            json!(false),
            json!(true),
        ] {
            if local && value.is_boolean() {
                continue;
            }
            fs::write(
                root.path().join("config/mir-executor.local.json"),
                json!({"python_local_hooks":value}).to_string(),
            )
            .unwrap();
            let message = if value.is_boolean() {
                "python_local_hooks requires tools/mir_executor/local.py"
            } else {
                "python_local_hooks must be a boolean"
            };
            let expected =
                format!("[mir_executor] native local policy configuration error: {message}\n");
            for argv in commands {
                let out = std::process::Command::new(env!("CARGO_BIN_EXE_executor-query"))
                    .arg("--home-root")
                    .arg(root.path())
                    .args(*argv)
                    .current_dir(root.path())
                    .env("HOME", root.path())
                    .env("PATH", "")
                    .output()
                    .unwrap();
                assert_eq!(
                    out.status.code(),
                    Some(1),
                    "{local} {value} {argv:?}: {out:?}"
                );
                assert!(out.stdout.is_empty(), "{local} {value} {argv:?}: {out:?}");
                let expected = if cfg!(windows) {
                    expected.replace('\n', "\r\n")
                } else {
                    expected.clone()
                };
                assert_eq!(out.stderr, expected.as_bytes(), "{local} {value} {argv:?}");
                assert_eq!(fs::read(&db).unwrap(), before, "{argv:?}: registry changed");
            }
        }
    }
}

#[test]
fn absent_selector_retains_head_dispatch_diagnostics() {
    let scratch = std::env::var_os("MIR_NATIVE_TEST_SCRATCH")
        .map(PathBuf::from)
        .unwrap_or_else(std::env::temp_dir);
    let root = tempfile::tempdir_in(scratch).unwrap();
    assert!(
        std::process::Command::new("git")
            .args(["init", "-q"])
            .arg(root.path())
            .status()
            .unwrap()
            .success()
    );
    fs::create_dir(root.path().join("config")).unwrap();
    fs::create_dir_all(root.path().join("tools/mir_executor")).unwrap();
    fs::write(
        root.path().join("config/mir-executor.local.json"),
        r#"{"native_policy":{"version":1,"brief_profile":{"name":"base_v1"}}}"#,
    )
    .unwrap();
    // Frozen from executor-query built at 58e7a0e7c291ef3c15f4526c658be2341e94ba6f.
    // A new opt-in may not fix diagnostics for existing unselected consumers.
    let cases: &[(&[u8], &str)] = &[
        (
            b"{\r?}",
            "Expecting property name enclosed in double quotes: line 1 column 3 (char 2)",
        ),
        (
            b"{\r\n?}",
            "Expecting property name enclosed in double quotes: line 2 column 1 (char 3)",
        ),
        (b"{}\r\nx", "Extra data: line 2 column 1 (char 4)"),
        (
            br#"{"task_id":"\ud800"}"#,
            "unexpected end of hex escape at line 1 column 19",
        ),
    ];
    for (bytes, expected) in cases {
        fs::write(root.path().join("brief.json"), bytes).unwrap();
        let out = std::process::Command::new(env!("CARGO_BIN_EXE_executor-query"))
            .arg("--home-root")
            .arg(root.path())
            .args(["execute", "--dispatch", "--dispatch-brief", "brief.json"])
            .current_dir(root.path())
            .env("HOME", root.path())
            .output()
            .unwrap();
        assert_eq!(out.status.code(), Some(1), "{bytes:?}: {out:?}");
        assert!(out.stdout.is_empty());
        let expected = format!("[mir_executor] DispatchBrief error: {expected}\n");
        let expected = if cfg!(windows) {
            expected.replace('\n', "\r\n")
        } else {
            expected
        };
        assert_eq!(out.stderr, expected.as_bytes(), "{bytes:?}");
    }
}

#[test]
fn absent_selector_does_not_eagerly_validate_unparseable_legacy_data() {
    let scratch = std::env::var_os("MIR_NATIVE_TEST_SCRATCH")
        .map(PathBuf::from)
        .unwrap_or_else(std::env::temp_dir);
    let root = tempfile::tempdir_in(scratch).unwrap();
    fs::create_dir(root.path().join("config")).unwrap();
    fs::write(
        root.path().join("config/mir-executor.local.json"),
        r#"{"ignored":"python_local_hooks",?}"#,
    )
    .unwrap();
    let out = std::process::Command::new(env!("CARGO_BIN_EXE_executor-query"))
        .arg("--home-root")
        .arg(root.path())
        .args(["status", "--job-id", "missing"])
        .current_dir(root.path())
        .env("HOME", root.path())
        .output()
        .unwrap();
    assert_eq!(out.status.code(), Some(1));
    assert!(out.stdout.is_empty());
    // Frozen HEAD status outcome: the absent selector does not own this config.
    let expected = "[mir_executor] job_id not found: 'missing'\n";
    let expected = if cfg!(windows) {
        expected.replace('\n', "\r\n")
    } else {
        expected.to_owned()
    };
    assert_eq!(out.stderr, expected.as_bytes());
}
