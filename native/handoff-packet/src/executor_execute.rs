//! Direct execute; after admission every failure is final.
use crate::{
    executor_admission::{self, Admission},
    executor_local::LocalConfig,
    executor_policy,
    executor_registry::JobRegistry,
    executor_transport::{CallOptions, Client, Error as TransportError},
    local_bridge::LocalBridge,
};
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
type Result<T> = std::result::Result<T, String>;
const BASE: &str = "You are a code-implementation sub-agent in an isolated git worktree for the Mir harness. Read .mir-dispatch/brief.md and implement the task fully. Rules: modify only files inside this worktree, never edit tasks/plan.md, follow existing code style and structure, keep changes minimal and scoped to the brief, when tests are specified make them pass. Report a concise summary of what you changed.";
static SERIAL: AtomicU64 = AtomicU64::new(0);
static OUTPUT_FAILED: AtomicBool = AtomicBool::new(false);
static NONPRINTABLE: OnceLock<std::result::Result<regex::Regex, regex::Error>> = OnceLock::new();
fn emit(text: &str, error: bool) -> io::Result<()> {
    #[cfg(windows)]
    let text = text.replace('\n', "\r\n");
    if error {
        io::stderr().write_all(text.as_bytes())
    } else {
        io::stdout().write_all(text.as_bytes())
    }
}
fn line(text: &str) {
    if emit(&format!("{text}\n"), false).is_err() {
        OUTPUT_FAILED.store(true, Ordering::Relaxed);
    }
}
fn diagnostic(text: &str) {
    let _ = emit(&format!("[mir_executor] {text}\n"), true);
}
fn path(path: &Path) -> Value {
    json!({"$type":"path","value":path.to_str().unwrap_or("")})
}
fn namespace(args: &Value) -> Value {
    json!({"$type":"namespace","value":args})
}
fn value_path(value: &Value, cwd: &Path) -> PathBuf {
    let raw = value["value"]
        .as_str()
        .or_else(|| value.as_str())
        .unwrap_or("");
    let p = Path::new(raw);
    if p.is_absolute() {
        p.into()
    } else {
        cwd.join(p)
    }
}
fn repr(s: &str) -> String {
    let nonprintable = NONPRINTABLE
        .get_or_init(|| regex::Regex::new(r"[\p{C}\p{Z}]"))
        .as_ref();
    let quote = if s.contains('\'') && !s.contains('"') {
        '"'
    } else {
        '\''
    };
    let mut out = quote.to_string();
    for c in s.chars() {
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
fn repr_value(v: &Value) -> String {
    if v.is_null() {
        "None".into()
    } else {
        repr(v.as_str().unwrap_or(""))
    }
}
fn list_repr(values: &[String]) -> String {
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
fn hook(bridge: &mut Option<Box<LocalBridge>>, name: &str, args: Vec<Value>) -> Result<Value> {
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
fn interpreter(environment: &BTreeMap<OsString, OsString>, cwd: &Path) -> Option<PathBuf> {
    if let Some(p) = environment.get(&OsString::from("MIR_EXECUTOR_PYTHON")) {
        return fs::canonicalize(p).ok().map(crate::supply::plain);
    }
    let names = if cfg!(windows) {
        &["python3.exe", "python.exe"][..]
    } else {
        &["python3", "python"][..]
    };
    for dir in std::env::split_paths(environment.get(&OsString::from("PATH"))?) {
        for name in names {
            let p = dir.join(name);
            if p.is_file() {
                return fs::canonicalize(if p.is_absolute() { p } else { cwd.join(p) })
                    .ok()
                    .map(crate::supply::plain);
            }
        }
    }
    None
}
/// Raw argv includes execute; global --jobs-db may precede it. 64 declines silently.
pub fn run(raw: &[OsString], cwd: &Path, home_root: &Path) -> i32 {
    OUTPUT_FAILED.store(false, Ordering::Relaxed);
    let Some(argv) = preflight(raw) else {
        return 64;
    };
    let target = fs::canonicalize(argv_root(&argv, cwd)).ok();
    let home = fs::canonicalize(home_root).ok();
    if target.is_none() || target != home {
        return 64;
    }
    // Decline explicit parser extensions without importing target-owned code.
    // A computed export discovered by hello is already owned and must fail finally.
    let extension = argv_root(&argv, cwd).join("tools/mir_executor/local.py");
    match fs::read(extension) {
        Ok(source)
            if source
                .windows(b"register_execute_options".len())
                .any(|part| part == b"register_execute_options") =>
        {
            return 64;
        }
        Ok(_) => (),
        Err(error) if error.kind() == io::ErrorKind::NotFound => (),
        Err(_) => return 64,
    }
    if !ledger_preflight(&argv, cwd) {
        return 64;
    }
    let environment: BTreeMap<OsString, OsString> = std::env::vars_os().collect();
    if environment
        .get(&OsString::from("CODEX_BIN"))
        .is_some_and(|s| s.to_str().is_none())
    {
        return 64;
    }
    let Some(python) = interpreter(&environment, cwd) else {
        return 64;
    };
    let admission = executor_admission::admit_execute(executor_admission::Request {
        argv: &argv,
        cwd,
        invoking_home: home_root,
        environment: &environment,
        interpreter: &python,
        bridge_script: &home_root.join("tools/mir_executor/local_bridge.py"),
    });
    let (root, args, mut bridge, writer_handle) = match admission {
        Ok(Admission::Admitted {
            root,
            args,
            bridge,
            writer_handle,
            ..
        }) => (root, args, bridge, writer_handle),
        Ok(Admission::Decline { code, .. }) => return code,
        Ok(Admission::Refused { code, stderr }) => {
            let _ = io::stderr().write_all(&stderr);
            return code;
        }
        Err(e) => {
            diagnostic(&e.to_string());
            return 1;
        }
    };
    let result = execute(&root, &args, cwd, &environment, &mut bridge);
    let mut code = match result {
        Ok(code) => code,
        Err(error) => {
            diagnostic(&error);
            1
        }
    };
    if let (Some(bridge), Some(handle)) = (bridge.as_mut(), writer_handle) {
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
fn preflight(raw: &[OsString]) -> Option<Vec<String>> {
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
        if !matches!(
            option["dest"].as_str()?,
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
        ) {
            return None;
        }
        if option["dest"] == "execution_backend"
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
    bridge: &mut Option<Box<LocalBridge>>,
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
            local
                .validate_timeout(args.get(key))
                .map_err(|e| format!("argument parse error: {e}"))?;
        }
    }
    let codex_args =
        resolve_args(args, cwd, &local).map_err(|e| format!("argument parse error: {e}"))?;
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
            root.join("tasks/jobs.db")
        } else {
            value_path(&args["jobs_db"], cwd)
        };
        let registry = JobRegistry::open(&db).map_err(|e| format!("registry error: {e:?}"))?;
        let id = unique_id();
        let mut record = json!({"job_id":id,"change_id":change,"category":category,"family":args["family"],"repo_root":root.to_str(),"codex_args":codex_args,"timeout_seconds":args["timeout"].as_i64().unwrap_or(600),"status":"running","started_at":utc_now(),"cancel_requested":false,"allow_harness_self_modify":args["allow_harness_self_modify"]==true,"resume_count":0});
        let inserted = (|| -> Result<()> {
            record["identity_json"] = hook(
                bridge,
                "job_identity",
                vec![namespace(args), path(root), json!(prompt), json!(model)],
            )?;
            registry.insert(&record).map_err(|e| format!("{e:?}"))?;
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
                registry.insert(&record).map_err(|e| format!("{e:?}"))?;
            }
            fail_job(&registry, &id, &strip_class(&error))?;
            return Err(format!("background insert failed: {}", strip_class(&error)));
        }
        line(&format!("[BACKGROUND] job_id={id}"));
        let _ = io::stdout().flush();
        if let Err(error) = validate_ledger(&ledger, change, category) {
            fail_job(&registry, &id, &strip_class(&error))?;
            return Err(error);
        }
        let cancelled = registry
            .connection()
            .query_row(
                "SELECT cancel_requested FROM jobs WHERE job_id=?",
                [&id],
                |r| r.get::<_, bool>(0),
            )
            .map_err(|e| e.to_string())?;
        if cancelled {
            registry
                .update_status(&id, "cancelled", &json!({"completed_at":utc_now()}))
                .map_err(|e| format!("{e:?}"))?;
            return Ok(1);
        }
        let completed = (|| -> Result<Value> {
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
            Ok(result)
        })();
        return match completed {
            Ok(result) => {
                let code = result["exit_code"].as_i64().unwrap_or(1) as i32;
                registry.update_status(&id,if code==0{"completed"}else{"failed"},&json!({"exit_code":code,"stdout":result["stdout"],"stderr":result["stderr"],"duration_seconds":result["duration_seconds"],"completed_at":utc_now()})).map_err(|e|format!("{e:?}"))?;
                Ok(code)
            }
            Err(error) => {
                fail_job(&registry, &id, &strip_class(&error))?;
                Ok(1)
            }
        };
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
    line(&format!(
        "[RESULT] change_id={} category={}",
        repr(change),
        repr(category)
    ));
    line(&format!(
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
    line(&format!("[RESULT] command={}", list_repr(&command)));
    line(&format!(
        "[LEDGER] previous_status={} -> new_status={}",
        repr_value(&previous),
        repr(status)
    ));
    line(&format!("[LEDGER] notes={}", repr(&notes)));
    for (key, label) in [("stdout", "STDOUT"), ("stderr", "STDERR")] {
        if let Some(s) = result[key].as_str().filter(|s| !s.is_empty()) {
            line(&format!("[{label}] {}", repr(&chars(s, 500))));
        }
    }
    Ok(result["exit_code"].as_i64().unwrap_or(1) as i32)
}
fn strip_class(s: &str) -> String {
    s.split_once(": ")
        .map_or(s, |(_, message)| message)
        .to_owned()
}
fn fail_job(registry: &JobRegistry, id: &str, error: &str) -> Result<()> {
    registry
        .update_status(
            id,
            "failed",
            &json!({"exit_code":1,"stderr":error,"completed_at":utc_now()}),
        )
        .map_err(|e| format!("{e:?}"))
}
fn resolve_args(args: &Value, cwd: &Path, local: &LocalConfig) -> Result<Vec<String>> {
    if !args["codex_args_file"].is_null() {
        let file = value_path(&args["codex_args_file"], cwd);
        let metadata = fs::metadata(&file).map_err(|e| format!("OSError: {e}"))?;
        local
            .validate_input_size(metadata.len())
            .map_err(|e| e.to_string())?;
        return fs::read_to_string(&file)
            .map(|s| vec![s.replace("\r\n", "\n").replace('\r', "\n")])
            .map_err(|e| format!("OSError: {e}"));
    }
    let text = args["codex_args"]
        .as_str()
        .ok_or("exactly one of --codex-args or --codex-args-file must be provided")?;
    local
        .validate_input_size(text.len() as u64)
        .map_err(|e| e.to_string())?;
    shell_words(text)
}
fn shell_words(text: &str) -> Result<Vec<String>> {
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
fn prompt(args: &[String]) -> String {
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
fn entry<'a>(ledger: &'a Value, change: &str) -> Option<&'a Value> {
    ledger["changes"]
        .as_array()
        .and_then(|items| items.iter().find(|item| item["id"] == change))
        .or_else(|| ledger.get(change).filter(|v| v.is_object()))
}
fn validate_ledger(file: &Path, change: &str, category: &str) -> Result<Value> {
    let bytes=fs::read(file).map_err(|e|if e.kind()==io::ErrorKind::NotFound{format!("FileNotFoundError: Ledger not found: {}. Create tasks/tdd.json with a planned entry before calling execute.",file.display())}else{format!("OSError: {e}")})?;
    let ledger: Value =
        serde_json::from_slice(&bytes).map_err(|e| format!("JSONDecodeError: {e}"))?;
    let entry = entry(&ledger, change).ok_or_else(|| {
        format!(
            "KeyError: {}",
            repr(&format!(
                "unknown change_id {} in {}. Add a TDD entry for this id before executing.",
                repr(change),
                file.display()
            ))
        )
    })?;
    let value=entry["categories"].get(category).ok_or_else(||format!("KeyError: {}",repr(&format!("category {} not in entry {}. Declare the category in tdd.json before updating it (do not silently add).",repr(category),repr(change)))))?;
    if value["status"] == "not_applicable" {
        return Err(format!(
            "ValueError: category {} is marked not_applicable; cannot run executor on it. Edit tdd.json manually if you intend to reclassify.",
            repr(category)
        ));
    }
    if !value.is_object() {
        return Err("TypeError: ledger category must contain an object".into());
    }
    Ok(ledger)
}
fn update_ledger(
    file: &Path,
    change: &str,
    category: &str,
    result: &Value,
) -> Result<(Value, &'static str, String)> {
    let mut ledger = validate_ledger(file, change, category)?;
    let original = fs::read_to_string(file).map_err(|e| format!("OSError: {e}"))?;
    let value = if let Some(index) = ledger["changes"]
        .as_array()
        .and_then(|items| items.iter().position(|item| item["id"] == change))
    {
        &mut ledger["changes"][index]["categories"][category]
    } else {
        &mut ledger[change]["categories"][category]
    };
    let previous = value["status"].clone();
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
    value["status"] = json!(status);
    value["executed_argv"] = result["command"].clone();
    value["notes"] = json!(notes);
    let parent = file.parent().ok_or("OSError: ledger parent missing")?;
    let temp = parent.join(format!(".mir-executor-{}.tmp", unique_id()));
    let written = (|| -> Result<()> {
        let mut out = fs::OpenOptions::new()
            .create_new(true)
            .write(true)
            .open(&temp)
            .map_err(|e| format!("OSError: {e}"))?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            out.set_permissions(fs::Permissions::from_mode(0o600))
                .map_err(|e| format!("OSError: {e}"))?;
        }
        let rendered = crate::executor_ledger_json::render(&original, &ledger)?;
        #[cfg(windows)]
        let rendered = rendered.replace('\n', "\r\n");
        out.write_all(rendered.as_bytes())
            .map_err(|e| format!("OSError: {e}"))?;
        drop(out);
        atomic_replace(&temp, file)
    })();
    if written.is_err() {
        let _ = fs::remove_file(&temp);
    }
    written?;
    Ok((previous, status, notes))
}
fn atomic_replace(source: &Path, target: &Path) -> Result<()> {
    fs::rename(source, target).map_err(|e| format!("OSError: {e}"))
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
    bridge: &mut Option<Box<LocalBridge>>,
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
    let binary = environment
        .get(&OsString::from("CODEX_BIN"))
        .and_then(|v| v.to_str())
        .unwrap_or("codex");
    let start = Instant::now();
    let mut command = Command::new(binary);
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
    let timeout = args["timeout"]
        .as_f64()
        .map(|n| Duration::try_from_secs_f64(n.max(0.0)).map_err(|e| format!("ValueError: {e}")))
        .transpose()?;
    let mut options = CallOptions::new(prompt, cwd.to_str().ok_or("ValueError: non UTF-8 cwd")?);
    options.timeout = timeout;
    options.stall_timeout = args["stall_timeout"]
        .as_f64()
        .map(|n| Duration::try_from_secs_f64(n.max(0.0)).map_err(|e| format!("ValueError: {e}")))
        .transpose()?;
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
        let result = client.call(options, &mut |_, _| Ok(()));
        client.close();
        result
    })();
    let (mut result, metadata) = match raw {
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
        Err(TransportError::Timeout(_)) if timeout.is_some() => {
            return Err(if args["use_async"] == true {
                format!("async timeout after {}s", args["timeout"])
            } else {
                format!(
                    "Codex timeout after {}s: Command '{}' timed out after {} seconds",
                    args["timeout"],
                    list_repr(&[binary.into(), "app-server".into()]),
                    args["timeout"]
                )
            });
        }
        Err(TransportError::Process(message))
            if message.contains("No such file") || message.contains("cannot find the file") =>
        {
            return Err(format!(
                "FileNotFoundError: Codex binary not found: {}. Set CODEX_BIN to the full path of the codex executable.",
                repr(binary)
            ));
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
    if !replacement.is_null() {
        result = if replacement["$type"] == "subprocess_result" {
            replacement["value"].clone()
        } else {
            replacement
        };
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
fn unique_id() -> String {
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
fn utc_now() -> String {
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

#[cfg(test)]
mod tests {
    use super::*;

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
        assert_eq!(previous, "pending");
        assert_eq!(status, "pass");
        let updated: Value = serde_json::from_slice(&fs::read(&ledger).unwrap()).unwrap();
        assert_eq!(updated["c"]["categories"]["unit"]["status"], "pass");
        assert_eq!(fs::read_dir(&root).unwrap().count(), 1);
        fs::remove_dir_all(root).unwrap();
    }
}
