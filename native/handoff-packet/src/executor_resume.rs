//! Integrity-bound resume preparation; no CLI selection or provider startup.
//! Parser defaults and route policy are supplied by the owning execution layer.
use crate::{
    executor_command_hooks::HookClient,
    executor_dispatch::{
        self, CodexAttempt, DispatchContext, DispatchOptions, DispatchOutcome, Error, Result,
    },
    executor_local::LocalConfig,
    executor_registry::JobRegistry,
};
use serde_json::{Value, json};
use std::{
    fs,
    path::{Path, PathBuf},
};

/// Unknown saved fields are tolerated for compatibility with repository extensions.
#[derive(Debug)]
pub struct PreparedResume {
    pub args: Value,
    pub codex_args: Value,
    row: Value,
    saved: Option<Value>,
    authorized: bool,
    attempt: Option<String>,
}
fn invalid(message: &str) -> Error {
    Error::Invalid(message.into())
}
fn text<'a>(v: &'a Value, key: &str) -> Result<&'a str> {
    v[key]
        .as_str()
        .ok_or_else(|| invalid(&format!("invalid saved {key}")))
}
fn path_wire(v: &Value) -> Value {
    if v.is_null() {
        Value::Null
    } else {
        json!({"$type":"path","value":v})
    }
}
fn namespace(args: &Value) -> Value {
    let mut args = args.clone();
    if let Some(map) = args.as_object_mut() {
        map.remove("__native_brief");
    }
    for key in [
        "repo_root",
        "dispatch_brief",
        "artifacts_dir",
        "agent_definition_path",
    ] {
        if args.get(key).is_some() {
            args[key] = path_wire(&args[key]);
        }
    }
    json!({"$type":"namespace","value":args})
}
fn hook(bridge: &mut dyn HookClient, name: &str, args: Vec<Value>) -> Result<Value> {
    let reply = bridge.call(name, args, json!({})).map_err(Error::Bridge)?;
    if reply["ok"] != true {
        return Err(Error::Hook {
            kind: reply["error"]["type"]
                .as_str()
                .unwrap_or("RuntimeError")
                .into(),
            message: reply["error"]["message"]
                .as_str()
                .unwrap_or("hook refused")
                .into(),
        });
    }
    Ok(reply)
}
/// Pure read/validation phase. A caller must load the row without migrating its
/// registry, then authorize it before opening a writable registry or launching.
pub fn prepare(row: &Value, defaults: &Value, timeout: Option<Value>) -> Result<PreparedResume> {
    text(row, "job_id")?;
    let brief = text(row, "dispatch_brief_path")?;
    if brief.is_empty() {
        return Err(invalid("resume requires a dispatch_brief_path"));
    }
    let saved = match row.get("dispatch_options_json").filter(|v| !v.is_null()) {
        Some(value) => {
            let options: Value = serde_json::from_str(
                value
                    .as_str()
                    .ok_or_else(|| invalid("stored dispatch options must be a JSON object"))?,
            )
            .map_err(Error::Json)?;
            if !options.is_object() {
                return Err(invalid("stored dispatch options must be a JSON object"));
            }
            let path = options["dispatch_brief"]
                .as_str()
                .filter(|p| !p.is_empty())
                .unwrap_or(brief);
            let digest = text(&options, "brief_sha256")?;
            let bytes =
                fs::read(path).map_err(|e| Error::Local(crate::executor_local::Error::Io(e)))?;
            if crate::digest::sha256(&bytes) != digest {
                return Err(invalid("dispatch brief sha256 changed; refusing resume"));
            }
            Some(options)
        }
        None => None,
    };
    if !defaults.is_object() {
        return Err(invalid("execute defaults must be an object"));
    }
    let mut args = defaults.clone();
    for key in [
        "repo_root",
        "execution_backend",
        "target_agent",
        "agent_definition_path",
        "family",
        "category",
        "allow_harness_self_modify",
    ] {
        args[key] = row[key].clone();
    }
    args["resume_job_id"] = row["job_id"].clone();
    args["dispatch_brief"] = row["dispatch_brief_path"].clone();
    args["model"] = row["resolved_model"].clone();
    args["reasoning_effort"] = row["resolved_reasoning_effort"].clone();
    args["timeout"] = timeout
        .clone()
        .unwrap_or_else(|| row["timeout_seconds"].clone());
    if let Some(options) = &saved {
        // Fifteen saved fields include the integrity receipt. Fourteen are
        // execution options; the receipt is consumed above, never a CLI option.
        for key in [
            "allow_paths",
            "verify_cmds",
            "expect_changes",
            "change_id",
            "category",
            "model",
            "reasoning_effort",
            "max_codex_attempts",
            "execution_backend",
            "finalize_lock_timeout",
            "stall_timeout",
            "dispatch_brief",
            "artifacts_dir",
            "timeout",
        ] {
            if key == "timeout" && timeout.is_some() {
                continue;
            }
            if let Some(value) = options.get(key) {
                args[key] = value.clone();
            }
        }
    }
    let root = Path::new(text(&args, "repo_root")?);
    let config = LocalConfig::load(root).map_err(Error::Local)?;
    if config.raw().contains_key("timeout_seconds_range") {
        for key in ["timeout", "stall_timeout", "finalize_lock_timeout"] {
            config
                .validate_timeout(args.get(key))
                .map_err(Error::Local)?;
        }
    }
    Ok(PreparedResume {
        args,
        codex_args: row["codex_args"].clone(),
        row: row.clone(),
        saved,
        authorized: false,
        attempt: None,
    })
}
impl PreparedResume {
    /// Re-authorize the saved target through the invoking owner's bridge.
    /// Target hook validation precedes all durable resume writes and events.
    pub fn authorize(
        &mut self,
        owner: &Path,
        authority: &mut dyn HookClient,
        target: &mut dyn HookClient,
    ) -> Result<()> {
        self.authorized = false;
        let root = PathBuf::from(text(&self.args, "repo_root")?);
        hook(
            authority,
            "authorize_target",
            vec![
                path_wire(&json!(owner)),
                path_wire(&json!(root)),
                namespace(&self.args),
            ],
        )?;
        let reply = hook(
            target,
            "pre_execute",
            vec![namespace(&self.args), path_wire(&json!(root))],
        )?;
        if let Some(args) = reply
            .get("args")
            .and_then(|a| a.get(0))
            .and_then(|v| v.get("value"))
        {
            let mut args = args.clone();
            for key in [
                "repo_root",
                "dispatch_brief",
                "artifacts_dir",
                "agent_definition_path",
            ] {
                if args[key]["$type"] == "path" {
                    args[key] = args[key]["value"].clone();
                }
            }
            let next = Path::new(text(&args, "repo_root")?);
            if fs::canonicalize(next)
                .map_err(|e| Error::Local(crate::executor_local::Error::Io(e)))?
                != fs::canonicalize(&root)
                    .map_err(|e| Error::Local(crate::executor_local::Error::Io(e)))?
            {
                hook(
                    authority,
                    "authorize_target",
                    vec![
                        path_wire(&json!(owner)),
                        path_wire(&json!(next)),
                        namespace(&args),
                    ],
                )?;
                return Err(invalid("resume root changed; refusing resume"));
            }
            self.args = args;
        }
        hook(
            target,
            "validate_brief",
            vec![
                path_wire(&self.args["dispatch_brief"]),
                path_wire(&json!(root)),
            ],
        )?;
        self.authorized = true;
        Ok(())
    }
    /// Start one attempt on the same job. Call only after authorization and route
    /// resolution; the caller supplies a fresh attempt ID, as in E8 orchestration.
    pub fn begin(
        &mut self,
        registry: &JobRegistry,
        attempt: &str,
        at: &str,
        bridge: Option<&mut dyn HookClient>,
    ) -> Result<()> {
        if !self.authorized || self.attempt.is_some() {
            return Err(invalid("resume requires reauthorization"));
        }
        let id = text(&self.row, "job_id")?;
        let mut metadata = self.row["ai_run_metadata"].clone();
        if !metadata.is_object() {
            metadata = json!({});
        }
        let mut ids = Vec::<String>::new();
        for v in metadata["dispatch_ids"]
            .as_array()
            .into_iter()
            .flatten()
            .chain(std::iter::once(&metadata["dispatch_id"]))
        {
            if let Some(v) = v.as_str()
                && !ids.iter().any(|id| id == v)
            {
                ids.push(v.into());
            }
        }
        if attempt.is_empty() || attempt == id || ids.iter().any(|id| id == attempt) {
            return Err(invalid("resume requires a new attempt id"));
        }
        ids.push(attempt.into());
        metadata["dispatch_id"] = json!(attempt);
        metadata["dispatch_ids"] = json!(ids);
        if let Some(bridge) = bridge {
            // Resume event errors propagate, matching the Python resume handler.
            hook(
                bridge,
                "on_job_event",
                vec![
                    json!("job_resumed"),
                    json!({"job_id":id,"path":"resume","args":namespace(&self.args),"repo_root":path_wire(&self.args["repo_root"]),"jobs_db":self.args["jobs_db"],"dispatch_options":self.saved}),
                ],
            )?;
        }
        registry.mark_resumed(id, at).map_err(Error::Registry)?;
        registry
            .update_ai_run_metadata(id, &metadata)
            .map_err(Error::Registry)?;
        registry
            .update_route_metadata(
                id,
                &self.args["execution_backend"],
                &self.args["model"],
                &self.args["reasoning_effort"],
            )
            .map_err(Error::Registry)?;
        self.attempt = Some(attempt.into());
        Ok(())
    }
    /// Feed a prepared resume into E8. E9 finalization remains caller-owned,
    /// with restored verification, allow paths and finalization options in args.
    pub fn dispatch<F>(
        &self,
        options: &DispatchOptions,
        context: &mut DispatchContext<'_>,
        runner: F,
    ) -> Result<DispatchOutcome>
    where
        F: FnMut(&crate::executor_worktree::DispatchWorktree, usize) -> Result<CodexAttempt>,
    {
        if !self.authorized
            || self.attempt.as_deref() != Some(options.dispatch_id.as_str())
            || context.registry.map(|(_, id)| id) != self.row["job_id"].as_str()
        {
            return Err(invalid(
                "resume dispatch requires its authorized job and started attempt",
            ));
        }
        if options.main_repo_root != Path::new(text(&self.args, "repo_root")?) {
            return Err(invalid("resume root changed; refusing resume"));
        }
        executor_dispatch::run_dispatch(options, context, runner)
    }
}
