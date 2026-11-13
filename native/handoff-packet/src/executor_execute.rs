//! Direct execute; after admission every failure is final.
use crate::{
    executor_admission::{self, Admission},
    executor_command_hooks::{CommandHooks, TeardownOutcome},
    executor_local::LocalConfig,
    executor_policy,
    executor_registry::JobRegistry,
    executor_transport::{CallOptions, Client, Error as TransportError},
};
use rusqlite::OptionalExtension;
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    ffi::OsString,
    fs,
    io::{self, Write},
    path::{Path, PathBuf},
    process::Command,
    sync::{
        OnceLock,
        atomic::{AtomicBool, AtomicU64, Ordering},
    },
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};
pub(crate) type Result<T> = std::result::Result<T, String>;
const BASE: &str = "You are a code-implementation sub-agent in an isolated git worktree for the Mir harness. Read .mir-dispatch/brief.md and implement the task fully. Rules: modify only files inside this worktree, never edit tasks/plan.md, follow existing code style and structure, keep changes minimal and scoped to the brief, when tests are specified make them pass. Report a concise summary of what you changed.";
static SERIAL: AtomicU64 = AtomicU64::new(0);
static OUTPUT_FAILED: AtomicBool = AtomicBool::new(false);
static STDOUT_STARTED: AtomicBool = AtomicBool::new(false);
static STDERR_STARTED: AtomicBool = AtomicBool::new(false);
static NONPRINTABLE: OnceLock<std::result::Result<regex::Regex, regex::Error>> = OnceLock::new();
pub(crate) fn emit(text: &str, error: bool) -> io::Result<()> {
    if OUTPUT_FAILED.load(Ordering::Relaxed) {
        return Err(io::Error::other("output failed"));
    }
    #[cfg(windows)]
    let text = text.replace('\n', "\r\n");
    #[cfg(windows)]
    let text = text.as_str();
    let started = if error {
        &STDERR_STARTED
    } else {
        &STDOUT_STARTED
    };
    let bytes =
        match crate::executor_text::encode(text, error, !started.swap(true, Ordering::Relaxed)) {
            Ok(bytes) => bytes,
            Err(error) => {
                OUTPUT_FAILED.store(true, Ordering::Relaxed);
                let text = format!("{error}\n");
                let bytes = crate::executor_text::encode(
                    &text,
                    true,
                    !STDERR_STARTED.swap(true, Ordering::Relaxed),
                )
                .unwrap_or_else(|_| text.into_bytes());
                let _ = io::stderr().write_all(&bytes);
                return Err(io::Error::other(error));
            }
        };
    if error {
        io::stderr().write_all(&bytes)
    } else {
        io::stdout().write_all(&bytes)
    }
}
pub(crate) fn line(text: &str) {
    if emit(&format!("{text}\n"), false).is_err() {
        OUTPUT_FAILED.store(true, Ordering::Relaxed);
    }
}
pub(crate) fn diagnostic(text: &str) {
    let _ = emit(&format!("[mir_executor] {text}\n"), true);
}
pub(crate) fn path(path: &Path) -> Value {
    crate::executor_admission::path_value(path)
        .unwrap_or_else(|| json!({"$type":"path","value":""}))
}
pub(crate) fn namespace(args: &Value) -> Value {
    // The native brief cache is executor-internal; hooks and events see the Python namespace.
    let mut args = args.clone();
    if let Some(map) = args.as_object_mut() {
        map.retain(|key, _| !key.starts_with("__native_"));
    }
    json!({"$type":"namespace","value":args})
}
pub(crate) fn value_path(value: &Value, cwd: &Path) -> PathBuf {
    let p = crate::executor_admission::from_path_value(value).unwrap_or_default();
    if p.is_absolute() { p } else { cwd.join(p) }
}
pub(crate) fn repr(s: &str) -> String {
    repr_codepoints(&s.chars().map(u32::from).collect::<Vec<_>>())
}
// Code points allow POSIX argv's surrogateescape values without lossy UTF-8.
pub(crate) fn repr_codepoints(s: &[u32]) -> String {
    let nonprintable = NONPRINTABLE
        .get_or_init(|| regex::Regex::new(r"[\p{C}\p{Z}]"))
        .as_ref();
    let quote = if s.contains(&u32::from('\'')) && !s.contains(&u32::from('"')) {
        '"'
    } else {
        '\''
    };
    let mut out = quote.to_string();
    for &n in s {
        let Some(c) = char::from_u32(n) else {
            out.push_str(&format!("\\u{n:04x}"));
            continue;
        };
        match c {
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if c == quote => {
                out.push('\\');
                out.push(c);
            }
            c if c != ' '
                && nonprintable.is_ok_and(|re| re.is_match(c.encode_utf8(&mut [0; 4]))) =>
            {
                let n = c as u32;
                out.push_str(&if n <= 0xff {
                    format!("\\x{n:02x}")
                } else if n <= 0xffff {
                    format!("\\u{n:04x}")
                } else {
                    format!("\\U{n:08x}")
                });
            }
            c => out.push(c),
        }
    }
    out.push(quote);
    out
}
pub(crate) fn list_repr(values: &[String]) -> String {
    format!(
        "[{}]",
        values
            .iter()
            .map(|v| repr(v))
            .collect::<Vec<_>>()
            .join(", ")
    )
}
fn chars(s: &str, n: usize) -> String {
    s.chars().take(n).collect()
}
pub(crate) fn hook(
    bridge: &mut Option<Box<CommandHooks>>,
    name: &str,
    args: Vec<Value>,
) -> Result<Value> {
    let Some(bridge) = bridge.as_mut() else {
        return Ok(Value::Null);
    };
    let reply = bridge
        .call(name, args, json!({}))
        .map_err(|e| e.to_string())?;
    if reply["ok"] != true {
        return Err(format!(
            "{}: {}",
            reply["error"]["type"].as_str().unwrap_or("Error"),
            reply["error"]["message"].as_str().unwrap_or("")
        ));
    }
    if !reply["handle"].is_null() && reply["result"].is_null() {
        return Err(format!("TypeError: {name} returned an unsupported object"));
    }
    Ok(reply["result"].clone())
}
// vars_os preserves Windows spelling (often Path); BTreeMap lookup does not
// retain the operating system's case-insensitive environment semantics.
fn environment_value<'a>(
    environment: &'a BTreeMap<OsString, OsString>,
    name: &str,
    windows: bool,
) -> Option<&'a OsString> {
    environment.get(&OsString::from(name)).or_else(|| {
        windows
            .then(|| {
                environment.iter().find_map(|(key, value)| {
                    key.to_str()
                        .filter(|key| key.eq_ignore_ascii_case(name))
                        .map(|_| value)
                })
            })
            .flatten()
    })
}
pub(crate) fn interpreter(
    environment: &BTreeMap<OsString, OsString>,
    cwd: &Path,
) -> Option<PathBuf> {
    if let Some(p) = environment_value(environment, "MIR_EXECUTOR_PYTHON", cfg!(windows)) {
        let p = PathBuf::from(p);
        let p = if p.is_absolute() { p } else { cwd.join(p) };
        return p.is_file().then(|| crate::supply::plain(p));
    }
    let names = if cfg!(windows) {
        &["python3.exe", "python.exe"][..]
    } else {
        &["python3", "python"][..]
    };
    for dir in std::env::split_paths(environment_value(environment, "PATH", cfg!(windows))?) {
        for name in names {
            let p = dir.join(name);
            let p = if p.is_absolute() { p } else { cwd.join(p) };
            if p.is_file() {
                // The unresolved executable path selects a virtual environment.
                return Some(crate::supply::plain(p));
            }
        }
    }
    None
}
/// Raw argv includes execute; global --jobs-db may precede it. 64 declines silently.
pub fn run(raw: &[OsString], cwd: &Path, home_root: &Path) -> i32 {
    OUTPUT_FAILED.store(false, Ordering::Relaxed);
    STDOUT_STARTED.store(false, Ordering::Relaxed);
    STDERR_STARTED.store(false, Ordering::Relaxed);
    let direct = !crate::executor_execute_parser::dispatch(raw);
    let (argv, environment, python, parsed) = if direct {
        if !crate::executor_text::supported_streams() {
            return crate::executor_protocol::decline("execute stream codec or error handler");
        }
        let disabled = match crate::executor_local::python_local_hooks_disabled(home_root) {
            Ok(disabled) => disabled,
            Err(error) => {
                crate::executor_protocol::claim();
                diagnostic(&error);
                return 1;
            }
        };
        if !disabled
            && let Ok(source) = fs::read(home_root.join("tools/mir_executor/local.py"))
            && source
                .windows(b"register_execute_options".len())
                .any(|part| part == b"register_execute_options")
        {
            return crate::executor_protocol::decline(
                "execute invoking-home local parser extension",
            );
        }
        let args = match crate::executor_execute_parser::parse(raw, cwd) {
            crate::executor_execute_parser::Parsed::Args(args) => args,
            crate::executor_execute_parser::Parsed::Output {
                text,
                code,
                error,
                admission,
            } => {
                crate::executor_protocol::claim();
                if let Some(args) = admission {
                    let root = value_path(&args["repo_root"], cwd);
                    let root = match executor_admission::resolved(&root, cwd) {
                        Ok(root) => root,
                        Err(error) => {
                            let _ = emit(
                                &format!("{}\n", crate::executor_text::io_error(error, &root)),
                                true,
                            );
                            return 1;
                        }
                    };
                    if executor_admission::resolved(home_root, cwd).ok().as_ref() != Some(&root)
                        && let Err(stderr) = executor_admission::authorize_command(
                            home_root,
                            cwd,
                            &root,
                            args["family"].as_str(),
                            true,
                            1,
                        )
                    {
                        let _ = emit(&String::from_utf8_lossy(&stderr), true);
                        return 1;
                    }
                }
                return if emit(&text, error).is_err() { 1 } else { code };
            }
        };
        let environment: BTreeMap<OsString, OsString> = std::env::vars_os().collect();
        let python = interpreter(&environment, cwd).unwrap_or_else(|| cwd.join("unused-python"));
        (vec!["execute".into()], environment, python, Some(args))
    } else {
        let Some(argv) = preflight(raw) else {
            return crate::executor_protocol::decline("execute options preflight");
        };
        let target = fs::canonicalize(argv_root(&argv, cwd)).ok();
        let home = fs::canonicalize(home_root).ok();
        // Only a policy that owns pre_execute (target admission) may admit a
        // target other than the home root; an agent-route-only policy declines.
        let declared_policy = match executor_admission::native_policy(home_root) {
            Ok(policy) => policy.is_some_and(|p| p.covered_hooks().contains(&"pre_execute")),
            Err(error) => {
                crate::executor_protocol::claim();
                diagnostic(&error);
                return 1;
            }
        };
        if target.is_none() || (target != home && !declared_policy) {
            return crate::executor_protocol::decline("execute home/root mismatch");
        }
        // Decline explicit parser extensions without importing target-owned code.
        // A computed export discovered by hello is already owned and must fail finally.
        let disabled =
            match crate::executor_local::python_local_hooks_disabled(&argv_root(&argv, cwd)) {
                Ok(disabled) => disabled,
                Err(error) => {
                    crate::executor_protocol::claim();
                    diagnostic(&error);
                    return 1;
                }
            };
        let extension = argv_root(&argv, cwd).join("tools/mir_executor/local.py");
        if !disabled {
            match fs::read(extension) {
                Ok(source)
                    if source
                        .windows(b"register_execute_options".len())
                        .any(|part| part == b"register_execute_options") =>
                {
                    return crate::executor_protocol::decline("execute local parser extension");
                }
                Ok(_) => (),
                Err(error) if error.kind() == io::ErrorKind::NotFound => (),
                Err(_) => return crate::executor_protocol::decline("execute local source read"),
            }
        }
        if !ledger_preflight(&argv, cwd) {
            return crate::executor_protocol::decline("execute ledger preflight");
        }
        let environment: BTreeMap<OsString, OsString> = std::env::vars_os().collect();
        if environment_value(&environment, "CODEX_BIN", cfg!(windows))
            .is_some_and(|s| s.to_str().is_none())
        {
            return crate::executor_protocol::decline("execute non-UTF8 CODEX_BIN");
        }
        let target_policy = match executor_admission::native_policy(&argv_root(&argv, cwd)) {
            Ok(policy) => policy,
            Err(error) => {
                crate::executor_protocol::claim();
                diagnostic(&error);
                return 1;
            }
        };
        if target_policy.as_ref().is_some_and(|policy| {
            policy
                .brief_profile
                .as_ref()
                .is_some_and(|profile| profile.packet())
        }) && !crate::executor_packet_preflight::execute(&argv, cwd)
        {
            return crate::executor_protocol::decline("execute development packet representation");
        }
        let native_only = target_policy.is_some()
            && !argv_root(&argv, cwd)
                .join("tools")
                .join("mir_executor")
                .join("local.py")
                .exists();
        let python = if disabled {
            Some(cwd.join("unused-python"))
        } else {
            interpreter(&environment, cwd)
                .or_else(|| native_only.then(|| cwd.join("unused-python")))
        };
        let Some(python) = python else {
            return crate::executor_protocol::decline("execute Python interpreter lookup");
        };
        (argv, environment, python, None)
    };
    let request = executor_admission::Request {
        argv: &argv,
        cwd,
        invoking_home: home_root,
        environment: &environment,
        interpreter: &python,
        bridge_script: &home_root.join("tools/mir_executor/local_bridge.py"),
    };
    let admission = if let Some(args) = parsed {
        executor_admission::admit_execute_args(request, args)
    } else {
        executor_admission::admit_execute(request)
    };
    let (root, args, mut bridge, writer_handle) = match admission {
        Ok(Admission::Admitted {
            root,
            args,
            bridge,
            writer_handle,
            ..
        }) => (root, args, bridge, writer_handle),
        Ok(Admission::Decline { reason, .. }) if !direct => {
            return crate::executor_protocol::decline(reason);
        }
        Ok(Admission::Decline { .. }) => {
            crate::executor_protocol::claim();
            diagnostic("native execute admission refused common arguments");
            return 1;
        }
        Ok(Admission::Refused { code, stderr }) => {
            let _ = emit(&String::from_utf8_lossy(&stderr), true);
            return code;
        }
        Err(e) => {
            let error = e.to_string();
            if direct && error.starts_with("UnicodeEncodeError:") {
                let _ = emit(&format!("{error}\n"), true);
            } else {
                diagnostic(&error);
            }
            return 1;
        }
    };
    let result = if args["dispatch"] == true {
        dispatch(&root, &args, None, cwd, &environment, &mut bridge)
    } else {
        execute(&root, &args, cwd, &environment, &mut bridge)
    };
    let mut code = match result {
        Ok(code) => code,
        Err(error) => {
            if let Some(error) = error.strip_prefix("\0uncaught:") {
                let _ = emit(&format!("{error}\n"), true);
            } else if let Some(error) = error.strip_prefix("\0caught:") {
                diagnostic(error);
            } else if direct
                && (error.starts_with("sqlite3.")
                    || error.starts_with("AttributeError:")
                    || error.starts_with("TypeError:")
                    || error.starts_with("RuntimeError:")
                    || error.starts_with("NativeHookError:")
                    || error
                        .starts_with("tools.mir_executor.codex_mcp_client.CodexMcpTimeoutError:")
                    || error.starts_with("RecursionError:")
                    || error.starts_with("OverflowError:")
                    || error.starts_with("OSError:")
                    || error.starts_with("IsADirectoryError:")
                    || error.starts_with("NotADirectoryError:"))
            {
                let _ = emit(&format!("{error}\n"), true);
            } else {
                diagnostic(&error);
            }
            1
        }
    };
    if let (Some(bridge), Some(handle)) = (bridge.as_mut(), writer_handle) {
        bridge.teardown_outcome(if code == 0 {
            TeardownOutcome::Clean
        } else {
            TeardownOutcome::Unclean
        });
        match bridge.call(
            "writer_scope.exit",
            vec![Value::Null],
            json!({"handles":{"0":handle}}),
        ) {
            Ok(reply) if reply["ok"] == true => (),
            Ok(reply) => {
                diagnostic(&format!(
                    "{}: {}",
                    reply["error"]["type"].as_str().unwrap_or("Error"),
                    reply["error"]["message"].as_str().unwrap_or("")
                ));
                code = 1;
            }
            Err(e) => {
                diagnostic(&e.to_string());
                code = 1;
            }
        }
    }
    if OUTPUT_FAILED.load(Ordering::Relaxed) {
        1
    } else {
        code
    }
}
pub fn owns(raw: &[OsString]) -> bool {
    crate::executor_execute_parser::requested(raw)
}
pub(crate) fn preflight(raw: &[OsString]) -> Option<Vec<String>> {
    let mut argv = raw
        .iter()
        .map(|s| s.to_str().map(str::to_owned))
        .collect::<Option<Vec<_>>>()?;
    if argv.first().is_some_and(|s| s.starts_with("--jobs-db="))
        && argv.get(1).map(String::as_str) == Some("execute")
    {
        let db = argv.remove(0);
        argv.insert(1, db);
    }
    if argv.first().map(String::as_str) == Some("--jobs-db")
        && argv.get(2).map(String::as_str) == Some("execute")
    {
        let db = argv.get(1)?.clone();
        argv.drain(0..3);
        argv.splice(0..0, ["execute".into(), "--jobs-db".into(), db]);
    }
    if argv.first().map(String::as_str) != Some("execute") {
        return None;
    }
    let schema: Value = serde_json::from_str(include_str!(
        "../tests/fixtures/executor_admission_schema.json"
    ))
    .ok()?;
    let options = schema["execute"].as_array()?;
    let dispatch = argv.iter().any(|s| s == "--dispatch");
    let mut i = 1;
    while i < argv.len() {
        let token = &argv[i];
        let (flag, inline) = token
            .split_once('=')
            .map_or((token.as_str(), None), |(a, b)| (a, Some(b)));
        let option = options.iter().find(|o| {
            o["flags"]
                .as_array()
                .is_some_and(|a| a.iter().any(|v| v == flag))
        })?;
        let dest = option["dest"].as_str()?;
        if !(matches!(
            dest,
            "change_id"
                | "category"
                | "codex_args"
                | "codex_args_file"
                | "timeout"
                | "model"
                | "reasoning_effort"
                | "stall_timeout"
                | "jobs_db"
                | "repo_root"
                | "family"
                | "use_async"
                | "background"
                | "execution_backend"
                | "allow_harness_self_modify"
        ) || (dispatch
            && matches!(
                dest,
                "dispatch"
                    | "dispatch_brief"
                    | "artifacts_dir"
                    | "allow_paths"
                    | "verify_cmds"
                    | "expect_changes"
                    | "max_codex_attempts"
                    | "finalize_lock_timeout"
            )))
        {
            return None;
        }
        if !dispatch
            && option["dest"] == "execution_backend"
            && inline.or_else(|| argv.get(i + 1).map(String::as_str))? != "codex"
        {
            return None;
        }
        if matches!(
            option["kind"].as_str(),
            Some("_StoreAction" | "_AppendAction")
        ) && inline.is_none()
        {
            i += 1;
            argv.get(i)?;
        }
        i += 1;
    }
    Some(argv)
}
// JSON extensions and malformed ledgers retain Python diagnostics before hooks.
fn ledger_preflight(argv: &[String], cwd: &Path) -> bool {
    let root = argv_root(argv, cwd);
    let bytes = match fs::read(root.join("tasks/tdd.json")) {
        Ok(bytes) => bytes,
        Err(error) if error.kind() == io::ErrorKind::NotFound => return true,
        Err(_) => return false,
    };
    let Ok(text) = String::from_utf8(bytes) else {
        return false;
    };
    let Ok(extended) = LocalConfig::parse(&text) else {
        return false;
    };
    fn tagged(value: &Value, tag: &str) -> bool {
        match value {
            Value::Object(items) => {
                items.contains_key(tag) || items.values().any(|v| tagged(v, tag))
            }
            Value::Array(items) => items.iter().any(|v| tagged(v, tag)),
            _ => false,
        }
    }
    !extended
        .raw()
        .values()
        .any(|v| tagged(v, extended.numeric_tag()))
        && serde_json::from_str::<Value>(&text).is_ok()
}
fn argv_root(argv: &[String], cwd: &Path) -> PathBuf {
    let mut root = cwd.to_owned();
    for (index, arg) in argv.iter().enumerate() {
        let raw = arg.strip_prefix("--repo-root=").or_else(|| {
            (arg == "--repo-root")
                .then(|| argv.get(index + 1).map(String::as_str))
                .flatten()
        });
        if let Some(raw) = raw {
            let p = Path::new(raw);
            root = if p.is_absolute() {
                p.into()
            } else {
                cwd.join(p)
            };
        }
    }
    root
}
fn execute(
    root: &Path,
    args: &Value,
    cwd: &Path,
    environment: &BTreeMap<OsString, OsString>,
    bridge: &mut Option<Box<CommandHooks>>,
) -> Result<i32> {
    let change = args["change_id"].as_str();
    let category = args["category"].as_str();
    if change.is_some() != category.is_some() {
        return Err("--change-id and --category must be supplied together".into());
    }
    let (Some(change), Some(category)) = (change, category) else {
        return Err("--change-id and --category are required outside --dispatch".into());
    };
    let local = LocalConfig::load(root).map_err(|e| format!("{}: {e}", e.kind()))?;
    if local.raw().contains_key("timeout_seconds_range") {
        for key in ["timeout", "stall_timeout"] {
            let converted = numeric_token(&args[key])
                .map(|token| local.parse_argument(&canonical_number(token)))
                .transpose()
                .map_err(|error| format!("{}: {error}", error.kind()))?;
            local
                .validate_timeout(converted.as_ref().or_else(|| args.get(key)))
                .map_err(|error| {
                    if matches!(error.kind(), "OverflowError" | "TypeError") {
                        format!("\0uncaught:{}: {error}", error.kind())
                    } else {
                        format!("argument parse error: {error}")
                    }
                })?;
        }
    }
    let codex_args = resolve_args(args, cwd, &local).map_err(|error| {
        if [
            "OSError:",
            "FileNotFoundError:",
            "PermissionError:",
            "IsADirectoryError:",
            "NotADirectoryError:",
        ]
        .iter()
        .any(|kind| error.starts_with(kind))
        {
            format!("\0caught:{error}")
        } else {
            format!(
                "argument parse error: {}",
                error.strip_prefix("UnicodeDecodeError: ").unwrap_or(&error)
            )
        }
    })?;
    let env_text = environment
        .iter()
        .filter_map(|(k, v)| Some((k.to_str()?.to_owned(), v.to_str()?.to_owned())))
        .collect();
    #[cfg(windows)]
    let account = environment
        .get(&OsString::from("USERPROFILE"))
        .map(PathBuf::from)
        .ok_or("ValueError: account profile unavailable")?;
    #[cfg(unix)]
    let account = crate::account_home::get().ok_or("ValueError: account home unavailable")?;
    let policy = executor_policy::load(root, &account, &env_text);
    if !policy.warning.is_empty() {
        let _ = emit(&policy.warning, true);
    }
    let route = policy.category(category);
    let model = args["model"].as_str().or_else(|| route["model"].as_str());
    let effort = args["reasoning_effort"]
        .as_str()
        .or_else(|| route["reasoning_effort"].as_str());
    let prompt = prompt(&codex_args);
    let ledger = root.join("tasks/tdd.json");
    if args["background"] == true {
        let db = if args["jobs_db"].is_null() {
            // Join components so the path matches Python on Windows too.
            root.join("tasks").join("jobs.db")
        } else {
            value_path(&args["jobs_db"], cwd)
        };
        let registry = JobRegistry::open(&db).map_err(|error| {
            format!(
                "\0uncaught:{}",
                crate::executor_text::registry_error(error, &db)
            )
        })?;
        let id = unique_id();
        let mut record = json!({"job_id":id,"change_id":change,"category":category,"family":args["family"],"repo_root":root.to_str(),"codex_args":codex_args,"timeout_seconds":if args["timeout"].is_null(){json!(600)}else{args["timeout"].clone()},"status":"running","started_at":utc_now(),"cancel_requested":false,"allow_harness_self_modify":args["allow_harness_self_modify"]==true,"resume_count":0});
        let inserted = (|| -> Result<()> {
            record["identity_json"] = hook(
                bridge,
                "job_identity",
                vec![namespace(args), path(root), json!(prompt), json!(model)],
            )?;
            direct_insert(&registry, &record, args, root, &db)?;
            hook(
                bridge,
                "on_job_event",
                vec![
                    json!("job_inserted"),
                    json!({"job_id":id,"path":"background","args":namespace(args),"repo_root":path(root),"jobs_db":path(&db)}),
                ],
            )?;
            Ok(())
        })();
        if let Err(error) = inserted {
            let exists = registry
                .connection()
                .query_row("SELECT 1 FROM jobs WHERE job_id=?", [&id], |r| {
                    r.get::<_, i64>(0)
                })
                .is_ok();
            if !exists {
                direct_insert(&registry, &record, args, root, &db)
                    .map_err(|error| format!("\0uncaught:{error}"))?;
            }
            if let Some(points) = bridge
                .as_mut()
                .and_then(|bridge| bridge.take_error_points())
                && let Some(start) = points
                    .iter()
                    .position(|point| (0xd800..=0xdfff).contains(point))
            {
                let end = start
                    + points[start..]
                        .iter()
                        .take_while(|&&point| (0xd800..=0xdfff).contains(&point))
                        .count();
                return Err(format!(
                    "\0uncaught:{}",
                    crate::executor_text::encode_error(
                        "utf-8",
                        &points,
                        start,
                        end,
                        "surrogates not allowed",
                    )
                ));
            }
            fail_job(&registry, &id, &strip_class(&error))?;
            return Err(format!("background insert failed: {}", strip_class(&error)));
        }
        line(&format!("[BACKGROUND] job_id={id}"));
        let _ = io::stdout().flush();
        if let Err(error) = validate_ledger(&ledger, change, category) {
            if ![
                "FileNotFoundError:",
                "KeyError:",
                "ValueError:",
                "JSONDecodeError:",
                "UnicodeDecodeError:",
                "UnicodeEncodeError:",
            ]
            .iter()
            .any(|kind| error.starts_with(kind))
            {
                return Err(format!("\0uncaught:{error}"));
            }
            fail_job(&registry, &id, &strip_class(&error))?;
            return Err(error);
        }
        let completed = (|| -> Result<()> {
            let cancelled = registry
                .connection()
                .query_row(
                    "SELECT cancel_requested FROM jobs WHERE job_id=?",
                    [&id],
                    |r| r.get::<_, bool>(0),
                )
                .optional()
                .map_err(crate::executor_text::sql_error)?
                .unwrap_or(false);
            if cancelled {
                registry
                    .update_status(&id, "cancelled", &json!({"completed_at":utc_now()}))
                    .map_err(|error| crate::executor_text::registry_error(error, &db))?;
                return Ok(());
            }
            let result = provider(
                args,
                cwd,
                environment,
                &local,
                &prompt,
                model,
                effort,
                bridge,
            )?;
            update_ledger(&ledger, change, category, &result)?;
            let code = result["exit_code"].as_i64().unwrap_or(1) as i32;
            registry.update_status(&id,if code==0{"completed"}else{"failed"},&json!({"exit_code":code,"stdout":result["stdout"],"stderr":result["stderr"],"duration_seconds":result["duration_seconds"],"completed_at":utc_now()})).map_err(|error| crate::executor_text::registry_error(error, &db))?;
            Ok(())
        })();
        if let Err(error) = completed {
            fail_job(&registry, &id, &strip_class(&error))?;
        }
        let exit_code = registry
            .connection()
            .query_row("SELECT exit_code FROM jobs WHERE job_id=?", [&id], |row| {
                row.get::<_, Option<i32>>(0)
            })
            .optional()
            .map_err(crate::executor_text::sql_error)?
            .flatten();
        return Ok(exit_code.unwrap_or(1));
    }
    validate_ledger(&ledger, change, category)?;
    let result = provider(
        args,
        cwd,
        environment,
        &local,
        &prompt,
        model,
        effort,
        bridge,
    )?;
    let (previous, status, notes) = update_ledger(&ledger, change, category, &result)?;
    let mut frames = Vec::new();
    frames.push(format!(
        "[RESULT] change_id={} category={}",
        repr(change),
        repr(category)
    ));
    frames.push(format!(
        "[RESULT] codex exit_code={} duration={:.2}s",
        result["exit_code"],
        result["duration_seconds"].as_f64().unwrap_or(0.0)
    ));
    let command = result["command"]
        .as_array()
        .ok_or("TypeError: command must be a list")?
        .iter()
        .map(|v| {
            v.as_str()
                .map(str::to_owned)
                .ok_or("TypeError: command must contain strings".to_owned())
        })
        .collect::<Result<Vec<_>>>()?;
    frames.push(format!("[RESULT] command={}", list_repr(&command)));
    frames.push(format!(
        "[LEDGER] previous_status={} -> new_status={}",
        previous.repr(),
        repr(status)
    ));
    frames.push(format!("[LEDGER] notes={}", repr(&notes)));
    for (key, label) in [("stdout", "STDOUT"), ("stderr", "STDERR")] {
        if let Some(s) = result[key].as_str().filter(|s| !s.is_empty()) {
            frames.push(format!("[{label}] {}", repr(&chars(s, 500))));
        }
    }
    for frame in frames {
        if emit(&format!("{frame}\n"), false).is_err() {
            return Ok(1);
        }
    }
    Ok(result["exit_code"].as_i64().unwrap_or(1) as i32)
}
fn strip_class(s: &str) -> String {
    let s = s
        .strip_prefix("\0uncaught:")
        .or_else(|| s.strip_prefix("\0caught:"))
        .unwrap_or(s);
    s.split_once(": ")
        .map_or(s, |(_, message)| message)
        .to_owned()
}
fn numeric_token(value: &Value) -> Option<&str> {
    value["__native_integer"]
        .as_str()
        .or_else(|| value["__native_float"].as_str())
}
fn canonical_number(token: &str) -> String {
    let normalized = token.trim().replace('_', "");
    match normalized.to_ascii_lowercase().as_str() {
        "nan" | "+nan" | "-nan" => "NaN".into(),
        "inf" | "infinity" | "+inf" | "+infinity" => "Infinity".into(),
        "-inf" | "-infinity" => "-Infinity".into(),
        _ => normalized,
    }
}
fn argument_number(value: &Value) -> Option<f64> {
    value
        .as_f64()
        .or_else(|| numeric_token(value)?.trim().replace('_', "").parse().ok())
}
fn number_display(value: &Value) -> String {
    numeric_token(value).map_or_else(|| value.to_string(), str::to_owned)
}
fn utf8_error(points: &[u32]) -> Option<String> {
    let start = points
        .iter()
        .position(|point| (0xd800..=0xdfff).contains(point))?;
    let end = start
        + points[start..]
            .iter()
            .take_while(|point| (0xd800..=0xdfff).contains(*point))
            .count();
    Some(crate::executor_text::encode_error(
        "utf-8",
        points,
        start,
        end,
        "surrogates not allowed",
    ))
}
fn direct_insert(
    registry: &JobRegistry,
    record: &Value,
    args: &Value,
    root: &Path,
    db: &Path,
) -> Result<()> {
    if args["timeout"].get("__native_integer").is_some() {
        return Err("OverflowError: Python int too large to convert to SQLite INTEGER".into());
    }
    for name in ["change_id", "family"] {
        if let Some(points) = argument_codepoints(args, name)
            && let Some(error) = utf8_error(&points)
        {
            return Err(error);
        }
    }
    if let Some(error) = utf8_error(&crate::executor_text::os_points(root.as_os_str())) {
        return Err(error);
    }
    registry
        .insert(record)
        .map_err(|error| crate::executor_text::registry_error(error, db))
}
fn fail_job(registry: &JobRegistry, id: &str, error: &str) -> Result<()> {
    registry
        .update_status(
            id,
            "failed",
            &json!({"exit_code":1,"stderr":error,"completed_at":utc_now()}),
        )
        .map_err(|error| crate::executor_text::registry_error(error, Path::new("")))
}
pub(crate) fn resolve_args(args: &Value, cwd: &Path, local: &LocalConfig) -> Result<Vec<String>> {
    if !args["codex_args_file"].is_null() {
        let file = value_path(&args["codex_args_file"], cwd);
        let raw = args["codex_args_file"]["value"]
            .as_str()
            .map(Path::new)
            .unwrap_or(&file);
        let metadata =
            fs::metadata(&file).map_err(|error| crate::executor_text::io_error(error, raw))?;
        local
            .validate_input_size(metadata.len())
            .map_err(|e| e.to_string())?;
        let bytes = fs::read(&file).map_err(|error| crate::executor_text::io_error(error, raw))?;
        let text = String::from_utf8(bytes).map_err(|error| {
            format!(
                "UnicodeDecodeError: {}",
                crate::executor_local::Error::Unicode(error)
            )
        })?;
        return Ok(vec![text.replace("\r\n", "\n").replace('\r', "\n")]);
    }
    let text = args["codex_args"]
        .as_str()
        .ok_or("exactly one of --codex-args or --codex-args-file must be provided")?;
    local
        .validate_input_size(text.len() as u64)
        .map_err(|e| e.to_string())?;
    shell_words(text)
}
pub(crate) fn shell_words(text: &str) -> Result<Vec<String>> {
    let mut chars = text.chars();
    let mut out = Vec::new();
    let mut word = String::new();
    let mut quote = None;
    let mut started = false;
    while let Some(c) = chars.next() {
        match quote {
            Some('\'') => {
                if c == '\'' {
                    quote = None
                } else {
                    word.push(c)
                }
            }
            Some('"') => {
                if c == '"' {
                    quote = None
                } else if c == '\\' {
                    let next = chars.next().ok_or("No escaped character")?;
                    if !['"', '\\'].contains(&next) {
                        word.push('\\');
                    }
                    word.push(next);
                } else {
                    word.push(c)
                }
            }
            Some(_) => return Err("No closing quotation".into()),
            None => {
                if ['\'', '"'].contains(&c) {
                    quote = Some(c);
                    started = true
                } else if c == '\\' {
                    word.push(chars.next().ok_or("No escaped character")?);
                    started = true
                } else if [' ', '\t', '\r', '\n'].contains(&c) {
                    if started {
                        out.push(std::mem::take(&mut word));
                        started = false;
                    }
                } else {
                    word.push(c);
                    started = true
                }
            }
        }
    }
    if quote.is_some() {
        return Err("No closing quotation".into());
    }
    if started {
        out.push(word);
    }
    Ok(out)
}
pub(crate) fn prompt(args: &[String]) -> String {
    let mut index = 0;
    const FLAGS: &[&str] = &[
        "--approval",
        "--approval-policy",
        "--add-dir",
        "--cd",
        "--color",
        "--config",
        "--config-profile",
        "--cwd",
        "--disable",
        "--enable",
        "--image",
        "--local-provider",
        "--model",
        "--output-last-message",
        "--output-schema",
        "--profile",
        "--reasoning-effort",
        "--sandbox",
        "-C",
        "-c",
        "-i",
        "-m",
        "-o",
        "-p",
        "-s",
    ];
    while let Some(token) = args.get(index) {
        if token == "--" {
            index += 1;
            break;
        }
        if token == "exec" {
            index += 1;
            continue;
        }
        let flag = token.split('=').next().unwrap_or("");
        if FLAGS.contains(&flag) {
            index += if token.contains('=') { 1 } else { 2 };
            continue;
        }
        if token.starts_with('-') {
            index += 1;
            continue;
        }
        break;
    }
    let parts = args.get(index..).unwrap_or(&[]);
    if parts.len() == 1 {
        parts[0].clone()
    } else {
        parts.join(" ").trim().to_owned()
    }
}
fn argument_codepoints(args: &Value, name: &str) -> Option<Vec<u32>> {
    let points = args["__native_arg_codepoints"][name]
        .as_array()?
        .iter()
        .map(|point| point.as_u64().map(|point| point as u32))
        .collect::<Option<Vec<_>>>()?;
    (args[name].as_str() == Some(crate::executor_text::points_text(&points).as_str()))
        .then_some(points)
}
fn prompt_codepoints(args: &Value) -> Option<Vec<u32>> {
    let raw = argument_codepoints(args, "codex_args")?;
    // Surrogates have no shlex syntax. Substitute only input-absent scalars
    // while reusing the common shell-word and positional-prompt parsers.
    let mut replacements = BTreeMap::new();
    let mut candidates = (0xe000..=0xf8ff).filter(|point| !raw.contains(point));
    for point in raw
        .iter()
        .filter(|point| (0xd800..=0xdfff).contains(*point))
    {
        if !replacements.contains_key(point) {
            replacements.insert(*point, candidates.next()?);
        }
    }
    let text = raw
        .iter()
        .map(|point| char::from_u32(*replacements.get(point).unwrap_or(point)))
        .collect::<Option<String>>()?;
    let selected = prompt(&shell_words(&text).ok()?);
    Some(
        selected
            .chars()
            .map(|character| {
                let point = u32::from(character);
                replacements
                    .iter()
                    .find(|(_, replacement)| **replacement == point)
                    .map_or(point, |(original, _)| *original)
            })
            .collect(),
    )
}
fn ledger_index(ledger: &crate::python_json::Value, change: &str) -> Result<Option<usize>> {
    if !ledger.is_object() {
        return Err(format!(
            "AttributeError: '{}' object has no attribute 'get'",
            ledger.type_name()
        ));
    }
    if let Some(items) = ledger["changes"].as_array() {
        for (index, item) in items.iter().enumerate() {
            if !item.is_object() {
                return Err(format!(
                    "AttributeError: '{}' object has no attribute 'get'",
                    item.type_name()
                ));
            }
            if item["id"].as_str() == Some(change) {
                return Ok(Some(index));
            }
        }
    }
    Ok(None)
}
pub(crate) fn validate_ledger(
    file: &Path,
    change: &str,
    category: &str,
) -> Result<crate::python_json::Value> {
    use crate::python_json::Value as Python;
    if !file.exists() {
        return Err(format!(
            "FileNotFoundError: Ledger not found: {}. Create tasks/tdd.json with a planned entry before calling execute.",
            file.display()
        ));
    }
    let bytes = fs::read(file).map_err(|error| crate::executor_text::io_error(error, file))?;
    let text = String::from_utf8(bytes).map_err(|error| {
        format!(
            "UnicodeDecodeError: {}",
            crate::executor_local::Error::Unicode(error)
        )
    })?;
    let ledger = crate::python_json::parse(&text.replace("\r\n", "\n").replace('\r', "\n"))
        .map_err(|error| format!("{}: {error}", error.exception))?;
    let index = ledger_index(&ledger, change)?;
    let entry = index
        .and_then(|index| ledger["changes"].as_array()?.get(index))
        .or_else(|| ledger.get(change).filter(|value| value.is_object()))
        .ok_or_else(|| {
            format!(
                "KeyError: {}",
                repr(&format!(
                    "unknown change_id {} in {}. Add a TDD entry for this id before executing.",
                    repr(change),
                    file.display()
                ))
            )
        })?;
    let categories = entry.get("categories");
    let contains = match categories {
        None => false,
        Some(Python::Object(items)) => items.get(category).is_some(),
        Some(Python::Array(items)) => items.iter().any(|value| value.as_str() == Some(category)),
        Some(Python::String(text)) => text.as_str().is_some_and(|text| text.contains(category)),
        Some(value) => {
            return Err(format!(
                "TypeError: argument of type '{}' is not iterable",
                value.type_name()
            ));
        }
    };
    if !contains {
        return Err(format!(
            "KeyError: {}",
            repr(&format!(
                "category {} not in entry {}. Declare the category in tdd.json before updating it (do not silently add).",
                repr(category),
                repr(change)
            ))
        ));
    }
    let value = match categories {
        Some(Python::Object(items)) => items.get(category).ok_or("KeyError: missing category")?,
        Some(Python::Array(_)) => {
            return Err("TypeError: list indices must be integers or slices, not str".into());
        }
        Some(Python::String(_)) => {
            return Err("TypeError: string indices must be integers, not 'str'".into());
        }
        _ => return Err("TypeError: invalid categories".into()),
    };
    if !value.is_object() {
        return Err(format!(
            "AttributeError: '{}' object has no attribute 'get'",
            value.type_name()
        ));
    }
    if value["status"].as_str() == Some("not_applicable") {
        return Err(format!(
            "ValueError: category {} is marked not_applicable; cannot run executor on it. Edit tdd.json manually if you intend to reclassify.",
            repr(category)
        ));
    }
    Ok(ledger)
}
fn update_ledger(
    file: &Path,
    change: &str,
    category: &str,
    result: &Value,
) -> Result<(crate::python_json::Value, &'static str, String)> {
    use crate::python_json::{Text, Value as Python};
    let mut ledger = validate_ledger(file, change, category)?;
    let index = ledger_index(&ledger, change)?;
    let Python::Object(root) = &mut ledger else {
        return Err("TypeError: invalid ledger".into());
    };
    let entry = if let Some(index) = index {
        let Some(Python::Array(items)) = root.get_mut("changes") else {
            return Err("TypeError: invalid changes".into());
        };
        items.get_mut(index)
    } else {
        root.get_mut(change)
    };
    let Some(Python::Object(entry)) = entry else {
        return Err("TypeError: invalid ledger entry".into());
    };
    let Some(Python::Object(categories)) = entry.get_mut("categories") else {
        return Err("TypeError: invalid categories".into());
    };
    let Some(Python::Object(value)) = categories.get_mut(category) else {
        return Err("TypeError: invalid category".into());
    };
    let previous = value.get("status").cloned().unwrap_or(Python::Null);
    let status = if result["exit_code"] == 0 {
        "pass"
    } else {
        "fail"
    };
    let notes = format!(
        "P0-J auto: rc={}, stderr first 200 chars: {}",
        result["exit_code"],
        repr(&chars(
            result["stderr"]
                .as_str()
                .ok_or("TypeError: stderr must be a string")?,
            200
        ))
    );
    let string = |text: &str| Python::String(Text::new(text.chars().map(u32::from).collect()));
    value.insert(
        Text::new("status".chars().map(u32::from).collect()),
        string(status),
    );
    let command = if let Some(items) = result["__native_command_codepoints"].as_array() {
        Python::Array(
            items
                .iter()
                .map(|item| {
                    Python::String(Text::new(
                        item.as_array()
                            .into_iter()
                            .flatten()
                            .filter_map(Value::as_u64)
                            .map(|point| point as u32)
                            .collect(),
                    ))
                })
                .collect(),
        )
    } else {
        crate::python_json::parse(&result["command"].to_string())
            .map_err(|error| format!("{}: {error}", error.exception))?
    };
    value.insert(
        Text::new("executed_argv".chars().map(u32::from).collect()),
        command,
    );
    value.insert(
        Text::new("notes".chars().map(u32::from).collect()),
        string(&notes),
    );
    let rendered = crate::executor_ledger_json::render_python(&ledger)?;
    write_ledger(file, &rendered)?;
    Ok((previous, status, notes))
}

#[cfg(test)]
thread_local! {
    static LEDGER_TEMP_NAMES: std::cell::RefCell<Vec<OsString>> = const { std::cell::RefCell::new(Vec::new()) };
    static LEDGER_TEMP_LIMIT: std::cell::Cell<Option<usize>> = const { std::cell::Cell::new(None) };
    static BEFORE_LEDGER_REPLACE: std::cell::RefCell<Option<Box<dyn FnOnce()>>> =
        std::cell::RefCell::new(None);
}

fn ledger_temp_name() -> OsString {
    #[cfg(test)]
    if let Some(name) = LEDGER_TEMP_NAMES.with(|names| names.borrow_mut().pop()) {
        return name;
    }
    OsString::from(format!(".mir-executor-{}.tmp", unique_id()))
}

#[cfg(test)]
#[path = "executor_ledger_temp_tests.rs"]
mod ledger_temp_tests;

// CPython 3.12 Lib/tempfile.py: TMP_MAX = os.TMP_MAX (fallback 10000),
// _mkstemp_inner retries only FileExistsError and raises without a filename.
fn ledger_temp_limit() -> usize {
    #[cfg(test)]
    if let Some(limit) = LEDGER_TEMP_LIMIT.with(|limit| limit.get()) {
        return limit;
    }
    libc::TMP_MAX as usize
}

fn create_ledger_temp(
    parent: &Path,
    mut create: impl FnMut(&std::ffi::OsStr) -> io::Result<fs::File>,
) -> Result<(OsString, fs::File)> {
    for _ in 0..ledger_temp_limit() {
        let name = ledger_temp_name();
        match create(&name) {
            Ok(output) => return Ok((name, output)),
            Err(error) if error.kind() == io::ErrorKind::AlreadyExists => continue,
            Err(error) => return Err(crate::executor_text::io_error(error, &parent.join(name))),
        }
    }
    Err("FileExistsError: [Errno 17] No usable temporary file name found".into())
}

fn write_ledger(file: &Path, rendered: &str) -> Result<()> {
    #[cfg(windows)]
    let rendered = rendered.replace('\n', "\r\n");
    let parent = file.parent().ok_or("OSError: ledger parent missing")?;
    #[cfg(unix)]
    {
        // mkstemp(dir=ledger.parent) follows directory symlinks. Resolve only
        // the parent: os.replace replaces a leaf symlink, not its referent.
        let resolved_parent =
            fs::canonicalize(parent).map_err(|e| crate::executor_text::io_error(e, parent))?;
        let resolved_file = resolved_parent.join(file.file_name().unwrap_or_default());
        let pinned = crate::adoption_fs::parent(&resolved_parent, &resolved_file)
            .map_err(|e| crate::executor_text::io_error(e, parent))?;
        let (name, mut output) = create_ledger_temp(parent, |name| pinned.create(name, 0o600))?;
        let source = parent.join(&name);
        let written = (|| -> Result<()> {
            output
                .write_all(rendered.as_bytes())
                .map_err(|e| crate::executor_text::io_error(e, &source))?;
            let replacement = crate::adoption_fs::Move::prepare(
                &resolved_parent,
                &resolved_parent.join(&name),
                &resolved_file,
            )
            .map_err(|e| crate::executor_text::io_error(e, file))?;
            #[cfg(test)]
            BEFORE_LEDGER_REPLACE.with(|hook| {
                if let Some(hook) = hook.borrow_mut().take() {
                    hook();
                }
            });
            if !crate::adoption_fs::owns_file(&pinned, &name, &output) {
                return Err("OSError: ledger temporary file identity changed".into());
            }
            replacement
                .rename()
                .map_err(|e| crate::executor_text::io_error(e, file))
        })();
        // Keep the creation fd open: a substituted entry must never acquire
        // the original inode through reuse while cleanup checks its identity.
        if written.is_err() && crate::adoption_fs::owns_file(&pinned, &name, &output) {
            let _ = pinned.unlink(&name, false);
        }
        written
    }
    #[cfg(not(unix))]
    {
        let (name, mut output) = create_ledger_temp(parent, |name| {
            fs::OpenOptions::new()
                .create_new(true)
                .write(true)
                .open(parent.join(name))
        })?;
        let source = parent.join(name);
        let written = (|| -> Result<()> {
            output
                .write_all(rendered.as_bytes())
                .map_err(|e| crate::executor_text::io_error(e, &source))?;
            #[cfg(test)]
            BEFORE_LEDGER_REPLACE.with(|hook| {
                if let Some(hook) = hook.borrow_mut().take() {
                    hook();
                }
            });
            if !crate::adoption_fs::owns_file(&source, &output) {
                return Err("OSError: ledger temporary file identity changed".into());
            }
            fs::rename(&source, file).map_err(|e| crate::executor_text::io_error(e, file))
        })();
        if written.is_err() && crate::adoption_fs::owns_file(&source, &output) {
            let _ = fs::remove_file(&source);
        }
        written
    }
}
// Keep provider inputs explicit at this single adapter seam; no new state owner.
#[allow(clippy::too_many_arguments)]
fn provider(
    args: &Value,
    cwd: &Path,
    environment: &BTreeMap<OsString, OsString>,
    local: &LocalConfig,
    prompt: &str,
    model: Option<&str>,
    effort: Option<&str>,
    bridge: &mut Option<Box<CommandHooks>>,
) -> Result<Value> {
    if environment
        .get(&OsString::from("MIR_CODEX_MAIN"))
        .and_then(|v| v.to_str())
        != Some("1")
    {
        let output = Command::new("git")
            .arg("-C")
            .arg(cwd)
            .args(["rev-parse", "--git-common-dir"])
            .env_clear()
            .envs(environment)
            .output()
            .map_err(|e| format!("OSError: {e}"))?;
        let linked = std::str::from_utf8(&output.stdout)
            .ok()
            .and_then(|s| fs::canonicalize(cwd.join(s.trim())).ok())
            .is_some_and(|p| !p.starts_with(cwd));
        if !output.status.success() || !linked {
            return Err("RuntimeError: Delegated Codex refused in the main worktree per ADR-60 section 16 D3. Delegated execution must go through `mir_executor execute --background --dispatch`, which uses an R4 worktree, or set MIR_CODEX_MAIN=1 for the main process itself, such as loop_driver.".into());
        }
    }
    let binary_os = crate::codex_binary::resolve_os(environment);
    let binary = crate::executor_text::os_text(&binary_os);
    let binary_points = crate::executor_text::os_points(&binary_os);
    let start = Instant::now();
    let mut command = Command::new(&binary_os);
    command.arg("app-server").current_dir(cwd).env_clear();
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
            || k.to_str().is_some_and(|k| {
                KEYS.contains(&k)
                    || local
                        .raw()
                        .get("child_env_extra_keys")
                        .and_then(Value::as_array)
                        .is_some_and(|a| a.iter().any(|v| v == k))
            })
        {
            command.env(k, v);
        }
    }
    let timeout_number = argument_number(&args["timeout"]);
    let timeout_error = timeout_number.and_then(|number| {
        if number.is_infinite() {
            Some("OverflowError: int too large to convert to float")
        } else if number > 9_223_372_036.0 {
            Some("OverflowError: timestamp out of range for platform time_t")
        } else {
            None
        }
    });
    let timeout = timeout_number
        .filter(|_| timeout_error.is_none())
        .map(|number| Duration::from_secs_f64(number.max(0.0)));
    let mut options = CallOptions::new(prompt, crate::executor_text::os_text(cwd.as_os_str()));
    if cwd.to_str().is_none() {
        options
            .string_codepoints
            .insert("cwd", crate::executor_text::os_points(cwd.as_os_str()));
    }
    for (name, key) in [
        ("model", "model"),
        ("reasoning_effort", "model_reasoning_effort"),
    ] {
        if let Some(points) = argument_codepoints(args, name) {
            options.string_codepoints.insert(key, points);
        }
    }
    if let Some(points) = prompt_codepoints(args) {
        options.string_codepoints.insert("prompt", points);
    }
    options.timeout = timeout;
    options.wait_error = timeout_error.filter(|error| error.contains("timestamp out of range"));
    options.stall_timeout_float = argument_number(&args["stall_timeout"]);
    options.sandbox = local
        .raw()
        .get("codex_sandbox_default")
        .and_then(Value::as_str)
        .unwrap_or("workspace-write")
        .into();
    options.model = model.map(str::to_owned);
    options.base_instructions = Some(BASE.into());
    let mut config = json!({"project_doc_max_bytes":0});
    if let Some(effort) = effort {
        config["model_reasoning_effort"] = json!(effort);
    }
    options.config = Some(config);
    let raw = (|| {
        let mut client = Client::spawn(command, Duration::from_secs(10), Duration::from_secs(2))?;
        if let Some(error) = timeout_error.filter(|error| error.contains("int too large")) {
            client.close();
            return Err(TransportError::Encoding(error.into()));
        }
        let result = client.call(options, &mut |_, _| Ok(()));
        client.close();
        result
    })();
    let (mut result, metadata) = match raw {
        Err(TransportError::Encoding(error)) => return Err(error),
        Ok(raw) => {
            let usage = raw.token_usage.as_ref().unwrap_or(&raw.raw_result["usage"]);
            let usage = usage
                .get("last")
                .or_else(|| usage.get("total"))
                .unwrap_or(usage);
            let mut tokens = serde_json::Map::new();
            for (key, aliases) in [
                (
                    "input_tokens",
                    ["input_tokens", "inputTokens", "prompt_tokens"],
                ),
                (
                    "output_tokens",
                    ["output_tokens", "outputTokens", "completion_tokens"],
                ),
                ("total_tokens", ["total_tokens", "totalTokens", ""]),
            ] {
                if let Some(v) = aliases
                    .iter()
                    .find_map(|k| usage.get(k).filter(|v| v.as_u64().is_some()))
                {
                    tokens.insert(key.into(), v.clone());
                }
            }
            let duration = start.elapsed().as_secs_f64();
            (
                json!({"exit_code":0,"stdout":raw.content_text,"stderr":"","duration_seconds":duration,"command":[binary,"app-server"]}),
                json!({"prompt_sha256":crate::digest::sha256(prompt.as_bytes()),"model":raw.model_id.as_deref().or_else(||raw.raw_result["model"].as_str()).or(model),"reasoning_effort":effort,"tool_version":raw.tool_version.as_deref().or_else(||raw.raw_result["tool_version"].as_str()),"attempt":1,"elapsed_seconds":duration,"token_usage":if tokens.is_empty(){Value::Null}else{Value::Object(tokens)}}),
            )
        }
        Err(TransportError::Timeout(error)) if timeout.is_some() => {
            return Err(if args["background"] == true {
                format!("tools.mir_executor.codex_mcp_client.CodexMcpTimeoutError: {error}")
            } else if args["use_async"] == true {
                format!("async timeout after {}s", number_display(&args["timeout"]))
            } else {
                format!(
                    "Codex timeout after {}s: Command '[{}, 'app-server']' timed out after {} seconds",
                    number_display(&args["timeout"]),
                    repr_codepoints(&binary_points),
                    number_display(&args["timeout"])
                )
            });
        }
        Err(TransportError::Spawn {
            kind: std::io::ErrorKind::NotFound,
            ..
        }) => {
            return Err(format!(
                "FileNotFoundError: Codex binary not found: {}. Set CODEX_BIN to the full path of the codex executable.",
                repr_codepoints(&binary_points)
            ));
        }
        Err(TransportError::Spawn {
            kind, raw_os_error, ..
        }) => {
            let error =
                raw_os_error.map_or_else(|| io::Error::from(kind), io::Error::from_raw_os_error);
            return Err(crate::executor_text::io_error(error, Path::new(&binary_os)));
        }
        Err(error) => {
            let duration = start.elapsed().as_secs_f64();
            (
                json!({"exit_code":1,"stdout":"","stderr":error.to_string(),"duration_seconds":duration,"command":[binary,"app-server"]}),
                json!({"prompt_sha256":crate::digest::sha256(prompt.as_bytes()),"model":model,"reasoning_effort":effort,"tool_version":null,"attempt":1,"elapsed_seconds":duration,"token_usage":null}),
            )
        }
    };
    let replacement = hook(
        bridge,
        "after_provider_call",
        vec![
            json!({"$type":"subprocess_result","value":result}),
            metadata,
        ],
    )?;
    let replaced = !replacement.is_null();
    if replaced {
        result = if replacement["$type"] == "subprocess_result" {
            replacement["value"].clone()
        } else {
            replacement
        };
    }
    if binary_os.to_str().is_none() && !replaced {
        result["__native_command_codepoints"] = json!([
            binary_points,
            "app-server".chars().map(u32::from).collect::<Vec<_>>()
        ]);
    }
    if !result["exit_code"].is_i64()
        || !result["stdout"].is_string()
        || !result["stderr"].is_string()
        || !result["duration_seconds"].is_number()
        || !result["command"].is_array()
    {
        return Err("TypeError: invalid after_provider_call result".into());
    }
    Ok(result)
}
pub(crate) fn unique_id() -> String {
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos();
    crate::digest::sha256(
        format!(
            "{now}-{}-{}",
            std::process::id(),
            SERIAL.fetch_add(1, Ordering::Relaxed)
        )
        .as_bytes(),
    )[..32]
        .to_owned()
}
pub(crate) fn utc_now() -> String {
    let elapsed = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default();
    let seconds = elapsed.as_secs();
    let days = (seconds / 86400) as i64;
    let z = days + 719468;
    let era = if z >= 0 { z } else { z - 146096 } / 146097;
    let doe = z - era * 146097;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let mut year = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let day = doy - (153 * mp + 2) / 5 + 1;
    let month = mp + if mp < 10 { 3 } else { -9 };
    year += i64::from(month <= 2);
    format!(
        "{year:04}-{month:02}-{day:02}T{:02}:{:02}:{:02}.{:06}+00:00",
        seconds / 3600 % 24,
        seconds / 60 % 60,
        seconds % 60,
        elapsed.subsec_micros()
    )
}

/// Shared command path for execute dispatch and integrity-checked resume.
pub fn dispatch(
    root: &Path,
    args: &Value,
    codex_args: Option<Vec<String>>,
    cwd: &Path,
    environment: &BTreeMap<OsString, OsString>,
    bridge: &mut Option<Box<CommandHooks>>,
) -> Result<i32> {
    crate::executor_dispatch_cli::dispatch(root, args, codex_args, cwd, environment, bridge)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn direct_ledger_json_error_matches_python() {
        let directory = tempfile::tempdir().unwrap();
        let file = directory.path().join("tdd.json");
        fs::write(&file, "{bad").unwrap();
        assert_eq!(
            validate_ledger(&file, "c", "unit").unwrap_err(),
            "JSONDecodeError: Expecting property name enclosed in double quotes: line 1 column 2 (char 1)"
        );
    }

    #[test]
    fn direct_ledger_scalar_preserves_attribute_error() {
        let directory = tempfile::tempdir().unwrap();
        let file = directory.path().join("tdd.json");
        for (source, error) in [
            ("[]", "AttributeError: 'list' object has no attribute 'get'"),
            (
                r#"{"c":{"categories":{"unit":4}}}"#,
                "AttributeError: 'int' object has no attribute 'get'",
            ),
        ] {
            fs::write(&file, source).unwrap();
            assert_eq!(validate_ledger(&file, "c", "unit").unwrap_err(), error);
        }
    }

    #[test]
    fn hook_namespace_omits_the_native_brief_cache() {
        let args = json!({"dispatch":true,"__native_brief":{"value":{"version":2}}});
        assert_eq!(
            namespace(&args),
            json!({"$type":"namespace","value":{"dispatch":true}})
        );
    }

    #[cfg(unix)]
    #[test]
    fn interpreter_preserves_virtual_environment_symlink() {
        let root = std::env::var_os("MIR_NATIVE_TEST_SCRATCH")
            .map(PathBuf::from)
            .unwrap_or_else(std::env::temp_dir)
            .join(format!("interpreter-symlink-{}", unique_id()));
        fs::create_dir_all(root.join("venv")).unwrap();
        let target = root.join("base-python");
        fs::write(&target, "fixture").unwrap();
        let link = root.join("venv").join("python3");
        std::os::unix::fs::symlink(&target, &link).unwrap();
        for override_path in [
            None,
            Some(link.clone()),
            Some(PathBuf::from("venv/python3")),
        ] {
            let mut environment =
                BTreeMap::from([(OsString::from("PATH"), root.join("venv").into_os_string())]);
            if let Some(path) = override_path {
                environment.insert(OsString::from("MIR_EXECUTOR_PYTHON"), path.into_os_string());
            }
            assert_eq!(interpreter(&environment, &root), Some(link.clone()));
        }
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn windows_environment_lookup_preserves_os_case_rules() {
        let environment = BTreeMap::from([
            (OsString::from("Path"), OsString::from("python-directory")),
            (
                OsString::from("mir_executor_python"),
                OsString::from("python-override"),
            ),
        ]);
        assert_eq!(
            environment_value(&environment, "PATH", true),
            Some(&OsString::from("python-directory"))
        );
        assert_eq!(
            environment_value(&environment, "MIR_EXECUTOR_PYTHON", true),
            Some(&OsString::from("python-override"))
        );
        assert_eq!(environment_value(&environment, "PATH", false), None);
    }

    #[cfg(unix)]
    #[test]
    fn native_account_home_matches_python_pwd() {
        let output = ["python3", "python"]
            .iter()
            .find_map(|name| {
                Command::new(name)
                    .args([
                        "-I",
                        "-c",
                        "import os,pwd;print(pwd.getpwuid(os.getuid()).pw_dir)",
                    ])
                    .output()
                    .ok()
                    .filter(|output| output.status.success())
            })
            .expect("Python interpreter with pwd");
        let expected = String::from_utf8(output.stdout).unwrap();
        assert_eq!(
            crate::account_home::get().unwrap(),
            PathBuf::from(expected.trim_end_matches('\n'))
        );
    }

    #[cfg(unix)]
    #[test]
    fn ledger_parent_swap_cannot_replace_an_outside_file() {
        let scratch = std::env::var_os("MIR_NATIVE_TEST_SCRATCH")
            .map(PathBuf::from)
            .unwrap_or_else(std::env::temp_dir);
        fs::create_dir_all(&scratch).unwrap();
        let temporary = tempfile::tempdir_in(&scratch).unwrap();
        let root = fs::canonicalize(temporary.path()).unwrap();
        let parent = root.join("tasks");
        let retained = root.join("retained");
        let outside = root.join("outside");
        fs::create_dir_all(&parent).unwrap();
        fs::create_dir_all(&outside).unwrap();
        fs::write(parent.join("tdd.json"), "original").unwrap();
        fs::write(outside.join("tdd.json"), "outside").unwrap();
        let old_parent = parent.clone();
        let old_retained = retained.clone();
        let old_outside = outside.clone();
        BEFORE_LEDGER_REPLACE.with(|hook| {
            *hook.borrow_mut() = Some(Box::new(move || {
                let temporary = fs::read_dir(&old_parent)
                    .unwrap()
                    .map(|entry| entry.unwrap().file_name())
                    .find(|name| name.to_string_lossy().starts_with(".mir-executor-"))
                    .unwrap();
                fs::write(old_outside.join(temporary), "outside-temp").unwrap();
                fs::rename(&old_parent, &old_retained).unwrap();
                std::os::unix::fs::symlink(&old_outside, &old_parent).unwrap();
            }))
        });
        write_ledger(&parent.join("tdd.json"), "updated").unwrap();
        assert_eq!(
            fs::read_to_string(outside.join("tdd.json")).unwrap(),
            "outside"
        );
        assert_eq!(
            fs::read_to_string(retained.join("tdd.json")).unwrap(),
            "updated"
        );
        let outside_temp = fs::read_dir(&outside)
            .unwrap()
            .map(|entry| entry.unwrap().path())
            .find(|path| {
                path.file_name()
                    .unwrap()
                    .to_string_lossy()
                    .starts_with(".mir-executor-")
            })
            .unwrap();
        assert_eq!(fs::read_to_string(outside_temp).unwrap(), "outside-temp");
        assert_eq!(fs::read_dir(&outside).unwrap().count(), 2);
        assert_eq!(fs::read_dir(&retained).unwrap().count(), 1);
    }

    #[test]
    #[cfg(unix)]
    fn ledger_follows_symlinked_directories() {
        let temporary = tempfile::tempdir().unwrap();
        let root = fs::canonicalize(temporary.path()).unwrap();
        let real = root.join("real");
        fs::create_dir_all(real.join("tasks")).unwrap();
        let alias = root.join("alias");
        std::os::unix::fs::symlink(&real, &alias).unwrap();
        // Exercise both a linked immediate parent and a linked ancestor.
        for parent in [&alias, &alias.join("tasks")] {
            let ledger = parent.join("tdd.json");
            fs::write(&ledger, "original").unwrap();
            let observed_parent = parent.to_path_buf();
            BEFORE_LEDGER_REPLACE.with(|hook| {
                *hook.borrow_mut() = Some(Box::new(move || {
                    let files: Vec<_> = fs::read_dir(&observed_parent)
                        .unwrap()
                        .map(|entry| entry.unwrap().path())
                        .filter(|path| path.is_file())
                        .collect();
                    let temporary = files
                        .iter()
                        .find(|path| {
                            path.file_name()
                                .unwrap()
                                .to_string_lossy()
                                .starts_with(".mir-executor-")
                        })
                        .unwrap();
                    assert_eq!(fs::read_to_string(temporary).unwrap(), "updated");
                    assert_eq!(files.len(), 2);
                }));
            });
            write_ledger(&ledger, "updated").unwrap();
            assert_eq!(fs::read_to_string(&ledger).unwrap(), "updated");
            assert_eq!(
                fs::read_dir(parent)
                    .unwrap()
                    .filter(|entry| entry.as_ref().unwrap().path().is_file())
                    .count(),
                1
            );
        }
    }

    #[test]
    #[cfg(unix)]
    fn ledger_replaces_leaf_symlink_without_writing_referent() {
        let temporary = tempfile::tempdir().unwrap();
        let root = temporary.path();
        let referent = root.join("referent.json");
        let ledger = root.join("tdd.json");
        fs::write(&referent, "original").unwrap();
        std::os::unix::fs::symlink(&referent, &ledger).unwrap();
        write_ledger(&ledger, "updated").unwrap();
        assert!(
            !fs::symlink_metadata(&ledger)
                .unwrap()
                .file_type()
                .is_symlink()
        );
        assert_eq!(fs::read_to_string(&referent).unwrap(), "original");
        assert_eq!(fs::read_to_string(&ledger).unwrap(), "updated");
        assert_eq!(fs::read_dir(root).unwrap().count(), 2);
    }

    #[test]
    fn ledger_replaces_existing_file() {
        let root = std::env::var_os("MIR_NATIVE_TEST_SCRATCH")
            .map(PathBuf::from)
            .unwrap_or_else(std::env::temp_dir)
            .join(format!("ledger-replace-{}", unique_id()));
        fs::create_dir_all(&root).unwrap();
        let ledger = root.join("tdd.json");
        fs::write(
            &ledger,
            r#"{"c":{"categories":{"unit":{"status":"pending"}}}}"#,
        )
        .unwrap();
        let result = json!({"exit_code":0,"stderr":"","command":["fake"]});
        let (previous, status, _) = update_ledger(&ledger, "c", "unit", &result).unwrap();
        assert_eq!(previous.as_str(), Some("pending"));
        assert_eq!(status, "pass");
        let updated: Value = serde_json::from_slice(&fs::read(&ledger).unwrap()).unwrap();
        assert_eq!(updated["c"]["categories"]["unit"]["status"], "pass");
        assert_eq!(fs::read_dir(&root).unwrap().count(), 1);
        fs::remove_dir_all(root).unwrap();
    }
}
