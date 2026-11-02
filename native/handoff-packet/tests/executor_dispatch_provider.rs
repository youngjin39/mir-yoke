use handoff_packet::{
    executor_dispatch_provider::{
        ClaudeOptions, CodexRequest, claude_attempt, codex_attempt, codex_call_options,
        resolve_route, resolve_route_with_agent,
    },
    executor_policy::Policy,
    executor_transport::CallOptions,
};
use serde_json::{Value, json};
use std::{
    fs,
    io::Write,
    path::PathBuf,
    process::{Command, Stdio},
    sync::atomic::{AtomicU64, Ordering},
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

struct Scratch(PathBuf);
static SCRATCH_SERIAL: AtomicU64 = AtomicU64::new(0);
impl Scratch {
    fn new() -> Self {
        let base = std::env::var_os("MIR_NATIVE_TEST_SCRATCH")
            .map(PathBuf::from)
            .unwrap_or_else(std::env::temp_dir);
        fs::create_dir_all(&base).unwrap();
        let root = fs::canonicalize(base).unwrap().join(format!(
            "provider-fixture-{}-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos(),
            SCRATCH_SERIAL.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&root).unwrap();
        Self(root)
    }
}
impl Drop for Scratch {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

fn fixture(mode: &str) -> Command {
    let python = ["python3", "python"]
        .into_iter()
        .find(|name| {
            Command::new(name)
                .arg("--version")
                .output()
                .is_ok_and(|o| o.status.success())
        })
        .expect("Python required");
    let mut command = Command::new(python);
    command
        .arg(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/tests/fixtures/executor_dispatch_claude.py"
        ))
        .arg(mode);
    command
}

#[test]
fn codex_builder_defaults_and_route_match_python() {
    let scratch = Scratch::new();
    for agent in [
        None,
        Some(json!({"sandbox":"read-only", "base_instructions":"fixture instructions"})),
    ] {
        let mut request = CodexRequest::new("fixture prompt", &scratch.0);
        request.agent_route = agent.as_ref();
        if agent.is_some() {
            request.model = Some("fixture-model");
            request.reasoning_effort = Some("high");
            request.timeout = Some(Duration::from_secs(10));
            request.stall_timeout = Some(Duration::from_secs(5));
        }
        let options = codex_call_options(&scratch.0, &request).unwrap();
        let observed = json!({"prompt":options.prompt,"cwd":options.cwd,"sandbox":options.sandbox,"approval_policy":options.approval_policy,"model":options.model,"base_instructions":options.base_instructions,"config":options.config,"timeout":options.timeout.map(|d|d.as_secs_f64()),"stall_timeout":options.stall_timeout.map(|d|d.as_secs_f64())});
        let mut oracle = fixture("codex_options_oracle")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .spawn()
            .unwrap();
        oracle.stdin.take().unwrap().write_all(json!({"root":scratch.0,"cwd":scratch.0,"prompt":request.prompt,"agent":agent,"model":request.model,"effort":request.reasoning_effort,"timeout":request.timeout.map(|d|d.as_secs_f64()),"stall_timeout":request.stall_timeout.map(|d|d.as_secs_f64())}).to_string().as_bytes()).unwrap();
        let output = oracle.wait_with_output().unwrap();
        assert!(output.status.success());
        let expected: Value = serde_json::from_slice(&output.stdout).unwrap();
        assert_eq!(observed, expected);
    }
    fs::create_dir_all(scratch.0.join("config")).unwrap();
    fs::write(
        scratch.0.join("config/mir-executor.local.json"),
        r#"{"codex_sandbox_default":"invalid"}"#,
    )
    .unwrap();
    assert!(codex_call_options(&scratch.0, &CodexRequest::new("x", &scratch.0)).is_err());
    fs::write(
        scratch.0.join("config/mir-executor.local.json"),
        r#"{"timeout_seconds_range":[1,20]}"#,
    )
    .unwrap();
    let mut request = CodexRequest::new("x", &scratch.0);
    request.timeout = Some(Duration::from_secs(30));
    assert!(codex_call_options(&scratch.0, &request).is_err());
}

#[test]
fn claude_arguments_environment_and_nonzero_exit() {
    let cwd = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let options = ClaudeOptions {
        cwd: cwd.clone(),
        target_agent: Some("fixture-agent".into()),
        model: Some("fixture-model".into()),
        reasoning_effort: Some("high".into()),
        timeout: Some(Duration::from_secs(10)),
    };
    let result = claude_attempt(fixture("claude"), &options).unwrap();
    assert_eq!(result.exit_code, 7);
    assert_eq!(result.stderr, "fixture diagnostic\n");
    let output: Value = serde_json::from_str(&result.stdout).unwrap();
    assert_eq!(
        output["argv"],
        json!([
            "--agent",
            "fixture-agent",
            "--model",
            "fixture-model",
            "--effort",
            "high",
            "-p",
            "Read the task brief at .mir-dispatch/brief.md and implement it fully in this worktree. Do not edit tasks/plan.md."
        ])
    );
    assert_eq!(output["project"], cwd.to_str().unwrap());
    assert_eq!(output["cwd"], cwd.to_str().unwrap());
    assert_eq!(output["text"], "completed \u{2713}");
}

#[test]
fn claude_timeout_reaps_and_matches_python_output_shape() {
    let options = ClaudeOptions {
        cwd: PathBuf::from(env!("CARGO_MANIFEST_DIR")),
        timeout: Some(Duration::from_secs(2)),
        ..Default::default()
    };
    let started = Instant::now();
    let result = claude_attempt(fixture("timeout"), &options).unwrap();
    assert_eq!(result.exit_code, 124);
    assert!(result.stdout.is_empty());
    assert!(result.stderr.starts_with("Command '["));
    assert!(result.stderr.ends_with("timed out after 2 seconds"));
    assert!(started.elapsed() < Duration::from_secs(10));
    let command = fixture("timeout");
    let mut argv: Vec<_> = std::iter::once(command.get_program())
        .chain(command.get_args())
        .map(|arg| arg.to_str().unwrap().to_owned())
        .collect();
    argv.extend([
        "-p".into(),
        handoff_packet::executor_dispatch_provider::CLAUDE_PROMPT.into(),
    ]);
    let mut oracle = fixture("claude_oracle")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()
        .unwrap();
    oracle
        .stdin
        .take()
        .unwrap()
        .write_all(
            json!({"command":argv,"cwd":options.cwd,"timeout":2})
                .to_string()
                .as_bytes(),
        )
        .unwrap();
    let output = oracle.wait_with_output().unwrap();
    assert!(output.status.success());
    let expected: Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(expected["exit_code"], result.exit_code);
    assert_eq!(expected["stdout"], result.stdout);
    assert_eq!(expected["stderr"], result.stderr);
}

#[test]
fn codex_metadata_and_failure_classification() {
    let mut options = CallOptions::new("fixture prompt", ".");
    options.model = Some("requested".into());
    options.timeout = Some(Duration::from_secs(10));
    let result = codex_attempt(
        fixture("codex"),
        options,
        Duration::from_secs(10),
        Duration::from_secs(1),
        None,
    )
    .unwrap();
    assert_eq!(result.exit_code, 0);
    assert_eq!(result.stdout, "completed \u{2713}");
    assert_eq!(
        result.tokens_used,
        vec![("input_tokens".into(), 12), ("output_tokens".into(), 3)]
    );
    assert_eq!(result.model_id.as_deref(), Some("resolved"));
    assert_eq!(result.mcp_protocol.as_deref(), Some("app-server"));
    assert_eq!(result.tool_version.as_deref(), Some("fixture/1"));
    let missing = Command::new("mir-nonexistent-provider-fixture");
    let result = codex_attempt(
        missing,
        CallOptions::new("x", "."),
        Duration::from_secs(10),
        Duration::from_secs(1),
        None,
    )
    .unwrap();
    assert_eq!(result.exit_code, 1);
    assert!(result.lane_unavailable);
    assert!(!result.retryable);
    assert_eq!(result.error_sig.len(), 12);
    let mut oracle = fixture("oracle")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()
        .unwrap();
    oracle
        .stdin
        .take()
        .unwrap()
        .write_all(
            json!({"raw":{"usage":{"inputTokens":12,"outputTokens":3}},"stderr":result.stderr})
                .to_string()
                .as_bytes(),
        )
        .unwrap();
    let output = oracle.wait_with_output().unwrap();
    assert!(output.status.success());
    let expected: Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(expected["signature"], result.error_sig);
    assert_eq!(
        expected["tokens"],
        json!([["input_tokens", 12], ["output_tokens", 3]])
    );
}

#[test]
fn existing_policy_owns_backend_precedence() {
    let policy = Policy::resolve(&json!({"delegation":{"mode":"force_claude"}}));
    let route = resolve_route(
        std::path::Path::new(env!("CARGO_MANIFEST_DIR")),
        &policy,
        None,
        Some("codex"),
        None,
        None,
    )
    .unwrap();
    assert_eq!(route.backend, "claude");
    assert!(route.agent.is_none());
    let agent = json!({"target_agent":"fixture-agent","execution_backend":"claude","model":"fixture-model","sandbox":"read-only","base_instructions":"fixture instructions"});
    for (mode, expected) in [
        ("force_codex", "codex"),
        ("force_claude", "claude"),
        ("user_command_priority", "codex"),
        ("per_project", "claude"),
    ] {
        let policy = Policy::resolve(
            &json!({"delegation":{"mode":mode}, "per_project":{"fixture":"codex"}}),
        );
        let result = resolve_route_with_agent(
            &policy,
            Some(agent.clone()),
            Some("codex"),
            Some("fixture"),
            None,
        );
        assert_eq!(result.backend, expected, "{mode}");
        assert_eq!(
            result.agent,
            Some(agent.clone()),
            "{mode}: route metadata lost"
        );
    }
    let scratch = Scratch::new();
    let agents = scratch.0.join(".claude/agents");
    fs::create_dir_all(&agents).unwrap();
    fs::write(agents.join("fixture-agent.md"), "---\nexecution_backend: claude\nmodel: fixture-model\ndisallowedTools: Write, Edit\n---\nFixture instructions.\n").unwrap();
    let policy = Policy::resolve(&json!({"mode":"per_project"}));
    let result = resolve_route(
        &scratch.0,
        &policy,
        Some("fixture-agent"),
        Some("codex"),
        None,
        Some("codex"),
    )
    .unwrap();
    assert_eq!(result.backend, "claude");
    let metadata = result.agent.unwrap();
    assert_eq!(metadata["model"], "fixture-model");
    assert_eq!(metadata["sandbox"], "read-only");
    assert_eq!(metadata["base_instructions"], "Fixture instructions.");
}

#[test]
fn codex_events_and_retryable_transport_errors() {
    let scratch = Scratch::new();
    let events = scratch.0.join("events.jsonl");
    let result = codex_attempt(
        fixture("codex"),
        CallOptions::new("fixture prompt", "."),
        Duration::from_secs(10),
        Duration::from_secs(1),
        Some(&events),
    )
    .unwrap();
    assert_eq!(result.exit_code, 0);
    let raw = fs::read_to_string(&events).unwrap();
    let events: Vec<Value> = raw
        .lines()
        .map(|line| serde_json::from_str(line).unwrap())
        .collect();
    assert!(events.iter().any(|event| event["event"] == "progress"));
    let last = events.last().unwrap();
    assert_eq!(last["threadId"], "thread-fixture");
    assert_eq!(last["exit_code"], 0);
    assert_eq!(last["lane_unavailable"], false);
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        assert_eq!(
            fs::metadata(scratch.0.join("events.jsonl"))
                .unwrap()
                .permissions()
                .mode()
                & 0o777,
            0o600
        );
    }
    for (mode, expected_exit) in [("codex_error", 1), ("codex_timeout", 124)] {
        let mut options = CallOptions::new("fixture prompt", ".");
        options.timeout = Some(Duration::from_secs(2));
        let started = Instant::now();
        let result = codex_attempt(
            fixture(mode),
            options,
            Duration::from_secs(10),
            Duration::from_secs(1),
            None,
        )
        .unwrap();
        assert_eq!(result.exit_code, expected_exit, "{mode}");
        assert!(!result.lane_unavailable, "{mode}");
        assert!(result.retryable, "{mode}");
        assert_eq!(result.error_sig.len(), 12);
        assert!(started.elapsed() < Duration::from_secs(10));
    }
}
