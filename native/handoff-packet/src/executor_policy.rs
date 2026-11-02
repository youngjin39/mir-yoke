//! Library-only policy resolution. Unknown external fields are retained like Python.
use crate::executor_local::{Error, LocalConfig};
use serde_json::{Value, json};
use std::{collections::BTreeMap, fs, path::Path};

fn object(value: &Value) -> Value {
    if value.is_object() {
        value.clone()
    } else {
        json!({})
    }
}
fn string(value: &Value) -> Option<&str> {
    value.as_str().map(str::trim).filter(|s| !s.is_empty())
}
fn strings(value: &Value) -> Vec<&str> {
    value
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(string)
        .collect()
}
/// The lock/overlay wins shallowly; only these three sections merge one level.
pub fn merge(local: &Value, overlay: &Value) -> Value {
    let mut merged = object(local);
    if let (Some(out), Some(values)) = (merged.as_object_mut(), overlay.as_object()) {
        out.extend(values.clone());
        for key in ["delegation", "per_project", "monitoring"] {
            if local.get(key).is_some() || overlay.get(key).is_some() {
                let mut section = object(&local[key]);
                if let (Some(out), Some(values)) =
                    (section.as_object_mut(), overlay[key].as_object())
                {
                    out.extend(values.clone());
                }
                out.insert(key.into(), section);
            }
        }
    }
    merged
}
#[derive(Debug, Clone)]
pub struct Policy {
    data: Value,
    pub warning: String,
}
impl Policy {
    pub fn resolve(data: &Value) -> Self {
        let delegation = object(&data["delegation"]);
        let declared = delegation.get("mode").unwrap_or(&data["mode"]);
        let mode = match declared.as_str() {
            Some("obey_user") => Some("user_command_priority"),
            other => other,
        };
        let project = data
            .get("per_project")
            .unwrap_or(&delegation["per_project"]);
        let valid = matches!(
            mode,
            Some(
                "force_codex"
                    | "force_claude"
                    | "select"
                    | "user_command_priority"
                    | "unrestricted"
                    | "per_project"
            )
        ) && (project.is_object()
            || (data.get("per_project").is_none() && delegation.get("per_project").is_none()));
        let unresolved = if valid {
            None
        } else {
            declared.as_str().filter(|s| !s.is_empty())
        };
        let warning = unresolved
            .map(|m| format!("[mir policy] unresolved mode: {m}; using select\n"))
            .unwrap_or_default();
        Self {
            data: json!({
                "mode": if valid {mode.unwrap_or("select")} else {"select"},
                "per_project": if valid {object(project)} else {json!({})},
                "routing": object(&data["routing"]), "monitoring": object(&data["monitoring"]),
                "delegation": delegation,
                "default_backend": string(&delegation["default_backend"]).or_else(|| string(&data["default_backend"])).unwrap_or("codex"),
                "unresolved_mode": unresolved,
            }),
            warning,
        }
    }
    pub fn snapshot(&self) -> Value {
        let mut value = self.data.clone();
        value["warning"] = json!(self.warning);
        value
    }
    pub fn mode(&self) -> &str {
        self.data["mode"].as_str().unwrap_or("select")
    }
    pub fn category(&self, category: &str) -> Value {
        let routing = &self.data["routing"];
        let route = &routing["by_category"][category];
        let primary = route["prefer"]
            .as_array()
            .and_then(|items| {
                items.iter().find(|item| {
                    string(&item["model"]).is_some() || string(&item["reasoning_effort"]).is_some()
                })
            })
            .unwrap_or(route);
        let field = |key: &str, flat: &str| {
            string(&primary[key])
                .or_else(|| string(&routing["default"][key]))
                .or_else(|| string(&routing[flat]))
                .map(str::to_owned)
        };
        json!({"model":field("model", "default_model"), "reasoning_effort":field("reasoning_effort", "default_reasoning_effort")})
    }
    pub fn backend(
        &self,
        requested: Option<&str>,
        slug: Option<&str>,
        declared: Option<&str>,
        agent: Option<&str>,
    ) -> String {
        match self.mode() {
            "force_codex" => return "codex".into(),
            "force_claude" => return "claude".into(),
            _ => {}
        }
        let valid = |s: &str| matches!(s, "codex" | "claude");
        let fallback = agent
            .or_else(|| self.data["default_backend"].as_str())
            .filter(|s| valid(s))
            .unwrap_or("codex");
        let project = slug.map(|s| &self.data["per_project"][s]);
        let declared = project
            .and_then(|v| v.as_str().or_else(|| v["backend"].as_str()))
            .or(declared);
        let configured = strings(&self.data["delegation"]["resolution_order"]);
        let order = if configured.is_empty() {
            vec!["user_command", "project_declaration", "default_backend"]
        } else {
            configured
        };
        for step in order {
            let enabled = match self.mode() {
                "user_command_priority" => true,
                "per_project" => step != "user_command",
                "select" | "unrestricted" => step != "project_declaration",
                _ => step == "default_backend",
            };
            let candidate = match step {
                "user_command" => requested,
                "project_declaration" => declared,
                "default_backend" => Some(fallback),
                _ => None,
            };
            if enabled && let Some(backend) = candidate.filter(|s| valid(s)) {
                return if step == "user_command" {
                    backend
                } else {
                    agent.unwrap_or(backend)
                }
                .into();
            }
        }
        fallback.into()
    }
    /// Explicit CLI models bypass the category/default forced-backend guard.
    pub fn guard(&self, model: &str, backend: &str, explicit: bool) -> Result<(), String> {
        if !explicit
            && matches!(self.mode(), "force_codex" | "force_claude")
            && let Some(owner) = model_backend(model)
            && owner != backend
        {
            return Err(format!(
                "{} cannot dispatch routed model {} for backend '{}' to backend '{}'; fix the category/default route or pass --model explicitly",
                self.mode(),
                python_repr(model),
                owner,
                backend
            ));
        }
        Ok(())
    }
}
fn python_repr(value: &str) -> String {
    let quote = if value.contains('\'') && !value.contains('"') {
        '"'
    } else {
        '\''
    };
    let mut out = String::from(quote);
    for c in value.chars() {
        match c {
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if c == quote => {
                out.push('\\');
                out.push(c);
            }
            c => out.push(c),
        }
    }
    out.push(quote);
    out
}
pub fn model_backend(model: &str) -> Option<&'static str> {
    let model = model.trim().to_lowercase();
    if matches!(model.as_str(), "sonnet" | "opus" | "fable" | "haiku")
        || model.starts_with("claude-")
    {
        Some("claude")
    } else if model.starts_with("gpt-") {
        Some("codex")
    } else {
        None
    }
}
fn read(path: &Path) -> Result<Value, String> {
    let bytes = fs::read(path).map_err(|e| e.to_string())?;
    LocalConfig::parse_bytes(bytes)
        .map(|v| Value::Object(v.raw().clone()))
        .map_err(|e| match e {
            Error::Object => "sub-agent policy must be a JSON object".into(),
            other => other.to_string(),
        })
}
/// `account_home` is supplied by the invoking account adapter, never inferred from HOME.
/// On Windows the adapter must pass the account profile directory (USERPROFILE),
/// or fail before calling this library if that account identity cannot be established.
pub fn load(root: &Path, account_home: &Path, environment: &BTreeMap<String, String>) -> Policy {
    let mut warning = String::new();
    let result: Result<Policy, String> = (|| {
        let lock = root.join("config/model-routing.lock.json");
        let local_path = root.join("config/sub-agent-policy.json");
        let early_local = if !lock.is_file() {
            Some(if local_path.is_file() {
                read(&local_path)?
            } else {
                json!({})
            })
        } else {
            None
        };
        let overlay = if lock.is_file() {
            let lock = read(&lock)?;
            if !lock["policy"].is_object() {
                return Err("model-routing lock `policy` must be a JSON object".into());
            }
            Some(lock["policy"].clone())
        } else {
            let global = account_home.join(".mir/model-routing/sub-agent-policy.json");
            let named = environment
                .get("MIR_SUB_AGENT_POLICY")
                .filter(|s| !s.is_empty())
                .map(|s| {
                    if s == "~" || s.starts_with("~/") {
                        Path::new(
                            environment
                                .get("HOME")
                                .map(String::as_str)
                                .unwrap_or_else(|| account_home.to_str().unwrap_or("")),
                        )
                        .join(s.trim_start_matches('~').trim_start_matches('/'))
                    } else {
                        s.into()
                    }
                });
            let path = match named {
                Some(path) if path.exists() => path,
                Some(path) => {
                    warning.push_str(&format!("[mir policy] MIR_SUB_AGENT_POLICY names a missing file: {}; falling back to the rendered policy\n", path.display()));
                    global
                }
                None => global,
            };
            if path.exists() {
                Some(read(&path)?)
            } else {
                None
            }
        };
        let local = if let Some(local) = early_local {
            local
        } else if local_path.is_file() {
            read(&local_path)?
        } else {
            json!({})
        };
        Ok(Policy::resolve(
            &overlay.map(|o| merge(&local, &o)).unwrap_or(local),
        ))
    })();
    match result {
        Ok(mut policy) => {
            warning.push_str(&policy.warning);
            policy.warning = warning;
            policy
        }
        Err(error) => {
            let mut policy = Policy::resolve(&json!({}));
            warning.push_str(&format!(
                "[mir policy] unreadable sub-agent policy ({error}); using select defaults\n"
            ));
            policy.warning = warning;
            policy
        }
    }
}

fn validate_agent_name(name: &str) -> Result<(), String> {
    let valid = regex::Regex::new(r"^[a-z0-9]+(?:-[a-z0-9]+)*$").map_err(|e| e.to_string())?;
    if !valid.is_match(name) {
        return Err(format!("invalid target_agent: {}", python_repr(name)));
    }
    Ok(())
}
fn agent_fields(text: &str) -> Result<(BTreeMap<String, String>, String), String> {
    let frontmatter =
        regex::Regex::new(r"(?s)^---\s*\n(.*?)\n---\s*(?:\n|$)").map_err(|e| e.to_string())?;
    let captures = frontmatter
        .captures(text)
        .ok_or("agent definition requires leading frontmatter")?;
    let block = captures
        .get(1)
        .ok_or("agent definition requires leading frontmatter")?
        .as_str();
    let end = captures
        .get(0)
        .ok_or("agent definition requires leading frontmatter")?
        .end();
    let instructions = text[end..].trim().to_owned();
    let field =
        regex::Regex::new(r"^([a-zA-Z_][a-zA-Z0-9_]*):\s*(.*)$").map_err(|e| e.to_string())?;
    let mut fields = BTreeMap::new();
    let mut lines = block.lines();
    while let Some(line) = lines.next() {
        let Some(c) = field.captures(line) else {
            continue;
        };
        let (Some(key), Some(value)) = (c.get(1), c.get(2)) else {
            continue;
        };
        let mut value = value.as_str().trim().to_owned();
        if value.starts_with('"') {
            while value.len() < 2 || !value.ends_with('"') || value.ends_with("\\\"") {
                let Some(line) = lines.next() else { break };
                value.push('\n');
                value.push_str(line);
            }
            if value.len() >= 2 && value.ends_with('"') {
                value = value[1..value.len() - 1].into();
            }
        }
        fields.insert(key.as_str().to_owned(), value);
    }
    Ok((fields, instructions))
}
fn read_only_agent(name: &str, fields: &BTreeMap<String, String>) -> bool {
    name == "codex-final-reviewer"
        || fields.get("disallowedTools").is_some_and(|s| {
            let tools: Vec<_> = s
                .split(',')
                .map(|s| s.trim().trim_matches(['[', ']']))
                .collect();
            tools.contains(&"Write") && tools.contains(&"Edit")
        })
}
fn agent_text(path: &Path) -> Result<String, String> {
    // Python's text reader normalizes newlines before parsing and hashing.
    fs::read_to_string(path)
        .map(|s| s.replace("\r\n", "\n").replace('\r', "\n"))
        .map_err(|e| e.to_string())
}
/// Local routes win, while repository read-only constraints still apply.
pub fn narrow_agent_route(root: &Path, name: &str, mut route: Value) -> Result<Value, String> {
    validate_agent_name(name)?;
    let definition = root
        .join(".claude")
        .join("agents")
        .join(format!("{name}.md"));
    let fields = if definition.is_file() {
        agent_fields(&agent_text(&definition)?)?.0
    } else {
        BTreeMap::new()
    };
    if read_only_agent(name, &fields) {
        route["sandbox"] = json!("read-only");
    }
    Ok(route)
}
/// Resolve repository definitions after the caller has tried the local bridge.
pub fn agent_route(
    root: &Path,
    name: &str,
    policy: &Policy,
) -> Result<(Option<Value>, String), String> {
    validate_agent_name(name)?;
    let mut definition = std::path::PathBuf::from(".claude")
        .join("agents")
        .join(format!("{name}.md"));
    if !root.join(&definition).is_file() {
        return Ok((
            None,
            format!(
                "[mir_executor] warning: no definition for target agent {}; dispatching without an agent route\n",
                python_repr(name)
            ),
        ));
    }
    let mut text = agent_text(&root.join(&definition))?;
    let (fields, mut instructions) = agent_fields(&text)?;
    let backend = fields
        .get("execution_backend")
        .map(String::as_str)
        .unwrap_or("");
    if !matches!(backend, "codex" | "claude") {
        return Err(format!(
            "agent {} has no executable backend",
            python_repr(name)
        ));
    }
    let readonly = read_only_agent(name, &fields);
    let mut sandbox = readonly.then_some("read-only".to_owned());
    let mut model = if backend == "claude" {
        fields.get("model").cloned()
    } else {
        None
    };
    let mut effort = fields.get("effort").filter(|s| !s.is_empty()).cloned();
    if backend == "codex" {
        let codex_definition = std::path::PathBuf::from(".codex")
            .join("agents")
            .join(format!("{name}.toml"));
        if root.join(&codex_definition).is_file() {
            definition = codex_definition;
            text = agent_text(&root.join(&definition))?;
            let parsed: toml::Value = text.parse::<toml::Value>().map_err(|e| e.to_string())?;
            if let Some(value) = parsed
                .get("developer_instructions")
                .and_then(toml::Value::as_str)
                .filter(|s| !s.trim().is_empty())
            {
                instructions = value.trim().into()
            }
            if let Some(value) = parsed.get("sandbox_mode") {
                let declared = value
                    .as_str()
                    .filter(|s| {
                        matches!(*s, "read-only" | "workspace-write" | "danger-full-access")
                    })
                    .ok_or_else(|| {
                        format!("agent {} has invalid sandbox_mode", python_repr(name))
                    })?;
                let widens = declared == "danger-full-access"
                    && LocalConfig::load(root)
                        .map_err(|e| e.to_string())?
                        .raw()
                        .get("codex_sandbox_default")
                        .and_then(Value::as_str)
                        != Some("danger-full-access");
                if !readonly && !widens {
                    sandbox = Some(declared.into())
                }
            }
        }
        if sandbox.is_none() {
            sandbox = Some("workspace-write".into())
        }
        let lock = root.join("config").join("model-routing.lock.json");
        let lock = if lock.is_file() {
            read(&lock).unwrap_or(json!({}))
        } else {
            json!({})
        };
        let criteria = lock.get("agent_criteria").cloned().unwrap_or(json!({}));
        if !criteria.is_object() {
            return Err("model-routing lock `agent_criteria` must be a JSON object".into());
        }
        let criteria = criteria.get(name).cloned().unwrap_or(json!({}));
        if !criteria.is_object() {
            return Err(format!(
                "model-routing lock `agent_criteria[{name}]` must be a JSON object"
            ));
        }
        let category = criteria
            .get("category")
            .and_then(Value::as_str)
            .unwrap_or("implementation");
        let route = policy.category(category);
        model = route["model"].as_str().map(str::to_owned);
        effort = effort.or_else(|| route["reasoning_effort"].as_str().map(str::to_owned));
    }
    Ok((
        Some(
            json!({"target_agent":name,"execution_backend":backend,"model":model,
        "reasoning_effort":effort,"definition_path":definition.to_str().ok_or("agent path is not UTF-8")?.replace('\\', "/"),"definition_sha256":crate::digest::sha256(text.as_bytes()),
        "base_instructions":instructions,"sandbox":sandbox}),
        ),
        String::new(),
    ))
}

/// Windows has no passwd database. Use the invoking account's USERPROFILE,
/// rejecting missing/relative profiles rather than silently trusting HOME.
/// On Unix the embedding adapter supplies the passwd account home explicitly.
pub fn windows_account_home(
    environment: &BTreeMap<String, String>,
) -> Result<std::path::PathBuf, &'static str> {
    let profile = environment
        .get("USERPROFILE")
        .filter(|s| !s.is_empty())
        .ok_or("missing Windows account USERPROFILE")?;
    let bytes = profile.as_bytes();
    let drive = bytes.len() >= 3
        && bytes[0].is_ascii_alphabetic()
        && bytes[1] == b':'
        && matches!(bytes[2], b'\\' | b'/');
    let unc = profile.starts_with("\\\\")
        && profile[2..].split('\\').filter(|s| !s.is_empty()).count() >= 2;
    if !drive && !unc {
        return Err("Windows account USERPROFILE must be absolute");
    }
    Ok(profile.into())
}
