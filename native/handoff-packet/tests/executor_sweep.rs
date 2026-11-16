//! Frozen Python outputs and effects on disposable real Git trees and private ledgers.
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
        Self(handoff_packet::supply::plain(reference_path(
            &fs::canonicalize(root).unwrap(),
        )))
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
        .expect("Python is required for fixture setup and observation")
}
// Preserve pathlib's display spelling. Only fixture creation collapses aliases.
fn reference_path(path: &Path) -> PathBuf {
    let out = Command::new(python())
        .args([
            "-I",
            "-c",
            "from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve())",
        ])
        .arg(path)
        .output()
        .unwrap();
    assert!(out.status.success());
    PathBuf::from(String::from_utf8(out.stdout).unwrap().trim())
}
#[cfg(target_os = "macos")]
#[test]
fn reference_display_preserves_data_spelling() {
    let base = fs::canonicalize(reference_path(&std::env::temp_dir())).unwrap();
    let directory = tempfile::TempDir::new_in(base).unwrap();
    let physical = fs::canonicalize(directory.path()).unwrap();
    let data = Path::new("/System/Volumes/Data").join(physical.strip_prefix("/").unwrap());
    assert_eq!(reference_path(&data), data);
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
    let mut value: Value = serde_json::from_slice(&out.stdout).unwrap();
    if mode == "snapshot" && args.is_empty() && root.join("jobs.db").exists() {
        value["rows"]["artifact_sweeps"] = receipts(root);
    }
    value
}
fn receipts(root: &Path) -> Value {
    let db = rusqlite::Connection::open_with_flags(
        root.join("jobs.db"),
        rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY,
    )
    .unwrap();
    let mut stmt = db
        .prepare("SELECT job_id,path,files,bytes,swept_at FROM artifact_sweeps ORDER BY rowid")
        .unwrap();
    let rows = stmt
        .query_map([], |r| {
            Ok(json!({
                "job_id": r.get::<_, String>(0)?, "path": r.get::<_, String>(1)?,
                "files": r.get::<_, i64>(2)?, "bytes": r.get::<_, i64>(3)?,
                "swept_at": r.get::<_, String>(4)?,
            }))
        })
        .unwrap()
        .collect::<Result<Vec<_>, _>>()
        .unwrap();
    normalize(json!(rows), root)
}
// SQL equality requires retaining suffix separators and the verbatim prefix.
fn normalize(value: Value, root: &Path) -> Value {
    match value {
        Value::String(s) => {
            let root = root.to_str().unwrap();
            let root = root
                .strip_prefix(r"\\?\")
                .or_else(|| root.strip_prefix("//?/"))
                .unwrap_or(root);
            let (prefix, candidate) = if let Some(tail) = s.strip_prefix(r"\\?\") {
                (r"\\?\", tail)
            } else if let Some(tail) = s.strip_prefix("//?/") {
                ("//?/", tail)
            } else {
                ("", s.as_str())
            };
            for alias in [root.to_owned(), root.replace('\\', "/")] {
                if let Some(tail) = candidate.strip_prefix(&alias)
                    && (tail.is_empty() || tail.starts_with(['/', '\\']))
                {
                    return json!(format!("{prefix}$ROOT{tail}"));
                }
            }
            json!(s)
        }
        Value::Array(a) => Value::Array(a.into_iter().map(|v| normalize(v, root)).collect()),
        Value::Object(o) => Value::Object(
            o.into_iter()
                .map(|(k, v)| (k, normalize(v, root)))
                .collect(),
        ),
        v => v,
    }
}
fn normalize_display(value: Value, root: &Path) -> Value {
    match value {
        Value::String(s) => {
            let root = root.to_str().unwrap().replace('\\', "/");
            let plain = |path: &str| {
                let candidate = path.strip_prefix("//?/").unwrap_or(path);
                if candidate.as_bytes().get(1..3) == Some(b":/") {
                    candidate.to_owned()
                } else {
                    path.to_owned()
                }
            };
            let root = plain(&root);
            let candidate = plain(&s.replace('\\', "/"));
            json!(match candidate.strip_prefix(&root) {
                Some("") => "$ROOT".to_owned(),
                Some(tail) if tail.starts_with('/') => format!("$ROOT{tail}"),
                _ => s,
            })
        }
        Value::Array(a) => {
            Value::Array(a.into_iter().map(|v| normalize_display(v, root)).collect())
        }
        Value::Object(o) => Value::Object(
            o.into_iter()
                .map(|(k, v)| (k, normalize_display(v, root)))
                .collect(),
        ),
        v => v,
    }
}
#[test]
fn snapshot_root_aliases_are_bounded() {
    for root in [r"C:\scratch\native", r"\\?\C:\scratch\native"] {
        for alias in [
            r"C:\scratch\native",
            r"\\?\C:\scratch\native",
            "C:/scratch/native",
            "//?/C:/scratch/native",
        ] {
            let prefix = if alias.starts_with(r"\\?\") || alias.starts_with("//?/") {
                &alias[..4]
            } else {
                ""
            };
            assert_eq!(
                normalize(json!(format!(r"{alias}\wt-clean")), Path::new(root)),
                json!(format!("{prefix}$ROOT\\wt-clean"))
            );
            assert_ne!(
                normalize(json!(format!("{alias}/wt-clean")), Path::new(root)),
                normalize(json!(format!(r"{alias}\wt-clean")), Path::new(root))
            );
        }
        for outside in [
            r"C:\scratch\native-other\keep",
            r"D:\elsewhere\keep",
            r"literal $ROOT\keep",
        ] {
            assert_eq!(normalize(json!(outside), Path::new(root)), json!(outside));
        }
    }
    assert_eq!(
        normalize(
            json!("/scratch/native/wt-clean"),
            Path::new("/scratch/native")
        ),
        json!("$ROOT/wt-clean")
    );
}
fn run_native(root: &Path, case: &str, apply: bool) -> Value {
    let repo = root.join("repo");
    let db = root.join("jobs.db");
    let result = if case.starts_with("run") || case == "missing-db" {
        executor_sweep::sweep_run_state(&repo, &db, NOW, 120, apply)
    } else {
        executor_sweep::sweep_terminal_artifacts(&repo, &db, NOW, 30, apply)
    };
    normalize_display(result.unwrap_or_else(|e| panic!("{case}: {e}")), root)
}
fn golden(case: &str, apply: bool, seam: &str, now: &str, step: usize) -> Value {
    let corpus: Value = serde_json::from_str(include_str!("fixtures/g6/sweep.json")).unwrap();
    let expected = corpus["cases"][format!("{case}|{apply}|{seam}|{now}")][step].clone();
    platform_golden(expected, cfg!(windows))
}
fn platform_golden(mut expected: Value, windows: bool) -> Value {
    if windows
        && let Some(rows) = expected["state"]["rows"]
            .get_mut("artifact_sweeps")
            .and_then(Value::as_array_mut)
    {
        for row in rows {
            row["path"] = json!(row["path"].as_str().unwrap().replace('/', "\\"));
        }
    }
    expected
}
#[test]
fn windows_golden_preserves_missing_ledger_snapshot() {
    let corpus: Value = serde_json::from_str(include_str!("fixtures/g6/sweep.json")).unwrap();
    // Both pinned Windows captures equal this G6 record, including the absent key.
    let expected = corpus["cases"][format!("missing-db|false||{NOW}")][0].clone();
    assert_eq!(expected["state"]["rows"], json!({}));
    assert_eq!(platform_golden(expected.clone(), false), expected);
    assert_eq!(platform_golden(expected.clone(), true), expected);
    let receipts = corpus["cases"][format!("artifact-receipt|false||{NOW}")][0].clone();
    let windows = platform_golden(receipts.clone(), true);
    assert_eq!(
        windows["state"]["rows"]["artifact_sweeps"][0]["path"],
        json!(format!(r"$ROOT\repo\tasks\dispatch\{}", "1".repeat(32)))
    );
    assert_eq!(
        windows["state"]["rows"]["jobs"],
        receipts["state"]["rows"]["jobs"]
    );
}
fn p2_record(windows: bool, variant: &str, step: &str) -> Option<Value> {
    if !windows {
        return None;
    }
    let corpus: Value =
        serde_json::from_str(include_str!("fixtures/unify2_s3_sweep_windows.json")).unwrap();
    corpus["records"]
        .as_array()
        .unwrap()
        .iter()
        .find(|r| {
            r["variant"] == variant
                && r["name"] == format!("executor_sweep.artifact-receipt.{step}")
        })
        .cloned()
}
#[test]
fn p2_selector_keeps_platform_rows_and_verbatim_spelling() {
    assert!(p2_record(false, "ordinary/backslash/python", "apply-true").is_none());
    for (variant, count) in [
        ("ordinary/backslash/python", 3),
        ("ordinary/slash/python", 4),
        ("verbatim/backslash/python", 4),
        ("verbatim/slash/python", 4),
    ] {
        let r = p2_record(true, variant, "apply-true").unwrap();
        let rows = r["after_sql"]["artifact_sweeps"].as_array().unwrap();
        assert_eq!(rows.len(), count);
        assert_eq!(rows[0]["swept_at"], "2026-01-01T00:00:00+00:00");
        assert_eq!(
            rows[1]["path"].as_str().unwrap().starts_with(r"\\?\"),
            variant.starts_with("verbatim")
        );
    }
}
// Kept native difference: canonicalize + plain removes an explicit verbatim
// root. Backslash receipts are reused; slash receipts remain a distinct row.
fn p2_native_verbatim_rows(style: &str, applied: bool) -> Value {
    let first_path = if style == "slash" {
        format!("$ROOT/repo/tasks/dispatch/{}", "1".repeat(32))
    } else {
        format!(r"$ROOT\repo\tasks\dispatch\{}", "1".repeat(32))
    };
    let row = |path: String, swept_at: &str| {
        json!({
            "job_id": "1".repeat(32), "path": path, "files": 1, "bytes": 6,
            "swept_at": swept_at,
        })
    };
    let mut rows = vec![row(first_path, "2026-01-01T00:00:00+00:00")];
    if applied {
        for id in if style == "slash" { 1..=3 } else { 2..=3 } {
            rows.push(row(
                format!(r"$ROOT\repo\tasks\dispatch\{}", id.to_string().repeat(32)),
                NOW,
            ));
        }
    }
    json!(rows)
}
#[test]
fn p2_verbatim_native_contract_preserves_count_and_exact_spelling() {
    for (style, count) in [("backslash", 3), ("slash", 4)] {
        for step in ["apply-false", "apply-true", "apply-true-repeat"] {
            let applied = step != "apply-false";
            let native = p2_native_verbatim_rows(style, applied);
            assert_eq!(
                native.as_array().unwrap().len(),
                if applied { count } else { 1 }
            );
            let ordinary = p2_record(true, &format!("ordinary/{style}/python"), step).unwrap();
            let root = Path::new(ordinary["input"]["root_argument"].as_str().unwrap());
            assert_eq!(
                native,
                normalize(ordinary["after_sql"]["artifact_sweeps"].clone(), root)
            );
            let verbatim = p2_record(true, &format!("verbatim/{style}/python"), step).unwrap();
            let root = Path::new(verbatim["input"]["root_argument"].as_str().unwrap());
            let python = normalize(verbatim["after_sql"]["artifact_sweeps"].clone(), root);
            if applied {
                assert_ne!(native, python);
            } else {
                assert_eq!(native, python);
            }
        }
    }
}
#[cfg(windows)]
fn replay_p2(spelling: &str) {
    for style in ["backslash", "slash"] {
        let fixture = Fixture::new("p2");
        let root = &fixture.0;
        reference("setup", root, "artifact-receipt", &[]);
        let stored = root
            .join("repo")
            .join("tasks")
            .join("dispatch")
            .join("1".repeat(32));
        let stored = stored.to_str().unwrap();
        let stored = if style == "slash" {
            stored.replace('\\', "/")
        } else {
            stored.to_owned()
        };
        rusqlite::Connection::open(root.join("jobs.db"))
            .unwrap()
            .execute("UPDATE artifact_sweeps SET path=?1", [stored])
            .unwrap();
        let repo = if spelling == "verbatim" {
            PathBuf::from(format!(r"\\?\{}\repo", root.display()))
        } else {
            root.join("repo")
        };
        for (step, apply) in [
            ("apply-false", false),
            ("apply-true", true),
            ("apply-true-repeat", true),
        ] {
            let before = reference("snapshot", root, "artifact-receipt", &["raw"]);
            let r = p2_record(true, &format!("{spelling}/{style}/python"), step).unwrap();
            let expected = |phase: &str| {
                normalize(
                    r[phase]["artifact_sweeps"].clone(),
                    Path::new(r["input"]["root_argument"].as_str().unwrap()),
                )
            };
            let expected_rows = |phase: &str| {
                if spelling == "verbatim" {
                    p2_native_verbatim_rows(
                        style,
                        if phase == "before_sql" {
                            step == "apply-true-repeat"
                        } else {
                            apply
                        },
                    )
                } else {
                    expected(phase)
                }
            };
            assert_eq!(receipts(root), expected_rows("before_sql"));
            let result = run_native(repo.parent().unwrap(), "artifact-receipt", apply);
            assert_eq!(result, r["result"], "{spelling}/{style}/{step}: result");
            assert_eq!(
                receipts(root),
                expected_rows("after_sql"),
                "{spelling}/{style}/{step}: exact SQL rows, including kept native verbatim difference"
            );
            if !apply {
                assert_eq!(
                    reference("snapshot", root, "artifact-receipt", &["raw"]),
                    before
                );
            }
        }
    }
}
#[cfg(windows)]
#[test]
fn p2_windows_receipt_oracle() {
    replay_p2("ordinary");
}
#[cfg(windows)]
#[test]
fn p2_windows_verbatim_reuses_plain_backslash_receipt_and_inserts_plain_paths_unlike_python() {
    replay_p2("verbatim");
}
fn parity(case: &str, apply: bool) {
    let fixture = Fixture::new(case);
    let native = fixture.0.join("native");
    reference("setup", &native, case, &[]);
    let before = reference("snapshot", &native, case, &["raw"]);
    #[cfg(windows)]
    if native.join("fixture-junction.json").exists() {
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
    for step in 0..if apply { 2 } else { 1 } {
        let expected = golden(case, apply, "", NOW, step);
        assert_eq!(
            run_native(&native, case, apply),
            expected["result"],
            "{case}, apply={apply}: report"
        );
        assert_eq!(
            reference("snapshot", &native, case, &[]),
            expected["state"],
            "{case}, apply={apply}: tree, refs, complete job records and receipts"
        );
    }
    if !apply {
        assert_eq!(
            reference("snapshot", &native, case, &["raw"]),
            before,
            "{case}: dry run changed database, worktree or Git bytes"
        );
    }
}
#[test]
fn run_state_frozen_python_oracle() {
    // Includes strict deadline boundary, live/stale jobs, dirt, ignored runtime,
    // unique commits, safe removal and real Git worktree lock refusal.
    parity("run-mixed", false);
    parity("run-mixed", true);
}
#[test]
fn terminal_artifacts_frozen_python_oracle() {
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
    let native = fixture.0.join("native");
    reference("setup", &native, "run-mixed", &[]);
    let expected = golden("run-mixed", true, "drift", NOW, 0);
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
    assert_eq!(normalize_display(actual, &native), expected["result"]);
    assert_eq!(
        reference("snapshot", &native, "run-mixed", &[]),
        expected["state"]
    );
}
#[test]
fn artifact_receipt_survives_interruption_and_recovery_reuses_it() {
    let fixture = Fixture::new("crash");
    let native = fixture.0.join("native");
    reference("setup", &native, "artifact-history", &[]);
    let expected = golden("artifact-history", true, "crash", NOW, 0);
    assert_eq!(expected["result"], json!({"crash":"injected crash"}));
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
        expected["state"],
        "interruption must leave intent receipt and directory intact"
    );
    let expected = golden("artifact-history", true, "crash", NOW, 1);
    assert_eq!(
        run_native(&native, "artifact-history", true),
        expected["result"]
    );
    assert_eq!(
        reference("snapshot", &native, "artifact-history", &[]),
        expected["state"],
        "recovery reuses durable intent rather than inserting duplicate receipts"
    );
}
#[test]
fn non_force_removal_preserves_dirt_created_after_reinspection() {
    let fixture = Fixture::new("non-force");
    reference("setup", &fixture.0, "run-mixed", &[]);
    let result = executor_sweep::sweep_run_state_with_observer(
        &fixture.0.join("repo"),
        &fixture.0.join("jobs.db"),
        NOW,
        120,
        true,
        |stage, path| {
            if stage == "before-remove" && path.file_name().is_some_and(|n| n == "wt-clean") {
                fs::write(path.join("late.txt"), "preserve late dirt\n").unwrap();
            }
            Ok(())
        },
    )
    .unwrap();
    assert_eq!(
        fs::read_to_string(fixture.0.join("wt-clean/late.txt")).unwrap(),
        "preserve late dirt\n"
    );
    eprintln!(
        "preserved_worktrees actual: {}",
        result["preserved_worktrees"]
    );
    let result = normalize_display(result, &fixture.0);
    assert!(
        result["preserved_worktrees"]
            .as_array()
            .unwrap()
            .contains(&json!({
                "path": "$ROOT/wt-clean", "reasons": ["apply-time-drift:remove-refused"]
            }))
    );
}
#[cfg(target_os = "macos")]
#[test]
fn registered_firmlink_removes_clean_and_finished_worktrees() {
    let fixture = Fixture::new("firmlink");
    let alias = Path::new("/System")
        .join("Volumes")
        .join("Data")
        .join(fixture.0.strip_prefix("/").unwrap());
    assert!(
        alias.is_dir(),
        "macOS Data firmlink must resolve to fixture"
    );
    reference("setup", &alias, "run-mixed", &[]);
    let listing = Command::new("git")
        .arg("-C")
        .arg(fixture.0.join("repo"))
        .args(["worktree", "list", "--porcelain"])
        .output()
        .unwrap();
    assert!(listing.status.success());
    assert!(
        String::from_utf8(listing.stdout)
            .unwrap()
            .contains(alias.to_str().unwrap())
    );
    // Resolve while the trees still exist; removal must report their inspected
    // spelling, which can differ from the fixture root's spelling.
    let expected = normalize_display(
        json!([
            reference_path(&alias.join("wt-clean")),
            reference_path(&alias.join("wt-finished"))
        ]),
        &fixture.0,
    );
    let result = run_native(&fixture.0, "run-mixed", true);
    assert_eq!(result["removed_worktrees"], expected);
    assert!(!fixture.0.join("wt-clean").exists());
    assert!(!fixture.0.join("wt-finished").exists());
}

#[cfg(unix)]
#[test]
fn registered_spelling_retarget_before_remove_is_refused() {
    use std::os::unix::fs::symlink;
    let fixture = Fixture::new("registered-retarget");
    reference("setup", &fixture.0, "run-mixed", &[]);
    let alias = fixture.0.join("registered");
    symlink(&fixture.0, &alias).unwrap();
    #[cfg(target_os = "macos")]
    let unchanged = Path::new("/System")
        .join("Volumes")
        .join("Data")
        .join(fixture.0.strip_prefix("/").unwrap());
    #[cfg(not(target_os = "macos"))]
    let unchanged = fixture.0.join("registered-unchanged");
    #[cfg(not(target_os = "macos"))]
    symlink(&fixture.0, &unchanged).unwrap();
    // Git lists the path from this registration, including its original spelling.
    for (registered, name) in [(&alias, "wt-clean"), (&unchanged, "wt-finished")] {
        fs::write(
            fixture
                .0
                .join("repo/.git/worktrees")
                .join(name)
                .join("gitdir"),
            format!("{}\n", registered.join(name).join(".git").display()),
        )
        .unwrap();
    }
    let outside = fixture.0.join("outside");
    fs::create_dir(&outside).unwrap();
    fs::create_dir(outside.join("wt-clean")).unwrap();
    for name in ["tracked.txt", ".gitignore", ".git"] {
        fs::copy(
            fixture.0.join("wt-clean").join(name),
            outside.join("wt-clean").join(name),
        )
        .unwrap();
    }
    let expected_finished = reference_path(&unchanged.join("wt-finished"));
    let result = executor_sweep::sweep_run_state_with_observer(
        &fixture.0.join("repo"),
        &fixture.0.join("jobs.db"),
        NOW,
        120,
        true,
        |stage, path| {
            if stage == "before-remove" && path.ends_with("wt-clean") {
                fs::remove_file(&alias).unwrap();
                symlink(&outside, &alias).unwrap();
            }
            Ok(())
        },
    )
    .unwrap();
    // A stable registered alias must still be removed while the retargeted one is refused.
    assert!(!fixture.0.join("wt-finished").exists());
    assert_eq!(result["removed_worktrees"], json!([expected_finished]));
    assert!(fixture.0.join("wt-clean/tracked.txt").is_file());
    assert_eq!(
        fs::read_to_string(outside.join("wt-clean/tracked.txt")).unwrap(),
        "initial\n"
    );
    assert!(
        result["preserved_worktrees"]
            .as_array()
            .unwrap()
            .contains(&json!({
                "path": fixture.0.join("wt-clean"), "reasons": ["apply-time-drift:remove-refused"]
            }))
    );
}

#[cfg(unix)]
#[test]
fn registered_parent_retarget_after_identity_check_is_refused() {
    use std::os::unix::fs::{PermissionsExt, symlink};
    // Run the sweep in a child so its shim PATH cannot affect parallel tests.
    const CHILD: &str = "MIR_SWEEP_RETARGET_CHILD";
    if let Some(root) = std::env::var_os(CHILD) {
        let root = PathBuf::from(root);
        let result = executor_sweep::sweep_run_state(
            &root.join("repo"),
            &root.join("jobs.db"),
            NOW,
            120,
            true,
        )
        .unwrap();
        fs::write(root.join("result.json"), result.to_string()).unwrap();
        return;
    }
    let fixture = Fixture::new("registered-retarget");
    reference("setup", &fixture.0, "run-mixed", &[]);
    let alias = fixture.0.join("registered");
    symlink(&fixture.0, &alias).unwrap();
    let stable = fixture.0.join("registered-stable");
    symlink(&fixture.0, &stable).unwrap();
    for (registered, name) in [(&alias, "wt-clean"), (&stable, "wt-finished")] {
        fs::write(
            fixture
                .0
                .join("repo/.git/worktrees")
                .join(name)
                .join("gitdir"),
            format!("{}\n", registered.join(name).join(".git").display()),
        )
        .unwrap();
    }
    let outside = fixture.0.join("outside/wt-clean");
    fs::create_dir_all(outside.join("empty-directory")).unwrap();
    for name in ["tracked.txt", ".gitignore", ".git"] {
        fs::copy(fixture.0.join("wt-clean").join(name), outside.join(name)).unwrap();
    }
    let real_git = Command::new("which").arg("git").output().unwrap();
    assert!(real_git.status.success());
    let real_git = String::from_utf8(real_git.stdout).unwrap();
    let shim = fixture.0.join("bin");
    fs::create_dir(&shim).unwrap();
    let script = fixture.0.join("git-shim.py");
    fs::write(
        &script,
        format!(
            r#"import json, os, pathlib, sys
root = pathlib.Path({root})
args = sys.argv[1:]
assert args[0] == '-C' and pathlib.Path(args[1]).is_relative_to(root)
if args[2:4] == ['worktree', 'remove'] and args[4].endswith('/wt-clean'):
    alias = root / 'registered'
    alias.unlink()
    alias.symlink_to(root / 'outside', target_is_directory=True)
    (root / 'remove-argv.json').write_text(json.dumps(args))
os.execv({git}, [{git}, *args])
"#,
            root = json!(fixture.0),
            git = json!(real_git.trim()),
        ),
    )
    .unwrap();
    let quote = |path: &Path| format!("'{}'", path.to_str().unwrap().replace('\'', "'\\''"));
    fs::write(
        shim.join("git"),
        format!(
            "#!/bin/sh\nexec {} -I {} \"$@\"\n",
            quote(&python()),
            quote(&script)
        ),
    )
    .unwrap();
    fs::set_permissions(shim.join("git"), fs::Permissions::from_mode(0o755)).unwrap();
    let mut paths = vec![shim];
    paths.extend(std::env::split_paths(&std::env::var_os("PATH").unwrap()));
    let child = Command::new(std::env::current_exe().unwrap())
        .args([
            "--exact",
            "registered_parent_retarget_after_identity_check_is_refused",
        ])
        .env(CHILD, &fixture.0)
        .env("PATH", std::env::join_paths(paths).unwrap())
        .current_dir(fixture.0.join("repo"))
        .output()
        .unwrap();
    assert!(child.status.success(), "{child:?}");
    let result: Value =
        serde_json::from_slice(&fs::read(fixture.0.join("result.json")).unwrap()).unwrap();
    assert!(
        fixture.0.join("remove-argv.json").is_file(),
        "shim must trigger after validation"
    );
    // Git matches a stable registered symlink via its physical spelling too.
    assert!(!fixture.0.join("wt-finished").exists());
    for name in ["tracked.txt", ".gitignore", ".git", "empty-directory"] {
        assert!(
            outside.join(name).exists(),
            "outside {name} removed: {result}"
        );
    }
    assert!(fixture.0.join("wt-clean/tracked.txt").is_file());
    assert_eq!(
        result["removed_worktrees"],
        json!([fixture.0.join("wt-finished")])
    );
    assert!(
        result["preserved_worktrees"]
            .as_array()
            .unwrap()
            .contains(&json!({
                "path": fixture.0.join("wt-clean"), "reasons": ["apply-time-drift:remove-refused"]
            }))
    );
    assert!(
        Command::new(real_git.trim())
            .arg("-C")
            .arg(fixture.0.join("repo"))
            .args(["show-ref", "--verify", "refs/heads/mir-dispatch/clean"])
            .status()
            .unwrap()
            .success()
    );
}

#[cfg(unix)]
#[test]
fn replacement_at_same_canonical_path_before_remove_is_refused() {
    let fixture = Fixture::new("directory-replacement");
    reference("setup", &fixture.0, "run-mixed", &[]);
    let result = executor_sweep::sweep_run_state_with_observer(
        &fixture.0.join("repo"),
        &fixture.0.join("jobs.db"),
        NOW,
        120,
        true,
        |stage, path| {
            if stage == "before-remove" && path.ends_with("wt-clean") {
                fs::rename(path, fixture.0.join("saved-clean")).unwrap();
                fs::create_dir(path).unwrap();
                for name in ["tracked.txt", ".gitignore", ".git"] {
                    fs::copy(fixture.0.join("saved-clean").join(name), path.join(name)).unwrap();
                }
            }
            Ok(())
        },
    )
    .unwrap();
    assert!(fixture.0.join("wt-clean/tracked.txt").is_file());
    assert!(fixture.0.join("saved-clean/tracked.txt").is_file());
    assert!(
        result["preserved_worktrees"]
            .as_array()
            .unwrap()
            .contains(&json!({
                "path": fixture.0.join("wt-clean"), "reasons": ["apply-time-drift:remove-refused"]
            }))
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
        let native = fixture.0.join("native");
        reference("setup", &native, "artifact-history", &[]);
        let expected = golden("artifact-history", true, "", now, 0);
        let actual = executor_sweep::sweep_terminal_artifacts(
            &native.join("repo"),
            &native.join("jobs.db"),
            now,
            30,
            true,
        )
        .unwrap();
        assert_eq!(normalize_display(actual, &native), expected["result"]);
        let actual = reference("snapshot", &native, "artifact-history", &[]);
        assert_eq!(
            actual["rows"]["artifact_sweeps"][0]["swept_at"], "2026-11-02T12:00:00+00:00",
            "{now}"
        );
        assert_eq!(actual, expected["state"], "{now}");
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
