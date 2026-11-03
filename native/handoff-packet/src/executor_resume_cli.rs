//! Saved dispatch restoration followed by the shared native dispatch CLI path.
use crate::{
    executor_execute as execute,
    executor_registry::JobRegistry,
    executor_resume,
    local_bridge::{BridgeConfig, LocalBridge},
};
use rusqlite::{Connection, OpenFlags, types::ValueRef};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    ffi::OsString,
    fs,
    io::Read,
    path::{Component, Path, PathBuf},
    time::Duration,
};

type Result<T> = std::result::Result<T, String>;
struct Args {
    root: PathBuf,
    db: PathBuf,
    job: String,
    timeout: Option<Value>,
}
fn parse(raw: &[OsString], cwd: &Path) -> Option<Args> {
    let words = raw.iter().map(|v| v.to_str()).collect::<Option<Vec<_>>>()?;
    let mut command = false;
    let mut root = cwd.to_owned();
    let mut db = None;
    let mut job = None;
    let mut timeout = None;
    let mut seen = BTreeSet::new();
    let mut i = 0;
    while i < words.len() {
        if words[i] == "resume" && !command {
            command = true;
            i += 1;
            continue;
        }
        let (flag, inline) = words[i]
            .split_once('=')
            .map_or((words[i], None), |(a, b)| (a, Some(b)));
        if matches!(flag, "--async" | "-a") && command && inline.is_none() {
            i += 1;
            continue;
        }
        if !matches!(flag, "--jobs-db" | "--repo-root" | "--job-id" | "--timeout")
            || (flag == "--jobs-db" && command)
            || (flag != "--jobs-db" && !command)
            || !seen.insert(flag)
        {
            return None;
        }
        let value = if let Some(value) = inline {
            value
        } else {
            i += 1;
            let value = *words.get(i)?;
            if value.starts_with('-') && flag != "--timeout" {
                return None;
            }
            value
        };
        match flag {
            "--jobs-db" => db = Some(PathBuf::from(value)),
            "--repo-root" => root = PathBuf::from(value),
            "--job-id" => job = Some(value.to_owned()),
            "--timeout" => timeout = Some(json!(value.parse::<i64>().ok()?)),
            _ => return None,
        }
        i += 1;
    }
    if !command {
        return None;
    }
    if !root.is_absolute() {
        root = cwd.join(root);
    }
    let root = crate::supply::plain(fs::canonicalize(root).ok()?);
    let db = db.unwrap_or_else(|| root.join("tasks").join("jobs.db"));
    let db = if db.is_absolute() { db } else { cwd.join(db) };
    if db.components().any(|c| c == Component::ParentDir) {
        return None;
    }
    Some(Args {
        root,
        db,
        job: job?,
        timeout,
    })
}
// Read without migration or sidecar creation, so unsupported saved targets can
// return to the reference before ownership and before importing local hooks.
fn read_row(path: &Path, id: &str) -> Result<Option<Value>> {
    match fs::symlink_metadata(path) {
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Ok(metadata) if metadata.is_file() => (),
        _ => return Err("resume registry is not a regular file or metadata unavailable".into()),
    }
    let mut header = [0; 100];
    fs::File::open(path)
        .map_err(|e| format!("resume registry read: {e}"))?
        .read_exact(&mut header)
        .map_err(|e| format!("resume registry read: {e}"))?;
    if &header[..16] != b"SQLite format 3\0" || header[18] != 1 || header[19] != 1 {
        return Err("resume registry unsupported SQLite header/journal mode".into());
    }
    for suffix in ["-journal", "-wal", "-shm"] {
        let mut sidecar = path.as_os_str().to_owned();
        sidecar.push(suffix);
        if Path::new(&sidecar).exists() {
            return Err("resume registry sidecar present".into());
        }
    }
    let db = Connection::open_with_flags(
        path,
        OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_NOFOLLOW,
    )
    .map_err(|e| format!("resume registry read: {e}"))?;
    let mut stmt = db
        .prepare("SELECT * FROM jobs WHERE job_id=?")
        .map_err(|e| format!("resume registry read: {e}"))?;
    let names = stmt
        .column_names()
        .iter()
        .map(|s| s.to_string())
        .collect::<Vec<_>>();
    let mut rows = stmt
        .query([id])
        .map_err(|e| format!("resume registry read: {e}"))?;
    let Some(row) = rows
        .next()
        .map_err(|e| format!("resume registry read: {e}"))?
    else {
        return Ok(None);
    };
    let mut result = json!({});
    for (index, name) in names.iter().enumerate() {
        let value = match row
            .get_ref(index)
            .map_err(|e| format!("resume registry read: {e}"))?
        {
            ValueRef::Null => Value::Null,
            ValueRef::Integer(n) => {
                if matches!(
                    name.as_str(),
                    "allow_harness_self_modify" | "cancel_requested"
                ) {
                    json!(n != 0)
                } else {
                    json!(n)
                }
            }
            ValueRef::Real(n) => json!(n),
            ValueRef::Text(bytes) => {
                let text =
                    std::str::from_utf8(bytes).map_err(|e| format!("resume registry read: {e}"))?;
                if matches!(
                    name.as_str(),
                    "codex_args" | "identity_json" | "ai_run_metadata"
                ) {
                    serde_json::from_str(text).map_err(|e| format!("resume registry read: {e}"))?
                } else {
                    json!(text)
                }
            }
            ValueRef::Blob(_) => return Err("resume registry blob column unsupported".into()),
        };
        result[name] = value;
    }
    Ok(Some(result))
}
fn defaults(root: &Path, db: &Path) -> Result<Value> {
    let schema: Value = serde_json::from_str(include_str!(
        "../tests/fixtures/executor_admission_schema.json"
    ))
    .map_err(|e| e.to_string())?;
    let mut args = json!({"subcommand":"execute","dispatch":true,"jobs_db":db});
    for option in schema["execute"]
        .as_array()
        .ok_or("missing execute schema")?
    {
        let key = option["dest"]
            .as_str()
            .ok_or("missing schema destination")?;
        if option["default"] != "==SUPPRESS==" {
            args[key] = option["default"].clone();
        }
    }
    args["repo_root"] = json!(root);
    args["dispatch"] = json!(true);
    Ok(args)
}
fn wire_paths(args: &mut Value) {
    for name in [
        "repo_root",
        "dispatch_brief",
        "artifacts_dir",
        "agent_definition_path",
    ] {
        if let Some(raw) = args[name].as_str() {
            args[name] = json!({"$type":"path","value":raw});
        }
    }
}
fn prepare_error(error: crate::executor_dispatch::Error, row: &Value) -> String {
    let timeout = match &error {
        crate::executor_dispatch::Error::Local(crate::executor_local::Error::Io(_)) => {
            // E10 reports brief reads and local configuration reads through the
            // same error variant. Resolve that ambiguity only on its error path.
            let saved = row["dispatch_options_json"]
                .as_str()
                .and_then(|text| serde_json::from_str::<Value>(text).ok());
            saved.is_none_or(|saved| {
                let brief = saved["dispatch_brief"]
                    .as_str()
                    .filter(|value| !value.is_empty())
                    .or_else(|| row["dispatch_brief_path"].as_str());
                brief.is_some_and(|path| fs::read(path).is_ok())
            })
        }
        crate::executor_dispatch::Error::Local(_) => true,
        _ => false,
    };
    format!(
        "resume {} error: {error}",
        if timeout { "timeout" } else { "integrity" }
    )
}
struct Lease {
    bridge: Option<Box<LocalBridge>>,
    handle: Option<String>,
}
impl Lease {
    fn exit(&mut self) -> Result<()> {
        if let (Some(bridge), Some(handle)) = (self.bridge.as_mut(), self.handle.take()) {
            let reply = bridge
                .call(
                    "writer_scope.exit",
                    vec![Value::Null],
                    json!({"handles":{"0":handle}}),
                )
                .map_err(|e| e.to_string())?;
            if reply["ok"] != true {
                return Err(format!(
                    "{}: {}",
                    reply["error"]["type"].as_str().unwrap_or("Error"),
                    reply["error"]["message"].as_str().unwrap_or("")
                ));
            }
        }
        Ok(())
    }
}
impl Drop for Lease {
    fn drop(&mut self) {
        let _ = self.exit();
    }
}
/// Exit 64 declines silently before the ownership receipt or Python effects.
pub fn run(raw: &[OsString], cwd: &Path, home: &Path) -> i32 {
    let Some(cli) = parse(raw, cwd) else {
        return crate::executor_protocol::decline("resume options/root parse");
    };
    if fs::canonicalize(home)
        .ok()
        .map(crate::supply::plain)
        .as_ref()
        != Some(&cli.root)
    {
        return crate::executor_protocol::decline("resume home/root mismatch");
    }
    let row = match read_row(&cli.db, &cli.job) {
        Ok(row) => row,
        Err(reason) => return crate::executor_protocol::decline(&reason),
    };
    if let Some(row) = &row {
        if row["repo_root"]
            .as_str()
            .and_then(|p| fs::canonicalize(p).ok())
            .map(crate::supply::plain)
            .as_ref()
            != Some(&cli.root)
        {
            return crate::executor_protocol::decline("resume saved root mismatch");
        }
        let saved = row["dispatch_options_json"]
            .as_str()
            .and_then(|s| serde_json::from_str::<Value>(s).ok());
        let backend = saved
            .as_ref()
            .and_then(|s| s.get("execution_backend"))
            .unwrap_or(&row["execution_backend"]);
        if backend
            .as_str()
            .is_some_and(|s| !matches!(s, "codex" | "claude"))
        {
            return crate::executor_protocol::decline("resume unsupported backend");
        }
    }
    let local = cli.root.join("tools").join("mir_executor").join("local.py");
    match fs::read(local) {
        Ok(source)
            if source
                .windows(b"register_execute_options".len())
                .any(|s| s == b"register_execute_options") =>
        {
            return crate::executor_protocol::decline("resume local parser extension");
        }
        Ok(_) => (),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => (),
        Err(_) => return crate::executor_protocol::decline("resume local source read"),
    }
    let environment: BTreeMap<OsString, OsString> = std::env::vars_os().collect();
    let target_policy = match crate::executor_admission::native_policy(&cli.root) {
        Ok(policy) => policy,
        Err(error) => {
            crate::executor_protocol::claim();
            execute::diagnostic(&error);
            return 1;
        }
    };
    let native_only = target_policy.is_some()
        && !cli
            .root
            .join("tools")
            .join("mir_executor")
            .join("local.py")
            .exists();
    let python = execute::interpreter(&environment, cwd)
        .or_else(|| native_only.then(|| cwd.join("unused-python")));
    let Some(python) = python else {
        return crate::executor_protocol::decline("resume Python interpreter lookup");
    };
    crate::executor_protocol::claim();
    let result = (|| -> Result<i32> {
        // The reference constructor migrates the registry before inspecting its job.
        let registry = JobRegistry::open(&cli.db).map_err(|e| format!("registry error: {e:?}"))?;
        drop(registry);
        let row = row.ok_or("resume requires an existing job with a dispatch_brief_path")?;
        if row["dispatch_brief_path"]
            .as_str()
            .is_none_or(str::is_empty)
        {
            return Err("resume requires an existing job with a dispatch_brief_path".into());
        }
        let mut prepared =
            executor_resume::prepare(&row, &defaults(&cli.root, &cli.db)?, cli.timeout)
                .map_err(|e| prepare_error(e, &row))?;
        wire_paths(&mut prepared.args);
        let native_policy = target_policy;
        let bridge = LocalBridge::start_in(
            BridgeConfig {
                interpreter: python,
                target_root: cli.root.clone(),
                bridge_script: home
                    .join("tools")
                    .join("mir_executor")
                    .join("local_bridge.py"),
                environment: environment.clone(),
                timeout: Duration::from_secs(10),
            },
            cwd,
        )
        .map_err(|e| e.to_string())?
        .map(Box::new);
        if bridge
            .as_ref()
            .is_some_and(|b| b.hello()["register_execute_options"] == true)
        {
            return Err("local import dynamically registered execute options; native ownership is final, invoke Python explicitly".into());
        }
        let mut lease = Lease {
            bridge,
            handle: None,
        };
        execute::line(&format!(
            "[RESUME] job_id={} allow_harness_self_modify={}",
            cli.job,
            if row["allow_harness_self_modify"] == true {
                "True"
            } else {
                "False"
            }
        ));
        if let Some(bridge) = lease.bridge.as_mut() {
            let reply = bridge
                .call("writer_scope", vec![execute::path(&cli.root)], json!({}))
                .map_err(|e| e.to_string())?;
            if reply["ok"] != true {
                return Err(format!(
                    "{}: {}",
                    reply["error"]["type"].as_str().unwrap_or("Error"),
                    reply["error"]["message"].as_str().unwrap_or("")
                ));
            }
            if let Some(handle) = reply["handle"].as_str() {
                lease.handle = Some(handle.to_owned());
                let reply = bridge
                    .call(
                        "writer_scope.enter",
                        vec![Value::Null],
                        json!({"handles":{"0":handle}}),
                    )
                    .map_err(|e| e.to_string())?;
                if reply["ok"] != true {
                    return Err(format!(
                        "{}: {}",
                        reply["error"]["type"].as_str().unwrap_or("Error"),
                        reply["error"]["message"].as_str().unwrap_or("")
                    ));
                }
            }
        }
        if let Some(policy) = native_policy {
            policy
                .pre_execute(&cli.root, cwd, &cli.root, &mut prepared.args, &environment)
                .map_err(|error| {
                    if let Some(stderr) = error.stderr {
                        let _ = execute::emit(&stderr, true);
                    }
                    format!("{}: {}", error.kind, error.message)
                })?;
        } else if let Some(bridge) = lease.bridge.as_mut() {
            let reply = bridge
                .call(
                    "pre_execute",
                    vec![execute::namespace(&prepared.args), execute::path(&cli.root)],
                    json!({}),
                )
                .map_err(|e| e.to_string())?;
            if reply["ok"] != true {
                return Err(format!(
                    "{}: {}",
                    reply["error"]["type"].as_str().unwrap_or("Error"),
                    reply["error"]["message"].as_str().unwrap_or("")
                ));
            }
            prepared.args = reply["args"][0]["value"].clone();
            if !prepared.args.is_object() {
                return Err("missing post-hook namespace".into());
            }
        }
        if fs::canonicalize(execute::value_path(&prepared.args["repo_root"], cwd))
            .ok()
            .map(crate::supply::plain)
            .as_ref()
            != Some(&cli.root)
        {
            return Err("resume root changed; refusing resume".into());
        }
        if prepared.args["execution_backend"]
            .as_str()
            .is_some_and(|s| !matches!(s, "codex" | "claude"))
        {
            return Err("pre_execute selected an unsupported native execution path".into());
        }
        let codex_args = prepared
            .codex_args
            .as_array()
            .ok_or("stored codex_args must be a list")?
            .iter()
            .map(|v| {
                v.as_str()
                    .map(str::to_owned)
                    .ok_or("stored codex_args must contain strings".to_owned())
            })
            .collect::<Result<Vec<_>>>()?;
        let result = execute::dispatch(
            &cli.root,
            &prepared.args,
            Some(codex_args),
            cwd,
            &environment,
            &mut lease.bridge,
        );
        let exit = lease.exit();
        let code = result?;
        exit?;
        Ok(code)
    })();
    match result {
        Ok(code) => code,
        Err(error) => {
            execute::diagnostic(&error);
            1
        }
    }
}
