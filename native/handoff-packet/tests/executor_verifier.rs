use handoff_packet::{
    executor_verifier::{GateOptions, evaluate_merge_gate, resolve_harness_self_modify},
    executor_worktree::{cleanup_worktree, create_dispatch_worktree},
};
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    fs,
    path::{Path, PathBuf},
    process::Command,
    sync::atomic::{AtomicU64, Ordering},
    time::{Duration, Instant},
};

struct Fixture(PathBuf);
impl Fixture {
    fn new(name: &str) -> Self {
        static NEXT: AtomicU64 = AtomicU64::new(0);
        let root = std::env::var_os("MIR_NATIVE_TEST_SCRATCH")
            .map(PathBuf::from)
            .unwrap_or_else(std::env::temp_dir)
            .join(format!(
                "e7-{}-{}-{name}",
                std::process::id(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
        fs::create_dir_all(&root).unwrap();
        Self(root)
    }
    fn directory(&self, name: &str) -> PathBuf {
        let path = self.0.join(name);
        fs::create_dir_all(&path).unwrap();
        path
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}
fn git(repo: &Path, args: &[&str]) -> String {
    let output = Command::new("git")
        .arg("-C")
        .arg(repo)
        .args(args)
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{args:?}: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    String::from_utf8(output.stdout).unwrap().trim().to_owned()
}
fn write(path: &Path, text: &str) {
    fs::create_dir_all(path.parent().unwrap()).unwrap();
    fs::write(path, text).unwrap();
}
fn python() -> String {
    ["python3", "python"]
        .into_iter()
        .find_map(|candidate| {
            let output = Command::new(candidate)
                .args(["-c", "import sys; print(sys.executable)"])
                .output()
                .ok()?;
            output
                .status
                .success()
                .then(|| String::from_utf8(output.stdout).unwrap().trim().to_owned())
        })
        .expect("Python is required for the portable fake verifier")
}
fn projection(mut receipt: Value, mode: &str, dispatch: &Path) -> Value {
    let env = receipt["env"].as_object_mut().unwrap();
    if mode == "isolated" {
        env.insert("HOME".into(), json!("<ISOLATED_HOME>"));
        env.insert("UV_CACHE_DIR".into(), json!("<ISOLATED_CACHE>"));
    } else {
        env.insert("HOME".into(), json!("<PARENT_HOME>"));
        env.insert("UV_CACHE_DIR".into(), json!("<PARENT_CACHE>"));
        env.insert(
            "CODEX_EVENTS_FILE".into(),
            json!("<REPO>/tasks/codex-exec-events.jsonl"),
        );
        env.insert("CODEX_HOME".into(), json!("<CODEX_HOME>"));
    }
    let mut projected = serde_json::Map::new();
    for key in [
        "literal",
        "stdin_eof",
        "code",
        "profile",
        "home_exists",
        "cache_exists",
        "home_preexisting",
        "env",
    ] {
        projected.insert(key.into(), receipt[key].clone());
    }
    projected.insert(
        "cwd_is_dispatch".into(),
        json!(Path::new(receipt["cwd"].as_str().unwrap()) == dispatch),
    );
    Value::Object(projected)
}

#[test]
fn python_golden_self_modify_profile_is_explicit_and_fail_closed() {
    let golden: Value =
        serde_json::from_str(include_str!("fixtures/executor_verifier.json")).unwrap();
    for (index, case) in golden["profiles"].as_array().unwrap().iter().enumerate() {
        let fixture = Fixture::new(&format!("profile-{index}"));
        if let Some(text) = case["text"].as_str() {
            write(&fixture.0.join(".mir/repo-profile.toml"), text);
        }
        assert_eq!(
            resolve_harness_self_modify(&fixture.0),
            case["expected"].as_bool().unwrap(),
            "{case}"
        );
    }
}

#[test]
fn python_golden_gate_decisions_receipts_isolation_and_cleanup() {
    let golden: Value =
        serde_json::from_str(include_str!("fixtures/executor_verifier.json")).unwrap();
    let python = python();
    let fake =
        Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/executor_verifier_fake.py");
    let mut timeout_receipts = Vec::new();
    let mut fixtures = Vec::new();
    for case in golden["cases"].as_array().unwrap() {
        let name = case["name"].as_str().unwrap();
        let fixture = Fixture::new(name);
        let repo = fixture.directory("repo");
        git(&repo, &["init", "-q"]);
        git(&repo, &["config", "core.autocrlf", "false"]);
        git(&repo, &["config", "user.name", "Fixture"]);
        git(&repo, &["config", "user.email", "fixture@example.invalid"]);
        write(
            &repo.join(".gitignore"),
            ".mir/\n.mir-dispatch/\nconfig/mir-executor.local.json\n",
        );
        write(&repo.join("code.txt"), "initial\n");
        git(&repo, &["add", "-A"]);
        git(&repo, &["commit", "-qm", "fixture"]);
        let mut profile = "[repo]\nrepository_type = \"fixture\"\n".to_owned();
        if let Some(secrets) = case.get("secrets") {
            profile.push_str(&format!("\n[boundaries]\nsecrets = {secrets}\n"));
        }
        write(&repo.join(".mir/repo-profile.toml"), &profile);
        let wt =
            create_dispatch_worktree(&repo, "fixture", "HEAD", "", Some(&fixture.0.join("trees")))
                .unwrap();
        let changes = case["changes"].as_object().unwrap();
        for (path, text) in changes {
            write(&wt.path.join(path), text.as_str().unwrap());
        }
        if !changes.is_empty() {
            git(&wt.path, &["add", "-A"]);
            git(&wt.path, &["commit", "-qm", "changes"]);
        }
        let source = git(&wt.path, &["rev-parse", "HEAD"]);
        if case["pinned"] == true {
            write(&wt.path.join("later.txt"), "not selected\n");
            write(&wt.path.join("code.txt"), "later\n");
            git(&wt.path, &["add", "-A"]);
            git(&wt.path, &["commit", "-qm", "later"]);
        }
        if case["dirty"] == true {
            write(&wt.path.join("dirty.txt"), "dirty\n");
        }
        if case["runtime_dirty"] == true {
            write(&wt.path.join(".mir-dispatch/runtime.log"), "runtime\n");
        }
        let mut verifiers = serde_json::Map::new();
        for command in ["first", "second"] {
            let mut argv = vec![
                json!(python),
                json!(fake),
                json!(fixture.0.join(format!("{command}.json"))),
                case["runs"].get(command).cloned().unwrap_or(json!("pass")),
                json!(wt.path),
            ];
            argv.extend(golden["literal"].as_array().unwrap().iter().cloned());
            verifiers.insert(command.into(), Value::Array(argv));
        }
        if let Some(overrides) = case["verifiers"].as_object() {
            verifiers.extend(overrides.clone());
        }
        let mut config = json!({"verifiers":verifiers,"verifier_env":case["mode"],
            "child_env_extra_keys":["EXPLICIT_TOKEN","UV_CACHE_DIR","SystemRoot"]});
        if let Some(bounds) = case.get("bounds") {
            config["timeout_seconds_range"] = bounds.clone();
        }
        write(
            &repo.join("config/mir-executor.local.json"),
            &config.to_string(),
        );
        let parent_home = fixture.directory("parent-home");
        let parent_cache = fixture.directory("parent-cache");
        let scratch = fixture.directory("tmp");
        let mut source_env: BTreeMap<String, String> = ["PATH", "SystemRoot"]
            .into_iter()
            .filter_map(|key| std::env::var(key).ok().map(|value| (key.to_owned(), value)))
            .collect();
        for (key, value) in [
            ("HOME", parent_home.to_str().unwrap()),
            ("UV_CACHE_DIR", parent_cache.to_str().unwrap()),
            ("TMPDIR", scratch.to_str().unwrap()),
            ("LANG", "C.UTF-8"),
            ("LC_MESSAGES", "C"),
            ("OPENAI_API_KEY", "must-not-inherit"),
            ("EXPLICIT_TOKEN", "explicit"),
            ("UNLISTED", "must-not-inherit"),
            ("CODEX_HOME", fixture.0.join("codex-home").to_str().unwrap()),
        ] {
            source_env.insert(key.into(), value.into());
        }
        let options = GateOptions {
            allowlist: serde_json::from_value(case["allowlist"].clone()).unwrap(),
            verification_commands: serde_json::from_value(case["commands"].clone()).unwrap(),
            verify_timeout: case.get("timeout").cloned(),
            allow_harness_self_modify: case["self_modify"] == true,
            expect_changes: case["expect_changes"].as_bool().unwrap(),
            source_commit: (case["pinned"] == true).then_some(source),
            scratch_root: scratch.clone(),
            source_env,
        };
        let start = Instant::now();
        let result = evaluate_merge_gate(&wt, &options);
        let expected = &case["expected"];
        if expected.get("error").is_some() {
            let error = result.unwrap_err();
            assert_eq!(
                error.kind(),
                expected["error"].as_str().unwrap(),
                "{name}: {error}"
            );
            // Native OS text varies by platform; deterministic validation text must match.
            if expected["error"] == "ValueError" {
                assert_eq!(
                    error.to_string(),
                    expected["message"].as_str().unwrap(),
                    "{name}"
                );
            }
        } else {
            let gate = result.unwrap_or_else(|error| panic!("{name}: {error}"));
            assert_eq!(
                json!({"approved":gate.approved,"reason":gate.reason,"changed_files":gate.changed_files}),
                expected["gate"],
                "{name}"
            );
        }
        if name.contains("timeout") && case["runs"]["first"] == "timeout" {
            assert!(
                start.elapsed() < Duration::from_secs(15),
                "{name}: timeout did not return promptly"
            );
            timeout_receipts.push(fixture.0.join("first.json.late"));
        }
        let mut receipts = Vec::new();
        let mut homes = Vec::new();
        let mut roots = Vec::new();
        for command in ["first", "second"] {
            let path = fixture.0.join(format!("{command}.json"));
            if !path.exists() {
                continue;
            }
            let receipt: Value = serde_json::from_slice(&fs::read(path).unwrap()).unwrap();
            let verification_root = PathBuf::from(receipt["cwd"].as_str().unwrap());
            if case["mode"] == "isolated" {
                let home = Path::new(receipt["home"].as_str().unwrap());
                let cache = Path::new(receipt["cache"].as_str().unwrap());
                assert_ne!(home, parent_home, "{name}: parent home leaked");
                assert_ne!(cache, parent_cache, "{name}: parent cache leaked");
                assert_eq!(
                    cache.parent(),
                    Some(home),
                    "{name}: cache must belong to isolated home"
                );
                assert_eq!(receipt["env"]["HOME"], receipt["home"], "{name}");
                assert_eq!(receipt["env"]["UV_CACHE_DIR"], receipt["cache"], "{name}");
                if name == "isolated-home-cleanup-error" {
                    assert!(
                        home.is_file(),
                        "the original cleanup error must remain observable"
                    );
                    fs::remove_file(home).unwrap();
                }
                for key in ["home", "cache"] {
                    let path = PathBuf::from(receipt[key].as_str().unwrap());
                    assert!(!path.exists(), "{name}: {key} was not cleaned: {path:?}");
                }
                homes.push(receipt["home"].clone());
            } else {
                assert_eq!(
                    Path::new(receipt["home"].as_str().unwrap()),
                    parent_home,
                    "{name}"
                );
                assert_eq!(
                    Path::new(receipt["cache"].as_str().unwrap()),
                    parent_cache,
                    "{name}"
                );
                assert_eq!(
                    Path::new(receipt["env"]["HOME"].as_str().unwrap()),
                    parent_home,
                    "{name}"
                );
                assert_eq!(
                    Path::new(receipt["env"]["UV_CACHE_DIR"].as_str().unwrap()),
                    parent_cache,
                    "{name}"
                );
                assert_eq!(
                    Path::new(receipt["env"]["CODEX_EVENTS_FILE"].as_str().unwrap()),
                    wt.main_repo_root.join("tasks/codex-exec-events.jsonl"),
                    "{name}"
                );
                assert_eq!(
                    Path::new(receipt["env"]["CODEX_HOME"].as_str().unwrap()),
                    fixture.0.join("codex-home"),
                    "{name}"
                );
            }
            if name.starts_with("cleanup-") {
                assert!(
                    verification_root.exists(),
                    "cleanup failure must preserve observable residue"
                );
                git(
                    &repo,
                    &["worktree", "unlock", verification_root.to_str().unwrap()],
                );
                git(
                    &repo,
                    &[
                        "worktree",
                        "remove",
                        "--force",
                        verification_root.to_str().unwrap(),
                    ],
                );
            } else {
                assert!(
                    !verification_root.exists(),
                    "{name}: verification checkout was not removed"
                );
            }
            roots.push(verification_root);
            receipts.push(json!({"name":command,"receipt":projection(receipt, case["mode"].as_str().unwrap(), &wt.path)}));
        }
        assert_eq!(json!(receipts), expected["receipts"], "{name}");
        if homes.len() == 2 {
            assert_ne!(homes[0], homes[1], "each verifier needs a fresh home");
        }
        if roots.len() == 2 {
            assert_eq!(
                roots[0], roots[1],
                "verifiers share one detached verification checkout"
            );
        }
        if !name.starts_with("cleanup-") {
            assert_eq!(
                fs::read_dir(&scratch).unwrap().count(),
                0,
                "{name}: temporary verifier state leaked"
            );
        }
        assert_eq!(
            git(&repo, &["worktree", "list", "--porcelain"])
                .matches("worktree ")
                .count(),
            2,
            "{name}"
        );
        assert_eq!(
            fs::read_to_string(repo.join("code.txt")).unwrap(),
            "initial\n",
            "{name}: main changed"
        );
        let dispatch_code = if case["pinned"] == true {
            "later\n"
        } else {
            changes
                .get("code.txt")
                .and_then(Value::as_str)
                .unwrap_or("initial\n")
        };
        assert_eq!(
            fs::read_to_string(wt.path.join("code.txt")).unwrap(),
            dispatch_code,
            "{name}: dispatch changed"
        );
        assert!(
            !wt.path.join("generated.txt").exists(),
            "{name}: verifier ran in dispatch"
        );
        cleanup_worktree(&wt, true).unwrap();
        fixtures.push(fixture);
    }
    // A timed-out immediate verifier must be killed, not merely detached.
    std::thread::sleep(Duration::from_secs(6));
    for path in timeout_receipts {
        assert!(!path.exists(), "timed-out child survived: {path:?}");
    }
    drop(fixtures);
}
