//! DispatchBrief builder and atomic persistence, without a live caller.
use crate::executor_brief_render::{ValidationIssue, python_value_repr, render_errors};
use crate::mir_core::contracts::{dispatch_brief::DispatchBrief, task_spec::TaskSpec};
use serde::{
    Deserialize,
    de::{MapAccess, Visitor},
};
use serde_json::{Value, json, value::RawValue};
use std::{
    fmt, fs,
    io::{self, Write},
    path::{Path, PathBuf},
};

pub const ROLE_TO_TARGET_AGENT: [(&str, &str); 4] = [
    ("executor", "executor-agent"),
    ("reviewer", "codex-final-reviewer"),
    ("planner", "main-orchestrator"),
    ("tester", "quality-agent"),
];
pub const EXPORTS: [&str; 5] = [
    "build_dispatch_brief",
    "codex_args_from_dispatch_brief",
    "load_dispatch_brief",
    "persist_dispatch_brief",
    "verification_commands_from_tdd_entry",
];
#[derive(Debug)]
pub struct Error {
    pub class: &'static str,
    pub message: String,
    pub source: Option<Box<dyn std::error::Error + Send + Sync>>,
}
impl Error {
    pub fn named(class: &'static str, message: impl Into<String>) -> Self {
        Self {
            class,
            message: message.into(),
            source: None,
        }
    }
}
impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.message)
    }
}
impl std::error::Error for Error {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        self.source.as_deref().map(|e| e as &dyn std::error::Error)
    }
}
impl From<io::Error> for Error {
    fn from(error: io::Error) -> Self {
        Self {
            class: "OSError",
            message: error.to_string(),
            source: Some(Box::new(error)),
        }
    }
}
impl From<crate::Error> for Error {
    fn from(error: crate::Error) -> Self {
        Self::named("RuntimeError", format!("{error:?}"))
    }
}
impl From<serde_json::Error> for Error {
    fn from(error: serde_json::Error) -> Self {
        let message = if error.to_string().contains("EOF while parsing an object") {
            format!(
                "Expecting property name enclosed in double quotes: line {} column {} (char {})",
                error.line(),
                error.column() + 1,
                error.column()
            )
        } else {
            error.to_string()
        };
        Self {
            class: "JSONDecodeError",
            message,
            source: Some(Box::new(error)),
        }
    }
}
// Raw JSON members retain the Python model's declaration/insertion order.
struct Members(Vec<(String, Box<RawValue>)>);
impl<'de> Deserialize<'de> for Members {
    fn deserialize<D: serde::Deserializer<'de>>(d: D) -> Result<Self, D::Error> {
        struct MapVisitor;
        impl<'de> Visitor<'de> for MapVisitor {
            type Value = Members;
            fn expecting(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
                f.write_str("a JSON object")
            }
            fn visit_map<M: MapAccess<'de>>(self, mut map: M) -> Result<Members, M::Error> {
                let mut items = Vec::new();
                while let Some(item) = map.next_entry()? {
                    items.push(item);
                }
                Ok(Members(items))
            }
        }
        d.deserialize_map(MapVisitor)
    }
}
/// Ordered Python dict repr, used for Pydantic's input diagnostics.
fn raw_repr(raw: &str) -> Result<String, Error> {
    let value: Value = serde_json::from_str(raw)?;
    if value.is_object() {
        let members: Members = serde_json::from_str(raw)?;
        let fields = members
            .0
            .iter()
            .map(|(k, v)| {
                Ok(format!(
                    "{}: {}",
                    python_value_repr(&json!(k)),
                    raw_repr(v.get())?
                ))
            })
            .collect::<Result<Vec<_>, Error>>()?;
        Ok(format!("{{{}}}", fields.join(", ")))
    } else {
        Ok(python_value_repr(&value))
    }
}
fn validation(class: &str, raw: &str, errors: Value) -> Error {
    let data: Value = serde_json::from_str(raw).unwrap_or(Value::Null);
    let issues = errors[1]
        .as_array()
        .into_iter()
        .flatten()
        .map(|error| {
            let loc = error["loc"].as_array().cloned().unwrap_or_default();
            let missing = error["type"] == "missing";
            let mut input = &data;
            for part in if missing {
                &loc[..loc.len().saturating_sub(1)]
            } else {
                &loc
            } {
                input = if let Some(key) = part.as_str() {
                    &input[key]
                } else {
                    &input[part.as_u64().unwrap_or(0) as usize]
                };
            }
            ValidationIssue {
                location: loc
                    .iter()
                    .map(|v| {
                        v.as_str()
                            .map(str::to_owned)
                            .unwrap_or_else(|| v.to_string())
                    })
                    .collect(),
                message: error["msg"].as_str().unwrap_or("").into(),
                code: error["type"].as_str().unwrap_or("").into(),
                input: input.clone(),
                input_type: None,
                input_repr: (input == &data).then(|| raw_repr(raw).unwrap_or_default()),
            }
        })
        .collect::<Vec<_>>();
    Error::named(
        "ValidationError",
        render_errors(&issues).replacen("for DispatchBrief", &format!("for {class}"), 1),
    )
}
pub fn validate_brief_json(raw: &str) -> Result<DispatchBrief, Error> {
    let data = serde_json::from_str(raw)?;
    DispatchBrief::from_dict(&data).map_err(|e| validation("DispatchBrief", raw, e))
}
pub fn validate_task_json(raw: &str) -> Result<TaskSpec, Error> {
    let data = serde_json::from_str(raw)?;
    TaskSpec::from_dict(&data).map_err(|e| validation("TaskSpec", raw, e))
}
pub fn slugify(value: &str) -> String {
    let mut slug = String::new();
    for ch in value.to_lowercase().chars() {
        if ch.is_alphanumeric() {
            slug.push(ch);
        } else if !slug.is_empty() && !slug.ends_with('-') {
            slug.push('-');
        }
    }
    slug.trim_end_matches('-').chars().take(80).collect()
}
pub fn derive_task_id(fingerprint: Option<&str>, intent: &str) -> String {
    fingerprint
        .filter(|s| !s.is_empty())
        .map(str::to_owned)
        .unwrap_or_else(|| nonempty(slugify(intent), "dispatch-task"))
}
pub fn derive_slice_id(phase: Option<&str>, role: &str, change: Option<&str>) -> String {
    let text = change
        .filter(|s| !s.is_empty())
        .map(str::to_owned)
        .unwrap_or_else(|| {
            format!(
                "{}-{role}",
                phase.filter(|s| !s.is_empty()).unwrap_or("task")
            )
        });
    nonempty(slugify(&text), "dispatch-slice")
}
fn nonempty(value: String, fallback: &str) -> String {
    if value.is_empty() {
        fallback.into()
    } else {
        value
    }
}
pub fn expanded_goal(task: &TaskSpec) -> String {
    let data = task.to_dict();
    format!(
        "{} [role={}, stack={}]",
        data["intent"].as_str().unwrap_or("").trim(),
        data["role_binding"].as_str().unwrap_or(""),
        data["stack"]
            .as_str()
            .filter(|s| !s.is_empty())
            .unwrap_or("default")
    )
}
pub fn stop_conditions(scope: &[Value]) -> [&'static str; 2] {
    if scope.contains(&json!("<unspecified>")) {
        [
            "Stop and hand control back if concrete file or module ownership remains unresolved.",
            "Stop if the requested work expands beyond the current slice intent.",
        ]
    } else {
        [
            "Stop if the change requires files outside owned_scope.",
            "Stop if verification_commands no longer match the edited surface.",
        ]
    }
}
pub fn build_dispatch_brief(
    task: &TaskSpec,
    _family_slug: &str,
    change_id: Option<&str>,
    verification_commands: &[String],
    phase_ref: &str,
) -> Result<DispatchBrief, Error> {
    let data = task.to_dict();
    let role = data["role_binding"].as_str().unwrap_or("");
    let task_id = derive_task_id(
        data["fingerprint"].as_str(),
        data["intent"].as_str().unwrap_or(""),
    );
    let slice_id = derive_slice_id(data["phase_tag"].as_str(), role, change_id);
    let verification = if verification_commands.is_empty() {
        json!(["uv run pytest -q"])
    } else {
        json!(verification_commands)
    };
    let refs = change_id
        .filter(|s| !s.is_empty())
        .map(|s| vec![format!("tasks/tdd.json#{s}")])
        .unwrap_or_default();
    let brief = json!({
        "version":1, "task_id":task_id, "phase_id":data["phase_tag"], "slice_id":slice_id,
        "target_agent": ROLE_TO_TARGET_AGENT.iter().find(|(r,_)| *r == role)
            .map_or("executor-agent", |(_,agent)| *agent),
        "user_intent":data["intent"].as_str().unwrap_or("").trim(),
        "expanded_goal":expanded_goal(task), "owned_scope":data["scope"],
        "out_of_scope":["Do not edit paths outside owned_scope without orchestration approval."],
        "verification_commands":verification,
        "stop_conditions":stop_conditions(data["scope"].as_array().map_or(&[], Vec::as_slice)),
        "handoff_refs":[], "tdd_change_refs":refs,
        "resume_state_ref":format!("tasks/dispatch/{task_id}/{slice_id}.json"),
        "source_refs":{"task_spec":format!("runtime://task-spec/{task_id}"),
            "plan":"tasks/plan.md", "phase":phase_ref}
    });
    validate_brief_json(&brief.to_string())
}
pub fn verification_commands_from_tdd_entry(entry: &Value) -> Vec<String> {
    let mut commands = Vec::new();
    for item in entry["categories"]
        .as_object()
        .into_iter()
        .flat_map(|m| m.values())
    {
        if let Some(command) = item.get("command").and_then(Value::as_str)
            && !command.is_empty()
            && !commands.iter().any(|s| s == command)
        {
            commands.push(command.to_owned());
        }
    }
    commands
}
pub fn codex_args_from_dispatch_brief(brief: &DispatchBrief) -> [String; 2] {
    [
        "exec".into(),
        brief.to_dict()["expanded_goal"]
            .as_str()
            .unwrap_or("")
            .into(),
    ]
}
fn pretty(raw: &str, depth: usize) -> Result<String, Error> {
    let pad = "  ".repeat(depth);
    let indent = format!("{pad}  ");
    let value: Value = serde_json::from_str(raw)?;
    if value.is_object() {
        let members: Members = serde_json::from_str(raw)?;
        if members.0.is_empty() {
            return Ok("{}".into());
        }
        let rows = members
            .0
            .iter()
            .map(|(k, v)| {
                Ok(format!(
                    "{indent}{}: {}",
                    json!(k),
                    pretty(v.get(), depth + 1)?
                ))
            })
            .collect::<Result<Vec<_>, Error>>()?;
        Ok(format!("{{\n{}\n{pad}}}", rows.join(",\n")))
    } else if value.is_array() {
        let items: Vec<Box<RawValue>> = serde_json::from_str(raw)?;
        if items.is_empty() {
            return Ok("[]".into());
        }
        let rows = items
            .iter()
            .map(|v| Ok(format!("{indent}{}", pretty(v.get(), depth + 1)?)))
            .collect::<Result<Vec<_>, Error>>()?;
        Ok(format!("[\n{}\n{pad}]", rows.join(",\n")))
    } else {
        Ok(value.to_string())
    }
}
/// mkstemp(suffix='.tmp'), close, replace; cleanup also runs after replacement failure.
/// Unlike checkpoint::atomic_write, this retains the source module's temp naming.
pub fn atomic_write(
    path: &Path,
    content: &str,
    before_replace: impl FnOnce(&Path, &Path) -> io::Result<()>,
) -> Result<(), Error> {
    let parent = path
        .parent()
        .ok_or_else(|| io::Error::other("missing parent"))?;
    let mut temporary = tempfile::Builder::new()
        .prefix("tmp")
        .suffix(".tmp")
        .tempfile_in(parent)?;
    // Frozen persistence bytes are explicitly UTF-8 with LF on every target.
    temporary.write_all(content.as_bytes())?;
    temporary.flush()?;
    let temporary = temporary.into_temp_path();
    before_replace(&temporary, path)?;
    temporary.persist(path).map_err(|e| Error::from(e.error))?;
    Ok(())
}
pub fn persist_dispatch_brief(
    brief: &DispatchBrief,
    repo_root: &Path,
    dispatch_root: Option<&Path>,
) -> Result<PathBuf, Error> {
    persist_dispatch_brief_with(brief, repo_root, dispatch_root, |_, _| Ok(()))
}
pub fn persist_dispatch_brief_with(
    brief: &DispatchBrief,
    repo_root: &Path,
    dispatch_root: Option<&Path>,
    before_replace: impl FnOnce(&Path, &Path) -> io::Result<()>,
) -> Result<PathBuf, Error> {
    let data = brief.to_dict();
    let target = if let Some(root) = dispatch_root {
        root.join(data["task_id"].as_str().unwrap_or(""))
            .join(format!("{}.json", data["slice_id"].as_str().unwrap_or("")))
    } else {
        repo_root.join(data["resume_state_ref"].as_str().unwrap_or(""))
    };
    fs::create_dir_all(
        target
            .parent()
            .ok_or_else(|| io::Error::other("missing parent"))?,
    )?;
    atomic_write(
        &target,
        &(pretty(&brief.to_json(), 0)? + "\n"),
        before_replace,
    )?;
    Ok(target)
}
pub fn load_dispatch_brief(path: &Path) -> Result<DispatchBrief, Error> {
    validate_brief_json(
        &fs::read_to_string(path)?
            .replace("\r\n", "\n")
            .replace('\r', "\n"),
    )
}
