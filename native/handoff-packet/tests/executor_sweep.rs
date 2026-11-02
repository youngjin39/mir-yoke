//! Dynamic Python parity using disposable real Git trees and private ledgers.
use handoff_packet::executor_sweep;
use serde_json::{Value, json};
use std::{
    fs,
    path::{Path, PathBuf},
    process::Command,
};

const NOW: &str = "2026-07-11T00:03:01+00:00";
struct Fixture(PathBuf);
impl Fixture {
    fn new(name: &str) -> Self {
        static NEXT: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
        let root = std::env::var_os("MIR_NATIVE_TEST_SCRATCH")
            .map(PathBuf::from)
            .unwrap_or_else(std::env::temp_dir)
            .join(format!(
                "e11-{}-{}-{name}",
                std::process::id(),
                NEXT.fetch_add(1, std::sync::atomic::Ordering::Relaxed)
            ));
        fs::create_dir_all(&root).unwrap();
        // Ordinary Windows paths, matching supply::plain.
        let out = Command::new(python())
            .args([
                "-c",
                "from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve())",
            ])
            .arg(root)
            .output()
            .unwrap();
        assert!(out.status.success());
        Self(PathBuf::from(String::from_utf8(out.stdout).unwrap().trim()))
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
            let out = Command::new(name)
                .args(["-c", "import sys; print(sys.executable)"])
                .output()
                .ok()?;
            out.status
                .success()
                .then(|| PathBuf::from(String::from_utf8(out.stdout).unwrap().trim()))
        })
        .expect("Python is required for the oracle")
}
fn reference(mode: &str, root: &Path, case: &str, args: &[&str]) -> Value {
    let out = Command::new(python())
        .arg(
            Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/generate_executor_sweep.py"),
        )
        .arg(mode)
        .arg(root)
        .arg(case)
        .args(args)
        .env("PYTHONDONTWRITEBYTECODE", "1")
        .env("GIT_OPTIONAL_LOCKS", "0")
        .output()
        .unwrap();
    assert!(
        out.status.success(),
        "{mode} {case}: {}",
        String::from_utf8_lossy(&out.stderr)
    );
    serde_json::from_slice(&out.stdout).unwrap()
}
fn normalize(value: Value, root: &Path) -> Value {
    match value {
        Value::String(s) => json!(s.replace(root.to_str().unwrap(), "$ROOT")),
        Value::Array(a) => Value::Array(a.into_iter().map(|v| normalize(v, root)).collect()),
        Value::Object(o) => Value::Object(
            o.into_iter()
                .map(|(k, v)| (k, normalize(v, root)))
                .collect(),
        ),
        v => v,
    }
}
fn run_native(root: &Path, case: &str, apply: bool) -> Value {
    let repo = root.join("repo");
    let db = root.join("jobs.db");
    let result = if case.starts_with("run") || case == "missing-db" {
        executor_sweep::sweep_run_state(&repo, &db, NOW, 120, apply)
    } else {
        executor_sweep::sweep_terminal_artifacts(&repo, &db, NOW, 30, apply)
    };
    normalize(result.unwrap_or_else(|e| panic!("{case}: {e}")), root)
}
fn parity(case: &str, apply: bool) {
    let fixture = Fixture::new(case);
    let py = fixture.0.join("python");
    let native = fixture.0.join("native");
    reference("setup", &py, case, &[]);
    reference("setup", &native, case, &[]);
    let before = reference("snapshot", &native, case, &["raw"]);
    #[cfg(windows)]
    if native.join("fixture-junction.json").exists() {
        // Python's unchanged is_symlink checks do not recognize junctions.
        // Assert the native conservative reparse-point extension separately.
        let result = run_native(&native, case, apply);
        assert_eq!(
            fs::read_to_string(native.join("outside/sentinel")).unwrap(),
            "preserve\n"
        );
        if case == "artifact-root-link" {
            assert_eq!(result["errors"], json!(["artifact root is a symlink"]));
            assert!(native.join("repo/tasks/dispatch").is_dir());
        } else {
            assert!(
                native
                    .join("repo/tasks/dispatch")
                    .join("2".repeat(32))
                    .is_dir()
            );
            assert!(
                !result["removed"]
                    .as_array()
                    .unwrap()
                    .contains(&json!("2".repeat(32)))
            );
        }
        if !apply {
            assert_eq!(reference("snapshot", &native, case, &["raw"]), before);
        }
        return;
    }
    let expected = reference("oracle", &py, case, &[if apply { "true" } else { "false" }]);
    assert_eq!(
        run_native(&native, case, apply),
        expected,
        "{case}, apply={apply}: report"
    );
    assert_eq!(
        reference("snapshot", &native, case, &[]),
        reference("snapshot", &py, case, &[]),
        "{case}, apply={apply}: tree, refs, complete job records and receipts"
    );
    if !apply {
        assert_eq!(
            reference("snapshot", &native, case, &["raw"]),
            before,
            "{case}: dry run changed database, worktree or Git bytes"
        );
    }
    if apply {
        let expected = reference("oracle", &py, case, &["true"]);
        assert_eq!(
            run_native(&native, case, true),
            expected,
            "{case}: repeat report"
        );
        assert_eq!(
            reference("snapshot", &native, case, &[]),
            reference("snapshot", &py, case, &[]),
            "{case}: repeat preserves history and avoids duplicate receipts"
        );
    }
}
#[test]
fn run_state_dynamic_python_oracle() {
    // Includes strict deadline boundary, live/stale jobs, dirt, ignored runtime,
    // unique commits, safe removal and real Git worktree lock refusal.
    parity("run-mixed", false);
    parity("run-mixed", true);
}
#[test]
fn terminal_artifacts_dynamic_python_oracle() {
    for case in [
        "artifact-history",
        "artifact-receipt",
        "artifact-link",
        "artifact-root-link",
    ] {
        parity(case, false);
        parity(case, true);
    }
}
#[test]
fn missing_ledger_dry_run_does_not_create_storage() {
    parity("missing-db", false);
}
#[test]
fn run_state_reinspection_preserves_late_dirt() {
    let fixture = Fixture::new("drift");
    let py = fixture.0.join("python");
    let native = fixture.0.join("native");
    for root in [&py, &native] {
        reference("setup", root, "run-mixed", &[]);
    }
    let expected = reference("oracle", &py, "run-mixed", &["true", "drift"]);
    let actual = executor_sweep::sweep_run_state_with_observer(
        &native.join("repo"),
        &native.join("jobs.db"),
        NOW,
        120,
        true,
        |stage, path| {
            if stage == "before-reinspect" && path.file_name().is_some_and(|n| n == "wt-clean") {
                fs::write(path.join("late.txt"), "late\n").unwrap();
            }
            Ok(())
        },
    )
    .unwrap();
    assert_eq!(normalize(actual, &native), expected);
    assert_eq!(
        reference("snapshot", &native, "run-mixed", &[]),
        reference("snapshot", &py, "run-mixed", &[])
    );
}
#[test]
fn artifact_receipt_survives_interruption_and_recovery_reuses_it() {
    let fixture = Fixture::new("crash");
    let py = fixture.0.join("python");
    let native = fixture.0.join("native");
    for root in [&py, &native] {
        reference("setup", root, "artifact-history", &[]);
    }
    let expected = reference("oracle", &py, "artifact-history", &["true", "crash"]);
    assert_eq!(expected, json!({"crash":"injected crash"}));
    let error = executor_sweep::sweep_terminal_artifacts_with_observer(
        &native.join("repo"),
        &native.join("jobs.db"),
        NOW,
        30,
        true,
        |stage, _| {
            if stage == "after-receipt" {
                Err("injected crash".into())
            } else {
                Ok(())
            }
        },
    )
    .unwrap_err();
    assert!(error.contains("injected crash"));
    assert_eq!(
        reference("snapshot", &native, "artifact-history", &[]),
        reference("snapshot", &py, "artifact-history", &[]),
        "interruption must leave intent receipt and directory intact"
    );
    let expected = reference("oracle", &py, "artifact-history", &["true"]);
    assert_eq!(run_native(&native, "artifact-history", true), expected);
    assert_eq!(
        reference("snapshot", &native, "artifact-history", &[]),
        reference("snapshot", &py, "artifact-history", &[]),
        "recovery reuses durable intent rather than inserting duplicate receipts"
    );
}
#[test]
fn negative_retention_is_rejected_without_mutation() {
    let fixture = Fixture::new("negative");
    reference("setup", &fixture.0, "artifact-history", &[]);
    let before = reference("snapshot", &fixture.0, "artifact-history", &["raw"]);
    assert!(
        executor_sweep::sweep_terminal_artifacts(
            &fixture.0.join("repo"),
            &fixture.0.join("jobs.db"),
            NOW,
            -1,
            true
        )
        .is_err()
    );
    assert_eq!(
        reference("snapshot", &fixture.0, "artifact-history", &["raw"]),
        before
    );
}

#[test]
fn receipt_timestamp_normalizes_z_offset_and_naive_input_like_python() {
    for now in [
        "2026-11-02T12:00:00Z",
        "2026-11-02T13:00:00+01:00",
        "2026-11-02T12:00:00",
    ] {
        let fixture = Fixture::new("timestamp");
        let py = fixture.0.join("python");
        let native = fixture.0.join("native");
        for root in [&py, &native] {
            reference("setup", root, "artifact-history", &[]);
        }
        let expected = reference("oracle", &py, "artifact-history", &["true", "", now]);
        let actual = executor_sweep::sweep_terminal_artifacts(
            &native.join("repo"),
            &native.join("jobs.db"),
            now,
            30,
            true,
        )
        .unwrap();
        assert_eq!(normalize(actual, &native), expected);
        let actual = reference("snapshot", &native, "artifact-history", &[]);
        assert_eq!(
            actual["rows"]["artifact_sweeps"][0]["swept_at"], "2026-11-02T12:00:00+00:00",
            "{now}"
        );
        assert_eq!(
            actual,
            reference("snapshot", &py, "artifact-history", &[]),
            "{now}"
        );
    }
}

#[test]
fn open_artifact_handle_obeys_platform_deletion_semantics() {
    let fixture = Fixture::new("open-handle");
    reference("setup", &fixture.0, "artifact-history", &[]);
    let target = fixture.0.join("repo/tasks/dispatch").join("1".repeat(32));
    let path = target.join("nested/data.txt");
    #[cfg(not(windows))]
    let _open = fs::File::open(&path).unwrap();
    #[cfg(windows)]
    let _open = {
        use std::os::windows::fs::OpenOptionsExt;
        fs::OpenOptions::new()
            .read(true)
            .share_mode(1)
            .open(&path)
            .unwrap()
    };
    let result = executor_sweep::sweep_terminal_artifacts(
        &fixture.0.join("repo"),
        &fixture.0.join("jobs.db"),
        NOW,
        30,
        true,
    )
    .unwrap();
    #[cfg(not(windows))]
    {
        assert!(!target.exists());
        assert_eq!(
            result["errors"],
            json!([format!("unparseable completed_at for {}", "7".repeat(32))])
        );
    }
    #[cfg(windows)]
    {
        assert!(target.exists());
        assert!(
            result["errors"]
                .as_array()
                .unwrap()
                .iter()
                .any(|e| e.as_str().unwrap().starts_with("remove 1111"))
        );
    }
    let snapshot = reference("snapshot", &fixture.0, "artifact-history", &[]);
    assert!(
        snapshot["rows"]["artifact_sweeps"]
            .as_array()
            .unwrap()
            .iter()
            .any(|r| r["job_id"] == "1".repeat(32) && r["files"] == 1 && r["bytes"] == 6)
    );
}

#[cfg(any(unix, windows))]
#[test]
fn artifact_shape_change_after_receipt_preserves_link_target() {
    let fixture = Fixture::new("shape-change");
    reference("setup", &fixture.0, "artifact-history", &[]);
    let outside = fixture.0.join("outside");
    fs::create_dir(&outside).unwrap();
    fs::write(outside.join("sentinel"), "keep\n").unwrap();
    let mut changed = false;
    let result = executor_sweep::sweep_terminal_artifacts_with_observer(
        &fixture.0.join("repo"),
        &fixture.0.join("jobs.db"),
        NOW,
        30,
        true,
        |stage, path| {
            if stage == "after-receipt" && !changed {
                fs::remove_dir_all(path).unwrap();
                #[cfg(unix)]
                std::os::unix::fs::symlink(&outside, path).unwrap();
                #[cfg(windows)]
                reference("link", path, outside.to_str().unwrap(), &[]);
                changed = true;
            }
            Ok(())
        },
    )
    .unwrap();
    assert!(changed);
    assert_eq!(
        fs::read_to_string(outside.join("sentinel")).unwrap(),
        "keep\n"
    );
    assert!(
        result["errors"]
            .as_array()
            .unwrap()
            .iter()
            .any(|v| v.as_str().unwrap().contains("shape changed before removal"))
    );
    let snapshot = reference("snapshot", &fixture.0, "artifact-history", &[]);
    assert_eq!(
        snapshot["rows"]["artifact_sweeps"]
            .as_array()
            .unwrap()
            .len(),
        3
    );
}
