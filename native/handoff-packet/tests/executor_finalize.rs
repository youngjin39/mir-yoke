//! Python parity on real Git repositories, including index and worktree state.
use handoff_packet::{
    executor_dispatch::DispatchOutcome,
    executor_finalize::{self, Error, FinalizeLock, FinalizeOptions, FinalizeStep},
    executor_registry::JobRegistry,
    executor_review::ReviewEvidence,
    executor_worktree::{DispatchWorktree, create_dispatch_worktree},
};
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    fs,
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    time::{Duration, Instant},
};

struct Fixture(PathBuf);
impl Fixture {
    fn new(name: &str) -> Self {
        static NEXT: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
        let root = std::env::var_os("MIR_NATIVE_TEST_SCRATCH")
            .map(PathBuf::from)
            .unwrap_or_else(std::env::temp_dir)
            .join(format!(
                "e9b-{}-{}-{name}",
                std::process::id(),
                NEXT.fetch_add(1, std::sync::atomic::Ordering::Relaxed)
            ));
        fs::create_dir_all(&root).unwrap();
        // Ordinary Windows path spelling, like crate::supply::plain.
        let out = Command::new(python())
            .args([
                "-c",
                "from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve())",
            ])
            .arg(&root)
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
fn write(root: &Path, name: &str, content: &str) {
    let p = root.join(name);
    fs::create_dir_all(p.parent().unwrap()).unwrap();
    fs::write(p, content).unwrap();
}
fn git(repo: &Path, args: &[&str]) -> String {
    let out = Command::new("git")
        .arg("-C")
        .arg(repo)
        .args(args)
        .output()
        .unwrap();
    assert!(
        out.status.success(),
        "{args:?}: {}",
        String::from_utf8_lossy(&out.stderr)
    );
    String::from_utf8(out.stdout).unwrap()
}
fn files(root: &Path, path: &Path, out: &mut BTreeMap<String, String>) {
    if path.is_file() {
        out.insert(
            path.strip_prefix(root)
                .unwrap()
                .to_str()
                .unwrap()
                .replace('\\', "/"),
            fs::read_to_string(path).unwrap(),
        );
    } else if path.is_dir() {
        for entry in fs::read_dir(path).unwrap() {
            files(root, &entry.unwrap().path(), out);
        }
    }
}
fn snapshot(repo: &Path) -> Value {
    if !repo.exists() {
        return Value::Null;
    }
    let mut entries = BTreeMap::new();
    for p in ["pkg", "wip"] {
        files(repo, &repo.join(p), &mut entries);
    }
    json!({"index":git(repo,&["ls-files","--stage"]),"status":git(repo,&["status","--porcelain=v1","-z","--untracked-files=all","--ignored=matching","--","pkg","wip"]),"files":entries})
}
fn both(repo: &Path, wt: &DispatchWorktree) -> Value {
    json!({"main":snapshot(repo),"dispatch":snapshot(&wt.path)})
}
fn seed(repo: &Path, source: &Value) {
    fs::create_dir_all(repo).unwrap();
    for args in [
        &["init", "-q"][..],
        &["config", "user.name", "Fixture"],
        &["config", "user.email", "fixture@example.invalid"],
        &["config", "core.autocrlf", "false"],
    ] {
        git(repo, args);
    }
    write(
        repo,
        ".gitignore",
        ".mir/\n.mir-dispatch/\nconfig/\n*.ignored\n",
    );
    for (name, content) in source.as_object().unwrap() {
        write(repo, name, content.as_str().unwrap());
    }
    git(repo, &["add", "-A"]);
    git(repo, &["commit", "-qm", "fixture"]);
    write(
        repo,
        "config/mir-executor.local.json",
        &json!({"verifiers":{"ok":[python(),"-c","pass"]}}).to_string(),
    );
}

// The second native process uses the same locking API on Unix and Windows.
#[test]
fn finalize_lock_child() {
    let Some(root) = std::env::var_os("E9B_LOCK_CHILD") else {
        return;
    };
    let root = PathBuf::from(root);
    let _lock = FinalizeLock::acquire(&root, Duration::from_secs(20))
        .unwrap()
        .unwrap();
    fs::write(root.join(".mir/lock-ready"), "ready").unwrap();
    let deadline = Instant::now() + Duration::from_secs(45);
    while !root.join(".mir/lock-release").exists() {
        assert!(Instant::now() < deadline);
        std::thread::sleep(Duration::from_millis(20));
    }
}
struct LockChild(Child, PathBuf);
impl LockChild {
    fn start(repo: &Path) -> Self {
        let child = Command::new(std::env::current_exe().unwrap())
            .args(["--exact", "finalize_lock_child", "--nocapture"])
            .env("E9B_LOCK_CHILD", repo)
            .stdout(Stdio::null())
            .stderr(Stdio::piped())
            .spawn()
            .unwrap();
        let mut guard = Self(child, repo.to_owned());
        let deadline = Instant::now() + Duration::from_secs(30);
        while !repo.join(".mir/lock-ready").exists() {
            if Instant::now() >= deadline {
                let _ = guard.0.kill();
                let _ = guard.0.wait();
                panic!("lock readiness timeout");
            }
            std::thread::sleep(Duration::from_millis(20));
        }
        guard
    }
}
impl Drop for LockChild {
    fn drop(&mut self) {
        let _ = fs::write(self.1.join(".mir/lock-release"), "release");
        let deadline = Instant::now() + Duration::from_secs(20);
        loop {
            match self.0.try_wait() {
                Ok(Some(status)) => {
                    if !std::thread::panicking() {
                        assert!(status.success());
                    }
                    break;
                }
                Ok(None) if Instant::now() < deadline => {
                    std::thread::sleep(Duration::from_millis(20))
                }
                _ => {
                    let _ = self.0.kill();
                    let _ = self.0.wait();
                    if !std::thread::panicking() {
                        panic!("lock child did not exit");
                    }
                    break;
                }
            }
        }
    }
}

#[test]
fn python_finalize_oracle() {
    let oracle: Value =
        serde_json::from_str(include_str!("fixtures/executor_finalize.json")).unwrap();
    for case in oracle["cases"].as_array().unwrap() {
        run_case(case, &oracle["files"]);
    }
}
fn run_case(case: &Value, source: &Value) {
    let name = case["name"].as_str().unwrap();
    let fixture = Fixture::new(name);
    let repo = fixture.0.join("repo");
    seed(&repo, source);
    if case["secret"] == true {
        write(
            &repo,
            ".mir/repo-profile.toml",
            "[boundaries]\nsecrets = [\"a.py\"]\n",
        );
    }
    let wt = create_dispatch_worktree(
        &repo,
        "fixture",
        "HEAD",
        "Fixture brief",
        Some(&fixture.0.join("trees")),
    )
    .unwrap();
    if case["empty"] != true {
        write(&wt.path, "pkg/a.py", "a = 2\n");
    }
    let inject = case["inject"].as_str().unwrap_or("");
    if ["merge", "restore", "rollback"].contains(&inject) {
        write(&wt.path, "pkg/new.py", "new = 2\n");
    }
    if case["paths"] == true {
        fs::remove_file(wt.path.join("pkg/delete.py")).unwrap();
        fs::rename(
            wt.path.join("pkg/rename-old.py"),
            wt.path.join("pkg/rename-new.py"),
        )
        .unwrap();
        write(&wt.path, "pkg/[ab].py", "literal changed\n");
    }
    let collision = case["collision"].as_str().unwrap_or("");
    if ["untracked", "ignored", "parent"].contains(&collision) {
        let target = match collision {
            "untracked" => "pkg/new.py",
            "ignored" => "pkg/new.ignored",
            _ => "pkg/parent/new.py",
        };
        write(&wt.path, target, "dispatch new\n");
        write(
            &repo,
            if collision == "parent" {
                "pkg/parent"
            } else {
                target
            },
            "main collision\n",
        );
        if collision == "ignored" {
            git(&wt.path, &["add", "-f", target]);
        }
    }
    if ["staged", "unstaged"].contains(&collision) {
        write(&repo, "pkg/a.py", "main wip\n");
        if collision == "staged" {
            git(&repo, &["add", "pkg/a.py"]);
        }
    }
    if case["wip"] == true {
        write(&repo, "wip/staged.txt", "staged wip\n");
        git(&repo, &["add", "wip/staged.txt"]);
        for (p, c) in [
            ("wip/unstaged.txt", "unstaged wip\n"),
            ("wip/untracked.txt", "untracked wip\n"),
            ("wip/cache.ignored", "ignored wip\n"),
        ] {
            write(&repo, p, c);
        }
    }
    assert_eq!(
        both(&repo, &wt),
        case["expected"]["before"],
        "{name}: before"
    );
    let registry = JobRegistry::open(&fixture.0.join("jobs.db")).unwrap();
    registry.insert(&json!({"job_id":"fixture-job","change_id":"fixture","category":"unit","family":null,"repo_root":repo,"codex_args":[],"timeout_seconds":60,"status":"running","started_at":"","allow_harness_self_modify":false,"resume_count":0,"cancel_requested":false})).unwrap();
    let outcome = DispatchOutcome {
        status: case["outcome"].as_str().unwrap_or("completed").into(),
        attempts: 1,
        fell_back: false,
        blocked_reason: case.get("outcome").map(|_| "fixture-blocked".into()),
        worktree: Some(wt.clone()),
        tokens_used: vec![],
        model_id: None,
        mcp_protocol: None,
        stdout: String::new(),
        exit_code: Some(0),
        stderr: String::new(),
    };
    let mut options = FinalizeOptions::default();
    options.gate.allowlist = vec!["pkg/".into()];
    options.gate.verification_commands = case
        .get("verification_commands")
        .map(|v| {
            v.as_array()
                .unwrap()
                .iter()
                .map(|v| v.as_str().unwrap().into())
                .collect()
        })
        .unwrap_or_else(|| vec!["ok".into()]);
    options.gate.expect_changes = case["expect_changes"].as_bool().unwrap_or(true);
    options.gate.scratch_root = fixture.0.join("verify");
    options.gate.source_env = std::env::vars().collect();
    options.finalize_lock_timeout = Duration::ZERO;
    options.require_review = case["require_review"].as_bool();
    options.artifacts_root = Some(fixture.0.join("artifacts"));
    let injected = std::cell::RefCell::new(Vec::<Value>::new());
    let mut reviewer = |wt: &DispatchWorktree, _files: &[String]| {
        let drift = case["drift"].as_str().unwrap_or("");
        match drift {
            "main" => {
                write(&repo, "pkg/b.py", "main moved\n");
                git(&repo, &["add", "pkg/b.py"]);
                git(&repo, &["commit", "-qm", "main drift"]);
            }
            "dispatch" => {
                write(&wt.path, "pkg/b.py", "dispatch moved\n");
                git(&wt.path, &["add", "pkg/b.py"]);
                git(&wt.path, &["commit", "-qm", "dispatch drift"]);
            }
            "dirty" => write(&wt.path, "pkg/b.py", "dispatch dirty\n"),
            _ => {}
        }
        if !drift.is_empty() {
            injected.borrow_mut().push(both(&repo, wt));
        }
        Ok(ReviewEvidence {
            passed: case["review"] != "reject",
            reason: if case["review"] == "reject" {
                "fixture-rejected"
            } else {
                "approved"
            }
            .into(),
            content: "fixture review".into(),
            provider: "fixture".into(),
        })
    };
    let mut observer = |step: FinalizeStep, wt: &DispatchWorktree| {
        match step {
            FinalizeStep::BeforeMerge if ["merge", "restore", "rollback"].contains(&inject) => {
                write(&repo, "pkg/a.py", "partial merge\n");
                write(&repo, "pkg/new.py", "new = 2\n");
                git(&repo, &["add", "pkg/a.py", "pkg/new.py"]);
                injected.borrow_mut().push(both(&repo, wt));
                return Err(Error::Invalid("boom".into()));
            }
            FinalizeStep::BeforeRestore(p) if inject == "restore" && p == "pkg/a.py" => {
                injected.borrow_mut().push(both(&repo, wt));
                return Err(Error::Invalid("restore refused".into()));
            }
            FinalizeStep::BeforeRollback if inject == "rollback" => {
                injected.borrow_mut().push(both(&repo, wt));
                return Err(Error::Invalid("rollback refused".into()));
            }
            FinalizeStep::BeforeCleanup if inject == "cleanup" => {
                injected.borrow_mut().push(both(&repo, wt));
                return Err(Error::Invalid("cleanup offline".into()));
            }
            FinalizeStep::BeforePersist if inject == "persist" => {
                injected.borrow_mut().push(both(&repo, wt));
                return Err(Error::Invalid("persist offline".into()));
            }
            _ => {}
        }
        Ok(())
    };
    let holder = (case["lock"] == true).then(|| LockChild::start(&repo));
    if holder.is_some() {
        let started = Instant::now();
        assert!(
            FinalizeLock::acquire(&repo, Duration::from_millis(200))
                .unwrap()
                .is_none()
        );
        assert!(started.elapsed() >= Duration::from_millis(150));
        assert!(started.elapsed() < Duration::from_secs(5));
    }
    let reviewer: Option<&mut executor_finalize::Reviewer<'_>> =
        if case.get("review").is_some() || case.get("drift").is_some() {
            Some(&mut reviewer)
        } else {
            None
        };
    let result = executor_finalize::finalize_dispatch_with_observer(
        &wt,
        &outcome,
        &options,
        reviewer,
        Some((&registry, "fixture-job")),
        &mut observer,
    )
    .unwrap_or_else(|e| panic!("{name}: {e}"));
    drop(holder);
    assert_eq!(
        result.to_value(),
        case["expected"]["result"],
        "{name}: result"
    );
    assert_eq!(
        json!(injected.into_inner()),
        case["expected"]["injected"],
        "{name}: injection state"
    );
    assert_eq!(both(&repo, &wt), case["expected"]["after"], "{name}: after");
    let mut artifacts = fs::read_dir(fixture.0.join("artifacts/fixture"))
        .ok()
        .map(|it| {
            it.map(|e| e.unwrap().file_name().to_string_lossy().into_owned())
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    artifacts.sort();
    assert_eq!(
        json!(artifacts),
        case["expected"]["artifacts"],
        "{name}: artifacts"
    );
    let mut content = serde_json::Map::new();
    for filename in ["brief.md", "reviewer.json"] {
        if let Ok(text) = fs::read_to_string(fixture.0.join("artifacts/fixture").join(filename)) {
            let value = if filename.ends_with(".json") {
                serde_json::from_str(&text).unwrap()
            } else {
                json!(text)
            };
            content.insert(filename.into(), value);
        }
    }
    assert_eq!(
        json!(content),
        case["expected"]["artifact_content"],
        "{name}: persisted evidence"
    );
    let job = registry
        .connection()
        .query_row(
            "SELECT status,exit_code FROM jobs WHERE job_id='fixture-job'",
            [],
            |r| Ok((r.get::<_, String>(0)?, r.get::<_, i64>(1)?)),
        )
        .unwrap();
    assert_eq!(
        json!({"status":job.0,"exit_code":job.1}),
        case["expected"]["registry"],
        "{name}: E3"
    );
    if case["lock"] == true {
        assert!(
            FinalizeLock::acquire(&repo, Duration::from_secs(5))
                .unwrap()
                .is_some()
        );
    }
}
