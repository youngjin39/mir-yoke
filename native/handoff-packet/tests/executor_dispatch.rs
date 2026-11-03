use handoff_packet::{
    executor_dispatch::{CodexAttempt, DispatchContext, DispatchOptions, run_dispatch},
    executor_registry::JobRegistry,
    local_bridge::{BridgeConfig, LocalBridge},
};
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    fs,
    path::{Path, PathBuf},
    process::Command,
    time::Duration,
};

struct Fixture(PathBuf);
impl Fixture {
    fn new(name: &str) -> Self {
        static NEXT: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
        let root = std::env::var_os("MIR_NATIVE_TEST_SCRATCH")
            .map(PathBuf::from)
            .unwrap_or_else(std::env::temp_dir)
            .join(format!(
                "e8-{}-{}-{name}",
                std::process::id(),
                NEXT.fetch_add(1, std::sync::atomic::Ordering::Relaxed)
            ));
        fs::create_dir_all(&root).unwrap();
        // Python Path.resolve supplies the bridge's path spelling, including
        // macOS /var aliases and Windows plain paths rather than extended paths.
        let resolved = Command::new(python())
            .args([
                "-c",
                "from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve())",
            ])
            .arg(&root)
            .output()
            .unwrap();
        assert!(resolved.status.success());
        Self(PathBuf::from(
            String::from_utf8(resolved.stdout).unwrap().trim(),
        ))
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}
fn write(path: &Path, text: &str) {
    fs::create_dir_all(path.parent().unwrap()).unwrap();
    fs::write(path, text).unwrap();
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
    String::from_utf8(output.stdout).unwrap().trim().into()
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
        .expect("Python is required for the real local bridge")
}
fn lines(path: &Path) -> Value {
    json!(
        fs::read_to_string(path)
            .unwrap_or_default()
            .lines()
            .map(|line| serde_json::from_str::<Value>(line).unwrap())
            .collect::<Vec<_>>()
    )
}
fn state(path: &Path) -> Value {
    let Ok(bytes) = fs::read(path) else {
        return Value::Null;
    };
    let value: Value = serde_json::from_slice(&bytes).unwrap();
    json!(
        value
            .as_object()
            .unwrap()
            .iter()
            .filter(|(key, _)| ["state", "attempt", "attempts", "reason"].contains(&key.as_str()))
            .map(|(key, value)| (key.clone(), value.clone()))
            .collect::<serde_json::Map<_, _>>()
    )
}

#[test]
fn python_dispatch_oracle() {
    let oracle: Value = serde_json::from_str(include_str!(
        "../../../tests/fixtures/executor_dispatch.json"
    ))
    .unwrap();
    let interpreter = python();
    for case in oracle["cases"].as_array().unwrap() {
        let name = case["name"].as_str().unwrap();
        let fixture = Fixture::new(name);
        let repo = fixture.0.join("repo");
        fs::create_dir_all(&repo).unwrap();
        git(&repo, &["init", "-q"]);
        git(&repo, &["config", "user.name", "Fixture"]);
        git(&repo, &["config", "user.email", "fixture@example.invalid"]);
        write(&repo.join(".gitignore"), ".mir/\n.mir-dispatch/\n");
        write(&repo.join("code.txt"), "initial\n");
        git(&repo, &["add", "-A"]);
        git(&repo, &["commit", "-qm", "fixture"]);
        write(
            &repo.join("config/mir-executor.local.json"),
            &case.get("config").cloned().unwrap_or(json!({})).to_string(),
        );
        if case.get("hooks").is_some() {
            write(
                &repo.join("tools/mir_executor/local.py"),
                oracle["hook_source"].as_str().unwrap(),
            );
            write(&repo.join("hook-config.json"), &case["hooks"].to_string());
        }
        let mut bridge = LocalBridge::start(BridgeConfig {
            interpreter: interpreter.clone(),
            target_root: repo.clone(),
            bridge_script: Path::new(env!("CARGO_MANIFEST_DIR"))
                .join("../../tools/mir_executor/local_bridge.py"),
            environment: BTreeMap::new(),
            timeout: Duration::from_secs(30),
        })
        .unwrap();
        let registry = JobRegistry::open(&fixture.0.join("jobs.db")).unwrap();
        registry.insert(&json!({"job_id":"fixture-job", "change_id":"fixture", "category":"unit",
            "family":null,"repo_root":repo,"codex_args":[],"timeout_seconds":60,"status":"running",
            "started_at":"","allow_harness_self_modify":false,"resume_count":0,"cancel_requested":false,
            "ai_run_metadata":case.get("previous_metadata").cloned().unwrap_or(Value::Null)})).unwrap();
        let mut options = DispatchOptions::new(&repo, "fixture");
        options.brief_text = "Fixture brief".into();
        options.worktrees_root = Some(fixture.0.join("trees"));
        if let Some(n) = case["max_codex_attempts"].as_i64() {
            options.max_codex_attempts = n;
        }
        if let Some(n) = case["outage_threshold"].as_i64() {
            options.outage_threshold = n;
        }
        if let Some(n) = case["prior_consecutive_codex_failures"].as_i64() {
            options.prior_consecutive_codex_failures = n;
        }
        let mut context = DispatchContext {
            bridge: bridge
                .as_mut()
                .map(|b| b as &mut dyn handoff_packet::executor_command_hooks::HookClient),
            registry: Some((&registry, "fixture-job")),
            provider_hook_applied: case["provider_hook_applied"] == true,
            ..Default::default()
        };
        let mut calls = Vec::new();
        let result = run_dispatch(&options, &mut context, |wt, attempt| {
            calls.push(json!({"attempt":attempt,"worktree_exists":wt.path.is_dir()}));
            if case["runner_error"] == true {
                return Err(handoff_packet::executor_dispatch::Error::Runner(
                    "fixture-runner".into(),
                ));
            }
            let results = case["results"].as_array().unwrap();
            CodexAttempt::from_value(&results[(attempt - 1).min(results.len() - 1)])
        });
        let expected = &case["expected"];
        if let Some(kind) = expected["error"].as_str() {
            let error = result.expect_err(name);
            assert_eq!(error.kind(), kind, "{name}: {error}");
            assert_eq!(
                error.to_string(),
                expected["message"].as_str().unwrap(),
                "{name}"
            );
        } else {
            let mut outcome = result.unwrap_or_else(|e| panic!("{name}: {e}")).to_value();
            outcome.as_object_mut().unwrap().remove("worktree");
            assert_eq!(outcome, expected["outcome"], "{name}: outcome");
        }
        assert_eq!(json!(calls), expected["calls"], "{name}: provider calls");
        assert_eq!(
            json!(context.event_errors),
            expected["event_errors"],
            "{name}: event errors"
        );
        drop(context);
        drop(bridge);
        let wt = fs::read_dir(fixture.0.join("trees"))
            .ok()
            .and_then(|entries| {
                entries
                    .filter_map(Result::ok)
                    .map(|entry| entry.path())
                    .find(|path| path.is_dir())
            });
        let actual_state = wt.as_ref().map_or(Value::Null, |path| {
            state(&path.join(".mir-dispatch/status.json"))
        });
        assert_eq!(actual_state, expected["state"], "{name}: status");
        let events = wt.as_ref().map_or(json!([]), |path| {
            lines(&path.join(".mir-dispatch/dispatch-events.jsonl"))
        });
        assert_eq!(
            events, expected["events"],
            "{name}: ordered dispatch events"
        );
        assert_eq!(
            lines(&repo.join("hooks.jsonl")),
            expected["hooks"],
            "{name}: ordered hooks"
        );
        let row: (String, Option<i64>, Option<String>, Option<String>) = registry.connection().query_row(
            "SELECT status,exit_code,stderr,ai_run_metadata FROM jobs WHERE job_id='fixture-job'", [],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?))).unwrap();
        let metadata = row
            .3
            .map(|text| serde_json::from_str::<Value>(&text).unwrap());
        assert_eq!(
            json!({"status":row.0,"exit_code":row.1,"stderr":row.2,"ai_run_metadata":metadata}),
            expected["registry"],
            "{name}: persisted job fields"
        );
        assert_eq!(
            fs::read_to_string(repo.join("code.txt")).unwrap(),
            "initial\n",
            "{name}: main content"
        );
    }
}

#[test]
fn python_failure_count_oracle() {
    use handoff_packet::executor_dispatch::count_consecutive_codex_failures;
    let oracle: Value = serde_json::from_str(include_str!(
        "../../../tests/fixtures/executor_dispatch.json"
    ))
    .unwrap();
    for case in oracle["counts"].as_array().unwrap() {
        let fixture = Fixture::new(case["name"].as_str().unwrap());
        let path = fixture.0.join("jobs.db");
        let registry = JobRegistry::open(&path).unwrap();
        for record in case["records"].as_array().unwrap() {
            registry.insert(record).unwrap();
        }
        drop(registry);
        assert_eq!(
            count_consecutive_codex_failures(&path, case["prefix"].as_str().unwrap()).unwrap(),
            case["expected"].as_u64().unwrap() as usize,
            "{}",
            case["name"]
        );
    }
}

#[test]
fn dispatch_calls_real_adapter_with_offline_child_and_matches_python() {
    use handoff_packet::executor_dispatch_provider::{ClaudeOptions, claude_attempt};
    let fixture = Fixture::new("adapter-composition");
    let repo = fixture.0.join("repo");
    fs::create_dir_all(&repo).unwrap();
    git(&repo, &["init", "-q"]);
    git(&repo, &["config", "user.name", "Fixture"]);
    git(&repo, &["config", "user.email", "fixture@example.invalid"]);
    write(&repo.join("code.txt"), "initial\n");
    git(&repo, &["add", "-A"]);
    git(&repo, &["commit", "-qm", "fixture"]);
    let interpreter = python();
    let fake =
        Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/executor_dispatch_claude.py");
    let mut options = DispatchOptions::new(&repo, "fixture");
    options.worktrees_root = Some(fixture.0.join("trees"));
    let mut context = DispatchContext::default();
    let mut observed = None;
    let outcome = run_dispatch(&options, &mut context, |wt, _| {
        let mut command = Command::new(&interpreter);
        command.arg(&fake).arg("claude");
        let attempt = claude_attempt(
            command,
            &ClaudeOptions {
                cwd: wt.path.clone(),
                timeout: Some(Duration::from_secs(30)),
                ..Default::default()
            },
        )
        .unwrap();
        observed = Some(attempt.clone());
        Ok(attempt)
    })
    .unwrap();
    let wt = outcome.worktree.as_ref().unwrap();
    // Inject only the executable command: the unchanged Python adapter produces
    // the expected attempt, including its stdout/stderr and exit classification.
    let reference = Command::new(&interpreter).args(["-c", r#"
import json, pathlib, subprocess, sys
from dataclasses import asdict
from unittest.mock import patch
from tools.mir_executor import dispatch
root, checkout, fake = map(pathlib.Path, sys.argv[1:])
def fake_command(command, cwd, env, timeout):
    return subprocess.run([sys.executable, str(fake), 'claude', *command[1:]],
                          cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
with patch.object(dispatch, '_run_guarded', fake_command):
    result = dispatch._run_claude_adapter(root, type('Worktree', (), {'path': checkout, 'dispatch_id': 'fixture'})(), timeout_seconds=30)
print(json.dumps(asdict(result)))
"#]).arg(&repo).arg(&wt.path).arg(&fake)
        .current_dir(Path::new(env!("CARGO_MANIFEST_DIR")).join("../.."))
        .output().unwrap();
    assert!(
        reference.status.success(),
        "{}",
        String::from_utf8_lossy(&reference.stderr)
    );
    let expected: Value = serde_json::from_slice(&reference.stdout).unwrap();
    assert_eq!(observed.unwrap().to_value(), expected);
    assert_eq!(outcome.exit_code, Some(7));
    assert_eq!(outcome.attempts, 1);
    assert_eq!(outcome.blocked_reason.as_deref(), Some("retry-exhausted"));
    assert_eq!(
        lines(&wt.path.join(".mir-dispatch/dispatch-events.jsonl")),
        json!([
            {"kind":"codex_failure","dispatch_id":"fixture","attempt":1,"exit_code":7,
             "error_sig":"","lane_unavailable":false,"retryable":true},
            {"kind":"retry_exhausted","dispatch_id":"fixture","attempts":1}
        ])
    );
}
