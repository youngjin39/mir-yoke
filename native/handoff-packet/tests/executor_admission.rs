use handoff_packet::executor_admission::{Admission, Request, admit};
use std::{collections::BTreeMap, path::Path};
#[test]
fn unsupported_declines_without_launching_bridge() {
    let result = admit(Request {
        argv: &["resume".into()],
        cwd: Path::new("."),
        invoking_home: Path::new("."),
        environment: &BTreeMap::new(),
        interpreter: Path::new("missing-python"),
        bridge_script: Path::new("missing.py"),
    })
    .unwrap();
    assert!(matches!(result, Admission::Decline { code: 64, .. }));
}

use std::{fs, path::PathBuf, process::Command};
struct Fixture(PathBuf);
impl Fixture {
    fn new() -> Self {
        static NEXT: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
        let root = std::env::var_os("MIR_NATIVE_TEST_SCRATCH")
            .map(PathBuf::from)
            .unwrap_or_else(std::env::temp_dir)
            .join(format!(
                "admission-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, std::sync::atomic::Ordering::Relaxed)
            ));
        for dir in ["home", "target"] {
            fs::create_dir_all(root.join(dir).join("tools/mir_executor")).unwrap();
            assert!(
                Command::new("git")
                    .args(["init", "-q"])
                    .arg(root.join(dir))
                    .status()
                    .unwrap()
                    .success()
            );
        }
        // Python resolves the fixture root (/var -> /private/var on macOS, 8.3 short
        // names -> long names on Windows) and never keeps the verbatim prefix.
        let root = fs::canonicalize(&root).unwrap();
        let root = match root.to_str().and_then(|text| text.strip_prefix(r"\\?\")) {
            Some(rest) if rest.as_bytes().get(1) == Some(&b':') => PathBuf::from(rest),
            _ => root,
        };
        Self(root)
    }
    fn run(&self, argv: &[String], home: &Path) -> Admission {
        let python = ["python3", "python"]
            .iter()
            .find_map(|name| {
                let output = Command::new(name)
                    .args(["-c", "import sys;print(sys.executable)"])
                    .output()
                    .ok()?;
                output
                    .status
                    .success()
                    .then(|| PathBuf::from(String::from_utf8(output.stdout).unwrap().trim()))
            })
            .expect("Python interpreter");
        admit(Request {
            argv,
            cwd: &self.0.join("target"),
            invoking_home: home,
            environment: &std::env::vars_os().collect(),
            interpreter: &python,
            bridge_script: &PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                .join("../../tools/mir_executor/local_bridge.py")
                .canonicalize()
                .unwrap(),
        })
        .unwrap()
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}
#[test]
fn python_home_refusal_bytes_and_no_target_writes() {
    let cases: serde_json::Value =
        serde_json::from_str(include_str!("fixtures/executor_admission.json")).unwrap();
    for case in cases.as_array().unwrap() {
        let fixture = Fixture::new();
        fs::write(fixture.0.join("home/tools/mir_executor/local.py"), "def authorize_target(home, target, args):\n assert args.subcommand\n raise RuntimeError('fixture refusal')\n").unwrap();
        let command = case["command"].as_str().unwrap();
        let mut argv = vec![
            command.into(),
            "--repo-root".into(),
            fixture.0.join("target").to_str().unwrap().into(),
        ];
        if ["status", "result", "cancel"].contains(&command) {
            argv.extend(["--job-id".into(), "fixture".into()])
        }
        let expected = case["stderr"].as_str().unwrap().to_owned();
        let expected = expand(&expected, &fixture.0, false);
        assert_refusal(
            fixture.run(&argv, &fixture.0.join("home")),
            Admission::Refused {
                code: 1,
                stderr: expected.into_bytes(),
            },
        );
        assert!(!fixture.0.join("target/tasks/jobs.db").exists());
    }
}
#[test]
fn same_home_cross_home_nested_package_and_non_git() {
    let fixture = Fixture::new();
    let home = fixture.0.join("home");
    let target = fixture.0.join("target");
    let argv = vec![
        "execute".into(),
        "--repo-root".into(),
        target.to_str().unwrap().into(),
    ];
    assert!(matches!(
        fixture.run(&argv, &target),
        Admission::Admitted {
            cross_target: false,
            ..
        }
    ));
    assert!(matches!(
        fixture.run(&argv, &home),
        Admission::Admitted {
            cross_target: true,
            ..
        }
    ));
    fs::write(
        home.join("tools/mir_executor/local.py"),
        "raise AssertionError('not Git package root')",
    )
    .unwrap();
    fs::create_dir_all(home.join("nested")).unwrap();
    assert!(matches!(
        fixture.run(&argv, &home.join("nested")),
        Admission::Admitted { .. }
    ));
    let absent = fixture.0.join("absent");
    let argv = vec![
        "execute".into(),
        "--repo-root".into(),
        absent.to_str().unwrap().into(),
    ];
    assert_refusal(
        fixture.run(&argv, &target),
        Admission::Refused {
            code: 1,
            stderr: format!(
                "[mir_executor] argument parse error: repo root is not a git repository: {}\n",
                absent.display()
            )
            .into_bytes(),
        },
    );
}
#[test]
fn authorization_count_matches_main_and_execute_preparation() {
    let fixture = Fixture::new();
    let home = fixture.0.join("home");
    fs::write(home.join("tools/mir_executor/local.py"), "def authorize_target(home, target, args):\n assert args.family == 'selected' and args.dispatch is True\n p=home/'calls'\n p.write_text(p.read_text()+'x' if p.exists() else 'x')\n").unwrap();
    let argv = vec![
        "execute".into(),
        "--family".into(),
        "selected".into(),
        "--dispatch".into(),
    ];
    assert!(matches!(
        fixture.run(&argv, &home),
        Admission::Admitted { .. }
    ));
    assert_eq!(fs::read_to_string(home.join("calls")).unwrap(), "xxx");
}
#[test]
fn python_admitted_argument_goldens() {
    let cases: serde_json::Value =
        serde_json::from_str(include_str!("fixtures/executor_admission_args.json")).unwrap();
    let fixture = Fixture::new();
    for case in cases.as_array().unwrap() {
        let argv: Vec<String> = case["argv"]
            .as_array()
            .unwrap()
            .iter()
            .map(|v| v.as_str().unwrap().into())
            .collect();
        let Admission::Admitted { args, .. } = fixture.run(&argv, &fixture.0.join("target")) else {
            panic!("expected admission: {argv:?}")
        };
        let expected: serde_json::Value = serde_json::from_str(&expand(
            &serde_json::to_string(&case["expected"]).unwrap(),
            &fixture.0,
            true,
        ))
        .unwrap();
        assert_eq!(args, expected, "{argv:?}");
    }
}

#[test]
fn python_local_hook_goldens_and_persistent_bridge() {
    let cases: serde_json::Value =
        serde_json::from_str(include_str!("fixtures/executor_local_admission.json")).unwrap();
    for case in cases.as_array().unwrap() {
        let fixture = Fixture::new();
        let home = fixture.0.join("home");
        let target = fixture.0.join("target");
        fs::create_dir_all(fixture.0.join("redirected")).unwrap();
        fs::write(
            target.join("tools/mir_executor/local.py"),
            case["source"].as_str().unwrap(),
        )
        .unwrap();
        fs::write(
            home.join("tools/mir_executor/local.py"),
            case["home_source"].as_str().unwrap(),
        )
        .unwrap();
        let argv = vec![
            "execute".into(),
            "--repo-root".into(),
            target.to_str().unwrap().into(),
        ];
        let result = fixture.run(&argv, &home);
        let expected = &case["expected"];
        if expected.get("code").is_some() {
            let Admission::Refused { code, stderr } = result else {
                panic!("expected refusal: {result:?}")
            };
            assert_eq!(code, expected["code"]);
            assert_eq!(
                String::from_utf8(stderr).unwrap(),
                expand(expected["stderr"].as_str().unwrap(), &fixture.0, false)
            );
        } else {
            let Admission::Admitted {
                root,
                args,
                mut bridge,
                cross_target,
                ..
            } = result
            else {
                panic!("expected admission: {result:?}")
            };
            assert_eq!(
                root.to_str().unwrap(),
                expand(expected["root"].as_str().unwrap(), &fixture.0, false)
            );
            assert_eq!(args["family"], expected["family"]);
            assert_eq!(args["dispatch"], expected["dispatch"]);
            assert_eq!(cross_target, root != home);
            assert!(
                bridge
                    .as_mut()
                    .unwrap()
                    .call(
                        "pre_execute",
                        vec![
                            serde_json::json!({"$type":"namespace","value":args}),
                            serde_json::json!({"$type":"path","value":target})
                        ],
                        serde_json::json!({})
                    )
                    .unwrap()["ok"]
                    .as_bool()
                    .unwrap()
            );
        }
        assert!(!target.join("tasks/jobs.db").exists());
    }
}

#[test]
fn local_options_and_import_failure_decline_without_hook_calls() {
    for source in [
        "def register_execute_options(parser): pass\ndef pre_execute(args, root): raise AssertionError('must not call')\n",
        "raise ImportError('fixture import error')\n",
    ] {
        let fixture = Fixture::new();
        fs::write(fixture.0.join("target/tools/mir_executor/local.py"), source).unwrap();
        assert!(matches!(
            fixture.run(&["execute".into()], &fixture.0.join("target")),
            Admission::Decline { code: 64, .. }
        ));
    }
}

#[test]
fn home_refusal_precedes_target_import() {
    let fixture = Fixture::new();
    fs::write(
        fixture.0.join("home/tools/mir_executor/local.py"),
        "def authorize_target(home, target, args): raise RuntimeError('home denied')\n",
    )
    .unwrap();
    fs::write(
        fixture.0.join("target/tools/mir_executor/local.py"),
        "raise AssertionError('target imported')\n",
    )
    .unwrap();
    assert!(matches!(
        fixture.run(&["execute".into()], &fixture.0.join("home")),
        Admission::Refused { code: 1, .. }
    ));
}

fn assert_refusal(actual: Admission, expected: Admission) {
    let Admission::Refused { code, stderr } = actual else {
        panic!("expected refusal: {actual:?}")
    };
    let Admission::Refused {
        code: expected_code,
        stderr: expected_stderr,
    } = expected
    else {
        panic!("invalid expectation")
    };
    assert_eq!((code, stderr), (expected_code, expected_stderr));
}

#[test]
fn admitted_bridge_keeps_the_pre_execute_module_snapshot() {
    let fixture = Fixture::new();
    let target = fixture.0.join("target");
    fs::write(target.join("tools/mir_executor/local.py"), "calls = 0\ndef pre_execute(args, root):\n global calls\n calls += 1\n args.family = str(calls)\ndef validate_brief(): return calls\n").unwrap();
    let Admission::Admitted {
        args, mut bridge, ..
    } = fixture.run(&["execute".into()], &target)
    else {
        panic!("expected admission")
    };
    assert_eq!(args["family"], "1");
    // Removing the source cannot affect the already imported module.
    fs::remove_file(target.join("tools/mir_executor/local.py")).unwrap();
    assert_eq!(
        bridge
            .as_mut()
            .unwrap()
            .call("validate_brief", vec![], serde_json::json!({}))
            .unwrap()["result"],
        1
    );
}

#[test]
fn query_commands_keep_local_bridge_without_running_pre_execute() {
    let fixture = Fixture::new();
    let target = fixture.0.join("target");
    fs::write(
        target.join("tools/mir_executor/local.py"),
        "def pre_execute(*args): raise AssertionError('execute only')\n",
    )
    .unwrap();
    for command in ["status", "result", "cancel", "sweep", "list-jobs"] {
        let mut argv = vec![command.into()];
        if ["status", "result", "cancel"].contains(&command) {
            argv.extend(["--job-id".into(), "fixture".into()]);
        }
        assert!(matches!(
            fixture.run(&argv, &target),
            Admission::Admitted {
                bridge: Some(_),
                ..
            }
        ));
    }
}

#[test]
fn pre_execute_preserves_invoking_cwd_for_an_explicit_root() {
    let fixture = Fixture::new();
    let home = fixture.0.join("home");
    fs::write(home.join("tools/mir_executor/local.py"), "from pathlib import Path\ndef pre_execute(args, root):\n assert Path.cwd() == root.parent / 'target'\n args.family = 'cwd preserved'\n").unwrap();
    let argv = vec![
        "execute".into(),
        "--repo-root".into(),
        home.to_str().unwrap().into(),
    ];
    let Admission::Admitted { args, .. } = fixture.run(&argv, &home) else {
        panic!("expected admission")
    };
    assert_eq!(args["family"], "cwd preserved");
}

// Fixtures are generated on POSIX hosts as `$scratch/<name>`; Python prints the
// platform separator, so expand them with the native one (escaped inside JSON).
fn expand(text: &str, root: &Path, json: bool) -> String {
    let escape = |value: &str| {
        if json {
            value.replace('\\', "\\\\")
        } else {
            value.to_owned()
        }
    };
    let root = escape(root.to_str().unwrap());
    let separator = escape(std::path::MAIN_SEPARATOR_STR);
    text.replace("$scratch/", &format!("{root}{separator}"))
        .replace("$scratch", &root)
}

#[test]
fn native_policy_duplicate_hook_fails_before_import() {
    let fixture = Fixture::new();
    let target = fixture.0.join("target");
    fs::create_dir_all(target.join("config")).unwrap();
    fs::write(
        target.join("config/mir-executor.local.json"),
        r#"{"native_policy":{"version":1,"target_admission":{}}}"#,
    )
    .unwrap();
    fs::write(
        target.join("tools/mir_executor/local.py"),
        "raise AssertionError('must not import')\ndef pre_execute(*args): pass\n",
    )
    .unwrap();
    let Admission::Refused { code, stderr } = fixture.run(&["execute".into()], &target) else {
        panic!("expected configuration refusal")
    };
    assert_eq!(code, 1);
    assert!(
        String::from_utf8(stderr)
            .unwrap()
            .contains("configuration error: pre_execute")
    );
}

#[test]
fn native_policy_computed_hook_fails_before_callback() {
    let fixture = Fixture::new();
    let target = fixture.0.join("target");
    fs::create_dir_all(target.join("config")).unwrap();
    fs::write(
        target.join("config/mir-executor.local.json"),
        r#"{"native_policy":{"version":1,"target_admission":{}}}"#,
    )
    .unwrap();
    fs::write(target.join("tools/mir_executor/local.py"), "def callback(*args): raise AssertionError('must not call')\nglobals()['pre_' + 'execute'] = callback\n").unwrap();
    // Library admission declines an untrusted hello; command admission owns the
    // same error finally. Neither invokes the computed callback.
    assert!(matches!(
        fixture.run(&["execute".into()], &target),
        Admission::Decline { code: 64, .. }
    ));
}
