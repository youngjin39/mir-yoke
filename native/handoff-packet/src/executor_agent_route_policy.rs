//! Finite local agent-route selection; policy precedence is owned by executor_policy.
use super::{invalid, object, string};
use crate::{
    executor_dispatch_provider::CODEX_BASE_INSTRUCTIONS,
    executor_local::{Error, LocalConfig},
    executor_policy::Policy,
};
use serde_json::{Value, json};
use std::{fs, path::Path};

#[derive(Clone, Debug)]
pub struct AgentRoutePolicy {
    source: String,
    criteria: String,
    backend: String,
    sandbox: String,
    invalid_lock: String,
    names: Option<Vec<String>>,
    name_filter: bool,
    pub requested_backend: bool,
}
impl AgentRoutePolicy {
    pub fn parse(value: &Value) -> Result<Self, Error> {
        let data = object(
            value,
            &[
                "source",
                "criteria",
                "backend",
                "sandbox",
                "invalid_lock",
                "names",
                "name_filter",
                "requested_backend",
            ],
            "agent_route",
        )?;
        let choice = |key, choices: &[&str]| -> Result<String, Error> {
            let value = string(data, key)?;
            if !choices.contains(&value) {
                return Err(invalid(format!("invalid agent_route.{key}")));
            }
            Ok(value.into())
        };
        let boolean = |key| -> Result<bool, Error> {
            match data.get(key) {
                None => Ok(false),
                Some(Value::Bool(v)) => Ok(*v),
                _ => Err(invalid(format!("agent_route.{key} must be boolean"))),
            }
        };
        let names = data
            .get("names")
            .map(|v| {
                let values = v
                    .as_array()
                    .ok_or_else(|| invalid("agent_route.names must be an array"))?;
                let mut names = Vec::new();
                for v in values {
                    let name = v
                        .as_str()
                        .filter(|s| {
                            !s.is_empty()
                                && s.bytes().all(|b| {
                                    b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-'
                                })
                        })
                        .ok_or_else(|| invalid("invalid agent_route name"))?;
                    if names.iter().any(|s| s == name) {
                        return Err(invalid("duplicate agent_route name"));
                    }
                    names.push(name.to_owned());
                }
                Ok(names)
            })
            .transpose()?;
        let result = Self {
            source: choice("source", &["claude", "codex"])?,
            criteria: choice("criteria", &["defer", "declared", "default"])?,
            backend: choice("backend", &["policy", "codex"])?,
            sandbox: choice("sandbox", &["unset", "read_only", "double_opt_in"])?,
            invalid_lock: choice("invalid_lock", &["empty", "error"])?,
            names,
            name_filter: boolean("name_filter")?,
            requested_backend: boolean("requested_backend")?,
        };
        if (result.source == "claude" && result.sandbox != "unset")
            || (result.source == "codex" && result.sandbox == "unset")
        {
            return Err(invalid("agent_route sandbox is incompatible with source"));
        }
        Ok(result)
    }
    pub fn resolve(
        &self,
        root: &Path,
        name: &str,
        policy: &Policy,
        requested: Option<&str>,
        slug: Option<&str>,
        declared: Option<&str>,
    ) -> Result<Option<Value>, String> {
        if self
            .names
            .as_ref()
            .is_some_and(|names| !names.iter().any(|s| s == name))
            || (self.name_filter
                && !regex::Regex::new(r"^[a-z0-9][a-z0-9-]*$")
                    .map_err(|e| e.to_string())?
                    .is_match(name))
        {
            return Ok(None);
        }
        let relative = if self.source == "claude" {
            format!(".claude/agents/{name}.md")
        } else {
            format!(".codex/agents/{name}.toml")
        };
        let path = root.join(&relative);
        if !path.is_file() {
            return Ok(None);
        }
        let lock_path = root.join("config/model-routing.lock.json");
        let lock = if lock_path.is_file() {
            let read = fs::read(&lock_path)
                .map_err(|e| e.to_string())
                .and_then(|b| {
                    LocalConfig::parse_bytes(b)
                        .map(|c| Value::Object(c.raw().clone()))
                        .map_err(|e| match e {
                            Error::Object => "sub-agent policy must be a JSON object".into(),
                            other => other.to_string(),
                        })
                });
            match read {
                Ok(v) => v,
                Err(_) if self.invalid_lock == "empty" => json!({}),
                Err(e) => return Err(e),
            }
        } else {
            json!({})
        };
        let criteria = lock.get("agent_criteria").cloned().unwrap_or(json!({}));
        let criteria = criteria
            .as_object()
            .ok_or("model-routing lock `agent_criteria` must be a JSON object")?;
        if self.criteria == "defer" && criteria.contains_key(name) {
            return Ok(None);
        }
        let entry = criteria.get(name).cloned().unwrap_or(json!({}));
        let entry = entry
            .as_object()
            .ok_or("agent criteria must be a JSON object")?;
        let category = entry
            .get("category")
            .and_then(Value::as_str)
            .filter(|s| !s.is_empty())
            .or(if self.criteria == "default" {
                Some("implementation")
            } else {
                None
            });
        // Python policy loading emits diagnostics at each hook-owned load.
        // The declared Markdown route loads again when selecting a category.
        if !policy.warning.is_empty() {
            crate::executor_execute::emit(&policy.warning, true).map_err(|e| e.to_string())?;
            if self.source == "claude" && self.criteria == "declared" && category.is_some() {
                crate::executor_execute::emit(&policy.warning, true).map_err(|e| e.to_string())?;
            }
        }
        let route = category.map(|c| policy.category(c)).unwrap_or(json!({}));
        let backend = if self.backend == "codex" {
            "codex".into()
        } else {
            policy.backend(
                if self.requested_backend {
                    requested
                } else {
                    None
                },
                slug,
                declared,
                None,
            )
        };
        let mut raw = fs::read(&path).map_err(|e| e.to_string())?;
        let mut instructions = CODEX_BASE_INSTRUCTIONS.to_owned();
        let mut sandbox = None;
        if self.source == "codex" {
            let text = std::str::from_utf8(&raw).map_err(|e| e.to_string())?;
            let definition = text.parse::<toml::Value>().map_err(|e| e.to_string())?;
            instructions = definition
                .get("developer_instructions")
                .and_then(toml::Value::as_str)
                .unwrap_or("")
                .into();
            let mode = definition.get("sandbox_mode").and_then(toml::Value::as_str);
            if self.sandbox == "double_opt_in" {
                instructions = definition
                    .get("developer_instructions")
                    .and_then(toml::Value::as_str)
                    .ok_or("developer_instructions")?
                    .trim()
                    .into();
                sandbox = Some("workspace-write");
                if mode == Some("danger-full-access")
                    && LocalConfig::load(root)
                        .map_err(|e| e.to_string())?
                        .raw()
                        .get("codex_sandbox_default")
                        .and_then(Value::as_str)
                        == Some("danger-full-access")
                {
                    sandbox = Some("danger-full-access");
                }
                raw = text.replace("\r\n", "\n").replace('\r', "\n").into_bytes();
            } else if mode == Some("read-only") {
                sandbox = Some("read-only");
            }
        }
        Ok(Some(
            json!({"target_agent":name,"execution_backend":backend,"model":route.get("model"),"reasoning_effort":route.get("reasoning_effort"),"definition_path":relative,"definition_sha256":crate::digest::sha256(&raw),"base_instructions":instructions,"sandbox":sandbox}),
        ))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn route_identity_category_backend_and_sandbox() {
        let base = std::env::var_os("MIR_NATIVE_TEST_SCRATCH")
            .map(std::path::PathBuf::from)
            .unwrap_or_else(std::env::temp_dir)
            .join(format!("agent-route-{}", std::process::id()));
        fs::create_dir_all(base.join(".codex/agents")).unwrap();
        fs::create_dir_all(base.join("config")).unwrap();
        let raw = b"developer_instructions = '  Instructions.  '\r\nsandbox_mode = 'read-only'\r\n";
        fs::write(base.join(".codex/agents/sample.toml"), raw).unwrap();
        fs::write(
            base.join("config/model-routing.lock.json"),
            r#"{"agent_criteria":{"sample":{"category":"unit"}}}"#,
        )
        .unwrap();
        let rule = AgentRoutePolicy::parse(&json!({"source":"codex","criteria":"declared","backend":"policy","sandbox":"read_only","invalid_lock":"empty","requested_backend":true})).unwrap();
        let policy = Policy::resolve(
            &json!({"mode":"user_command_priority","routing":{"by_category":{"unit":{"model":"selected","reasoning_effort":"high"}}}}),
        );
        let route = rule
            .resolve(&base, "sample", &policy, Some("claude"), None, None)
            .unwrap()
            .unwrap();
        assert_eq!(route["definition_sha256"], crate::digest::sha256(raw));
        assert_eq!(route["model"], "selected");
        assert_eq!(route["reasoning_effort"], "high");
        assert_eq!(route["execution_backend"], "claude");
        assert_eq!(route["sandbox"], "read-only");
        assert_eq!(route["base_instructions"], "  Instructions.  ");
        assert!(
            rule.resolve(&base, "missing", &policy, None, None, None)
                .unwrap()
                .is_none()
        );
        fs::remove_dir_all(base).unwrap();
    }
}
