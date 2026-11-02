//! Process-level sweep parity on disposable repositories.
use std::{
    fs,
    path::PathBuf,
    process::{Command, Output},
};

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
        // Match pathlib.resolve, including ordinary Windows paths and Unix
        // aliases such as the platform temporary-directory prefix.
        let output = Command::new(python())
            .args([
                "-c",
                "from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve())",
            ])
            .arg(root)
            .output()
            .unwrap();
        assert!(output.status.success());
        Self(PathBuf::from(
            String::from_utf8(output.stdout).unwrap().trim(),
        ))
    }
    fn repo(&self) -> PathBuf {
        self.0.join("repo")
    }
    fn native(&self, args: &[&str]) -> Output {
        Command::new(env!("CARGO_BIN_EXE_executor-query"))
            .arg("--home-root")
            .arg(self.repo())
            .args(args)
            .current_dir(self.repo())
            .env("MIR_EXECUTOR_OWNED_RECEIPT", self.0.join("receipt"))
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
        .expect("Python oracle required")
}
const SETUP: &str = r#"
import importlib.util, pathlib, sys
crate, root = map(pathlib.Path, sys.argv[1:])
spec = importlib.util.spec_from_file_location('fixture', crate / 'tests' / 'fixtures' / 'generate_executor_sweep.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
fixture.setup(root, 'artifact')
"#;
const ORACLE: &str = r#"
import json, pathlib, sys
crate, root = map(pathlib.Path, sys.argv[1:3])
sys.path.insert(0, str(crate.parent.parent))
from tools.mir_executor.sweep import sweep_run_state, sweep_terminal_artifacts
repo, db = root / 'repo', root / 'jobs.db'
apply = len(sys.argv) > 3 and sys.argv[3] == 'apply'
result = sweep_run_state(repo, db, apply=apply)
result['terminal_artifacts'] = sweep_terminal_artifacts(repo, db, apply=apply)
print(json.dumps(result, separators=(',', ':')))
"#;
fn parity(apply: bool) {
    let fixture = Fixture::new();
    fixture.setup();
    let reference = Command::new(python())
        .args(["-c", ORACLE])
        .arg(env!("CARGO_MANIFEST_DIR"))
        .arg(&fixture.0)
        .env("PYTHONDONTWRITEBYTECODE", "1")
        .output()
        .unwrap();
    assert!(
        reference.status.success(),
        "{}",
        String::from_utf8_lossy(&reference.stderr)
    );
    let db = fixture.0.join("jobs.db");
    let native = fixture.native(&["sweep", "--jobs-db", db.to_str().unwrap()]);
    assert_eq!(native.status.code(), Some(0));
    assert_eq!(native.stdout, reference.stdout);
    assert_eq!(native.stderr, reference.stderr);
    assert_eq!(fs::read(fixture.0.join("receipt")).unwrap(), b"owned");
    if apply {
        let oracle = Fixture::new();
        oracle.setup();
        let oracle_output = Command::new(python())
            .args(["-c", ORACLE])
            .arg(env!("CARGO_MANIFEST_DIR"))
            .arg(&oracle.0)
            .arg("apply")
            .env("PYTHONDONTWRITEBYTECODE", "1")
            .output()
            .unwrap();
        assert!(
            oracle_output.status.success(),
            "{}",
            String::from_utf8_lossy(&oracle_output.stderr)
        );
        let expected: serde_json::Value = serde_json::from_slice(&reference.stdout).unwrap();
        let applied = fixture.native(&["sweep", "--apply", "--jobs-db", db.to_str().unwrap()]);
        assert_eq!(
            applied.status.code(),
            Some(0),
            "{}",
            String::from_utf8_lossy(&applied.stderr)
        );
        assert_eq!(applied.stdout, oracle_output.stdout);
        assert_eq!(applied.stderr, oracle_output.stderr);
        let result: serde_json::Value = serde_json::from_slice(&applied.stdout).unwrap();
        assert_eq!(
            result["terminal_artifacts"]["removed"],
            expected["terminal_artifacts"]["expired"]
        );
        assert!(
            !fixture
                .repo()
                .join("tasks")
                .join("dispatch")
                .join("1".repeat(32))
                .exists()
        );
    }
}
#[test]
fn dry_run_matches_python_bytes() {
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
