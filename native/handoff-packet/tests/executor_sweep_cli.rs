//! Process-level sweep parity on disposable repositories.
use std::{
    fs,
    path::PathBuf,
    process::{Command, Output},
};

#[cfg(windows)]
#[path = "support/executor_text.rs"]
mod executor_text;

struct Fixture(PathBuf);
impl Fixture {
    fn new() -> Self {
        static NEXT: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
        let root = std::env::var_os("MIR_NATIVE_TEST_SCRATCH")
            .map(PathBuf::from)
            .unwrap_or_else(std::env::temp_dir)
            .join(format!(
                "e12b-sweep-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, std::sync::atomic::Ordering::Relaxed)
            ));
        fs::create_dir_all(&root).unwrap();
        // Resolve filesystem aliases before setup, including macOS firmlinks
        // that pathlib.resolve does not collapse. Keep ordinary Windows paths.
        let output = Command::new(python())
            .args([
                "-c",
                "from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve())",
            ])
            .arg(fs::canonicalize(root).unwrap())
            .output()
            .unwrap();
        assert!(output.status.success());
        // SQLite URI mode treats a verbatim drive prefix as authority "%3F".
        Self(handoff_packet::supply::plain(PathBuf::from(
            String::from_utf8(output.stdout).unwrap().trim(),
        )))
    }
    fn repo(&self) -> PathBuf {
        self.0.join("repo")
    }
    fn native(&self, args: &[&str]) -> Output {
        let mut command = Command::new(env!("CARGO_BIN_EXE_executor-query"));
        windows_path_only(&mut command);
        command
            .arg("--home-root")
            .arg(self.repo())
            .args(args)
            .current_dir(self.repo())
            .env("MIR_EXECUTOR_OWNED_RECEIPT", self.0.join("receipt"))
            .env(
                "MIR_EXECUTOR_DECLINE_TRACE",
                self.0.join("decline-trace.log"),
            )
            .output()
            .unwrap()
    }
    fn setup(&self) {
        let out = Command::new(python())
            .args(["-c", SETUP])
            .arg(env!("CARGO_MANIFEST_DIR"))
            .arg(&self.0)
            .env("PYTHONDONTWRITEBYTECODE", "1")
            .output()
            .unwrap();
        assert!(
            out.status.success(),
            "{}",
            String::from_utf8_lossy(&out.stderr)
        );
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        if std::thread::panicking() {
            eprintln!(
                "native decline trace ({}):\n{}",
                self.0.join("decline-trace.log").display(),
                fs::read_to_string(self.0.join("decline-trace.log"))
                    .unwrap_or_else(|_| "<no declines>".into())
            );
        }
        let _ = fs::remove_dir_all(&self.0);
    }
}
fn python() -> PathBuf {
    ["python3", "python"]
        .into_iter()
        .find_map(|name| {
            let output = Command::new(name)
                .args(["-c", "import sys; print(sys.executable)"])
                .output()
                .ok()?;
            output
                .status
                .success()
                .then(|| PathBuf::from(String::from_utf8(output.stdout).unwrap().trim()))
        })
        .expect("Python fixture setup required")
}
const SETUP: &str = r#"
import importlib.util, pathlib, sys
crate, root = map(pathlib.Path, sys.argv[1:])
spec = importlib.util.spec_from_file_location('fixture', crate / 'tests' / 'fixtures' / 'generate_executor_sweep.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
fixture.setup(root, 'artifact')
"#;
fn normalize(value: serde_json::Value, root: &std::path::Path) -> serde_json::Value {
    match value {
        serde_json::Value::String(s) => {
            // Match cc468eee's generator: only synthetic root/path aliases.
            let plain = |path: &str| {
                let path = path.replace('\\', "/");
                match path.strip_prefix("//?/") {
                    Some(candidate) if candidate.as_bytes().get(1..3) == Some(b":/") => {
                        candidate.to_owned()
                    }
                    _ => path,
                }
            };
            let root = plain(root.to_str().unwrap());
            let candidate = plain(&s);
            serde_json::json!(if candidate == root {
                "$ROOT".to_owned()
            } else if let Some(tail) = candidate.strip_prefix(&(root + "/")) {
                format!("$ROOT/{tail}")
            } else {
                s
            })
        }
        serde_json::Value::Array(a) => {
            serde_json::Value::Array(a.into_iter().map(|v| normalize(v, root)).collect())
        }
        serde_json::Value::Object(o) => serde_json::Value::Object(
            o.into_iter()
                .map(|(k, v)| {
                    (
                        k.clone(),
                        if k == "swept_at" {
                            serde_json::json!("$NOW")
                        } else {
                            normalize(v, root)
                        },
                    )
                })
                .collect(),
        ),
        v => v,
    }
}
#[test]
fn normalize_only_synthetic_root_aliases() {
    for root in [r"C:\fixture", r"\\?\C:\fixture"] {
        for (input, expected) in [
            (r"C:\fixture", "$ROOT"),
            (r"\\?\C:\fixture\repo\job", "$ROOT/repo/job"),
            (r"C:\fixture\repo\job", "$ROOT/repo/job"),
            ("C:/fixture/repo/job", "$ROOT/repo/job"),
            (r"C:\fixture-other\job", r"C:\fixture-other\job"),
            (r"prefix C:\fixture\job", r"prefix C:\fixture\job"),
            (r"D:\elsewhere\job", r"D:\elsewhere\job"),
        ] {
            assert_eq!(
                normalize(serde_json::json!(input), std::path::Path::new(root)),
                serde_json::json!(expected),
                "root={root:?}, input={input:?}"
            );
        }
    }
}
fn parity(apply: bool) {
    let fixture = Fixture::new();
    fixture.setup();
    let corpus: serde_json::Value =
        serde_json::from_str(include_str!("fixtures/g6/sweep.json")).unwrap();
    let expected = &corpus["cli"][apply.to_string()];
    let db = fixture.0.join("jobs.db");
    let mut args = vec!["sweep", "--jobs-db", db.to_str().unwrap()];
    if apply {
        args.push("--apply");
    }
    let native = fixture.native(&args);
    assert_eq!(
        native.status.code(),
        expected["status"].as_i64().map(|v| v as i32),
        "{}",
        String::from_utf8_lossy(&native.stderr)
    );
    #[cfg(windows)]
    let windows_record = executor_text::record("sweep", &apply.to_string());
    #[cfg(windows)]
    assert_eq!(
        native.status.code(),
        windows_record["exit"].as_i64().map(|v| v as i32)
    );
    #[cfg(windows)]
    let expected_stderr = executor_text::bytes(&windows_record, "stderr");
    #[cfg(not(windows))]
    let expected_stderr = expected["stderr"].as_str().unwrap().as_bytes();
    assert_eq!(
        native.stderr, expected_stderr,
        "sweep stderr bytes, apply={apply}"
    );
    assert_eq!(native.stdout.iter().filter(|b| **b == b'\n').count(), 1);
    let escaped_root = fixture.0.to_str().unwrap().replace('\\', "\\\\");
    let stdout = String::from_utf8(native.stdout.clone())
        .unwrap()
        .replace(&escaped_root, "$ROOT");
    #[cfg(windows)]
    let expected_stdout = executor_text::bytes(&windows_record, "stdout");
    #[cfg(not(windows))]
    let expected_stdout = expected["stdout"].as_str().unwrap().as_bytes();
    assert_eq!(
        stdout.as_bytes(),
        expected_stdout,
        "sweep stdout bytes, apply={apply}"
    );
    let result = serde_json::from_slice(&native.stdout).unwrap();
    assert_eq!(normalize(result, &fixture.0), expected["result"]);
    assert_eq!(fs::read(fixture.0.join("receipt")).unwrap(), b"owned");
    // The ownership receipt is a caller transport effect, separate from sweep effects.
    fs::remove_file(fixture.0.join("receipt")).unwrap();
    let snapshot = Command::new(python())
        .arg(
            std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
                .join("tests/fixtures/generate_executor_sweep.py"),
        )
        .arg("snapshot")
        .arg(&fixture.0)
        .arg("artifact")
        .env("PYTHONDONTWRITEBYTECODE", "1")
        .output()
        .unwrap();
    assert!(snapshot.status.success(), "snapshot: {snapshot:?}");
    assert_eq!(
        normalize(
            serde_json::from_slice(&snapshot.stdout).unwrap(),
            &fixture.0
        ),
        expected["state"]
    );
}
#[test]
fn dry_run_matches_frozen_python_result() {
    parity(false);
}
#[test]
fn apply_composes_native_library() {
    parity(true);
}
#[test]
fn unsupported_declines_without_receipt_or_output() {
    let fixture = Fixture::new();
    fixture.setup();
    for args in [
        vec!["sweep", "--unknown"],
        vec!["sweep", "--retention-days", "1"],
        vec!["sweep", "--grace-seconds", "9999999999999999999999999999"],
    ] {
        let output = fixture.native(&args);
        assert_eq!(output.status.code(), Some(64));
        assert!(output.stdout.is_empty());
        assert!(output.stderr.is_empty());
        assert!(!fixture.0.join("receipt").exists());
    }
}
#[test]
fn local_hook_declines_before_import() {
    let fixture = Fixture::new();
    fixture.setup();
    let local = fixture.repo().join("tools").join("mir_executor");
    fs::create_dir_all(&local).unwrap();
    fs::write(
        local.join("local.py"),
        "def register_execute_options(parser):\n    raise RuntimeError('must not import')\n",
    )
    .unwrap();
    let output = fixture.native(&["sweep"]);
    assert_eq!(output.status.code(), Some(64));
    assert!(!fixture.0.join("receipt").exists());
}

#[test]
fn stock_local_import_uses_bridge_after_receipt_without_execution_hooks() {
    let fixture = Fixture::new();
    fixture.setup();
    let local = fixture.repo().join("tools").join("mir_executor");
    fs::create_dir_all(&local).unwrap();
    fs::write(local.join("local.py"), "def validate_brief(brief, repo_root):\n    raise RuntimeError('sweep must not call this')\n").unwrap();
    fs::write(local.join("local_bridge.py"), r#"
import json, os, pathlib, runpy, sys
root = pathlib.Path(sys.argv[1])
assert pathlib.Path(os.environ['MIR_EXECUTOR_OWNED_RECEIPT']).read_bytes() == b'owned'
runpy.run_path(str(root / 'tools' / 'mir_executor' / 'local.py'))
(root / 'imported').write_text('once', encoding='utf-8')
print(json.dumps(dict(version='mir-executor.local@1', hooks=['validate_brief'], register_execute_options=False)), flush=True)
for line in sys.stdin:
    raise RuntimeError('sweep must not invoke hooks')
"#).unwrap();
    let output = fixture.native(&["sweep"]);
    assert_eq!(
        output.status.code(),
        Some(0),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert!(output.stderr.is_empty());
    assert_eq!(fs::read(fixture.repo().join("imported")).unwrap(), b"once");
}

#[test]
fn missing_ledger_dry_run_and_apply_ownership() {
    let fixture = Fixture::new();
    fixture.setup();
    let db = fixture.repo().join("tasks").join("jobs.db");
    assert!(!db.exists());
    assert_eq!(fixture.native(&["sweep"]).status.code(), Some(0));
    assert!(!db.exists());
    assert_eq!(fixture.native(&["sweep", "--apply"]).status.code(), Some(0));
    assert!(db.exists());
}

#[test]
fn failed_ownership_receipt_prevents_registry_creation() {
    let fixture = Fixture::new();
    fixture.setup();
    fs::create_dir(fixture.0.join("receipt")).unwrap();
    let output = fixture.native(&["sweep", "--apply"]);
    assert_eq!(output.status.code(), Some(64));
    assert!(output.stdout.is_empty());
    assert!(output.stderr.is_empty());
    assert!(!fixture.repo().join("tasks").join("jobs.db").exists());
}

#[test]
fn invalid_config_and_ledger_decline_without_receipt() {
    let fixture = Fixture::new();
    fixture.setup();
    let config = fixture.repo().join("config");
    fs::create_dir_all(&config).unwrap();
    let config = config.join("mir-executor.local.json");
    fs::write(&config, r#"{"artifact_retention_days":true}"#).unwrap();
    assert_eq!(fixture.native(&["sweep"]).status.code(), Some(64));
    assert!(!fixture.0.join("receipt").exists());
    fs::remove_file(config).unwrap();
    let db = fixture.0.join("invalid.db");
    fs::write(&db, "not sqlite").unwrap();
    assert_eq!(
        fixture
            .native(&["--jobs-db", db.to_str().unwrap(), "sweep"])
            .status
            .code(),
        Some(64)
    );
    assert!(!fixture.0.join("receipt").exists());
}

#[cfg(unix)]
#[test]
fn parent_alias_resolves_but_final_database_symlink_declines() {
    let fixture = Fixture::new();
    fixture.setup();
    let alias = fixture.0.join("parent-alias");
    std::os::unix::fs::symlink(&fixture.0, &alias).unwrap();
    let database = alias.join("jobs.db");
    let repo = alias.join("repo");
    let worktree = Command::new("git")
        .arg("-C")
        .arg(fixture.repo())
        .args(["worktree", "add", "-q", "-b", "mir-dispatch/orphan"])
        .arg(alias.join("orphan"))
        .arg("HEAD")
        .output()
        .unwrap();
    assert!(
        worktree.status.success(),
        "{}",
        String::from_utf8_lossy(&worktree.stderr)
    );
    let output = fixture.native(&[
        "sweep",
        "--repo-root",
        repo.to_str().unwrap(),
        "--jobs-db",
        database.to_str().unwrap(),
    ]);
    assert_eq!(output.status.code(), Some(0));
    assert!(output.stderr.is_empty());
    let payload: serde_json::Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(
        payload["orphan_worktrees"],
        serde_json::json!([fixture.0.join("orphan")])
    );
    assert!(
        !String::from_utf8(output.stdout)
            .unwrap()
            .contains("parent-alias")
    );
    fs::remove_file(fixture.0.join("receipt")).unwrap();
    let linked = fixture.0.join("linked.db");
    std::os::unix::fs::symlink(fixture.0.join("jobs.db"), &linked).unwrap();
    let output = fixture.native(&["sweep", "--jobs-db", linked.to_str().unwrap()]);
    assert_eq!(output.status.code(), Some(64));
    assert!(output.stdout.is_empty());
    assert!(output.stderr.is_empty());
    assert!(!fixture.0.join("receipt").exists());
}

fn windows_path_only(command: &mut Command) {
    #[cfg(windows)]
    {
        let path = std::env::var_os("PATH").or_else(|| std::env::var_os("Path"));
        command.env_remove("MIR_EXECUTOR_PYTHON").env_remove("PATH");
        if let Some(path) = path {
            command.env("Path", path);
        }
    }
    #[cfg(not(windows))]
    let _ = command;
}

#[test]
fn cross_root_policy_admission_and_legacy_decline() {
    let fixture = Fixture::new();
    fixture.setup();
    let home = fixture.0.join("home");
    fs::create_dir_all(home.join("config")).unwrap();
    assert!(
        Command::new("git")
            .args(["init", "-q"])
            .arg(&home)
            .status()
            .unwrap()
            .success()
    );
    let run = |cwd: &std::path::Path| {
        Command::new(env!("CARGO_BIN_EXE_executor-query"))
            .arg("--home-root")
            .arg(&home)
            .args(["sweep", "--repo-root"])
            .arg(fixture.repo())
            .args(["--jobs-db"])
            .arg(fixture.0.join("jobs.db"))
            .current_dir(cwd)
            .output()
            .unwrap()
    };
    assert_eq!(run(&fixture.repo()).status.code(), Some(64));
    fs::write(home.join("config/mir-executor.local.json"), r#"{"native_policy":{"version":1,"target_admission":{"authorize_target":true,"family":{"mode":"reject","failure":{"kind":"ValueError","message":"no families"}},"repository_local":{"kind":"ValueError","message":"current Git root only"}}}}"#).unwrap();
    let admitted = run(&fixture.repo());
    assert_eq!(
        admitted.status.code(),
        Some(0),
        "{}",
        String::from_utf8_lossy(&admitted.stderr)
    );
    let refused = run(&home);
    assert_eq!(refused.status.code(), Some(1));
    assert_eq!(
        String::from_utf8(refused.stderr).unwrap(),
        format!(
            "[mir_executor] authorize_target refused {}: ValueError: current Git root only\n",
            handoff_packet::supply::plain(fixture.repo()).display()
        )
        .replace('\n', if cfg!(windows) { "\r\n" } else { "\n" })
    );
}

#[test]
fn family_option_still_declines_before_effects() {
    let fixture = Fixture::new();
    fixture.setup();
    let output = fixture.native(&["sweep", "--family", "rejected"]);
    assert_eq!(output.status.code(), Some(64));
    assert!(output.stdout.is_empty());
    assert!(!fixture.0.join("receipt").exists());
}
