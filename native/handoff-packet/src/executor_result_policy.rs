//! Finite result retention policy, sharing the registry's redaction and bound.
use crate::{
    executor_dispatch::{CodexAttempt, Error, Result},
    executor_local,
    executor_registry::sanitize,
    executor_worktree,
};
use serde_json::Value;
use std::path::Path;

#[derive(Clone, Debug)]
pub struct ResultPolicy {
    provider_output: bool,
    attempt_artifact: bool,
}

impl ResultPolicy {
    pub fn covered_hooks(&self) -> Vec<&'static str> {
        let mut hooks = Vec::new();
        if self.provider_output {
            hooks.push("after_provider_call");
        }
        if self.attempt_artifact {
            hooks.push("after_run");
        }
        hooks
    }

    pub fn parse(value: &Value) -> std::result::Result<Self, executor_local::Error> {
        let invalid = |message: String| {
            executor_local::Error::Invalid(format!("native_policy.result_policy: {message}"))
        };
        let data = value
            .as_object()
            .ok_or_else(|| invalid("must be an object".into()))?;
        for (key, value) in data {
            let expected = match key.as_str() {
                "provider_output" => "sanitize_persisted_text",
                "attempt_artifact" => "result_json",
                _ => return Err(invalid(format!("unknown field {key}"))),
            };
            if value.as_str() != Some(expected) {
                return Err(invalid(format!("{key} must be {expected:?}")));
            }
        }
        Ok(Self {
            provider_output: data.contains_key("provider_output"),
            attempt_artifact: data.contains_key("attempt_artifact"),
        })
    }

    /// Only CodexAttempt is admitted: direct subprocess results retain their type
    /// and output. A clean attempt produces no replacement, matching the hook.
    pub fn after_provider_call(&self, result: &CodexAttempt) -> Result<Option<CodexAttempt>> {
        if !self.provider_output {
            return Ok(None);
        }
        let stdout = sanitize(&result.stdout).map_err(Error::Registry)?;
        let stderr = sanitize(&result.stderr).map_err(Error::Registry)?;
        if stdout == result.stdout && stderr == result.stderr {
            return Ok(None);
        }
        let mut replacement = result.clone();
        replacement.stdout = stdout;
        replacement.stderr = stderr;
        Ok(Some(replacement))
    }

    pub fn after_run(&self, path: &Path, result: &CodexAttempt) -> Result<()> {
        if !self.attempt_artifact {
            return Ok(());
        }
        // Explicit field serialization retains the Python insertion order even
        // though serde_json's default object representation sorts keys.
        let fields = [
            ("exit_code", Value::from(result.exit_code)),
            (
                "error_sig",
                Value::from(sanitize(&result.error_sig).map_err(Error::Registry)?),
            ),
            (
                "stdout",
                Value::from(sanitize(&result.stdout).map_err(Error::Registry)?),
            ),
            (
                "stderr",
                Value::from(sanitize(&result.stderr).map_err(Error::Registry)?),
            ),
            ("lane_unavailable", Value::from(result.lane_unavailable)),
            ("retryable", Value::from(result.retryable)),
            (
                "blocked_reason",
                result
                    .blocked_reason
                    .as_deref()
                    .map(sanitize)
                    .transpose()
                    .map_err(Error::Registry)?
                    .map_or(Value::Null, Value::from),
            ),
        ];
        let mut text = String::from("{\n");
        for (index, (key, value)) in fields.iter().enumerate() {
            text.push_str(&format!(
                "  \"{key}\": {}",
                serde_json::to_string(value).map_err(Error::Json)?
            ));
            if index + 1 < fields.len() {
                text.push(',');
            }
            text.push('\n');
        }
        text.push_str("}\n");
        executor_worktree::write_private_text(path, &text, false).map_err(Error::Worktree)
    }
}
