//! Saved dispatch restoration followed by the shared native dispatch CLI path.
use crate::{
    executor_command_hooks::{CommandHooks, TeardownOutcome},
    executor_execute as execute,
    executor_registry::JobRegistry,
    executor_resume,
    executor_text::IoOperation,
    local_bridge::BridgeConfig,
};
use rusqlite::{Connection, OpenFlags, types::ValueRef};
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    ffi::OsString,
    fs,
    path::{Path, PathBuf},
    time::Duration,
};

type Result<T> = std::result::Result<T, String>;
struct Args {
    root: PathBuf,
    db: PathBuf,
    job: String,
    timeout: Option<Value>,
    admission: Value,
}
const USAGE: &str = "usage: python -m tools.mir_executor resume --job-id JOB_ID [--timeout SECONDS]\n                                           [--async] [--repo-root PATH]\n";
fn parse(raw: &[OsString], cwd: &Path) -> Result<Args> {
    let words = raw
        .iter()
        .map(|v| crate::executor_text::os_text(v))
        .collect::<Vec<_>>();
    // cli.main parses root options first, then job-id, before building the
    // full parser. Unknown options (including timeout) have no type here.
    for (options, usage) in [
        (
            &["--repo-root", "--jobs-db"][..],
            "[--repo-root REPO_ROOT] [--jobs-db JOBS_DB] [subcommand]",
        ),
        (&["--job-id"][..], "[--job-id JOB_ID]"),
    ] {
        let mut i = 0;
        while i < words.len() {
            if words[i] == "--" {
                break;
            }
            let (key, inline) = words[i]
                .split_once('=')
                .map_or((words[i].as_str(), false), |(key, _)| (key, true));
            if let Some(flag) = options
                .iter()
                .find(|flag| key.starts_with("--") && key.len() > 2 && flag.starts_with(key))
                && !inline
            {
                i += 1;
                if !words
                    .get(i)
                    .is_some_and(|v| crate::executor_execute_parser::value_token(v))
                {
                    let prog =
                        std::env::var("MIR_EXECUTOR_ARGPARSE_PROG").unwrap_or_else(|_| "-c".into());
                    return Err(format!(
                        "usage: {prog} {usage}\n{prog}: error: argument {flag}: expected one argument\n"
                    ));
                }
            }
            i += 1;
        }
    }
    let failure =
        |message: &str| format!("{USAGE}python -m tools.mir_executor resume: error: {message}\n");
    let mut command = false;
    let mut root = cwd.to_owned();
    let mut db = None;
    let mut job = None;
    let mut timeout = None;
    let mut use_async = false;
    let mut root_given = false;
    let mut unknown = Vec::new();
    let mut i = 0;
    while i < words.len() {
        if words[i] == "resume" && !command {
            command = true;
            i += 1;
            continue;
        }
        let (key, inline) = words[i]
            .split_once('=')
            .map_or((words[i].as_str(), None), |(a, b)| (a, Some(b)));
        let flag = if key == "-h" {
            Some("--help")
        } else if key == "-a" {
            Some("--async")
        } else {
            [
                "--jobs-db",
                "--repo-root",
                "--job-id",
                "--timeout",
                "--async",
                "--help",
            ]
            .into_iter()
            .filter(|flag| command || *flag == "--jobs-db")
            .filter(|flag| !command || *flag != "--jobs-db")
            .find(|flag| {
                *flag == key || (key.starts_with("--") && key.len() > 2 && flag.starts_with(key))
            })
        };
        let Some(flag) = flag.filter(|flag| command || *flag == "--jobs-db") else {
            unknown.push(words[i].clone());
            i += 1;
            continue;
        };
        if flag == "--help" || flag == "--async" {
            use_async |= flag == "--async";
            i += 1;
            continue;
        }
        let value = if let Some(value) = inline {
            value
        } else {
            i += 1;
            let value = words
                .get(i)
                .filter(|v| crate::executor_execute_parser::value_token(v));
            let Some(value) = value else {
                if flag == "--job-id" {
                    let prog =
                        std::env::var("MIR_EXECUTOR_ARGPARSE_PROG").unwrap_or_else(|_| "-c".into());
                    return Err(format!(
                        "usage: {prog} [--job-id JOB_ID]\n{prog}: error: argument --job-id: expected one argument\n"
                    ));
                }
                return Err(failure(&format!("argument {flag}: expected one argument")));
            };
            value
        };
        match flag {
            "--jobs-db" => db = Some(PathBuf::from(value)),
            "--repo-root" => {
                root = PathBuf::from(value);
                root_given = true;
            }
            "--job-id" => job = Some(value.to_owned()),
            "--timeout" => {
                let number =
                    crate::executor_execute_parser::integer_text(value).ok_or_else(|| {
                        failure(&format!(
                            "argument --timeout: invalid int value: {}",
                            execute::repr(value)
                        ))
                    })?;
                timeout = Some(
                    number
                        .parse::<i64>()
                        .map_or_else(|_| json!({"__native_integer":number}), |n| json!(n)),
                );
            }
            _ => (),
        }
        i += 1;
    }
    let job = job.ok_or_else(|| failure("the following arguments are required: --job-id"))?;
    if !unknown.is_empty() {
        return Err(format!(
            "usage: python -m tools.mir_executor [-h] [--jobs-db PATH]\n                                    {{execute,status,result,cancel,resume,list-jobs,sweep}}\n                                    ...\npython -m tools.mir_executor: error: unrecognized arguments: {}\n",
            unknown.join(" ")
        ));
    }
    let admission = json!({"subcommand":"resume", "jobs_db":db.as_ref().map(|p| crate::executor_text::os_text(p.as_os_str())),
        "repo_root":if root_given {execute::path(&root)} else {Value::Null},
        "job_id":job, "timeout":timeout, "use_async":use_async});
    let root = crate::executor_admission::resolved(&root, cwd)
        .map_err(|e| crate::executor_text::io_error(e, &root, IoOperation::Win32))?;
    let db = db.unwrap_or_else(|| root.join("tasks/jobs.db"));
    let db = match crate::executor_admission::resolved(&db, cwd) {
        Ok(path) => path,
        Err(e) if e.kind() == std::io::ErrorKind::NotADirectory => {
            if db.is_absolute() {
                db
            } else {
                cwd.join(db)
            }
        }
        Err(e) => return Err(crate::executor_text::io_error(e, &db, IoOperation::Win32)),
    };
    Ok(Args {
        root,
        db,
        job,
        timeout,
        admission,
    })
}
// Read without migration or sidecar creation, so unsupported saved targets can
// return to the reference before ownership and before importing local hooks.
fn read_row(path: &Path, id: &str) -> Result<Option<Value>> {
    if !path.exists() {
        return Ok(None);
    }
    let db = Connection::open_with_flags(path, OpenFlags::SQLITE_OPEN_READ_ONLY)
        .map_err(crate::executor_text::sql_error)?;
    let mut stmt = db
        .prepare("SELECT * FROM jobs WHERE job_id=?")
        .map_err(crate::executor_text::sql_error)?;
    let names = stmt
        .column_names()
        .iter()
        .map(|s| s.to_string())
        .collect::<Vec<_>>();
    let mut rows = stmt.query([id]).map_err(crate::executor_text::sql_error)?;
    let Some(row) = rows.next().map_err(crate::executor_text::sql_error)? else {
        return Ok(None);
    };
    let mut result = json!({});
    // sqlite3 decodes the complete SQL row before _row_to_record loads JSON.
    for (index, name) in names.iter().enumerate() {
        if let ValueRef::Text(bytes) = row
            .get_ref(index)
            .map_err(crate::executor_text::sql_error)?
        {
            std::str::from_utf8(bytes).map_err(|_| {
                format!(
                    "OperationalError: Could not decode to UTF-8 column '{name}' with text {}",
                    execute::repr(&String::from_utf8_lossy(bytes))
                )
            })?;
        }
    }
    for (index, name) in names.iter().enumerate() {
        let raw = row
            .get_ref(index)
            .map_err(crate::executor_text::sql_error)?;
        if name == "codex_args" || (name == "ai_run_metadata" && raw != ValueRef::Null) {
            result[name] = crate::executor_registry::saved_json(raw)?.to_serde();
            continue;
        }
        let value = match raw {
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
                json!(text)
            }
            ValueRef::Blob(bytes) if name == "dispatch_options_json" => {
                // Decode at the integrity phase, inside its caught error boundary.
                json!({"__saved_blob":bytes})
            }
            ValueRef::Blob(bytes) => json!(bytes),
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
fn pre_execute_refusal(has_options: bool, kind: &str, message: &str) -> String {
    const CAUGHT: [&str; 9] = [
        "OSError",
        "FileNotFoundError",
        "PermissionError",
        "IsADirectoryError",
        "NotADirectoryError",
        "TypeError",
        "ValueError",
        "ValidationError",
        "UnicodeDecodeError",
    ];
    if has_options && CAUGHT.contains(&kind) {
        format!("resume root error: {message}")
    } else {
        format!("\0resume_uncaught:{kind}: {message}")
    }
}
fn prepare_error(error: crate::executor_dispatch::Error, row: &Value) -> String {
    if let crate::executor_dispatch::Error::Hook { kind, message } = &error {
        return format!("\0resume_uncaught:{kind}: {message}");
    }
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
fn report_error(error: &str) {
    if let Some(error) = error.strip_prefix("\0resume_uncaught:") {
        let _ = execute::emit(&format!("{error}\n"), true);
    } else {
        execute::diagnostic(error);
    }
}
fn parse_local(bridge: &mut CommandHooks, argv: Value, root: &Path) -> Result<Option<i32>> {
    let reply = bridge
        .call(
            "bridge.parse_execute",
            vec![argv, execute::path(root)],
            json!({}),
        )
        .map_err(|e| e.to_string())?;
    let output = &reply["result"];
    for (name, error) in [("stdout", false), ("stderr", true)] {
        let _ = execute::emit(output[name].as_str().unwrap_or(""), error);
    }
    Ok((!output["args"].is_object()).then(|| output["code"].as_i64().unwrap_or(1) as i32))
}
struct Lease {
    bridge: Option<Box<CommandHooks>>,
    handle: Option<String>,
}
impl Lease {
    fn exit(&mut self, outcome: TeardownOutcome) -> Result<()> {
        if let (Some(bridge), Some(handle)) = (self.bridge.as_mut(), self.handle.take()) {
            bridge.teardown_outcome(outcome);
            let reply = bridge
                .call(
                    "writer_scope.exit",
                    vec![Value::Null],
                    json!({"handles":{"0":handle}}),
                )
                .map_err(|e| e.to_string())?;
            if reply["ok"] != true {
                return Err(format!(
                    "\0resume_uncaught:{}: {}",
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
        let _ = self.exit(if std::thread::panicking() {
            TeardownOutcome::Uncertain
        } else {
            TeardownOutcome::Unclean
        });
    }
}
/// Exit 64 declines silently before the ownership receipt or Python effects.
pub fn run(raw: &[OsString], cwd: &Path, home: &Path) -> i32 {
    // Python resolves the invoking root as well as the selected repo root.
    // Aliased temp paths must not enter cross-target admission and spawn git.
    let home = match crate::executor_admission::resolved(home, cwd) {
        Ok(home) => home,
        Err(_) => return crate::executor_protocol::decline("resume home resolve"),
    };
    let home = home.as_path();
    let packaged = home.join("tools/mir_executor/local_bridge.py").is_file();
    let mut cli = match parse(raw, cwd) {
        Ok(cli) => cli,
        Err(_) if !packaged => {
            return crate::executor_protocol::decline("resume options/root parse");
        }
        Err(text) => {
            crate::executor_protocol::claim();
            let _ = execute::emit(&text, true);
            return 2;
        }
    };
    if raw.iter().any(|v| {
        let text = crate::executor_text::os_text(v);
        let key = text.split_once('=').map_or(text.as_str(), |(k, _)| k);
        (key == "-h" || (key.len() > 2 && key.starts_with("--") && "--help".starts_with(key)))
            || text.split_once('=').is_some_and(|(k, _)| {
                k == "-a" || (k.starts_with("--") && "--async".starts_with(k))
            })
    }) {
        return crate::executor_protocol::decline("resume unsupported parser action");
    }
    let disabled = match crate::executor_local::python_local_hooks_disabled(&cli.root) {
        Ok(disabled) => disabled,
        Err(error) => {
            crate::executor_protocol::claim();
            execute::diagnostic(&error);
            return 1;
        }
    };
    let target_policy = if cli.root.is_dir() {
        crate::executor_admission::native_policy(&cli.root)
    } else {
        Ok(None)
    };
    // A packaged parser can serve legacy resumes, but Python compatibility
    // routes must still decline before effects when native policy owns admission.
    let policy_compatibility = !matches!(&target_policy, Ok(None));
    let row = read_row(&cli.db, &cli.job).ok().flatten();
    if let Some(row) = &row {
        if (!packaged || policy_compatibility)
            && row["repo_root"]
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
        if !packaged
            && backend
                .as_str()
                .is_some_and(|s| !matches!(s, "codex" | "claude"))
        {
            return crate::executor_protocol::decline("resume unsupported backend");
        }
    }
    if let (Ok(Some(policy)), Some(row)) = (&target_policy, &row)
        && policy
            .brief_profile
            .as_ref()
            .is_some_and(|profile| profile.packet())
        && !crate::executor_packet_preflight::resume(row, cwd)
    {
        return crate::executor_protocol::decline("resume development packet representation");
    }
    let cross_target = fs::canonicalize(home)
        .ok()
        .map(crate::supply::plain)
        .as_ref()
        != Some(&cli.root);
    let native_authorized = cross_target
        && crate::executor_admission::native_policy(home)
            .is_ok_and(|p| p.is_some_and(|p| p.has_authorize_target()));
    if cross_target && (!packaged || native_authorized) {
        let family = row.as_ref().and_then(|row| row["family"].as_str());
        match crate::executor_admission::authorize_command(home, cwd, &cli.root, family, false, 2) {
            Ok(true) => (),
            Ok(false) => {
                return crate::executor_protocol::decline("resume home/root mismatch");
            }
            Err(stderr) => {
                crate::executor_protocol::claim();
                let _ = execute::emit(&String::from_utf8_lossy(&stderr), true);
                return 1;
            }
        }
    }
    let local = cli.root.join("tools").join("mir_executor").join("local.py");
    if !disabled && (!packaged || policy_compatibility) {
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
    }
    let environment: BTreeMap<OsString, OsString> = std::env::vars_os().collect();
    let target_policy = match target_policy {
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
    let python = if disabled {
        Some(cwd.join("unused-python"))
    } else {
        execute::interpreter(&environment, cwd)
            .or_else(|| native_only.then(|| cwd.join("unused-python")))
    };
    let Some(python) = python else {
        return crate::executor_protocol::decline("resume Python interpreter lookup");
    };
    crate::executor_protocol::claim();
    let result = (|| -> Result<i32> {
        let mut home_bridge = None;
        let request = crate::executor_admission::Request {
            argv: &[],
            cwd,
            invoking_home: home,
            environment: &environment,
            interpreter: &python,
            bridge_script: &home.join("tools/mir_executor/local_bridge.py"),
        };
        let preauthorized = native_authorized.then(|| cli.root.clone());
        let authorize = |root: &Path, args: &Value, home_bridge: &mut _| -> Result<()> {
            if preauthorized.as_deref() == Some(root) {
                return Ok(());
            }
            match crate::executor_admission::authorize(
                &request,
                home,
                root,
                args,
                home_bridge,
                false,
            )
            .map_err(|e| format!("\0resume_uncaught:{e}"))?
            {
                Some(crate::executor_admission::Admission::Refused { stderr, .. }) => Err(format!(
                    "\0resume_uncaught:{}",
                    String::from_utf8_lossy(&stderr).trim_end()
                )),
                _ => Ok(()),
            }
        };
        let resume_args = &cli.admission;
        authorize(&cli.root, resume_args, &mut home_bridge)?;
        let local_path = cli.root.join("tools/mir_executor/local.py");
        if local_path.is_dir() {
            let error = fs::read(&local_path)
                .err()
                .ok_or("local directory unexpectedly readable")?;
            return Err(format!(
                "\0resume_uncaught:{}",
                crate::executor_text::io_error(error, &local_path, IoOperation::Read)
            ));
        }
        let mut bridge = if cli.root.is_dir() {
            CommandHooks::start_in(
                BridgeConfig {
                    interpreter: python.clone(),
                    target_root: cli.root.clone(),
                    bridge_script: home.join("tools/mir_executor/local_bridge.py"),
                    environment: environment.clone(),
                    timeout: Duration::from_secs(10),
                },
                cwd,
            )
            .map_err(|e| format!("\0resume_uncaught:{e}"))?
            .map(Box::new)
        } else {
            None
        };
        if let Some(local) = bridge.as_mut()
            && local.hello()["register_execute_options"] == true
        {
            let argv = raw
                .iter()
                .map(|v| crate::executor_text::os_text(v))
                .collect::<Vec<_>>();
            if let Some(code) = parse_local(local, json!(argv), &cli.root)? {
                return Ok(code);
            }
        }
        authorize(&cli.root, resume_args, &mut home_bridge)?;
        if cli.root.is_dir() {
            crate::executor_local::LocalConfig::load(&cli.root).map_err(|e| e.to_string())?;
        }
        if let Some(raw_job) = raw.iter().rev().find(|v| {
            let text = crate::executor_text::os_text(v);
            text == cli.job || text.split_once('=').is_some_and(|(_, v)| v == cli.job)
        }) {
            let bytes = raw_job.as_encoded_bytes();
            let value = bytes
                .iter()
                .position(|b| *b == b'=')
                .map_or(bytes, |i| &bytes[i + 1..]);
            if let Some(error) = execute::utf8_error(&crate::executor_text::codepoints(value)) {
                return Err(error
                    .strip_prefix("UnicodeEncodeError: ")
                    .unwrap_or(&error)
                    .into());
            }
        }
        // The constructor migrates/chmods even malformed and unreadable registries.
        let registry = JobRegistry::open(&cli.db).map_err(|e| {
            format!(
                "\0resume_uncaught:{}",
                crate::executor_text::registry_error(
                    e,
                    if cli.root.is_file() {
                        cli.db.parent().unwrap_or(&cli.db)
                    } else {
                        &cli.db
                    }
                )
            )
        })?;
        drop(registry);
        let row = read_row(&cli.db, &cli.job)
            .map_err(|e| format!("\0resume_uncaught:{e}"))?
            .ok_or("resume requires an existing job with a dispatch_brief_path")?;
        if !row["codex_args"].is_array() {
            return Err("stored codex_args must be a list".into());
        }
        if row["dispatch_brief_path"]
            .as_str()
            .is_none_or(str::is_empty)
        {
            return Err("resume requires an existing job with a dispatch_brief_path".into());
        }
        let saved_root = crate::executor_admission::resolved(
            Path::new(row["repo_root"].as_str().unwrap_or("")),
            cwd,
        )
        .map_err(|e| e.to_string())?;
        authorize(&saved_root, resume_args, &mut home_bridge)?;
        if saved_root != cli.root {
            cli.root = saved_root;
            bridge = if cli.root.is_dir() {
                CommandHooks::start_in(
                    BridgeConfig {
                        interpreter: python.clone(),
                        target_root: cli.root.clone(),
                        bridge_script: home.join("tools/mir_executor/local_bridge.py"),
                        environment: environment.clone(),
                        timeout: Duration::from_secs(10),
                    },
                    cwd,
                )
                .map_err(|e| format!("\0resume_uncaught:{e}"))?
                .map(Box::new)
            } else {
                None
            };
        }
        if let Some(local) = bridge.as_mut()
            && local.hello()["register_execute_options"] == true
            && let Some(code) = parse_local(local, json!(["execute", "--dispatch"]), &cli.root)?
        {
            return Ok(code);
        }
        let mut prepared =
            executor_resume::prepare(&row, &defaults(&cli.root, &cli.db)?, cli.timeout)
                .map_err(|e| prepare_error(e, &row))?;
        wire_paths(&mut prepared.args);
        let native_policy = target_policy;
        let mut lease = Lease {
            bridge,
            handle: None,
        };
        let result = (|| {
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
                        "\0resume_uncaught:{}: {}",
                        reply["error"]["type"].as_str().unwrap_or("Error"),
                        reply["error"]["message"].as_str().unwrap_or("")
                    ));
                }
                if let Some(handle) = reply["handle"].as_str() {
                    let reply = bridge
                        .call(
                            "writer_scope.enter",
                            vec![Value::Null],
                            json!({"handles":{"0":handle}}),
                        )
                        .map_err(|e| e.to_string())?;
                    if reply["ok"] != true {
                        return Err(format!(
                            "\0resume_uncaught:{}: {}",
                            reply["error"]["type"].as_str().unwrap_or("Error"),
                            reply["error"]["message"].as_str().unwrap_or("")
                        ));
                    }
                    lease.handle = Some(handle.to_owned());
                }
            }
            // Python resumes a job with saved dispatch options through _prepare_execute_root,
            // which reports OSError, TypeError and ValueError as a resume root error.
            let has_options = !row["dispatch_options_json"].is_null();
            if let Some(policy) =
                native_policy.filter(|p| p.covered_hooks().contains(&"pre_execute"))
            {
                policy
                    .pre_execute(&cli.root, cwd, &cli.root, &mut prepared.args, &environment)
                    .map_err(|error| {
                        if let Some(stderr) = error.stderr {
                            let _ = execute::emit(&stderr, true);
                        }
                        pre_execute_refusal(has_options, &error.kind, &error.message)
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
                    return Err(pre_execute_refusal(
                        has_options,
                        reply["error"]["type"].as_str().unwrap_or("Error"),
                        reply["error"]["message"].as_str().unwrap_or(""),
                    ));
                }
                prepared.args = reply["args"][0]["value"].clone();
                if !prepared.args.is_object() {
                    return Err("missing post-hook namespace".into());
                }
            }
            if let Some(bridge) = lease.bridge.as_mut() {
                let argv = prepared.codex_args.as_array().map(|v| {
                    v.iter()
                        .filter_map(Value::as_str)
                        .map(str::to_owned)
                        .collect()
                });
                bridge
                    .bind_instruction(&cli.root, cwd, &prepared.args, argv)
                    .map_err(|e| pre_execute_refusal(has_options, &e.kind, &e.message))?;
            }
            if !crate::executor_admission::git(&request, &cli.root, "--is-inside-work-tree")
                .map_err(|e| {
                    format!(
                        "\0resume_uncaught:{}",
                        crate::executor_text::io_error(e, Path::new("git"), IoOperation::Win32)
                    )
                })?
                .status
                .success()
            {
                return Err(format!(
                    "resume root error: repo root is not a git repository: {}",
                    cli.root.display()
                ));
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
            execute::dispatch(
                &cli.root,
                &prepared.args,
                Some(codex_args),
                cwd,
                &environment,
                &mut lease.bridge,
            )
        })();
        // Caught root errors are printed inside writer_scope. Uncaught errors
        // propagate after exit, and an exit failure replaces the pending error.
        if let Err(error) = &result
            && !error.starts_with("\0resume_uncaught:")
        {
            report_error(error);
        }
        lease.exit(if matches!(result, Ok(0)) {
            TeardownOutcome::Clean
        } else {
            TeardownOutcome::Unclean
        })?;
        match result {
            Err(error) if error.starts_with("\0resume_uncaught:") => Err(error),
            result => Ok(result.unwrap_or(1)),
        }
    })();
    match result {
        Ok(code) => code,
        Err(error) => {
            report_error(&error);
            1
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn metadata_row(column: &str, value: rusqlite::types::Value) -> Result<Value> {
        let temp = tempfile::tempdir().unwrap();
        let path = temp.path().join("jobs.db");
        let db = Connection::open(&path).unwrap();
        db.execute_batch("CREATE TABLE jobs(job_id TEXT, codex_args TEXT, identity_json TEXT, ai_run_metadata TEXT, dispatch_options_json TEXT); INSERT INTO jobs VALUES('saved','[]',NULL,NULL,NULL);").unwrap();
        db.execute(&format!("UPDATE jobs SET {column}=?"), [value])
            .unwrap();
        read_row(&path, "saved").map(Option::unwrap)
    }

    #[test]
    fn saved_metadata_sqlite_storage_classes() {
        use rusqlite::types::Value as Sql;
        for value in [
            Sql::Text("[]".into()),
            Sql::Blob(b"[]".to_vec()),
            Sql::Blob(vec![0xff, 0xfe, 91, 0, 93, 0]),
            Sql::Blob(vec![0xff, 0xfe, 0, 0, 91, 0, 0, 0, 93, 0, 0, 0]),
        ] {
            assert_eq!(
                metadata_row("codex_args", value).unwrap()["codex_args"],
                json!([])
            );
        }
        for (value, expected) in [
            (Sql::Integer(42), json!(42)),
            (Sql::Real(4.25), json!(4.25)),
            (Sql::Null, Value::Null),
        ] {
            assert_eq!(
                metadata_row("ai_run_metadata", value).unwrap()["ai_run_metadata"],
                expected
            );
        }
    }

    #[test]
    fn saved_identity_is_opaque() {
        use rusqlite::types::Value as Sql;
        assert!(metadata_row("identity_json", Sql::Text("{".into())).is_ok());
        assert!(metadata_row("identity_json", Sql::Blob(vec![0xff])).is_ok());
    }

    #[test]
    fn saved_metadata_diagnostics() {
        use rusqlite::types::Value as Sql;
        assert_eq!(
            metadata_row("codex_args", Sql::Text("{".into())).unwrap_err(),
            "JSONDecodeError: Expecting property name enclosed in double quotes: line 1 column 2 (char 1)"
        );
        assert_eq!(
            metadata_row("ai_run_metadata", Sql::Blob(vec![0xff])).unwrap_err(),
            "UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff in position 0: invalid start byte"
        );
        let temp = tempfile::tempdir().unwrap();
        let path = temp.path().join("jobs.db");
        let db = Connection::open(&path).unwrap();
        db.execute_batch("CREATE TABLE jobs(job_id,codex_args,identity_json); INSERT INTO jobs VALUES('saved','{',CAST(x'ff' AS TEXT));").unwrap();
        assert_eq!(
            read_row(&path, "saved").unwrap_err(),
            "OperationalError: Could not decode to UTF-8 column 'identity_json' with text '�'"
        );
    }

    #[test]
    fn saved_metadata_python_json_shapes() {
        use rusqlite::types::Value as Sql;
        for source in [
            format!("{{\"extra\":{}0{}}}", "[".repeat(180), "]".repeat(180)),
            r#"{"extra":"\ud800"}"#.into(),
        ] {
            assert!(metadata_row("ai_run_metadata", Sql::Text(source)).is_ok());
        }
    }

    #[test]
    fn saved_metadata_scalar_dict_refusal() {
        for (source, kind) in [("42", "int"), ("4.25", "float"), ("true", "bool")] {
            let value = crate::python_json::parse(source).unwrap();
            assert_eq!(
                crate::executor_registry::saved_dict(&value).unwrap_err(),
                format!("TypeError: '{kind}' object is not iterable")
            );
        }
        for source in [
            "0",
            "false",
            "null",
            "[]",
            "{}",
            r#"[["k",1],"ab",{"x":1,"y":2},[null,0],[true,1],[2,2]]"#,
        ] {
            let value = crate::python_json::parse(source).unwrap();
            assert!(
                crate::executor_registry::saved_dict(&value)
                    .unwrap()
                    .is_object()
            );
        }
        for source in [r#""k""#, "[1]", "[[]]", "[[[],0]]"] {
            let value = crate::python_json::parse(source).unwrap();
            assert!(crate::executor_registry::saved_dict(&value).is_err());
        }
        for raw in [ValueRef::Null, ValueRef::Integer(42), ValueRef::Real(4.25)] {
            assert!(
                crate::executor_registry::saved_json(raw)
                    .unwrap_err()
                    .starts_with(
                        "TypeError: the JSON object must be str, bytes or bytearray, not "
                    )
            );
        }
    }

    #[test]
    fn saved_option_resume_reports_python_resume_root_errors() {
        assert_eq!(
            pre_execute_refusal(true, "ValueError", "owned"),
            "resume root error: owned"
        );
        assert_eq!(
            pre_execute_refusal(true, "RuntimeError", "other"),
            "\0resume_uncaught:RuntimeError: other"
        );
        assert_eq!(
            pre_execute_refusal(false, "ValueError", "owned"),
            "\0resume_uncaught:ValueError: owned"
        );
    }
}
