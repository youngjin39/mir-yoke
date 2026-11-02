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
        // Python resolves the fixture root (for example /var -> /private/var on macOS).
        #[cfg(unix)]
        let root = fs::canonicalize(&root).unwrap();
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
        let expected = case["stderr"]
            .as_str()
            .unwrap()
            .replace("$scratch", fixture.0.to_str().unwrap());
        assert_eq!(
            fixture.run(&argv, &fixture.0.join("home")),
            Admission::Refused {
                code: 1,
                stderr: expected.into_bytes()
            }
        );
        assert!(!fixture.0.join("target/tasks/jobs.db").exists());
    }
}
#[test]
fn target_options_decline_before_home_hook_or_target_import() {
    let fixture = Fixture::new();
    for root in ["home", "target"] {
        fs::write(fixture.0.join(root).join("tools/mir_executor/local.py"), "raise AssertionError('must never import')\ndef register_execute_options(parser): pass\n").unwrap();
    }
    let argv = vec![
        "execute".into(),
        "--repo-root".into(),
        fixture.0.join("target").to_str().unwrap().into(),
    ];
    assert!(matches!(
        fixture.run(&argv, &fixture.0.join("home")),
        Admission::Decline { code: 64, .. }
    ));
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
    assert_eq!(
        fixture.run(&argv, &target),
        Admission::Refused {
            code: 1,
            stderr: format!(
                "[mir_executor] ValueError: repo root is not a git repository: {}\n",
                absent.display()
            )
            .into_bytes()
        }
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
        let expected: serde_json::Value =
            serde_json::from_str(&serde_json::to_string(&case["expected"]).unwrap().replace(
                "$scratch",
                &fixture.0.to_str().unwrap().replace('\\', "\\\\"),
            ))
            .unwrap();
        assert_eq!(args, expected, "{argv:?}");
    }
}
