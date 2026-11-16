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
// Match pathlib.Path before filesystem access; preserve parent components.
fn python_path(raw: &str) -> PathBuf {
    let path = crate::executor_admission::lexical(Path::new(raw));
    let path = path.strip_prefix(".").unwrap_or(&path);
    #[cfg(unix)]
    if raw.starts_with("//") && !raw.starts_with("///") {
        return PathBuf::from(format!("/{}", path.display()));
    }
    if path.as_os_str().is_empty() {
        PathBuf::from(".")
    } else {
        path.to_owned()
    }
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
            let blob = value["__saved_blob"].as_array().map(|v| {
                v.iter()
                    .filter_map(Value::as_u64)
                    .map(|n| n as u8)
                    .collect::<Vec<_>>()
            });
            let raw = if let Some(bytes) = &blob {
                rusqlite::types::ValueRef::Blob(bytes)
            } else if let Some(text) = value.as_str() {
                rusqlite::types::ValueRef::Text(text.as_bytes())
            } else {
                return Err(invalid("stored dispatch options must be a JSON object"));
            };
            let decoded = crate::executor_registry::saved_json(raw).map_err(|e| {
                invalid(
                    e.split_once(": ")
                        .map_or(e.as_str(), |(_, message)| message),
                )
            })?;
            let options = decoded.to_serde();
            if !options.is_object() {
                return Err(invalid("stored dispatch options must be a JSON object"));
            }
            let saved_brief = &options["dispatch_brief"];
            let selected = if decoded["dispatch_brief"].truthy() {
                saved_brief.clone()
            } else {
                json!(brief)
            };
            let (Some(path), Some(digest)) = (selected.as_str(), options["brief_sha256"].as_str())
            else {
                return Err(invalid("stored dispatch brief requires a sha256 digest"));
            };
            let path = python_path(path);
            let bytes = fs::read(&path).map_err(|e| {
                invalid(&crate::executor_brief_profile::python_os_error_message(
                    &e, &path,
                ))
            })?;
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
            "timeout",
        ] {
            if key == "timeout" && timeout.is_some() {
                continue;
            }
            if let Some(value) = options.get(key) {
                args[key] = value.clone();
            }
        }
        for key in ["dispatch_brief", "artifacts_dir"] {
            if let Some(value) = options.get(key) {
                if !value.is_null() && !value.is_string() {
                    return Err(Error::Hook {
                        kind: "TypeError".into(),
                        message: format!(
                            "argument should be a str or an os.PathLike object where __fspath__ returns a str, not '{}'",
                            crate::executor_brief_render::python_type(value)
                        ),
                    });
                }
                args[key] = value.clone();
            }
        }
    }
    let root = Path::new(text(&args, "repo_root")?);
    let config = if root.is_file() {
        LocalConfig::default()
    } else {
        LocalConfig::load(root).map_err(Error::Local)?
    };
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
        let mut metadata = crate::executor_registry::saved_dict(&crate::python_json::Value::from(
            &self.row["ai_run_metadata"],
        ))
        .map_err(|e| invalid(&e))?
        .to_serde();
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

#[cfg(test)]
mod tests {
    use super::*;
    #[cfg(windows)]
    mod path_records {
        include!(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/tests/support/path_records.rs"
        ));
    }

    fn fixture() -> (tempfile::TempDir, Value, Value) {
        let scratch =
            Path::new(env!("CARGO_MANIFEST_DIR")).join("target/mig-scratch/sd-yoke-resume-b1");
        fs::create_dir_all(&scratch).unwrap();
        let root = tempfile::tempdir_in(scratch).unwrap();
        let brief = root.path().join("brief.json");
        fs::write(&brief, b"{}").unwrap();
        let options = json!({
            "dispatch_brief": brief,
            "brief_sha256": crate::digest::sha256(b"{}"),
        });
        let row = json!({
            "job_id": "resume-test",
            "repo_root": root.path(),
            "dispatch_brief_path": brief,
            "dispatch_options_json": options.to_string(),
        });
        (root, row, options)
    }

    #[test]
    fn resume_integrity_json_error_uses_python_character_position() {
        let (_root, mut row, _) = fixture();
        row["dispatch_options_json"] = json!("{");
        let error = prepare(&row, &json!({}), None).unwrap_err();
        assert_eq!(
            error.to_string(),
            "Expecting property name enclosed in double quotes: line 1 column 2 (char 1)"
        );
    }

    #[test]
    fn resume_integrity_requires_string_brief_and_digest() {
        let (_root, mut row, options) = fixture();
        for (field, value) in [
            ("brief_sha256", Value::Null),
            ("brief_sha256", json!(42)),
            ("dispatch_brief", json!(42)),
        ] {
            let mut saved = options.clone();
            saved[field] = value;
            row["dispatch_options_json"] = json!(saved.to_string());
            assert_eq!(
                prepare(&row, &json!({}), None).unwrap_err().to_string(),
                "stored dispatch brief requires a sha256 digest"
            );
        }
    }

    #[test]
    fn resume_integrity_read_error_keeps_python_errno_and_path() {
        let (root, mut row, mut options) = fixture();
        let missing = root.path().join("missing.json");
        options["dispatch_brief"] = json!(missing);
        row["dispatch_options_json"] = json!(options.to_string());
        let error = prepare(&row, &json!({}), None).unwrap_err();
        assert!(matches!(error, Error::Invalid(_)));
        let actual = error.to_string();
        #[cfg(not(windows))]
        let expected = format!(
            "[Errno 2] No such file or directory: {}",
            crate::executor_execute::repr(&missing.display().to_string())
        );
        #[cfg(windows)]
        let (actual, expected) = (
            path_records::root_token(
                &actual,
                &root.path().components().collect::<PathBuf>(),
                "{ROOT}",
            ),
            path_records::record("resume.2")["error"]["message"]
                .as_str()
                .unwrap()
                .replace("{ROOT}\\\\target\\\\mig-scratch\\\\resume", "{ROOT}"),
        );
        assert_eq!(actual, expected);
    }

    #[test]
    fn resume_integrity_diagnostic_normalizes_path_spelling() {
        let (_root, mut row, mut options) = fixture();
        for raw in [
            "./__b1_review_missing__/./brief.json",
            "__b1_review_missing__//brief.json/",
        ] {
            options["dispatch_brief"] = json!(raw);
            row["dispatch_options_json"] = json!(options.to_string());
            #[cfg(not(windows))]
            let expected =
                "[Errno 2] No such file or directory: '__b1_review_missing__/brief.json'";
            #[cfg(windows)]
            let expected = path_records::record("resume.0")["error"]["message"]
                .as_str()
                .unwrap()
                .to_owned();
            assert_eq!(
                prepare(&row, &json!({}), None).unwrap_err().to_string(),
                expected,
                "{raw}"
            );
        }
        assert_eq!(python_path(""), Path::new("."));
        assert_eq!(python_path("./x/../y"), Path::new("x/../y"));
        #[cfg(unix)]
        assert_eq!(python_path("//x/./y").as_os_str(), "//x/y");
    }

    #[test]
    fn resume_restored_path_type_error_remains_uncaught() {
        let (_root, mut row, mut options) = fixture();
        options["artifacts_dir"] = json!(42);
        row["dispatch_options_json"] = json!(options.to_string());
        let error = prepare(&row, &json!({}), None).unwrap_err();
        assert!(matches!(error, Error::Hook { ref kind, .. } if kind == "TypeError"));
        assert_eq!(
            error.to_string(),
            "argument should be a str or an os.PathLike object where __fspath__ returns a str, not 'int'"
        );
    }
}
