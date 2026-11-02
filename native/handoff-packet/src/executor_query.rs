//! Executor registry queries and cancel. Exit 64 silently requests the Python reference.
#![forbid(unsafe_code)]
#![cfg_attr(
    not(test),
    deny(clippy::unwrap_used, clippy::expect_used, clippy::panic)
)]

use regex::Regex;
use rusqlite::{Connection, OpenFlags, Row, types::ValueRef};
use std::collections::BTreeSet;
use std::ffi::OsString;
use std::fs;
use std::io::{self, Read, Write};
use std::path::{Component, Path, PathBuf};

type Result<T> = std::result::Result<T, ()>;

// Admit current schemas and missing Python-migratable columns. Extended and
// dynamically typed rows still go to Python before any native write.
const COLUMNS: &[(&str, &str)] = &[
    ("job_id", "TEXT"),
    ("change_id", "TEXT"),
    ("category", "TEXT"),
    ("family", "TEXT"),
    ("repo_root", "TEXT"),
    ("codex_args", "TEXT"),
    ("dispatch_brief_path", "TEXT"),
    ("allow_harness_self_modify", "INTEGER"),
    ("resume_count", "INTEGER"),
    ("last_resumed_at", "TEXT"),
    ("timeout_seconds", "INTEGER"),
    ("status", "TEXT"),
    ("exit_code", "INTEGER"),
    ("stdout", "TEXT"),
    ("stderr", "TEXT"),
    ("duration_seconds", "REAL"),
    ("started_at", "TEXT"),
    ("completed_at", "TEXT"),
    ("cancel_requested", "INTEGER"),
    ("target_agent", "TEXT"),
    ("execution_backend", "TEXT"),
    ("resolved_model", "TEXT"),
    ("resolved_reasoning_effort", "TEXT"),
    ("agent_definition_path", "TEXT"),
    ("agent_definition_sha256", "TEXT"),
    ("identity_json", "TEXT"),
    ("dispatch_options_json", "TEXT"),
    ("ai_run_metadata", "TEXT"),
];

#[derive(Debug, PartialEq)]
enum Command {
    Cancel(String),
    Status(String),
    Result(String),
    List(Option<String>),
}

#[derive(Debug)]
struct Args {
    db: PathBuf,
    command: Command,
}

fn text_arg(arg: OsString) -> Result<String> {
    arg.into_string().map_err(|_| ())
}

fn parse(raw: impl IntoIterator<Item = OsString>, cwd: &Path) -> Result<Args> {
    let mut raw = raw.into_iter();
    if raw.next().ok_or(())? != "--home-root" {
        return Err(());
    }
    let home = PathBuf::from(raw.next().ok_or(())?);
    let mut db = None;
    let mut root = None;
    let mut job = None;
    let mut status = None;
    let mut command = None;
    let mut seen = BTreeSet::new();
    while let Some(arg) = raw.next() {
        let arg = text_arg(arg)?;
        if matches!(arg.as_str(), "status" | "result" | "list-jobs" | "cancel") && command.is_none()
        {
            command = Some(arg);
            continue;
        }
        let (key, inline) = arg
            .split_once('=')
            .map_or((arg.as_str(), None), |(k, v)| (k, Some(v)));
        let allowed = match key {
            "--jobs-db" => command.is_none(),
            "--repo-root" => command.is_some(),
            "--job-id" => matches!(command.as_deref(), Some("status" | "result" | "cancel")),
            "--status" => command.as_deref() == Some("list-jobs"),
            _ => false,
        };
        if !allowed || !seen.insert(key.to_owned()) {
            return Err(());
        }
        let value = match inline {
            Some(value) => value.to_owned(),
            None => text_arg(raw.next().ok_or(())?)?,
        };
        // argparse may interpret these as another option; leave those cases to it.
        if inline.is_none() && value.starts_with('-') {
            return Err(());
        }
        match key {
            "--jobs-db" => db = Some(PathBuf::from(value)),
            "--repo-root" => root = Some(PathBuf::from(value)),
            "--job-id" => job = Some(value),
            "--status" => status = Some(value),
            _ => return Err(()),
        }
    }
    let command = match command.as_deref() {
        Some("cancel") => Command::Cancel(job.ok_or(())?),
        Some("status") => Command::Status(job.ok_or(())?),
        Some("result") => Command::Result(job.ok_or(())?),
        Some("list-jobs") => {
            if status
                .as_deref()
                .is_some_and(|s| !matches!(s, "running" | "completed" | "cancelled" | "failed"))
            {
                return Err(());
            }
            Command::List(status)
        }
        _ => return Err(()),
    };
    let root = fs::canonicalize(root.unwrap_or_else(|| cwd.to_owned())).map_err(|_| ())?;
    let home = fs::canonicalize(home).map_err(|_| ())?;
    if root != home || !root.is_dir() {
        return Err(());
    }
    if matches!(command, Command::Cancel(_)) && !absent(&root.join("tools/mir_executor/local.py"))?
    {
        return Err(());
    }
    let db = db.unwrap_or_else(|| root.join("tasks/jobs.db"));
    let db = if db.is_absolute() { db } else { cwd.join(db) };
    // pathlib.resolve collapses even missing components before '..'; the OS
    // path lookup does not. Defer that spelling instead of reading another DB.
    if db.components().any(|part| part == Component::ParentDir) {
        return Err(());
    }
    Ok(Args { db, command })
}

fn absent(path: &Path) -> Result<bool> {
    match fs::symlink_metadata(path) {
        Ok(_) => Ok(false),
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(true),
        Err(_) => Err(()),
    }
}

fn no_sidecars(path: &Path) -> Result<()> {
    for suffix in ["-journal", "-wal", "-shm"] {
        let mut sidecar = path.as_os_str().to_owned();
        sidecar.push(suffix);
        if !absent(Path::new(&sidecar))? {
            return Err(());
        }
    }
    Ok(())
}

fn safely_absent(path: &Path) -> Result<bool> {
    if !absent(path)? {
        return Ok(false);
    }
    let mut parent = path.parent().ok_or(())?;
    while absent(parent)? {
        parent = parent.parent().ok_or(())?;
    }
    // A dangling symlink ancestor is not an absent database Python can create.
    if !fs::metadata(parent).map_err(|_| ())?.is_dir() {
        return Err(());
    }
    Ok(true)
}

fn utf8_encoding(value: &str) -> bool {
    let encoding = value.split(':').next().unwrap_or("");
    encoding.is_empty()
        || encoding.eq_ignore_ascii_case("utf8")
        || encoding.eq_ignore_ascii_case("utf-8")
        || encoding.eq_ignore_ascii_case("utf_8")
}

fn check_schema(db: &Connection) -> Result<Vec<String>> {
    for pragma in ["user_version", "application_id"] {
        let value: i64 = db
            .pragma_query_value(None, pragma, |r| r.get(0))
            .map_err(|_| ())?;
        if value != 0 {
            return Err(());
        }
    }
    let kind: String = db
        .query_row(
            "SELECT type FROM sqlite_master WHERE name = 'jobs'",
            [],
            |r| r.get(0),
        )
        .map_err(|_| ())?;
    if kind != "table" {
        return Err(());
    }
    let mut stmt = db.prepare("PRAGMA table_xinfo(jobs)").map_err(|_| ())?;
    let columns = stmt
        .query_map([], |r| {
            Ok((
                r.get::<_, String>(1)?,
                r.get::<_, String>(2)?,
                r.get::<_, i64>(5)?,
                r.get::<_, i64>(6)?,
            ))
        })
        .map_err(|_| ())?;
    let mut seen = BTreeSet::new();
    for column in columns {
        let (name, kind, primary, hidden) = column.map_err(|_| ())?;
        if !COLUMNS.iter().any(|(n, t)| name == *n && kind == *t)
            || primary != i64::from(name == "job_id")
            || hidden != 0
            || !seen.insert(name)
        {
            return Err(());
        }
    }
    let optional = [
        "target_agent",
        "execution_backend",
        "resolved_model",
        "resolved_reasoning_effort",
        "agent_definition_path",
        "agent_definition_sha256",
        "identity_json",
        "dispatch_options_json",
        "ai_run_metadata",
        "dispatch_brief_path",
        "allow_harness_self_modify",
        "resume_count",
        "last_resumed_at",
    ];
    let mut projection = Vec::new();
    for (name, _) in COLUMNS {
        if seen.contains(*name) {
            projection.push((*name).to_owned());
        } else if optional.contains(name) {
            let default = if matches!(*name, "allow_harness_self_modify" | "resume_count") {
                "0"
            } else {
                "NULL"
            };
            projection.push(format!("{default} AS {name}"));
        } else {
            return Err(());
        }
    }
    let triggers: i64 = db
        .query_row(
            "SELECT count(*) FROM sqlite_master WHERE type='trigger'",
            [],
            |r| r.get(0),
        )
        .map_err(|_| ())?;
    if triggers != 0 {
        return Err(());
    }
    Ok(projection)
}

#[derive(Debug)]
struct Job {
    id: String,
    change: String,
    category: String,
    family: Option<String>,
    root: String,
    brief: Option<String>,
    allow: bool,
    resumes: i64,
    resumed: Option<String>,
    status: String,
    exit: Option<i64>,
    stdout: Option<String>,
    stderr: Option<String>,
    duration: Option<f64>,
    started: String,
    completed: Option<String>,
    cancel: bool,
}

// These fields are validated, never rendered. Python accepts unpaired surrogate
// escapes, which Rust strings cannot represent. Substitute only complete surrogate
// escapes in this validation copy, preserving escape boundaries and JSON shape.
fn validation_json(input: &str) -> Result<serde_json::Value> {
    let mut bytes = input.as_bytes().to_vec();
    let mut index = 0;
    while index < bytes.len() {
        if bytes[index] != b'\\' {
            index += 1;
            continue;
        }
        if bytes.get(index + 1) == Some(&b'u')
            && let Some(hex) = bytes.get(index + 2..index + 6)
            && matches!(hex[0], b'd' | b'D')
            && matches!(hex[1], b'8'..=b'9' | b'a'..=b'f' | b'A'..=b'F')
            && hex.iter().all(u8::is_ascii_hexdigit)
        {
            bytes[index + 2..index + 6].copy_from_slice(b"e000");
            index += 6;
        } else {
            // In particular, skip both bytes of an escaped backslash.
            index += 2;
        }
    }
    serde_json::from_slice(&bytes).map_err(|_| ())
}

fn read_job(row: &Row<'_>) -> Result<Job> {
    // Validate all fields decoded by the reference, including unused JSON. This
    // prevents a successful native answer from masking a Python decode failure.
    for (name, kind) in COLUMNS {
        let value = row.get_ref(*name).map_err(|_| ())?;
        let nullable = !matches!(
            *name,
            "job_id"
                | "change_id"
                | "category"
                | "repo_root"
                | "codex_args"
                | "timeout_seconds"
                | "status"
                | "started_at"
                | "cancel_requested"
                | "allow_harness_self_modify"
                | "resume_count"
        );
        match (value, *kind) {
            (ValueRef::Null, _) if nullable => {}
            (ValueRef::Text(bytes), "TEXT") => {
                std::str::from_utf8(bytes).map_err(|_| ())?;
            }
            (ValueRef::Integer(_), "INTEGER") => {}
            (ValueRef::Real(value), "REAL") if value.is_finite() => {}
            _ => return Err(()),
        }
    }
    let args: String = row.get("codex_args").map_err(|_| ())?;
    let args: serde_json::Value = validation_json(&args)?;
    if !args
        .as_array()
        .is_some_and(|a| a.iter().all(serde_json::Value::is_string))
    {
        return Err(());
    }
    if let Some(metadata) = row
        .get::<_, Option<String>>("ai_run_metadata")
        .map_err(|_| ())?
    {
        let _: serde_json::Value = validation_json(&metadata)?;
    }
    Ok(Job {
        id: row.get("job_id").map_err(|_| ())?,
        change: row.get("change_id").map_err(|_| ())?,
        category: row.get("category").map_err(|_| ())?,
        family: row.get("family").map_err(|_| ())?,
        root: row.get("repo_root").map_err(|_| ())?,
        brief: row.get("dispatch_brief_path").map_err(|_| ())?,
        allow: row
            .get::<_, i64>("allow_harness_self_modify")
            .map_err(|_| ())?
            != 0,
        resumes: row.get("resume_count").map_err(|_| ())?,
        resumed: row.get("last_resumed_at").map_err(|_| ())?,
        status: row.get("status").map_err(|_| ())?,
        exit: row.get("exit_code").map_err(|_| ())?,
        stdout: row.get("stdout").map_err(|_| ())?,
        stderr: row.get("stderr").map_err(|_| ())?,
        duration: row.get("duration_seconds").map_err(|_| ())?,
        started: row.get("started_at").map_err(|_| ())?,
        completed: row.get("completed_at").map_err(|_| ())?,
        cancel: row.get::<_, i64>("cancel_requested").map_err(|_| ())? != 0,
    })
}

struct PythonText {
    nonprintable: Regex,
    unstable: Regex,
}

impl PythonText {
    fn new() -> Result<Self> {
        Ok(Self {
            nonprintable: Regex::new(r"[\p{C}\p{Z}]").map_err(|_| ())?,
            // Supported Python 3.12..3.14 use Unicode 15..16. Newly assigned
            // characters may print literally in only one version. Keep those
            // queries on Python; established unassigned characters still escape.
            unstable: Regex::new(r"[\p{Assigned}--\p{Age:15.0}]").map_err(|_| ())?,
        })
    }

    fn admit(&self, value: &str) -> Result<()> {
        if self.unstable.is_match(value) {
            return Err(());
        }
        Ok(())
    }

    fn repr(&self, value: &str) -> String {
        let quote = if value.contains('\'') && !value.contains('"') {
            '"'
        } else {
            '\''
        };
        let mut output = String::new();
        output.push(quote);
        for c in value.chars() {
            match c {
                '\\' => output.push_str("\\\\"),
                '\n' => output.push_str("\\n"),
                '\r' => output.push_str("\\r"),
                '\t' => output.push_str("\\t"),
                _ if c == quote => {
                    output.push('\\');
                    output.push(c);
                }
                _ if c != ' ' && self.nonprintable.is_match(c.encode_utf8(&mut [0; 4])) => {
                    let n = c as u32;
                    output.push_str(&if n <= 0xff {
                        format!("\\x{n:02x}")
                    } else if n <= 0xffff {
                        format!("\\u{n:04x}")
                    } else {
                        format!("\\U{n:08x}")
                    });
                }
                _ => output.push(c),
            }
        }
        output.push(quote);
        output
    }

    fn optional(&self, value: Option<&str>) -> String {
        value.map_or_else(|| "None".to_owned(), |v| self.repr(v))
    }
}

fn boolean(value: bool) -> &'static str {
    if value { "True" } else { "False" }
}

fn whitespace(c: char) -> bool {
    c.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&c)
}

fn blocked(payload: Option<&str>) -> Result<Option<&str>> {
    let Some((_, rest)) = payload.and_then(|s| s.split_once("blocked_reason=")) else {
        return Ok(None);
    };
    rest.split(whitespace)
        .find(|s| !s.is_empty())
        .map(Some)
        .ok_or(())
}

fn blocked_reason(job: &Job) -> Result<Option<&str>> {
    match blocked(job.stdout.as_deref())? {
        Some(reason) => Ok(Some(reason)),
        None => blocked(job.stderr.as_deref()),
    }
}

// Match Python's shortest float spelling, including exponent thresholds and .0.
fn python_float(value: f64) -> Result<String> {
    let encoded = serde_json::to_string(&value).map_err(|_| ())?;
    let sign = if encoded.starts_with('-') { "-" } else { "" };
    let magnitude = encoded.trim_start_matches('-');
    let (mantissa, exponent) = match magnitude.split_once(['e', 'E']) {
        Some((m, e)) => (m, e.parse::<i32>().map_err(|_| ())?),
        None => (magnitude, 0),
    };
    let decimal = mantissa.find('.').unwrap_or(mantissa.len()) as i32;
    let all: String = mantissa.chars().filter(|c| *c != '.').collect();
    let Some(first) = all.find(|c| c != '0') else {
        return Ok(format!("{sign}0.0"));
    };
    let exponent = exponent + decimal - first as i32 - 1;
    let digits = all[first..].trim_end_matches('0');
    if !(-4..16).contains(&exponent) {
        let fraction = if digits.len() > 1 {
            format!(".{}", &digits[1..])
        } else {
            String::new()
        };
        return Ok(format!(
            "{sign}{}{fraction}e{}{:02}",
            &digits[..1],
            if exponent < 0 { '-' } else { '+' },
            exponent.abs()
        ));
    }
    if exponent < 0 {
        return Ok(format!(
            "{sign}0.{}{}",
            "0".repeat((-exponent - 1) as usize),
            digits
        ));
    }
    let decimal = (exponent + 1) as usize;
    if decimal >= digits.len() {
        return Ok(format!(
            "{sign}{digits}{}.0",
            "0".repeat(decimal - digits.len())
        ));
    }
    Ok(format!(
        "{sign}{}.{}",
        &digits[..decimal],
        &digits[decimal..]
    ))
}

fn output(command: &Command, jobs: &[Job], py: &PythonText) -> Result<(String, String, i32)> {
    if let Command::Cancel(id) | Command::Status(id) | Command::Result(id) = command {
        py.admit(id)?;
    }
    for job in jobs {
        for value in [
            Some(job.id.as_str()),
            Some(job.change.as_str()),
            Some(job.category.as_str()),
            job.family.as_deref(),
            Some(job.root.as_str()),
            job.brief.as_deref(),
            job.resumed.as_deref(),
            Some(job.status.as_str()),
            job.stdout.as_deref(),
            job.stderr.as_deref(),
            Some(job.started.as_str()),
            job.completed.as_deref(),
        ]
        .into_iter()
        .flatten()
        {
            py.admit(value)?;
        }
    }
    let mut out = String::new();
    match command {
        Command::Cancel(id) | Command::Status(id) | Command::Result(id) if jobs.is_empty() => {
            return Ok((
                out,
                format!("[mir_executor] job_id not found: {}\n", py.repr(id)),
                1,
            ));
        }
        Command::Cancel(id) => {
            out.push_str(&format!("[CANCEL] cancel_requested=True for job_id={id}\n"))
        }
        Command::Status(_) => {
            let job = jobs.first().ok_or(())?;
            out.push_str(&format!("[STATUS] job_id={}\n[STATUS] status={}\n[STATUS] change_id={} category={}\n[STATUS] family={} repo_root={}\n[STATUS] dispatch_brief_path={}\n[STATUS] allow_harness_self_modify={}\n[STATUS] resume_count={} last_resumed_at={}\n[STATUS] started_at={} completed_at={}\n[STATUS] cancel_requested={}\n", job.id, job.status, py.repr(&job.change), py.repr(&job.category), py.optional(job.family.as_deref()), py.repr(&job.root), py.optional(job.brief.as_deref()), boolean(job.allow), job.resumes, py.optional(job.resumed.as_deref()), job.started, job.completed.as_deref().unwrap_or("None"), boolean(job.cancel)));
            if let Some(reason) = blocked_reason(job)? {
                out.push_str(&format!("[STATUS] blocked_reason={reason}\n"));
            }
        }
        Command::Result(_) => {
            let job = jobs.first().ok_or(())?;
            if job.status == "running" {
                out.push_str(&format!(
                    "[RESULT] job_id={} status=running (not yet completed)\n",
                    job.id
                ));
            } else {
                let duration = job
                    .duration
                    .map(python_float)
                    .transpose()?
                    .unwrap_or_else(|| "None".to_owned());
                let exit = job
                    .exit
                    .map_or_else(|| "None".to_owned(), |e| e.to_string());
                out.push_str(&format!("[RESULT] job_id={}\n[RESULT] status={}\n[RESULT] exit_code={exit}\n[RESULT] dispatch_brief_path={}\n[RESULT] allow_harness_self_modify={}\n[RESULT] resume_count={} last_resumed_at={}\n[RESULT] duration_seconds={duration}\n", job.id, job.status, py.optional(job.brief.as_deref()), boolean(job.allow), job.resumes, py.optional(job.resumed.as_deref())));
                for (label, value) in [("STDOUT", &job.stdout), ("STDERR", &job.stderr)] {
                    if let Some(value) = value.as_ref().filter(|s| !s.is_empty()) {
                        out.push_str(&format!(
                            "[{label}] {}\n",
                            py.repr(&value.chars().take(500).collect::<String>())
                        ));
                    }
                }
            }
        }
        Command::List(status) => {
            if jobs.is_empty() {
                let filter = status
                    .as_ref()
                    .map_or_else(String::new, |s| format!(" (status={})", py.repr(s)));
                out.push_str(&format!("[LIST] no jobs found{filter}\n"));
            }
            for job in jobs {
                out.push_str(&format!("[JOB] job_id={} status={} change_id={} category={} dispatch_brief_path={} resume_count={} started_at={} blocked_reason={}\n", job.id, job.status, py.repr(&job.change), py.repr(&job.category), py.optional(job.brief.as_deref()), job.resumes, job.started, py.optional(blocked_reason(job)?)));
            }
        }
    }
    Ok((out, String::new(), 0))
}

fn run(args: &Args) -> Result<(String, String, i32)> {
    match std::env::var("PYTHONIOENCODING") {
        Ok(value) if !utf8_encoding(&value) => return Err(()),
        Err(std::env::VarError::NotUnicode(_)) => return Err(()),
        Ok(_) | Err(std::env::VarError::NotPresent) => {}
    }
    no_sidecars(&args.db)?;
    let py = PythonText::new()?;
    if safely_absent(&args.db)? {
        let answer = output(&args.command, &[], &py)?;
        handoff_packet::executor_protocol::claim();
        let _registry =
            handoff_packet::executor_registry::JobRegistry::open(&args.db).map_err(|_| ())?;
        return Ok(answer);
    }
    if !fs::symlink_metadata(&args.db)
        .map_err(|_| ())?
        .file_type()
        .is_file()
    {
        return Err(());
    }
    let mut header = [0; 100];
    fs::File::open(&args.db)
        .map_err(|_| ())?
        .read_exact(&mut header)
        .map_err(|_| ())?;
    if &header[..16] != b"SQLite format 3\0" || header[18] != 1 || header[19] != 1 {
        return Err(());
    }
    let db = Connection::open_with_flags(
        &args.db,
        OpenFlags::SQLITE_OPEN_READ_ONLY
            | OpenFlags::SQLITE_OPEN_NO_MUTEX
            | OpenFlags::SQLITE_OPEN_NOFOLLOW,
    )
    .map_err(|_| ())?;
    db.execute_batch("BEGIN").map_err(|_| ())?;
    let projection = check_schema(&db)?.join(",");
    let (sql, filter) = match &args.command {
        Command::Cancel(id) | Command::Status(id) | Command::Result(id) => {
            ("SELECT * FROM jobs WHERE job_id = ?", Some(id.as_str()))
        }
        Command::List(Some(status)) => (
            "SELECT * FROM jobs WHERE status = ? ORDER BY started_at DESC",
            Some(status.as_str()),
        ),
        Command::List(None) => ("SELECT * FROM jobs ORDER BY started_at DESC", None),
    };
    let sql = sql.replace("SELECT *", &format!("SELECT {projection}"));
    let mut stmt = db.prepare(&sql).map_err(|_| ())?;
    let mut rows = match filter {
        Some(filter) => stmt.query([filter]),
        None => stmt.query([]),
    }
    .map_err(|_| ())?;
    let mut jobs = Vec::new();
    while let Some(row) = rows.next().map_err(|_| ())? {
        jobs.push(read_job(row)?);
    }
    let output = output(&args.command, &jobs, &py)?;
    no_sidecars(&args.db)?;
    drop(rows);
    drop(stmt);
    drop(db);
    handoff_packet::executor_protocol::claim();
    let registry =
        handoff_packet::executor_registry::JobRegistry::open(&args.db).map_err(|_| ())?;
    if let Command::Cancel(id) = &args.command {
        // Use the write's row count, including when another writer changed the
        // row after the validation snapshot was released.
        if registry.cancel(id).map_err(|_| ())? {
            return Ok((
                format!("[CANCEL] cancel_requested=True for job_id={id}\n"),
                String::new(),
                0,
            ));
        }
        return self::output(&args.command, &[], &py);
    }
    Ok(output)
}

fn main() {
    let raw: Vec<OsString> = std::env::args_os().skip(1).collect();
    if raw.first().is_some_and(|value| value == "--home-root")
        && let Some(home) = raw.get(1)
    {
        let command = match raw.get(2).and_then(|s| s.to_str()) {
            Some("--jobs-db") => raw.get(4),
            Some(s) if s.starts_with("--jobs-db=") => raw.get(3),
            _ => raw.get(2),
        }
        .and_then(|s| s.to_str());
        if matches!(command, Some("execute" | "resume" | "sweep")) {
            let code = match std::env::current_dir() {
                Ok(cwd) => match command {
                    Some("execute") => {
                        handoff_packet::executor_execute::run(&raw[2..], &cwd, Path::new(home))
                    }
                    Some("resume") => {
                        handoff_packet::executor_resume_cli::run(&raw[2..], &cwd, Path::new(home))
                    }
                    Some("sweep") => {
                        handoff_packet::executor_sweep_cli::run(&raw[2..], &cwd, Path::new(home))
                    }
                    _ => 64,
                },
                Err(_) => 64,
            };
            std::process::exit(code);
        }
    }
    let result = std::env::current_dir()
        .map_err(|_| ())
        .and_then(|cwd| parse(std::env::args_os().skip(1), &cwd))
        .and_then(|args| run(&args));
    let code = match result {
        Ok((out, err, code)) => {
            handoff_packet::executor_protocol::claim();
            // Python's text streams translate every LF, including stored text.
            #[cfg(windows)]
            let (out, err) = (out.replace('\n', "\r\n"), err.replace('\n', "\r\n"));
            if io::stdout().lock().write_all(out.as_bytes()).is_err()
                || io::stderr().lock().write_all(err.as_bytes()).is_err()
            {
                64
            } else {
                code
            }
        }
        Err(()) => 64,
    };
    std::process::exit(code);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn python_text_quotes_unicode_and_controls() {
        let py = PythonText::new().unwrap();
        assert_eq!(py.repr("can't"), "\"can't\"");
        assert_eq!(
            py.repr("'\"\\\n\t\r\0\u{1b}\u{a0}\u{200b}\u{e000}\u{d55c}\u{ae00}😀"),
            "'\\'\"\\\\\\n\\t\\r\\x00\\x1b\\xa0\\u200b\\ue000\u{d55c}\u{ae00}😀'"
        );
    }

    #[test]
    fn python_unicode_version_uncertainty_requests_fallback() {
        let py = PythonText::new().unwrap();
        assert_eq!(py.admit("\u{d55c}\u{ae00}😀\u{0378}"), Ok(()));
        assert_eq!(py.admit("\u{1fae9}"), Err(()));
    }

    #[test]
    fn non_utf8_stream_overrides_request_fallback() {
        assert!(utf8_encoding("UTF-8:strict"));
        assert!(utf8_encoding("utf_8"));
        assert!(!utf8_encoding("ascii:backslashreplace"));
        assert!(!utf8_encoding("utf-8-sig"));
    }

    #[test]
    fn python_float_boundaries() {
        for (value, expected) in [
            (0.0, "0.0"),
            (-0.0, "-0.0"),
            (1e-4, "0.0001"),
            (1e-5, "1e-05"),
            (1e15, "1000000000000000.0"),
            (1e16, "1e+16"),
            (1.25, "1.25"),
            (1e100, "1e+100"),
        ] {
            assert_eq!(python_float(value).unwrap(), expected);
        }
    }

    #[test]
    fn blocked_reason_python_whitespace_and_malformed_marker() {
        assert_eq!(
            blocked(Some("prefix blocked_reason=\u{1c}wait next")).unwrap(),
            Some("wait")
        );
        assert_eq!(blocked(Some("blocked_reason=")), Err(()));
        assert_eq!(blocked(Some("other")).unwrap(), None);
    }
}
