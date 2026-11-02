//! Independent read-only review evidence for an embedding finalizer.
use crate::{
    executor_dispatch::CodexAttempt,
    executor_dispatch_provider::{Error, Result, codex_attempt},
    executor_transport::CallOptions,
};
use serde_json::{Value, json};
use std::{
    path::Path,
    process::Command,
    time::{Duration, Instant},
};

pub const BASE_INSTRUCTIONS: &str = "You are codex-final-reviewer in a separate read-only Mir session. Read .mir-dispatch/brief.md and inspect the current git diff. Check correctness, scope, security, tests, and regressions. Return only strict JSON with keys verdict ('pass' or 'fail'), reason (string), and findings (array of strings).";
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ReviewEvidence {
    pub passed: bool,
    pub reason: String,
    pub content: String,
    pub provider: String,
}
impl ReviewEvidence {
    pub fn to_value(&self) -> Value {
        json!({"passed":self.passed,"reason":self.reason,"content":self.content,"provider":self.provider})
    }
}
#[derive(Debug)]
pub struct ReviewOutput {
    pub evidence: ReviewEvidence,
    pub attempt: CodexAttempt,
    pub metadata: Value,
}
/// The first whitespace-delimited diagnostic value wins, including an empty value.
pub fn diagnostic_token<'a>(payload: Option<&'a str>, key: &str) -> Option<&'a str> {
    let prefix = format!("{key}=");
    payload
        .unwrap_or_default()
        .split_whitespace()
        .find_map(|token| token.strip_prefix(&prefix))
}
pub fn evidence(attempt: Option<&CodexAttempt>) -> ReviewEvidence {
    let mut result = ReviewEvidence {
        passed: false,
        reason: "reviewer-missing".into(),
        content: String::new(),
        provider: "codex-final-reviewer".into(),
    };
    let Some(attempt) = attempt else {
        return result;
    };
    result.content = attempt.stdout.clone();
    if attempt.exit_code != 0 {
        result.reason = attempt
            .blocked_reason
            .clone()
            .unwrap_or_else(|| "reviewer-provider-failed".into());
        if result.content.is_empty() {
            result.content = attempt.stderr.clone();
        }
        return result;
    }
    result.reason = "reviewer-malformed".into();
    let Ok(Value::Object(payload)) = serde_json::from_str::<Value>(&attempt.stdout) else {
        return result;
    };
    if payload.len() != 3 {
        return result;
    }
    let (Some(Value::String(verdict)), Some(Value::String(reason)), Some(Value::Array(findings))) = (
        payload.get("verdict"),
        payload.get("reason"),
        payload.get("findings"),
    ) else {
        return result;
    };
    if !matches!(verdict.as_str(), "pass" | "fail") || !findings.iter().all(Value::is_string) {
        return result;
    }
    result.passed = verdict == "pass" && findings.is_empty();
    result.reason = if reason.is_empty() {
        if result.passed {
            "approved"
        } else {
            "reviewer-rejected"
        }
        .into()
    } else {
        reason.clone()
    };
    result
}
// Match json.dumps' default ensure_ascii=True, including UTF-16 surrogate pairs.
fn json_string(text: &str) -> String {
    let encoded = json!(text).to_string();
    let mut result = String::new();
    for c in encoded.chars() {
        if c.is_ascii() && c != '\u{7f}' {
            result.push(c);
        } else {
            for unit in c.encode_utf16(&mut [0; 2]) {
                result.push_str(&format!("\\u{unit:04x}"));
            }
        }
    }
    result
}
/// Explicit command and hook only; no executable discovery, target imports or CLI wiring.
pub fn review(
    command: Command,
    main_repo_root: &Path,
    cwd: &Path,
    changed_files: &[String],
    timeout: Option<Duration>,
    after_provider_call: &mut dyn FnMut(CodexAttempt, &Value) -> Result<CodexAttempt>,
) -> Result<ReviewOutput> {
    crate::executor_local::LocalConfig::load(main_repo_root)
        .map_err(Error::Local)?
        .validate_timeout(timeout.map(|value| json!(value.as_secs_f64())).as_ref())
        .map_err(Error::Local)?;
    let files = changed_files
        .iter()
        .map(|s| json_string(s))
        .collect::<Vec<_>>()
        .join(", ");
    let prompt = format!(
        "Review the completed delegated change. Read .mir-dispatch/brief.md and run read-only inspection commands as needed. Changed files: [{files}]"
    );
    let cwd = crate::supply::plain(cwd.to_path_buf());
    let cwd = cwd
        .to_str()
        .ok_or_else(|| Error::Output("review cwd is not UTF-8".into()))?;
    let mut options = CallOptions::new(&prompt, cwd);
    options.sandbox = "read-only".into();
    options.base_instructions = Some(BASE_INSTRUCTIONS.into());
    options.timeout = timeout;
    let started = Instant::now();
    let mut attempt = codex_attempt(
        command,
        options,
        Duration::from_secs(15),
        Duration::from_secs(1),
        None,
    )?;
    if attempt.exit_code != 0 {
        attempt.blocked_reason = Some(
            if attempt.exit_code == 124 {
                "reviewer-timeout"
            } else {
                "reviewer-unavailable"
            }
            .into(),
        );
    }
    let tokens = attempt
        .tokens_used
        .iter()
        .cloned()
        .collect::<std::collections::BTreeMap<_, _>>();
    let metadata = json!({"prompt_sha256":crate::digest::sha256(prompt.as_bytes()),"model":attempt.model_id,"reasoning_effort":null,"tool_version":attempt.tool_version,"attempt":1,"elapsed_seconds":started.elapsed().as_secs_f64(),"token_usage":if tokens.is_empty(){Value::Null}else{json!(tokens)}});
    let attempt = after_provider_call(attempt, &metadata)?;
    Ok(ReviewOutput {
        evidence: evidence(Some(&attempt)),
        attempt,
        metadata,
    })
}
