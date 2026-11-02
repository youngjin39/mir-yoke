//! Isolated attempt orchestration. Providers and finalization remain caller-owned.
use crate::{
    executor_local::LocalConfig,
    executor_registry::JobRegistry,
    executor_worktree::{self, DispatchWorktree},
    local_bridge::LocalBridge,
};
use serde_json::{Value, json};
use std::{
    fmt,
    path::{Path, PathBuf},
    time::Instant,
};

pub const MAX_CODEX_ATTEMPTS: i64 = 1;
pub const OUTAGE_THRESHOLD: i64 = 3;

/// Count newest-leading execution failures, optionally scoped to a change prefix.
pub fn count_consecutive_codex_failures(
    jobs_db_path: &Path,
    change_id_prefix: &str,
) -> Result<usize> {
    let registry = JobRegistry::open(jobs_db_path).map_err(Error::Registry)?;
    let mut statement = registry
        .connection()
        .prepare("SELECT change_id,status,stderr FROM jobs ORDER BY started_at DESC")
        .map_err(|e| Error::Registry(e.into()))?;
    let jobs = statement
        .query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, Option<String>>(2)?,
            ))
        })
        .map_err(|e| Error::Registry(e.into()))?;
    let mut count = 0;
    for job in jobs {
        let (change, status, stderr) = job.map_err(|e| Error::Registry(e.into()))?;
        if !change.starts_with(change_id_prefix) {
            continue;
        }
        let completed = stderr
            .as_deref()
            .unwrap_or("")
            .split_whitespace()
            .find_map(|token| token.strip_prefix("dispatch_status="))
            == Some("completed");
        if status != "failed" || completed {
            break;
        }
        count += 1;
    }
    Ok(count)
}
#[derive(Debug)]
pub enum Error {
    Local(crate::executor_local::Error),
    Worktree(executor_worktree::Error),
    Bridge(crate::local_bridge::BridgeError),
    Registry(crate::executor_registry::Error),
    Json(serde_json::Error),
    Hook { kind: String, message: String },
    Invalid(String),
    Type(String),
    Runner(String),
}
impl Error {
    pub fn kind(&self) -> &str {
        match self {
            Self::Local(e) => e.kind(),
            Self::Worktree(e) => e.kind(),
            Self::Hook { kind, .. } => kind,
            Self::Invalid(_) | Self::Json(_) => "ValueError",
            Self::Type(_) => "TypeError",
            Self::Bridge(_) | Self::Registry(_) | Self::Runner(_) => "RuntimeError",
        }
    }
}
impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Local(e) => e.fmt(f),
            Self::Worktree(e) => e.fmt(f),
            Self::Bridge(e) => e.fmt(f),
            Self::Json(e) => e.fmt(f),
            Self::Registry(e) => write!(f, "registry error: {e:?}"),
            Self::Hook { message, .. }
            | Self::Invalid(message)
            | Self::Type(message)
            | Self::Runner(message) => f.write_str(message),
        }
    }
}
impl std::error::Error for Error {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::Local(e) => Some(e),
            Self::Worktree(e) => Some(e),
            Self::Bridge(e) => Some(e),
            Self::Json(e) => Some(e),
            Self::Registry(_)
            | Self::Hook { .. }
            | Self::Invalid(_)
            | Self::Type(_)
            | Self::Runner(_) => None,
        }
    }
}
pub type Result<T> = std::result::Result<T, Error>;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CodexAttempt {
    pub exit_code: i32,
    pub error_sig: String,
    pub stdout: String,
    pub stderr: String,
    pub lane_unavailable: bool,
    pub retryable: bool,
    pub blocked_reason: Option<String>,
    pub tokens_used: Vec<(String, i64)>,
    pub model_id: Option<String>,
    pub mcp_protocol: Option<String>,
    pub tool_version: Option<String>,
}
impl Default for CodexAttempt {
    fn default() -> Self {
        Self {
            exit_code: 0,
            error_sig: String::new(),
            stdout: String::new(),
            stderr: String::new(),
            lane_unavailable: false,
            retryable: true,
            blocked_reason: None,
            tokens_used: vec![],
            model_id: None,
            mcp_protocol: None,
            tool_version: None,
        }
    }
}
impl CodexAttempt {
    pub fn to_value(&self) -> Value {
        json!({"exit_code":self.exit_code,"error_sig":self.error_sig,"stdout":self.stdout,"stderr":self.stderr,"lane_unavailable":self.lane_unavailable,"retryable":self.retryable,"blocked_reason":self.blocked_reason,"tokens_used":self.tokens_used,"model_id":self.model_id,"mcp_protocol":self.mcp_protocol,"tool_version":self.tool_version})
    }
    /// Target hook replies may carry extra fields; known fields retain strict types.
    pub fn from_value(v: &Value) -> Result<Self> {
        if !v.is_object() {
            return Err(Error::Type("invalid CodexAttempt result".into()));
        }
        let mut out = Self::default();
        if let Some(n) = v.get("exit_code") {
            out.exit_code = n
                .as_i64()
                .and_then(|n| i32::try_from(n).ok())
                .ok_or_else(|| Error::Type("invalid CodexAttempt exit_code".into()))?;
        }
        for (name, dest) in [
            ("error_sig", &mut out.error_sig),
            ("stdout", &mut out.stdout),
            ("stderr", &mut out.stderr),
        ] {
            if let Some(v) = v.get(name) {
                *dest = v
                    .as_str()
                    .ok_or_else(|| Error::Type(format!("invalid CodexAttempt {name}")))?
                    .into();
            }
        }
        for (name, dest) in [
            ("lane_unavailable", &mut out.lane_unavailable),
            ("retryable", &mut out.retryable),
        ] {
            if let Some(v) = v.get(name) {
                *dest = v
                    .as_bool()
                    .ok_or_else(|| Error::Type(format!("invalid CodexAttempt {name}")))?;
            }
        }
        for (name, dest) in [
            ("blocked_reason", &mut out.blocked_reason),
            ("model_id", &mut out.model_id),
            ("mcp_protocol", &mut out.mcp_protocol),
            ("tool_version", &mut out.tool_version),
        ] {
            if let Some(v) = v.get(name).filter(|v| !v.is_null()) {
                *dest = Some(
                    v.as_str()
                        .ok_or_else(|| Error::Type(format!("invalid CodexAttempt {name}")))?
                        .into(),
                );
            }
        }
        if let Some(tokens) = v.get("tokens_used") {
            out.tokens_used = tokens
                .as_array()
                .ok_or_else(|| Error::Type("invalid tokens_used".into()))?
                .iter()
                .map(|pair| {
                    let pair = pair
                        .as_array()
                        .filter(|p| p.len() == 2)
                        .ok_or_else(|| Error::Type("invalid token pair".into()))?;
                    Ok((
                        pair[0]
                            .as_str()
                            .ok_or_else(|| Error::Type("invalid token name".into()))?
                            .into(),
                        pair[1]
                            .as_i64()
                            .ok_or_else(|| Error::Type("invalid token count".into()))?,
                    ))
                })
                .collect::<Result<_>>()?;
        }
        Ok(out)
    }
}
#[derive(Debug, Clone)]
pub struct DispatchOutcome {
    pub status: String,
    pub attempts: usize,
    pub fell_back: bool,
    pub blocked_reason: Option<String>,
    pub worktree: Option<DispatchWorktree>,
    pub tokens_used: Vec<(String, i64)>,
    pub model_id: Option<String>,
    pub mcp_protocol: Option<String>,
    pub stdout: String,
    pub exit_code: Option<i32>,
    pub stderr: String,
}
impl DispatchOutcome {
    pub fn to_value(&self) -> Value {
        json!({"status":self.status,"attempts":self.attempts,"fell_back":self.fell_back,"blocked_reason":self.blocked_reason,"worktree":self.worktree.as_ref().map(worktree_value),"tokens_used":self.tokens_used,"model_id":self.model_id,"mcp_protocol":self.mcp_protocol,"stdout":self.stdout,"exit_code":self.exit_code,"stderr":self.stderr})
    }
}
#[derive(Debug, Clone)]
pub struct DispatchOptions {
    pub main_repo_root: PathBuf,
    pub dispatch_id: String,
    pub brief_text: String,
    pub base_commit: String,
    pub max_codex_attempts: i64,
    pub outage_threshold: i64,
    pub prior_consecutive_codex_failures: i64,
    pub dispatch_events_path: Option<PathBuf>,
    pub worktrees_root: Option<PathBuf>,
    pub artifacts_root: Option<PathBuf>,
}
impl DispatchOptions {
    pub fn new(root: impl Into<PathBuf>, id: impl Into<String>) -> Self {
        Self {
            main_repo_root: root.into(),
            dispatch_id: id.into(),
            brief_text: String::new(),
            base_commit: "HEAD".into(),
            max_codex_attempts: MAX_CODEX_ATTEMPTS,
            outage_threshold: OUTAGE_THRESHOLD,
            prior_consecutive_codex_failures: 0,
            dispatch_events_path: None,
            worktrees_root: None,
            artifacts_root: None,
        }
    }
}
#[derive(Default)]
pub struct DispatchContext<'a> {
    pub bridge: Option<&'a mut LocalBridge>,
    pub registry: Option<(&'a JobRegistry, &'a str)>,
    pub worktree: Option<DispatchWorktree>,
    pub provider_hook_applied: bool,
    pub event_errors: Vec<String>,
}
fn path_value(p: &Path) -> Value {
    json!({"$type":"path","value":p})
}
fn worktree_value(w: &DispatchWorktree) -> Value {
    json!({"dispatch_id":w.dispatch_id,"main_repo_root":w.main_repo_root,"path":w.path,"branch":w.branch,"base_commit":w.base_commit,"brief_path":w.brief_path,"status_path":w.status_path,"result_path":w.result_path})
}
fn worktree_wire(w: &DispatchWorktree) -> Value {
    json!({"$type":"dispatch_worktree","value":worktree_value(w)})
}
fn hook(
    c: &mut DispatchContext<'_>,
    name: &str,
    args: Vec<Value>,
    options: Value,
) -> Result<Value> {
    let Some(b) = c.bridge.as_deref_mut() else {
        return Ok(json!({"ok":true,"result":null,"handle":null}));
    };
    let reply = b.call(name, args, options).map_err(Error::Bridge)?;
    if reply["ok"] != true {
        return Err(Error::Hook {
            kind: reply["error"]["type"].as_str().unwrap_or("Error").into(),
            message: reply["error"]["message"].as_str().unwrap_or("").into(),
        });
    }
    Ok(reply)
}
fn event(c: &mut DispatchContext<'_>, name: &str, mut payload: Value) {
    payload["job_id"] = c.registry.map_or(Value::Null, |(_, id)| json!(id));
    if let Err(e) = hook(c, "on_job_event", vec![json!(name), payload], json!({})) {
        let message = format!("on_job_event {name}: {}: {e}", e.kind());
        eprintln!("[mir_executor] {message}");
        c.event_errors.push(message);
    }
}
fn state(
    c: &mut DispatchContext<'_>,
    w: &DispatchWorktree,
    name: &str,
    evidence: Value,
) -> Result<()> {
    executor_worktree::write_status(w, name, &evidence).map_err(Error::Worktree)?;
    event(
        c,
        "dispatch_state",
        json!({"dispatch_id":w.dispatch_id,"state":name,"evidence":evidence}),
    );
    Ok(())
}
fn append(p: &Path, v: Value) -> Result<()> {
    executor_worktree::secure_write(
        p,
        &(serde_json::to_string(&v).map_err(Error::Json)? + "\n"),
        true,
    )
    .map_err(Error::Worktree)
}
fn outcome(
    w: &DispatchWorktree,
    r: CodexAttempt,
    attempts: usize,
    reason: Option<String>,
) -> DispatchOutcome {
    DispatchOutcome {
        status: if reason.is_some() {
            "blocked"
        } else {
            "completed"
        }
        .into(),
        attempts,
        fell_back: false,
        blocked_reason: reason,
        worktree: Some(w.clone()),
        tokens_used: r.tokens_used,
        model_id: r.model_id,
        mcp_protocol: r.mcp_protocol,
        stdout: r.stdout,
        exit_code: Some(r.exit_code),
        stderr: r.stderr,
    }
}
/// Runs bounded attempts, retaining the checkout for inspection without finalizing it.
pub fn run_dispatch<F>(
    o: &DispatchOptions,
    c: &mut DispatchContext<'_>,
    mut runner: F,
) -> Result<DispatchOutcome>
where
    F: FnMut(&DispatchWorktree, usize) -> Result<CodexAttempt>,
{
    let result = run_scoped(o, c, &mut runner);
    if let Some((registry, id)) = c.registry {
        match &result {
            Ok(out) => {
                let previous = registry
                    .connection()
                    .query_row(
                        "SELECT ai_run_metadata FROM jobs WHERE job_id=?",
                        [id],
                        |row| row.get::<_, Option<String>>(0),
                    )
                    .map_err(|e| Error::Registry(e.into()))?;
                let previous: Value = previous
                    .map(|text| serde_json::from_str(&text))
                    .transpose()
                    .map_err(Error::Json)?
                    .unwrap_or(Value::Null);
                let mut dispatch_ids = Vec::<String>::new();
                for value in previous["dispatch_ids"]
                    .as_array()
                    .into_iter()
                    .flatten()
                    .chain(std::iter::once(&previous["dispatch_id"]))
                    .chain(std::iter::once(&json!(o.dispatch_id)))
                {
                    if let Some(value) = value.as_str()
                        && !dispatch_ids.iter().any(|id| id == value)
                    {
                        dispatch_ids.push(value.into());
                    }
                }
                registry.update_ai_run_metadata(id, &json!({
                    "model_id":out.model_id,"tokens_used":out.tokens_used.iter().cloned().collect::<std::collections::BTreeMap<_,_>>(),
                    "mcp_protocol":out.mcp_protocol,"dispatch_id":o.dispatch_id,"dispatch_ids":dispatch_ids
                })).map_err(Error::Registry)?;
            }
            Err(e) => {
                event(
                    c,
                    "dispatch_failed",
                    json!({"dispatch_id":o.dispatch_id,"error_type":e.kind(),"message":e.to_string()}),
                );
                let stderr = std::iter::once(e.to_string())
                    .chain(c.event_errors.iter().cloned())
                    .collect::<Vec<_>>()
                    .join("; ");
                registry
                    .update_status(id, "failed", &json!({"exit_code":1,"stderr":stderr}))
                    .map_err(Error::Registry)?;
            }
        }
    }
    result
}
fn run_scoped<F>(
    o: &DispatchOptions,
    c: &mut DispatchContext<'_>,
    runner: &mut F,
) -> Result<DispatchOutcome>
where
    F: FnMut(&DispatchWorktree, usize) -> Result<CodexAttempt>,
{
    let config = LocalConfig::load(&o.main_repo_root).map_err(Error::Local)?;
    // The reference validates the cap before the brief, then requires positivity.
    if o.max_codex_attempts >= 0 {
        match config.validate_attempts(o.max_codex_attempts as u64) {
            Err(crate::executor_local::Error::Invalid(s))
                if s == "max_codex_attempts must be positive" => {}
            other => other.map_err(Error::Local)?,
        }
    }
    hook(
        c,
        "validate_brief",
        vec![json!(o.brief_text), path_value(&o.main_repo_root)],
        json!({}),
    )?;
    if o.max_codex_attempts < 1 {
        return Err(Error::Invalid("max_codex_attempts must be positive".into()));
    }
    let scope = hook(
        c,
        "writer_scope",
        vec![path_value(&o.main_repo_root)],
        json!({}),
    )?;
    let handle = scope["handle"].as_str().map(str::to_owned);
    if let Some(h) = &handle {
        hook(
            c,
            "writer_scope.enter",
            vec![Value::Null],
            json!({"handles":{"0":h}}),
        )?;
    }
    let result = attempts(o, c, runner);
    if let Some(h) = handle {
        hook(
            c,
            "writer_scope.exit",
            vec![Value::Null],
            json!({"handles":{"0":h}}),
        )?;
    }
    result
}
fn attempts<F>(
    o: &DispatchOptions,
    c: &mut DispatchContext<'_>,
    runner: &mut F,
) -> Result<DispatchOutcome>
where
    F: FnMut(&DispatchWorktree, usize) -> Result<CodexAttempt>,
{
    let w = if let Some(w) = &c.worktree {
        w.clone()
    } else {
        let w = executor_worktree::create_dispatch_worktree(
            &o.main_repo_root,
            &o.dispatch_id,
            &o.base_commit,
            &o.brief_text,
            o.worktrees_root.as_deref(),
        )
        .map_err(Error::Worktree)?;
        c.worktree = Some(w.clone());
        w
    };
    event(
        c,
        "dispatch_state",
        json!({"dispatch_id":o.dispatch_id,"state":"started","evidence":{}}),
    );
    let events = o.dispatch_events_path.clone().unwrap_or_else(|| {
        o.artifacts_root.as_ref().map_or_else(
            || w.path.join(".mir-dispatch/dispatch-events.jsonl"),
            |p| p.join(&o.dispatch_id).join("dispatch-events.jsonl"),
        )
    });
    let budget = usize::try_from(o.max_codex_attempts)
        .map_err(|_| Error::Invalid("attempt budget exceeds platform capacity".into()))?;
    let mut last = CodexAttempt::default();
    for attempt in 1..=budget {
        event(
            c,
            "dispatch_state",
            json!({"dispatch_id":o.dispatch_id,"state":"running","evidence":{"attempt":attempt}}),
        );
        hook(
            c,
            "before_run",
            vec![worktree_wire(&w), json!(attempt)],
            json!({}),
        )?;
        let started = Instant::now();
        let mut r = runner(&w, attempt)?;
        if !c.provider_hook_applied {
            let tokens = r
                .tokens_used
                .iter()
                .cloned()
                .collect::<std::collections::BTreeMap<_, _>>();
            let reply = hook(
                c,
                "after_provider_call",
                vec![
                    json!({"$type":"codex_attempt","value":r.to_value()}),
                    json!({"prompt_sha256":crate::digest::sha256(o.brief_text.as_bytes()),"model":r.model_id,"reasoning_effort":null,"tool_version":r.tool_version,"attempt":attempt,"elapsed_seconds":started.elapsed().as_secs_f64(),"token_usage":if tokens.is_empty(){Value::Null}else{json!(tokens)}}),
                ],
                json!({}),
            )?;
            if !reply["result"].is_null() {
                let value = &reply["result"];
                r = CodexAttempt::from_value(if value["$type"] == "codex_attempt" {
                    &value["value"]
                } else {
                    value
                })?;
            } else if !reply["handle"].is_null() {
                return Err(Error::Type(
                    "after_provider_call returned an unsupported object".into(),
                ));
            }
        }
        hook(
            c,
            "after_run",
            vec![
                worktree_wire(&w),
                json!(attempt),
                json!({"$type":"codex_attempt","value":r.to_value()}),
            ],
            json!({}),
        )?;
        if r.exit_code == 0 {
            state(c, &w, "codex_completed", json!({"attempt":attempt}))?;
            append(
                &events,
                json!({"kind":"codex_success","dispatch_id":o.dispatch_id,"attempt":attempt}),
            )?;
            return Ok(outcome(&w, r, attempt, None));
        }
        append(
            &events,
            json!({"kind":"codex_failure","dispatch_id":o.dispatch_id,"attempt":attempt,"exit_code":r.exit_code,"error_sig":r.error_sig,"lane_unavailable":r.lane_unavailable,"retryable":r.retryable}),
        )?;
        let reason = if r.lane_unavailable {
            append(
                &events,
                json!({"kind":"lane_unavailable","dispatch_id":o.dispatch_id,"attempt":attempt}),
            )?;
            Some("lane-unavailable".to_owned())
        } else if !r.retryable {
            let reason = r
                .blocked_reason
                .as_ref()
                .filter(|s| !s.is_empty())
                .cloned()
                .unwrap_or_else(|| "non-retryable".into());
            append(
                &events,
                json!({"kind":"non_retryable_blocker","dispatch_id":o.dispatch_id,"attempt":attempt,"reason":reason}),
            )?;
            Some(reason)
        } else {
            None
        };
        if let Some(reason) = reason {
            state(c, &w, "blocked", json!({"reason":reason,"attempt":attempt}))?;
            return Ok(outcome(&w, r, attempt, Some(reason)));
        }
        last = r;
    }
    state(c, &w, "codex_failed", json!({"attempts":budget}))?;
    let consecutive = o
        .prior_consecutive_codex_failures
        .checked_add(1)
        .ok_or_else(|| Error::Invalid("consecutive failures overflow".into()))?;
    let reason = if consecutive >= o.outage_threshold {
        append(
            &events,
            json!({"kind":"codex_outage_halt","dispatch_id":o.dispatch_id,"consecutive_failures":consecutive,"threshold":o.outage_threshold}),
        )?;
        "codex-outage"
    } else {
        append(
            &events,
            json!({"kind":"retry_exhausted","dispatch_id":o.dispatch_id,"attempts":budget}),
        )?;
        "retry-exhausted"
    };
    state(c, &w, "blocked", json!({"reason":reason}))?;
    Ok(outcome(&w, last, budget, Some(reason.into())))
}
