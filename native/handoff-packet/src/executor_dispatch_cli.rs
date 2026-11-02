//! CLI composition of isolated attempts, merge admission, review and finalization.
use crate::{
    executor_dispatch::{self, CodexAttempt, DispatchContext, DispatchOptions},
    executor_dispatch_provider::{self as provider, ClaudeOptions, CodexRequest},
    executor_execute::{
        Result, diagnostic, emit, hook, line, list_repr, namespace, path, prompt, repr,
        resolve_args, unique_id, utc_now, validate_ledger, value_path,
    },
    executor_finalize::{self, FinalizeOptions},
    executor_local::LocalConfig,
    executor_policy,
    executor_registry::{self, JobRegistry},
    executor_review,
    executor_verifier::GateOptions,
    local_bridge::LocalBridge,
};
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    ffi::OsString,
    fs,
    path::{Path, PathBuf},
    process::Command,
    time::Duration,
};

// Validated briefs may be project-owned objects. Preserve their bridge handle
// through rendering and target extraction rather than requiring a JSON object.
fn brief_call(
    bridge: &mut Option<Box<LocalBridge>>,
    name: &str,
    args: Vec<Value>,
    handles: Value,
) -> Result<Value> {
    let Some(bridge) = bridge.as_mut() else {
        return Ok(json!({"result":null}));
    };
    let reply = bridge
        .call(name, args, json!({"handles":handles}))
        .map_err(|e| e.to_string())?;
    if reply["ok"] != true {
        return Err(format!(
            "{}: {}",
            reply["error"]["type"].as_str().unwrap_or("Error"),
            reply["error"]["message"].as_str().unwrap_or("")
        ));
    }
    Ok(reply)
}
fn resolved(value: &Value, cwd: &Path) -> Result<PathBuf> {
    let p = value_path(value, cwd);
    // Path.resolve(strict=False), including a missing leaf.
    if p.exists() {
        return fs::canonicalize(p)
            .map(crate::supply::plain)
            .map_err(|e| e.to_string());
    }
    let parent = p.parent().ok_or("invalid path")?;
    let name = p.file_name().ok_or("invalid path")?;
    Ok(resolved(&json!(parent), cwd)?.join(name))
}
fn duration(v: &Value) -> Result<Option<Duration>> {
    v.as_f64()
        .map(|n| Duration::try_from_secs_f64(n.max(0.0)).map_err(|e| e.to_string()))
        .transpose()
}
fn strings(v: &Value) -> Vec<String> {
    v.as_array()
        .into_iter()
        .flatten()
        .filter_map(Value::as_str)
        .map(str::to_owned)
        .collect()
}
fn emit_event(
    bridge: &mut Option<Box<LocalBridge>>,
    name: &str,
    payload: Value,
    errors: Option<&mut Vec<String>>,
) -> Result<()> {
    match hook(bridge, "on_job_event", vec![json!(name), payload]) {
        Ok(_) => Ok(()),
        Err(e) => {
            if let Some(errors) = errors {
                let message = format!("on_job_event {name}: {e}");
                diagnostic(&message);
                errors.push(message);
                Ok(())
            } else {
                Err(e)
            }
        }
    }
}
fn command(
    binary: &str,
    cwd: &Path,
    environment: &BTreeMap<OsString, OsString>,
    local: &LocalConfig,
    session: &str,
    events: &Path,
) -> Command {
    let mut cmd = Command::new(binary);
    cmd.current_dir(cwd).env_clear();
    const KEYS: &[&str] = &[
        "CODEX_BIN",
        "CODEX_EVENTS_FILE",
        "CODEX_HOME",
        "CODEX_REAL_BIN",
        "COLORTERM",
        "HOME",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "LOGNAME",
        "NO_COLOR",
        "PATH",
        "SHELL",
        "TERM",
        "TMPDIR",
        "USER",
        "MIR_CODEX_SESSION_ID",
        "MIR_CODEX_MAIN",
        "MIR_DISPATCH_FALLBACK_DEPTH",
        "MIR_SUB_AGENT_POLICY",
    ];
    for (k, v) in environment {
        if !local.child_env_filter()
            || k.to_str().is_some_and(|key| {
                KEYS.contains(&key)
                    || local
                        .raw()
                        .get("child_env_extra_keys")
                        .and_then(Value::as_array)
                        .is_some_and(|a| a.iter().any(|v| v == key))
            })
        {
            cmd.env(k, v);
        }
    }
    cmd.env("MIR_CODEX_SESSION_ID", session)
        .env("CODEX_EVENTS_FILE", events);
    cmd
}
fn project(root: &Path, policy: &executor_policy::Policy) -> (Option<String>, Option<String>) {
    let profile = fs::read_to_string(root.join(".mir").join("repo-profile.toml"))
        .ok()
        .and_then(|s| s.parse::<toml::Value>().ok());
    let slug = profile
        .as_ref()
        .and_then(|p| p.get("repo")?.get("slug")?.as_str())
        .map(|s| s.trim().to_owned());
    let spec = &policy.snapshot()["delegation"]["project_declaration"];
    let declaration =
        fs::read_to_string(root.join(spec["path"].as_str().unwrap_or(".mir/repo-profile.toml")))
            .ok()
            .and_then(|s| s.parse::<toml::Value>().ok());
    let section = declaration
        .as_ref()
        .and_then(|d| d.get(spec["section"].as_str().unwrap_or("execution")));
    let fields = spec["fields"]
        .as_array()
        .cloned()
        .unwrap_or_else(|| vec![json!("backend"), json!("delegated_execution_contract")]);
    let mut found = Vec::new();
    for field in fields {
        if let Some(s) = field.as_str().and_then(|f| section?.get(f)?.as_str()) {
            for token in s
                .to_lowercase()
                .split(|c: char| !c.is_ascii_lowercase() && !c.is_ascii_digit())
            {
                if matches!(token, "codex" | "claude") && !found.iter().any(|v| v == token) {
                    found.push(token.to_owned());
                }
            }
        }
    }
    (slug, if found.len() == 1 { found.pop() } else { None })
}
fn load_policy(
    root: &Path,
    environment: &BTreeMap<OsString, OsString>,
) -> Result<executor_policy::Policy> {
    let env_text = environment
        .iter()
        .filter_map(|(k, v)| Some((k.to_str()?.to_owned(), v.to_str()?.to_owned())))
        .collect();
    #[cfg(unix)]
    let account = crate::account_home::get().ok_or("account home unavailable")?;
    #[cfg(windows)]
    let account = environment
        .get(&OsString::from("USERPROFILE"))
        .map(PathBuf::from)
        .ok_or("account home unavailable")?;
    Ok(executor_policy::load(root, &account, &env_text))
}

pub fn dispatch(
    root: &Path,
    args: &Value,
    codex_args: Option<Vec<String>>,
    cwd: &Path,
    environment: &BTreeMap<OsString, OsString>,
    bridge: &mut Option<Box<LocalBridge>>,
) -> Result<i32> {
    let local = LocalConfig::load(root).map_err(|e| format!("{}: {e}", e.kind()))?;
    if local.raw().contains_key("timeout_seconds_range") {
        for key in ["timeout", "stall_timeout", "finalize_lock_timeout"] {
            local
                .validate_timeout(args.get(key))
                .map_err(|e| format!("argument parse error: {e}"))?;
        }
    }
    let codex_args = match codex_args {
        Some(args) => args,
        None if args["codex_args"].is_null()
            && args["codex_args_file"].is_null()
            && !args["dispatch_brief"].is_null() =>
        {
            vec![]
        }
        None => {
            resolve_args(args, cwd, &local).map_err(|e| format!("argument parse error: {e}"))?
        }
    };
    let brief = if args["dispatch_brief"].is_null() {
        None
    } else {
        Some(resolved(&args["dispatch_brief"], cwd)?)
    };
    let prepared = (|| -> Result<(String, String, Option<Value>)> {
        let mut validated = if let Some(p) = &brief {
            brief_call(
                bridge,
                "validate_brief",
                vec![path(p), path(root)],
                json!({}),
            )?
        } else {
            json!({"result":null})
        };
        let mut text = prompt(&codex_args);
        if text.is_empty()
            && let Some(p) = &brief
        {
            let data: Value = serde_json::from_slice(&fs::read(p).map_err(|e| e.to_string())?)
                .map_err(|e| e.to_string())?;
            text = data["expanded_goal"]
                .as_str()
                .ok_or("DispatchBrief expanded_goal must be a string")?
                .trim()
                .into();
        }
        if text.is_empty() {
            if codex_args.is_empty() {
                return Err("DispatchBrief expanded_goal must be non-empty".into());
            }
            text = provider::CLAUDE_PROMPT.into();
        }
        if brief.is_none()
            && bridge.as_ref().is_some_and(|b| {
                b.hello()["hooks"]
                    .as_array()
                    .is_some_and(|h| h.iter().any(|h| h == "render_brief"))
            })
        {
            validated = brief_call(
                bridge,
                "validate_brief",
                vec![json!(text), path(root)],
                json!({}),
            )?;
        }
        let handles = validated["handle"]
            .as_str()
            .map_or_else(|| json!({}), |h| json!({"0":h}));
        let rendered = brief_call(
            bridge,
            "render_brief",
            vec![validated["result"].clone(), path(root)],
            handles.clone(),
        )?;
        if !rendered["handle"].is_null() && rendered["result"].is_null() {
            return Err("render_brief must return str or None".into());
        }
        let rendered = &rendered["result"];
        let brief_text = if rendered.is_null() {
            text.clone()
        } else {
            rendered
                .as_str()
                .ok_or("render_brief must return str or None")?
                .into()
        };
        let mut target = brief_call(
            bridge,
            "bridge.target_agent",
            vec![validated["result"].clone()],
            handles,
        )?["result"]
            .clone();
        if target.is_null()
            && let Some(p) = &brief
        {
            let data: Value = serde_json::from_slice(&fs::read(p).map_err(|e| e.to_string())?)
                .map_err(|e| e.to_string())?;
            target = data["target_agent"].clone();
        }
        let agent = if target.is_null() {
            None
        } else {
            let name = target
                .as_str()
                .filter(|s| !s.trim().is_empty())
                .ok_or("DispatchBrief target_agent must be a non-empty string")?;
            let route = hook(bridge, "resolve_agent_route", vec![path(root), json!(name)])?;
            if route.is_null() {
                // Local hooks may change policy; the reference reads it here.
                let policy = load_policy(root, environment)?;
                let (agent, warning) = executor_policy::agent_route(root, name, &policy)?;
                if agent
                    .as_ref()
                    .is_some_and(|a| a["execution_backend"] == "codex")
                    && !policy.warning.is_empty()
                {
                    emit(&policy.warning, true).map_err(|e| e.to_string())?;
                }
                if !warning.is_empty() {
                    emit(&warning, true).map_err(|e| e.to_string())?;
                }
                agent
            } else {
                if route["$type"] != "agent_route" || !route["value"].is_object() {
                    return Err(format!("invalid route for target agent: {}", repr(name)));
                }
                Some(executor_policy::narrow_agent_route(
                    root,
                    name,
                    route["value"].clone(),
                )?)
            }
        };
        Ok((text, brief_text, agent))
    })();
    let (text, brief_text, agent) = match prepared {
        Ok(v) => v,
        Err(e) => {
            diagnostic(&format!("DispatchBrief error: {}", strip_class(&e)));
            return Ok(1);
        }
    };
    if let Some(change) = args["change_id"].as_str() {
        validate_ledger(
            &root.join("tasks").join("tdd.json"),
            change,
            args["category"].as_str().unwrap_or(""),
        )?;
    }
    let db = if args["jobs_db"].is_null() {
        root.join("tasks").join("jobs.db")
    } else {
        resolved(&args["jobs_db"], cwd)?
    };
    let id = args["resume_job_id"]
        .as_str()
        .map(str::to_owned)
        .unwrap_or_else(unique_id);
    let dispatch_id = if args["resume_job_id"].is_null() {
        id.clone()
    } else {
        unique_id()
    };
    let change = args["change_id"]
        .as_str()
        .map(str::to_owned)
        .unwrap_or_else(|| format!("dispatch-{id}"));
    let prior = executor_dispatch::count_consecutive_codex_failures(&db, &change)
        .map_err(|e| e.to_string())?;
    let registry = JobRegistry::open(&db).map_err(|e| format!("registry error: {e:?}"))?;
    let previous = registry
        .connection()
        .query_row(
            "SELECT ai_run_metadata,dispatch_options_json FROM jobs WHERE job_id=?",
            [&id],
            |r| {
                Ok((
                    r.get::<_, Option<String>>(0)?,
                    r.get::<_, Option<String>>(1)?,
                ))
            },
        )
        .ok();
    let mut metadata = previous
        .as_ref()
        .and_then(|(m, _)| m.as_ref())
        .and_then(|s| serde_json::from_str::<Value>(s).ok())
        .filter(Value::is_object)
        .unwrap_or_else(|| json!({}));
    let mut ids = strings(&metadata["dispatch_ids"]);
    if let Some(old) = metadata["dispatch_id"].as_str()
        && !ids.iter().any(|s| s == old)
    {
        ids.push(old.into());
    }
    if !ids.contains(&dispatch_id) {
        ids.push(dispatch_id.clone());
    }
    metadata["dispatch_id"] = json!(dispatch_id);
    metadata["dispatch_ids"] = json!(ids);
    let mut pending = json!({"job_id":id,"change_id":change,"category":args["category"].as_str().unwrap_or("unclassified"),"family":args["family"],"repo_root":root,"codex_args":codex_args,"dispatch_brief_path":brief,"allow_harness_self_modify":args["allow_harness_self_modify"]==true,"timeout_seconds":args["timeout"].as_i64().unwrap_or(600),"status":"running","started_at":utc_now(),"cancel_requested":false,"resume_count":0});
    let mut errors = Vec::new();
    let work = (|| -> Result<_> {
        let policy = load_policy(root, environment)?;
        if !policy.warning.is_empty() {
            emit(&policy.warning, true).map_err(|e| e.to_string())?;
        }
        let route = policy.category(args["category"].as_str().unwrap_or(""));
        let mut model = args["model"].as_str().or_else(|| route["model"].as_str());
        let mut effort = args["reasoning_effort"]
            .as_str()
            .or_else(|| route["reasoning_effort"].as_str());
        let (slug, declared) = project(root, &policy);
        let backend = policy.backend(
            args["execution_backend"].as_str(),
            slug.as_deref(),
            declared.as_deref(),
            agent.as_ref().and_then(|a| a["execution_backend"].as_str()),
        );
        if let Some(agent) = &agent
            && agent["execution_backend"] == backend
        {
            model = args["model"]
                .as_str()
                .or_else(|| agent["model"].as_str().filter(|s| !s.is_empty()))
                .or(model);
            effort = args["reasoning_effort"]
                .as_str()
                .or_else(|| agent["reasoning_effort"].as_str().filter(|s| !s.is_empty()))
                .or(effort);
        }
        if let Some(model) = model {
            policy.guard(model, &backend, !args["model"].is_null())?;
        }
        if !args["resume_job_id"].is_null() {
            let saved = previous
                .as_ref()
                .and_then(|(_, s)| s.as_ref())
                .and_then(|s| serde_json::from_str::<Value>(s).ok());
            emit_event(
                bridge,
                "job_resumed",
                json!({"job_id":id,"path":"resume","args":namespace(args),"repo_root":path(root),"jobs_db":path(&db),"dispatch_options":saved}),
                None,
            )?;
            registry
                .mark_resumed(&id, &utc_now())
                .map_err(|e| format!("{e:?}"))?;
        } else {
            pending["identity_json"] = hook(
                bridge,
                "job_identity",
                vec![namespace(args), path(root), json!(text), json!(model)],
            )?;
            let mut options = json!({});
            for key in [
                "allow_paths",
                "verify_cmds",
                "expect_changes",
                "change_id",
                "category",
                "max_codex_attempts",
                "finalize_lock_timeout",
                "timeout",
            ] {
                options[key] = args[key].clone();
            }
            options["dispatch_brief"] = json!(brief);
            options["brief_sha256"] = brief
                .as_ref()
                .map(|p| fs::read(p).map(|b| json!(crate::digest::sha256(&b))))
                .transpose()
                .map_err(|e| e.to_string())?
                .unwrap_or(Value::Null);
            options["model"] = json!(model);
            options["reasoning_effort"] = json!(effort);
            options["execution_backend"] = json!(backend);
            options["stall_timeout"] = args["stall_timeout"].clone();
            options["artifacts_dir"] = if args["artifacts_dir"].is_null() {
                Value::Null
            } else {
                json!(resolved(&args["artifacts_dir"], cwd)?)
            };
            pending["dispatch_options_json"] =
                json!(executor_registry::json(&options, true).map_err(|e| format!("{e:?}"))?);
            registry.insert(&pending).map_err(|e| format!("{e:?}"))?;
            emit_event(
                bridge,
                "job_inserted",
                json!({"job_id":id,"path":"dispatch","args":namespace(args),"repo_root":path(root),"jobs_db":path(&db)}),
                None,
            )?;
        }
        registry
            .update_ai_run_metadata(&id, &metadata)
            .map_err(|e| format!("{e:?}"))?;
        registry
            .update_route_metadata(&id, &json!(backend), &json!(model), &json!(effort))
            .map_err(|e| format!("{e:?}"))?;
        if backend == "codex"
            && (model.is_none_or(|m| m.trim().is_empty())
                || effort.is_none_or(|e| e.trim().is_empty()))
        {
            return Err("Codex dispatch requires an explicit model and reasoning effort".into());
        }
        local
            .validate_timeout(args.get("timeout"))
            .map_err(|e| e.to_string())?;
        if backend == "codex" {
            local
                .validate_timeout(args.get("stall_timeout"))
                .map_err(|e| e.to_string())?;
        }
        let timeout = duration(&args["timeout"])?;
        let stall = duration(&args["stall_timeout"])?;
        let artifacts = if args["artifacts_dir"].is_null() {
            None
        } else {
            Some(value_path(&args["artifacts_dir"], cwd))
        };
        let mut options = DispatchOptions::new(root, &dispatch_id);
        options.brief_text = brief_text.clone();
        options.max_codex_attempts = args["max_codex_attempts"].as_i64().unwrap_or(1);
        options.prior_consecutive_codex_failures = prior as i64;
        options.artifacts_root = artifacts.clone();
        let provider_prompt = if backend == "claude" {
            provider::CLAUDE_PROMPT
        } else {
            &text
        };
        let mut context = DispatchContext {
            bridge: bridge.as_deref_mut(),
            registry: Some((&registry, &id)),
            writer_scope_held: true,
            caller_projects_result: true,
            provider_options: Some(
                json!({"prompt":provider_prompt,"model":if backend=="claude" && agent.is_none(){None}else{model},"reasoning_effort":if backend=="claude" && agent.is_none(){None}else{effort}}),
            ),
            ..Default::default()
        };
        let outcome = executor_dispatch::run_dispatch(&options, &mut context, |wt, _| {
            let events = wt.path.join(".mir-dispatch").join("events.jsonl");
            if backend == "claude" {
                let bin = environment
                    .get(&OsString::from("CLAUDE_BIN"))
                    .and_then(|s| s.to_str())
                    .unwrap_or("claude");
                provider::claude_attempt(
                    command(
                        bin,
                        &wt.path,
                        environment,
                        &local,
                        &dispatch_id,
                        &root.join("tasks").join("codex-exec-events.jsonl"),
                    ),
                    &ClaudeOptions {
                        cwd: wt.path.clone(),
                        timeout,
                        target_agent: agent
                            .as_ref()
                            .and_then(|a| a["target_agent"].as_str())
                            .map(str::to_owned),
                        model: agent.as_ref().and(model).map(str::to_owned),
                        reasoning_effort: agent.as_ref().and(effort).map(str::to_owned),
                    },
                )
            } else {
                let bin = environment
                    .get(&OsString::from("CODEX_BIN"))
                    .and_then(|s| s.to_str())
                    .unwrap_or("codex");
                let mut cmd = command(bin, cwd, environment, &local, &dispatch_id, &events);
                cmd.arg("app-server");
                let mut request = CodexRequest::new(&text, &wt.path);
                request.agent_route = agent.as_ref();
                request.model = model;
                request.reasoning_effort = effort;
                request.timeout = timeout;
                request.stall_timeout = stall;
                let call = provider::codex_call_options(root, &request)
                    .map_err(|e| executor_dispatch::Error::Runner(e.to_string()))?;
                provider::codex_attempt(
                    cmd,
                    call,
                    Duration::from_secs(15),
                    Duration::from_secs(1),
                    Some(&events),
                )
            }
            .map_err(|e| executor_dispatch::Error::Runner(e.to_string()))
        })
        .map_err(|e| format!("{}: {e}", e.kind()));
        errors.append(&mut context.event_errors);
        drop(context);
        let outcome = outcome?;
        let final_result = if let Some(wt) = &outcome.worktree {
            let mut reviewer = |wt: &crate::executor_worktree::DispatchWorktree,
                                changed: &[String]| {
                let bin = environment
                    .get(&OsString::from("CODEX_BIN"))
                    .and_then(|s| s.to_str())
                    .unwrap_or("codex");
                let mut cmd = command(
                    bin,
                    cwd,
                    environment,
                    &local,
                    &format!("{dispatch_id}-review"),
                    &root.join("tasks").join("codex-exec-events.jsonl"),
                );
                cmd.arg("app-server");
                executor_review::review(
                    cmd,
                    root,
                    &wt.path,
                    changed,
                    timeout,
                    &mut |attempt, meta| {
                        let replacement = hook(
                            bridge,
                            "after_provider_call",
                            vec![
                                json!({"$type":"codex_attempt","value":attempt.to_value()}),
                                meta.clone(),
                            ],
                        )
                        .map_err(provider::Error::Output)?;
                        if replacement.is_null() {
                            Ok(attempt)
                        } else {
                            CodexAttempt::from_value(if replacement["$type"] == "codex_attempt" {
                                &replacement["value"]
                            } else {
                                &replacement
                            })
                            .map_err(|e| provider::Error::Output(e.to_string()))
                        }
                    },
                )
                .map(|r| r.evidence)
                .map_err(|e| executor_finalize::Error::Invalid(e.to_string()))
            };
            let final_options = FinalizeOptions {
                gate: GateOptions {
                    allowlist: strings(&args["allow_paths"]),
                    verification_commands: strings(&args["verify_cmds"]),
                    allow_harness_self_modify: args["allow_harness_self_modify"] == true,
                    expect_changes: agent.as_ref().map_or_else(
                        || args["expect_changes"].as_bool().unwrap_or(true),
                        |a| a["sandbox"] != "read-only",
                    ),
                    source_env: environment
                        .iter()
                        .filter_map(|(k, v)| Some((k.to_str()?.into(), v.to_str()?.into())))
                        .collect(),
                    ..Default::default()
                },
                finalize_lock_timeout: duration(&args["finalize_lock_timeout"])?
                    .unwrap_or(Duration::from_secs(30)),
                require_review: None,
                artifacts_root: artifacts.clone(),
            };
            let required = local.raw().get("require_review") == Some(&json!(true));
            let final_result = executor_finalize::finalize_dispatch(
                wt,
                &outcome,
                &final_options,
                if required { Some(&mut reviewer) } else { None },
                None,
            )
            .map_err(|e| e.to_string())?;
            let review = fs::read(
                artifacts
                    .clone()
                    .unwrap_or_else(|| root.join("tasks").join("dispatch"))
                    .join(&dispatch_id)
                    .join("reviewer.json"),
            )
            .ok()
            .and_then(|b| serde_json::from_slice::<Value>(&b).ok());
            emit_event(
                bridge,
                "dispatch_finalized",
                json!({"job_id":id,"dispatch_id":dispatch_id,"status":outcome.status,"finalize_action":final_result.action,"merged_files":final_result.merged_files,"reason":final_result.reason,"review_evidence":review}),
                Some(&mut errors),
            )?;
            Some(final_result)
        } else {
            None
        };
        let merged = final_result.as_ref().is_some_and(|f| {
            matches!(
                f.action.as_str(),
                "merged" | "merged-but-cleanup-failed" | "reviewed" | "reviewed-but-cleanup-failed"
            )
        });
        let code = if merged {
            0
        } else {
            outcome.exit_code.filter(|c| *c != 0).unwrap_or(1)
        };
        metadata["model_id"] = outcome.model_id.as_ref().map_or(json!(model), |v| json!(v));
        metadata["tokens_used"] = json!(
            outcome
                .tokens_used
                .iter()
                .cloned()
                .collect::<BTreeMap<_, _>>()
        );
        metadata["mcp_protocol"] = json!(outcome.mcp_protocol);
        registry
            .update_ai_run_metadata(&id, &metadata)
            .map_err(|e| format!("{e:?}"))?;
        let artifact = args["artifacts_dir"]["value"]
            .as_str()
            .or_else(|| args["artifacts_dir"].as_str())
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from("tasks").join("dispatch"))
            .join(&dispatch_id);
        if outcome.status == "blocked" {
            diagnostic_dispatch(&artifact);
        }
        let reason = if let Some(f) = &final_result
            && f.action == "merged-but-cleanup-failed"
        {
            Some(format!(
                "dispatch_status={} finalize_action={} finalize_reason={}",
                outcome.status, f.action, f.reason
            ))
        } else if !merged {
            Some(format!(
                "dispatch_status={} dispatch_reason={} finalize_action={} finalize_reason={} blocked_reason={}",
                outcome.status,
                outcome.blocked_reason.as_deref().unwrap_or("None"),
                final_result.as_ref().map_or("None", |f| &f.action),
                final_result.as_ref().map_or("None", |f| &f.reason),
                final_result.as_ref().map_or_else(
                    || outcome
                        .blocked_reason
                        .as_deref()
                        .unwrap_or("no-finalize-result"),
                    |f| &f.reason
                )
            ))
        } else {
            None
        };
        let stderr = reason
            .into_iter()
            .chain(errors.iter().cloned())
            .collect::<Vec<_>>()
            .join("; ");
        registry.update_status(&id,if merged{"completed"}else{"failed"},&json!({"exit_code":code,"stdout":format!("artifacts={}",artifact.display()),"stderr":if stderr.is_empty(){None}else{Some(stderr)},"completed_at":utc_now()})).map_err(|e|format!("{e:?}"))?;
        Ok((outcome, final_result, code))
    })();
    match work {
        Ok((outcome, final_result, code)) => {
            line(&format!(
                "[DISPATCH] status={} attempts={} fell_back={} reason={}",
                outcome.status,
                outcome.attempts,
                if outcome.fell_back { "True" } else { "False" },
                outcome
                    .blocked_reason
                    .as_ref()
                    .map_or("None".into(), |r| repr(r))
            ));
            if let Some(f) = final_result {
                line(&format!(
                    "[FINALIZE] action={} reason={} merged={}",
                    f.action,
                    repr(&f.reason),
                    list_repr(&f.merged_files)
                ));
            }
            Ok(code)
        }
        Err(e) => {
            let exists = registry
                .connection()
                .query_row("SELECT 1 FROM jobs WHERE job_id=?", [&id], |r| {
                    r.get::<_, i64>(0)
                })
                .is_ok();
            if !exists {
                registry.insert(&pending).map_err(|e| format!("{e:?}"))?;
            }
            let (kind, message) = e
                .split_once(": ")
                .filter(|(k, _)| k.ends_with("Error"))
                .unwrap_or(("ValueError", &e));
            emit_event(
                bridge,
                "dispatch_failed",
                json!({"job_id":id,"dispatch_id":dispatch_id,"error_type":kind,"message":message}),
                Some(&mut errors),
            )?;
            let stderr = std::iter::once(message.to_owned())
                .chain(errors)
                .collect::<Vec<_>>()
                .join("; ");
            registry
                .update_status(
                    &id,
                    "failed",
                    &json!({"exit_code":1,"stderr":stderr,"completed_at":utc_now()}),
                )
                .map_err(|e| format!("{e:?}"))?;
            diagnostic(&format!("dispatch failed: {message}"));
            Ok(1)
        }
    }
}
fn strip_class(s: &str) -> &str {
    s.split_once(": ")
        .filter(|(k, _)| k.ends_with("Error"))
        .map_or(s, |(_, v)| v)
}
fn diagnostic_dispatch(path: &Path) {
    let _ = emit(
        &format!(
            "[DISPATCH] blocked; inspect the job artifacts under {} for the failing step\n",
            path.display()
        ),
        true,
    );
}
