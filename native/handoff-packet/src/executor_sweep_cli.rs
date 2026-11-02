//! Conservative native sweep entrypoint. Unsupported forms decline before ownership.
use crate::{
    executor_local::LocalConfig,
    executor_protocol, executor_sweep,
    local_bridge::{BridgeConfig, LocalBridge},
};
use serde_json::Value;
use std::{
    collections::{BTreeMap, BTreeSet},
    ffi::OsString,
    fs,
    io::{self, Write},
    path::{Component, Path, PathBuf},
    time::{Duration, SystemTime, UNIX_EPOCH},
};

struct Args {
    repo: PathBuf,
    db: PathBuf,
    grace: i64,
    apply: bool,
    retention: i64,
    bridge: Option<BridgeConfig>,
}
fn parse(raw: &[OsString], cwd: &Path, home: &Path) -> Option<Args> {
    let mut iter = raw.iter();
    let mut command = false;
    let mut repo = cwd.to_owned();
    let mut db = None;
    let mut grace = 120;
    let mut apply = false;
    let mut seen = BTreeSet::new();
    parse_options(
        &mut iter,
        &mut command,
        &mut repo,
        &mut db,
        &mut grace,
        &mut apply,
        &mut seen,
    )?;
    if !command {
        return None;
    }
    let repo = fs::canonicalize(if repo.is_absolute() {
        repo
    } else {
        cwd.join(repo)
    })
    .ok()
    .map(crate::supply::plain)?;
    if repo != fs::canonicalize(home).ok().map(crate::supply::plain)? {
        return None;
    }
    // Explicit parser extensions remain reference-owned before target import.
    let bridge = match fs::read(repo.join("tools").join("mir_executor").join("local.py")) {
        Err(e) if e.kind() == io::ErrorKind::NotFound => None,
        Ok(source) => {
            if source
                .windows(b"register_execute_options".len())
                .any(|part| part == b"register_execute_options")
            {
                return None;
            }
            let environment: BTreeMap<OsString, OsString> = std::env::vars_os().collect();
            let interpreter = crate::executor_execute::interpreter(&environment, cwd)?;
            let bridge_script = repo
                .join("tools")
                .join("mir_executor")
                .join("local_bridge.py");
            if !bridge_script.is_file() {
                return None;
            }
            Some(BridgeConfig {
                interpreter,
                target_root: repo.clone(),
                bridge_script,
                environment,
                timeout: Duration::from_secs(10),
            })
        }
        _ => return None,
    };
    let db = db.unwrap_or_else(|| repo.join("tasks").join("jobs.db"));
    let db = if db.is_absolute() { db } else { cwd.join(db) };
    if db.components().any(|p| p == Component::ParentDir) {
        return None;
    }
    // Python resolves parent aliases (for example the platform temp directory)
    // before opening SQLite. Preserve the final component so admission can
    // still decline an actual database symlink.
    let db = resolve_parent(db.parent()?)?.join(db.file_name()?);
    let config = LocalConfig::load(&repo).ok()?;
    let retention = config.retention_days(None).ok()?.as_i64()?;
    // Python datetime/timedelta overflow and exotic ledgers remain reference-owned.
    let today =
        i64::try_from(SystemTime::now().duration_since(UNIX_EPOCH).ok()?.as_secs() / 86400).ok()?;
    if retention > today + 719162 || !ledger_supported(&db) {
        return None;
    }
    Some(Args {
        repo,
        db,
        grace,
        apply,
        retention,
        bridge,
    })
}
fn resolve_parent(path: &Path) -> Option<PathBuf> {
    match fs::canonicalize(path) {
        Ok(path) => Some(crate::supply::plain(path)),
        Err(error) if error.kind() == io::ErrorKind::NotFound => {
            Some(resolve_parent(path.parent()?)?.join(path.file_name()?))
        }
        Err(_) => None,
    }
}
fn parse_options<'a>(
    iter: &mut impl Iterator<Item = &'a OsString>,
    command: &mut bool,
    repo: &mut PathBuf,
    db: &mut Option<PathBuf>,
    grace: &mut i64,
    apply: &mut bool,
    seen: &mut BTreeSet<String>,
) -> Option<()> {
    while let Some(arg) = iter.next() {
        let arg = arg.to_str()?;
        if arg == "sweep" && !*command {
            *command = true;
            continue;
        }
        let (key, inline) = arg
            .split_once('=')
            .map_or((arg, None), |(k, v)| (k, Some(v)));
        if key == "--apply" && *command && inline.is_none() && seen.insert(key.into()) {
            *apply = true;
            continue;
        }
        if !(key == "--jobs-db" || (*command && matches!(key, "--repo-root" | "--grace-seconds")))
            || !seen.insert(key.into())
        {
            return None;
        }
        let value = match inline {
            Some(v) => v,
            None => iter.next()?.to_str()?,
        };
        if inline.is_none() && value.starts_with('-') && key != "--grace-seconds" {
            return None;
        }
        match key {
            "--jobs-db" => *db = Some(PathBuf::from(value)),
            "--repo-root" => *repo = PathBuf::from(value),
            "--grace-seconds" => *grace = value.parse().ok()?,
            _ => return None,
        }
    }
    Some(())
}
fn ledger_supported(path: &Path) -> bool {
    use rusqlite::{Connection, OpenFlags};
    let check = || -> Option<()> {
        for suffix in ["-journal", "-wal", "-shm"] {
            let mut sidecar = path.as_os_str().to_owned();
            sidecar.push(suffix);
            match fs::symlink_metadata(Path::new(&sidecar)) {
                Err(e) if e.kind() == io::ErrorKind::NotFound => (),
                _ => return None,
            }
        }
        match fs::symlink_metadata(path) {
            Err(e) if e.kind() == io::ErrorKind::NotFound => return Some(()),
            Ok(meta) if meta.is_file() => (),
            _ => return None,
        }
        let db = Connection::open_with_flags(
            path,
            OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_NOFOLLOW,
        )
        .ok()?;
        let triggers: i64 = db
            .query_row(
                "SELECT count(*) FROM sqlite_master WHERE type='trigger'",
                [],
                |row| row.get(0),
            )
            .ok()?;
        if triggers != 0 {
            return None;
        }
        let names = db
            .prepare("PRAGMA table_info(jobs)")
            .ok()?
            .query_map([], |row| row.get::<_, String>(1))
            .ok()?
            .collect::<Result<Vec<_>, _>>()
            .ok()?;
        let metadata = if names.iter().any(|name| name == "ai_run_metadata") {
            "ai_run_metadata"
        } else {
            "NULL"
        };
        let mut statement = db
            .prepare(&format!(
                "SELECT job_id,status,started_at,completed_at,timeout_seconds,{metadata} FROM jobs"
            ))
            .ok()?;
        let mut rows = statement.query([]).ok()?;
        while let Some(row) = rows.next().ok()? {
            let _: String = row.get(0).ok()?;
            let _: String = row.get(1).ok()?;
            let _: String = row.get(2).ok()?;
            let _: Option<String> = row.get(3).ok()?;
            let _: i64 = row.get(4).ok()?;
            if let Some(text) = row.get::<_, Option<String>>(5).ok()? {
                let value: Value = serde_json::from_str(&text).ok()?;
                if !value.is_null() && !value.is_object() {
                    return None;
                }
            }
        }
        Some(())
    };
    check().is_some()
}
fn now() -> Option<String> {
    let duration = SystemTime::now().duration_since(UNIX_EPOCH).ok()?;
    let seconds = i64::try_from(duration.as_secs()).ok()?;
    let z = seconds / 86400 + 719468;
    let era = z / 146097;
    let doe = z - era * 146097;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let mut year = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let day = doy - (153 * mp + 2) / 5 + 1;
    let month = mp + if mp < 10 { 3 } else { -9 };
    year += i64::from(month <= 2);
    Some(format!(
        "{year:04}-{month:02}-{day:02}T{:02}:{:02}:{:02}.{:06}+00:00",
        seconds / 3600 % 24,
        seconds / 60 % 60,
        seconds % 60,
        duration.subsec_micros()
    ))
}
fn ascii_json(value: &Value) -> Result<String, String> {
    let encoded = serde_json::to_string(value).map_err(|e| e.to_string())?;
    let mut out = String::new();
    for c in encoded.chars() {
        if c < '\u{7f}' {
            out.push(c);
        } else {
            for unit in c.encode_utf16(&mut [0; 2]) {
                out.push_str(&format!("\\u{unit:04x}"));
            }
        }
    }
    Ok(out)
}
fn encode(value: &Value) -> Result<String, String> {
    match value {
        Value::Object(_) => object(value, &["path", "reasons"]),
        Value::Array(items) => Ok(format!(
            "[{}]",
            items
                .iter()
                .map(encode)
                .collect::<Result<Vec<_>, _>>()?
                .join(",")
        )),
        _ => ascii_json(value),
    }
}
fn object(value: &Value, keys: &[&str]) -> Result<String, String> {
    let mut fields = Vec::new();
    for key in keys {
        fields.push(format!(
            "{}:{}",
            ascii_json(&Value::String((*key).into()))?,
            encode(&value[*key])?
        ));
    }
    Ok(format!("{{{}}}", fields.join(",")))
}
fn execute(mut args: Args, cwd: &Path) -> Result<String, String> {
    // Sweeps have no writer scope or execution hooks. The parser still imports
    // local.py, so preserve that import through the existing transport seam.
    let bridge = match args.bridge.take() {
        Some(config) => LocalBridge::start_in(config, cwd).map_err(|e| e.to_string())?,
        None => None,
    };
    if let Some(bridge) = &bridge {
        if bridge.hello()["register_execute_options"] == true {
            return Err("local import dynamically registered execute options; native ownership is final, invoke Python explicitly".into());
        }
        args.retention = LocalConfig::load(&args.repo)
            .map_err(|e| e.to_string())?
            .retention_days(None)
            .map_err(|e| e.to_string())?
            .as_i64()
            .ok_or("retention overflow")?;
    }
    let time = now().ok_or("clock unavailable")?;
    let run = executor_sweep::sweep_run_state(&args.repo, &args.db, &time, args.grace, args.apply)?;
    let artifacts = executor_sweep::sweep_terminal_artifacts(
        &args.repo,
        &args.db,
        &time,
        args.retention,
        args.apply,
    )?;
    let mut text = object(
        &run,
        &[
            "stale_jobs",
            "orphan_worktrees",
            "removable_worktrees",
            "preserved_worktrees",
            "reaped_jobs",
            "removed_worktrees",
            "errors",
            "apply",
        ],
    )?;
    text.pop();
    text.push_str(",\"terminal_artifacts\":");
    text.push_str(&object(
        &artifacts,
        &["retention_days", "expired", "removed", "errors"],
    )?);
    text.push_str("}\n");
    Ok(text)
}
/// Raw argv includes `sweep`, with an optional preceding global `--jobs-db`.
/// Exit 64 without a receipt requests the Python reference.
pub fn run(raw: &[OsString], cwd: &Path, home_root: &Path) -> i32 {
    let Some(args) = parse(raw, cwd, home_root) else {
        return 64;
    };
    if let Ok(encoding) = std::env::var("PYTHONIOENCODING") {
        let encoding = encoding.split(':').next().unwrap_or("");
        if !encoding.is_empty()
            && !["utf8", "utf-8", "utf_8"]
                .iter()
                .any(|e| encoding.eq_ignore_ascii_case(e))
        {
            return 64;
        }
    } else if matches!(
        std::env::var("PYTHONIOENCODING"),
        Err(std::env::VarError::NotUnicode(_))
    ) {
        return 64;
    }
    // Read-only admission ends here. This precedes registry creation, child Git
    // commands, worktree removal, artifact receipts, and output.
    executor_protocol::claim();
    match execute(args, cwd) {
        Ok(text) => {
            #[cfg(windows)]
            let text = text.replace('\n', "\r\n");
            if io::stdout().lock().write_all(text.as_bytes()).is_ok() {
                0
            } else {
                1
            }
        }
        Err(error) => {
            let text = format!("[mir_executor] {error}\n");
            #[cfg(windows)]
            let text = text.replace('\n', "\r\n");
            let _ = io::stderr().lock().write_all(text.as_bytes());
            1
        }
    }
}
