//! Explicit-command provider adapters for dispatch. No executable discovery or CLI wiring.
//! Commands and their inherited environment belong to the embedding caller.
use crate::{
    executor_dispatch::CodexAttempt,
    executor_local::LocalConfig,
    executor_policy::{self, Policy},
    executor_transport::{CallOptions, Client, Error as TransportError},
};
use serde_json::{Value, json};
use std::{
    io::{self, Read},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    thread,
    time::{Duration, Instant},
};

pub const CLAUDE_PROMPT: &str = "Read the task brief at .mir-dispatch/brief.md and implement it fully in this worktree. Do not edit tasks/plan.md.";
pub const CODEX_BASE_INSTRUCTIONS: &str = "You are a code-implementation sub-agent in an isolated git worktree for the Mir harness. Read .mir-dispatch/brief.md and implement the task fully. Rules: modify only files inside this worktree, never edit tasks/plan.md, follow existing code style and structure, keep changes minimal and scoped to the brief, when tests are specified make them pass. Report a concise summary of what you changed.";

#[derive(Debug)]
pub enum Error {
    Io(io::Error),
    Local(crate::executor_local::Error),
    Policy(String),
    Output(String),
}
impl std::fmt::Display for Error {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Io(e) => e.fmt(f),
            Self::Local(e) => e.fmt(f),
            Self::Policy(s) | Self::Output(s) => f.write_str(s),
        }
    }
}
impl std::error::Error for Error {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::Io(e) => Some(e),
            Self::Local(e) => Some(e),
            Self::Policy(_) | Self::Output(_) => None,
        }
    }
}
impl From<io::Error> for Error {
    fn from(error: io::Error) -> Self {
        Self::Io(error)
    }
}
pub type Result<T> = std::result::Result<T, Error>;

pub struct CodexRequest<'a> {
    pub prompt: &'a str,
    pub cwd: &'a Path,
    pub agent_route: Option<&'a Value>,
    pub model: Option<&'a str>,
    pub reasoning_effort: Option<&'a str>,
    pub timeout: Option<Duration>,
    pub stall_timeout: Option<Duration>,
}
impl<'a> CodexRequest<'a> {
    pub fn new(prompt: &'a str, cwd: &'a Path) -> Self {
        Self {
            prompt,
            cwd,
            agent_route: None,
            model: None,
            reasoning_effort: None,
            timeout: None,
            stall_timeout: None,
        }
    }
}

/// Build dispatch defaults separately from the transport's general-purpose defaults.
pub fn codex_call_options(root: &Path, request: &CodexRequest<'_>) -> Result<CallOptions> {
    let local = LocalConfig::load(root).map_err(Error::Local)?;
    for timeout in [request.timeout, request.stall_timeout] {
        local
            .validate_timeout(timeout.map(|d| json!(d.as_secs_f64())).as_ref())
            .map_err(Error::Local)?;
    }
    let route_sandbox = request
        .agent_route
        .and_then(|route| route["sandbox"].as_str())
        .filter(|sandbox| !sandbox.is_empty());
    let sandbox = match route_sandbox {
        Some(sandbox) => sandbox,
        None => match local.raw().get("codex_sandbox_default") {
            Some(value) => value
                .as_str()
                .ok_or_else(|| Error::Policy("invalid codex_sandbox_default".into()))?,
            None => "workspace-write",
        },
    };
    if !matches!(
        sandbox,
        "workspace-write" | "read-only" | "danger-full-access"
    ) {
        return Err(Error::Policy("invalid codex_sandbox_default".into()));
    }
    let cwd = request
        .cwd
        .to_str()
        .ok_or_else(|| Error::Output("provider cwd is not UTF-8".into()))?;
    let mut options = CallOptions::new(request.prompt, cwd);
    options.sandbox = sandbox.into();
    options.approval_policy = "never".into();
    options.model = request.model.map(str::to_owned);
    options.base_instructions = match request.agent_route {
        Some(route) => route["base_instructions"].as_str().map(str::to_owned),
        None => Some(CODEX_BASE_INSTRUCTIONS.into()),
    };
    let mut config = json!({"project_doc_max_bytes":0});
    if let Some(effort) = request.reasoning_effort {
        config["model_reasoning_effort"] = effort.into();
    }
    options.config = Some(config);
    options.timeout = request.timeout;
    options.stall_timeout = request.stall_timeout;
    Ok(options)
}

#[derive(Debug)]
pub struct ResolvedRoute {
    pub backend: String,
    pub agent: Option<Value>,
    pub warning: String,
}

/// Preserve the shared policy's forced lane, user, project and agent precedence.
/// Local bridge route overrides, if any, must be resolved by the embedding caller.
pub fn resolve_route(
    root: &Path,
    policy: &Policy,
    target_agent: Option<&str>,
    requested: Option<&str>,
    project_slug: Option<&str>,
    declared_backend: Option<&str>,
) -> Result<ResolvedRoute> {
    let (agent, warning) = match target_agent {
        Some(name) => executor_policy::agent_route(root, name, policy).map_err(Error::Policy)?,
        None => (None, String::new()),
    };
    let mut resolved =
        resolve_route_with_agent(policy, agent, requested, project_slug, declared_backend);
    resolved.warning = warning;
    Ok(resolved)
}

/// Select a backend after the caller resolves a target-local route hook. Route
/// metadata, including narrowed sandbox and explicit model, is retained verbatim.
pub fn resolve_route_with_agent(
    policy: &Policy,
    agent: Option<Value>,
    requested: Option<&str>,
    project_slug: Option<&str>,
    declared_backend: Option<&str>,
) -> ResolvedRoute {
    let backend = policy.backend(
        requested,
        project_slug,
        declared_backend,
        agent.as_ref().and_then(|a| a["execution_backend"].as_str()),
    );
    ResolvedRoute {
        backend,
        agent,
        warning: String::new(),
    }
}

fn signature(text: &str) -> String {
    if text.is_empty() {
        return String::new();
    }
    let lines: Vec<_> = crate::lines(text).collect();
    crate::digest::sha256(
        lines[lines.len().saturating_sub(20)..]
            .join("\n")
            .as_bytes(),
    )[..12]
        .into()
}

fn tokens(raw: &Value) -> Vec<(String, i64)> {
    let usage = raw.get("usage").unwrap_or(&Value::Null);
    let source = if usage.is_object() {
        usage
            .get("last")
            .or_else(|| usage.get("total"))
            .unwrap_or(usage)
    } else {
        raw
    };
    let source = if source.is_object() { source } else { raw };
    [
        (
            "input_tokens",
            &["input_tokens", "inputTokens", "prompt_tokens"][..],
        ),
        (
            "output_tokens",
            &["output_tokens", "outputTokens", "completion_tokens"][..],
        ),
        ("total_tokens", &["total_tokens", "totalTokens"][..]),
    ]
    .into_iter()
    .filter_map(|(target, aliases)| {
        aliases
            .iter()
            .find_map(|name| source[*name].as_i64().filter(|n| *n >= 0))
            .map(|n| (target.to_owned(), n))
    })
    .collect()
}

fn event(path: Option<&Path>, value: &Value) -> Result<()> {
    if let Some(path) = path {
        let layout = if value["event"] == "progress" {
            r#"{"transport":null,"event":null,"duration_s":null,"method":null}"#
        } else {
            r#"{"exit_code":null,"duration_s":null,"error_sig":null,"transport":null,"threadId":null,"lane_unavailable":null}"#
        };
        let text = crate::executor_ledger_json::render(layout, value).map_err(Error::Output)?;
        let text = crate::executor_worktree::compact_json(&text)
            .map_err(|e| Error::Output(e.to_string()))?;
        crate::executor_worktree::secure_write(path, &text, true)
            .map_err(|e| Error::Output(e.to_string()))?;
    }
    Ok(())
}

fn unavailable(error: &TransportError) -> bool {
    matches!(
        error,
        TransportError::Spawn {
            kind: std::io::ErrorKind::NotFound | std::io::ErrorKind::PermissionDenied,
            ..
        }
    )
}

/// Run one app-server turn, preserving transport metadata and error classes.
/// The optional event file's parent must already exist; event write errors surface.
pub fn codex_attempt(
    command: Command,
    mut options: CallOptions,
    initialize_timeout: Duration,
    kill_timeout: Duration,
    events_file: Option<&Path>,
) -> Result<CodexAttempt> {
    let started = Instant::now();
    let requested_model = options.model.clone();
    options.approval_policy = "never".into();
    let mut progress_error = None;
    let result = match Client::spawn(command, initialize_timeout, kill_timeout) {
        Ok(mut client) => {
            let result = client.call(options, &mut |method, _| {
                match event(events_file, &json!({"transport":"app-server", "event":"progress", "duration_s":started.elapsed().as_secs_f64(), "method":method})) {
                    Ok(()) => Ok(()),
                    Err(error) => {
                        let message = error.to_string();
                        progress_error = Some(error);
                        Err(message)
                    }
                }
            });
            client.close();
            result
        }
        Err(error) => Err(error),
    };
    if let Some(error) = progress_error {
        return Err(error);
    }
    let (attempt, thread_id) = match result {
        Ok(result) => {
            let raw_tokens = result
                .token_usage
                .as_ref()
                .filter(|usage| usage.as_object().is_some_and(|object| !object.is_empty()))
                .map(|usage| json!({"usage":usage}));
            let attempt = CodexAttempt {
                stdout: result.content_text,
                tokens_used: tokens(raw_tokens.as_ref().unwrap_or(&result.raw_result)),
                model_id: result
                    .model_id
                    .or_else(|| result.raw_result["model"].as_str().map(str::to_owned))
                    .or(requested_model),
                mcp_protocol: Some("app-server".into()),
                tool_version: result.tool_version.or_else(|| {
                    result.raw_result["tool_version"]
                        .as_str()
                        .map(str::to_owned)
                }),
                ..Default::default()
            };
            (attempt, Some(result.thread_id))
        }
        Err(error) => {
            let lane_unavailable = unavailable(&error);
            let stderr = error.to_string();
            (
                CodexAttempt {
                    exit_code: if matches!(error, TransportError::Timeout(_)) {
                        124
                    } else {
                        1
                    },
                    error_sig: signature(&stderr),
                    stderr,
                    lane_unavailable,
                    retryable: !lane_unavailable,
                    ..Default::default()
                },
                None,
            )
        }
    };
    event(
        events_file,
        &json!({"exit_code":attempt.exit_code,"duration_s":started.elapsed().as_secs_f64(),"error_sig":attempt.error_sig,"transport":"app-server","threadId":thread_id,"lane_unavailable":attempt.lane_unavailable}),
    )?;
    Ok(attempt)
}

#[derive(Debug, Default)]
pub struct ClaudeOptions {
    pub cwd: PathBuf,
    pub target_agent: Option<String>,
    pub model: Option<String>,
    pub reasoning_effort: Option<String>,
    pub timeout: Option<Duration>,
}

struct RunningChild(Child);
impl Drop for RunningChild {
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}

fn capture(mut reader: impl Read) -> io::Result<Vec<u8>> {
    let mut bytes = Vec::new();
    reader.read_to_end(&mut bytes)?;
    Ok(bytes)
}
fn text(worker: thread::JoinHandle<io::Result<Vec<u8>>>) -> Result<String> {
    let bytes = worker
        .join()
        .map_err(|_| Error::Output("provider output reader panicked".into()))??;
    String::from_utf8(bytes)
        .map(|s| s.replace("\r\n", "\n").replace('\r', "\n"))
        .map_err(|e| Error::Output(e.to_string()))
}

fn python_repr(text: &str) -> String {
    let quote = if text.contains('\'') && !text.contains('"') {
        '"'
    } else {
        '\''
    };
    let mut result = quote.to_string();
    for c in text.chars() {
        match c {
            '\\' => result.push_str("\\\\"),
            '\n' => result.push_str("\\n"),
            '\r' => result.push_str("\\r"),
            '\t' => result.push_str("\\t"),
            c if c == quote => {
                result.push('\\');
                result.push(c);
            }
            c if c.is_control() => {
                let n = c as u32;
                result.push_str(&if n <= 0xff {
                    format!("\\x{n:02x}")
                } else if n <= 0xffff {
                    format!("\\u{n:04x}")
                } else {
                    format!("\\U{n:08x}")
                });
            }
            c => result.push(c),
        }
    }
    result.push(quote);
    result
}

/// Run headless Claude with argv and environment rather than a shell.
/// Timeout kills and reaps the direct child on every platform. Descendant processes
/// retaining inherited pipes are outside this adapter's supported process contract.
pub fn claude_attempt(mut command: Command, options: &ClaudeOptions) -> Result<CodexAttempt> {
    for (flag, value) in [
        ("--agent", &options.target_agent),
        ("--model", &options.model),
        ("--effort", &options.reasoning_effort),
    ] {
        if let Some(value) = value {
            command.args([flag, value]);
        }
    }
    command
        .args(["-p", CLAUDE_PROMPT])
        .current_dir(&options.cwd)
        .env("CLAUDE_PROJECT_DIR", &options.cwd)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    let argv = std::iter::once(command.get_program())
        .chain(command.get_args())
        .map(|arg| {
            arg.to_str()
                .map(python_repr)
                .ok_or_else(|| Error::Output("provider command is not UTF-8".into()))
        })
        .collect::<Result<Vec<_>>>()?;
    let command_repr = format!("[{}]", argv.join(", "));
    let mut child = RunningChild(command.spawn()?);
    let stdout = child
        .0
        .stdout
        .take()
        .ok_or_else(|| Error::Output("provider stdout unavailable".into()))?;
    let stderr = child
        .0
        .stderr
        .take()
        .ok_or_else(|| Error::Output("provider stderr unavailable".into()))?;
    let out = thread::spawn(move || capture(stdout));
    let err = thread::spawn(move || capture(stderr));
    let started = Instant::now();
    let (exit_code, timed_out) = loop {
        if let Some(status) = child.0.try_wait()? {
            #[cfg(unix)]
            let code = {
                use std::os::unix::process::ExitStatusExt;
                status
                    .code()
                    .unwrap_or_else(|| -status.signal().unwrap_or(1))
            };
            #[cfg(not(unix))]
            let code = status.code().unwrap_or(-1);
            break (code, false);
        }
        if options
            .timeout
            .is_some_and(|timeout| started.elapsed() >= timeout)
        {
            child.0.kill()?;
            child.0.wait()?;
            break (124, true);
        }
        thread::sleep(Duration::from_millis(10));
    };
    let mut stdout = text(out)?;
    let mut stderr = text(err)?;
    if timed_out && !cfg!(windows) {
        // POSIX TimeoutExpired retains bytes despite text=True, which the Python
        // adapter discards. Windows run() collects text after kill/communicate;
        // preserve both captured streams there, including empty stderr.
        stdout.clear();
        let seconds = options
            .timeout
            .map(|timeout| timeout.as_secs_f64())
            .unwrap_or(0.0);
        stderr = format!("Command '{command_repr}' timed out after {seconds} seconds");
    }
    Ok(CodexAttempt {
        exit_code,
        stdout,
        stderr,
        ..Default::default()
    })
}

#[cfg(test)]
mod spawn_error_tests {
    use super::*;

    #[test]
    fn spawn_classification_uses_kind_without_os_code() {
        for (kind, expected) in [
            (std::io::ErrorKind::NotFound, true),
            (std::io::ErrorKind::PermissionDenied, true),
            (std::io::ErrorKind::InvalidInput, false),
        ] {
            let error = TransportError::from(std::io::Error::new(kind, "program not found"));
            assert_eq!(unavailable(&error), expected, "{error:?}");
            assert_eq!(error.to_string(), "program not found");
            assert_eq!(error.python_class(), "CodexMcpProcessError");
        }
        assert!(!unavailable(&TransportError::Process(
            "program not found".into()
        )));
    }
}
