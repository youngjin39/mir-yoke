use handoff_packet::{
    executor_registry::JobRegistry,
    executor_resume,
    local_bridge::{BridgeConfig, LocalBridge},
};
use serde_json::{Value, json};
use std::{
    fs,
    path::PathBuf,
    process::Command,
    time::{SystemTime, UNIX_EPOCH},
};
struct Scratch(PathBuf);
impl Drop for Scratch {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}
fn setup() -> (Scratch, Value) {
    setup_inner(false)
}
static NEXT: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
fn setup_inner(git: bool) -> (Scratch, Value) {
    let base = std::env::var_os("MIR_NATIVE_TEST_SCRATCH")
        .map(PathBuf::from)
        .unwrap_or_else(std::env::temp_dir);
    let root = base.join(format!(
        "resume-{}-{}-{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos(),
        NEXT.fetch_add(1, std::sync::atomic::Ordering::Relaxed)
    ));
    let scratch = Scratch(root);
    if git {
        let out = Command::new("git")
            .args(["clone", "--shared", "--no-checkout", "--local", "-q"])
            .arg(concat!(env!("CARGO_MANIFEST_DIR"), "/../.."))
            .arg(&scratch.0)
            .output()
            .unwrap();
        assert!(
            out.status.success(),
            "{}",
            String::from_utf8_lossy(&out.stderr)
        );
    }
    let python = ["python3", "python"]
        .into_iter()
        .find(|p| {
            Command::new(p)
                .arg("--version")
                .output()
                .is_ok_and(|o| o.status.success())
        })
        .unwrap();
    let out = Command::new(python)
        .arg(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/tests/fixtures/executor_resume.py"
        ))
        .arg(&scratch.0)
        .output()
        .unwrap();
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stderr)
    );
    (scratch, serde_json::from_slice(&out.stdout).unwrap())
}
#[test]
fn python_saved_and_legacy_options_and_attempt_history() {
    let (_scratch, cases) = setup();
    for case in cases.as_array().unwrap() {
        let mut prepared = executor_resume::prepare(&case["row"], &case["defaults"], None).unwrap();
        for (key, expected) in case["expected"].as_object().unwrap() {
            assert_eq!(&prepared.args[key], expected, "{key}");
        }
        let override_plan =
            executor_resume::prepare(&case["row"], &case["defaults"], Some(json!(321))).unwrap();
        assert_eq!(override_plan.args["timeout"], 321);
        let root = PathBuf::from(case["row"]["repo_root"].as_str().unwrap());
        let registry = JobRegistry::open(&root.join("jobs.db")).unwrap();
        let mut authority = bridge(&root);
        let mut target = bridge(&root);
        prepared
            .authorize(&root, &mut authority, &mut target)
            .unwrap();
        assert!(
            prepared
                .begin(&registry, "old-attempt", "now", None)
                .is_err()
        );
        prepared
            .begin(&registry, "new-attempt", "now", Some(&mut target))
            .unwrap();
        let (count, status, stdout, metadata): (i64, String, Option<String>, String) = registry
            .connection()
            .query_row(
                "SELECT resume_count,status,stdout,ai_run_metadata FROM jobs WHERE job_id=?",
                [case["row"]["job_id"].as_str().unwrap()],
                |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?)),
            )
            .unwrap();
        assert_eq!((count, status.as_str(), stdout), (1, "running", None));
        let cleared: bool = registry.connection().query_row(
            "SELECT exit_code IS NULL AND stderr IS NULL AND duration_seconds IS NULL AND completed_at IS NULL AND cancel_requested=0 FROM jobs WHERE job_id=?",
            [case["row"]["job_id"].as_str().unwrap()], |r| r.get(0),
        ).unwrap();
        assert!(cleared);
        let route: (String, String, String) = registry.connection().query_row(
            "SELECT execution_backend,resolved_model,resolved_reasoning_effort FROM jobs WHERE job_id=?",
            [case["row"]["job_id"].as_str().unwrap()], |r| Ok((r.get(0)?,r.get(1)?,r.get(2)?)),
        ).unwrap();
        assert_eq!(
            json!([route.0, route.1, route.2]),
            json!([
                prepared.args["execution_backend"],
                prepared.args["model"],
                prepared.args["reasoning_effort"]
            ])
        );
        assert!(
            prepared
                .begin(&registry, "another-attempt", "now", None)
                .is_err()
        );
        let metadata: Value = serde_json::from_str(&metadata).unwrap();
        assert_eq!(
            metadata["dispatch_ids"],
            json!(["older", "old-attempt", "new-attempt"])
        );
    }
}
#[test]
fn hash_refusal_is_read_only() {
    let (scratch, cases) = setup();
    let db = fs::read(scratch.0.join("jobs.db")).unwrap();
    fs::write(scratch.0.join("brief.json"), "changed").unwrap();
    let before = snapshot(&scratch.0);
    assert!(executor_resume::prepare(&cases[0]["row"], &cases[0]["defaults"], None).is_err());
    assert_eq!(fs::read(scratch.0.join("jobs.db")).unwrap(), db);
    assert_eq!(
        fs::read_to_string(scratch.0.join("brief.json")).unwrap(),
        "changed"
    );
    assert!(!scratch.0.join("events.jsonl").exists());
    assert_eq!(snapshot(&scratch.0), before);
}
fn snapshot(root: &std::path::Path) -> std::collections::BTreeMap<PathBuf, Vec<u8>> {
    let mut result = std::collections::BTreeMap::new();
    for entry in fs::read_dir(root).unwrap() {
        let path = entry.unwrap().path();
        if path.is_dir() {
            result.extend(snapshot(&path));
        } else {
            result.insert(path.clone(), fs::read(path).unwrap());
        }
    }
    result
}

fn bridge(root: &std::path::Path) -> LocalBridge {
    let python = ["python3", "python"]
        .into_iter()
        .find_map(|p| {
            Command::new(p)
                .args(["-c", "import sys; print(sys.executable)"])
                .output()
                .ok()
                .filter(|o| o.status.success())
                .map(|o| PathBuf::from(String::from_utf8(o.stdout).unwrap().trim()))
        })
        .unwrap();
    LocalBridge::start(BridgeConfig {
        interpreter: python,
        target_root: root.to_path_buf(),
        bridge_script: PathBuf::from(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/../../tools/mir_executor/local_bridge.py"
        )),
        environment: std::env::vars_os().collect(),
        timeout: std::time::Duration::from_secs(30),
    })
    .unwrap()
    .unwrap()
}
#[test]
fn root_and_reauthorization_refuse_before_durable_effects() {
    for mode in ["deny", "redirect", "brief-root"] {
        let (scratch, cases) = setup();
        let mut row = cases[0]["row"].clone();
        let root = PathBuf::from(row["repo_root"].as_str().unwrap());
        if mode == "brief-root" {
            // Legacy rows have no hash; target validation still binds the root.
            row["dispatch_options_json"] = Value::Null;
            fs::write(root.join("brief.json"), r#"{"repo_root":"different"}"#).unwrap();
        } else {
            fs::write(root.join(mode), "").unwrap();
        }
        fs::create_dir_all(root.join("other")).unwrap();
        let db = fs::read(root.join("jobs.db")).unwrap();
        let brief = fs::read(root.join("brief.json")).unwrap();
        let mut plan = executor_resume::prepare(&row, &cases[0]["defaults"], None).unwrap();
        let mut authority = bridge(&root);
        let mut target = bridge(&root);
        // Bridge startup imports the fixture hook. Snapshot after that setup,
        // before the resume authorization boundary is exercised.
        let before = snapshot(&root);
        assert!(
            plan.authorize(&root, &mut authority, &mut target).is_err(),
            "{mode}"
        );
        let registry = JobRegistry::open(&root.join("jobs.db")).unwrap();
        assert!(
            plan.begin(&registry, "new", "now", Some(&mut target))
                .is_err()
        );
        drop(registry);
        assert_eq!(fs::read(root.join("jobs.db")).unwrap(), db, "{mode}");
        assert_eq!(fs::read(root.join("brief.json")).unwrap(), brief);
        assert!(!scratch.0.join("events.jsonl").exists());
        assert!(snapshot(&root) == before, "{mode}: durable files changed");
    }
}

#[test]
fn resume_handoff_runs_existing_e8_and_e9_with_fake_provider() {
    use handoff_packet::executor_dispatch::{CodexAttempt, DispatchContext, DispatchOptions};
    let (_scratch, cases) = setup_inner(true);
    let root = PathBuf::from(cases[0]["row"]["repo_root"].as_str().unwrap());
    let mut plan = executor_resume::prepare(&cases[0]["row"], &cases[0]["defaults"], None).unwrap();
    let mut authority = bridge(&root);
    let mut target = bridge(&root);
    plan.authorize(&root, &mut authority, &mut target).unwrap();
    let registry = JobRegistry::open(&root.join("jobs.db")).unwrap();
    plan.begin(&registry, "new-attempt", "now", Some(&mut target))
        .unwrap();
    let mut options = DispatchOptions::new(&root, "new-attempt");
    options.brief_text = "fixture task".into();
    options.worktrees_root = Some(root.join("worktrees"));
    options.artifacts_root = Some(root.join("artifacts"));
    let mut context = DispatchContext {
        registry: Some((&registry, "current")),
        ..Default::default()
    };
    let outcome = plan
        .dispatch(&options, &mut context, |_, _| {
            Ok(CodexAttempt {
                exit_code: 1,
                retryable: false,
                blocked_reason: Some("fixture-blocked".into()),
                ..Default::default()
            })
        })
        .unwrap();
    assert_eq!(outcome.status, "blocked");
    let final_options = handoff_packet::executor_finalize::FinalizeOptions {
        artifacts_root: Some(root.join("artifacts")),
        ..Default::default()
    };
    let finalized = handoff_packet::executor_finalize::finalize_dispatch(
        outcome.worktree.as_ref().unwrap(),
        &outcome,
        &final_options,
        None,
        Some((&registry, "current")),
    )
    .unwrap();
    assert_eq!(finalized.action, "preserved");
    let events = fs::read_to_string(root.join("events.jsonl")).unwrap();
    let event: Value = serde_json::from_str(events.lines().next().unwrap()).unwrap();
    assert_eq!(event[0], "job_resumed");
    assert_eq!(event[1]["job_id"], "current");
    assert_eq!(event[1]["args"]["verify_cmds"], json!(["unit", "lint"]));
    let metadata: String = registry
        .connection()
        .query_row(
            "SELECT ai_run_metadata FROM jobs WHERE job_id='current'",
            [],
            |r| r.get(0),
        )
        .unwrap();
    assert_eq!(
        serde_json::from_str::<Value>(&metadata).unwrap()["dispatch_ids"],
        json!(["older", "old-attempt", "new-attempt"])
    );
}

#[test]
fn malformed_saved_rows_and_timeout_policy_refuse() {
    let (_scratch, cases) = setup();
    for saved in ["[]", "null", "{", r#"{"dispatch_brief":null}"#] {
        let mut row = cases[0]["row"].clone();
        row["dispatch_options_json"] = json!(saved);
        assert!(
            executor_resume::prepare(&row, &cases[0]["defaults"], None).is_err(),
            "{saved}"
        );
    }
    let mut row = cases[0]["row"].clone();
    row["dispatch_brief_path"] = Value::Null;
    assert!(executor_resume::prepare(&row, &cases[0]["defaults"], None).is_err());
    let root = PathBuf::from(cases[0]["row"]["repo_root"].as_str().unwrap());
    fs::create_dir(root.join("config")).unwrap();
    fs::write(
        root.join("config/mir-executor.local.json"),
        r#"{"timeout_seconds_range":[1,600]}"#,
    )
    .unwrap();
    assert!(
        executor_resume::prepare(&cases[0]["row"], &cases[0]["defaults"], Some(json!(601)))
            .is_err()
    );
}
