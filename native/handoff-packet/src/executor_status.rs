//! Status, result, list-jobs and cancel share owned parsing, migration and text.
use handoff_packet::executor_registry::{Error as RegistryError, JobRegistry};
use rusqlite::types::{Value, ValueRef};
use std::{
    ffi::{OsStr, OsString},
    fs,
    io::{self, Write},
    path::{Path, PathBuf},
};

type Result<T> = std::result::Result<T, String>;
const PROG: &str = "python -m tools.mir_executor";
const USAGE: &str =
    "usage: python -m tools.mir_executor status --job-id JOB_ID [--repo-root PATH]\n";
const HELP: &str = "usage: python -m tools.mir_executor status [-h] --job-id JOB_ID\n                                           [--repo-root PATH]\n\noptions:\n  -h, --help        show this help message and exit\n  --job-id JOB_ID   UUID job_id returned by execute --background.\n  --repo-root PATH  Repository root path (for default jobs.db location).\n";
const GLOBAL_HELP: &str = "usage: python -m tools.mir_executor [-h] [--jobs-db PATH]\n                                    {execute,status,result,cancel,resume,list-jobs,sweep}\n                                    ...\n\nMir Executor — isolated delegated execution with optional TDD ledger update.\n\npositional arguments:\n  {execute,status,result,cancel,resume,list-jobs,sweep}\n    execute             Run a delegated command; ledger identity is optional\n                        in dispatch mode.\n    status              Print job status from the JobRegistry.\n    result              Print job result (exit_code, stdout, stderr, duration)\n                        from the JobRegistry.\n    cancel              Request cancellation of a background job.\n    resume              Resume a job from its persisted DispatchBrief and\n                        stored registry state.\n    list-jobs           List background jobs, optionally filtered by status.\n    sweep               Report advisory-overdue jobs and orphan dispatch\n                        worktrees.\n\noptions:\n  -h, --help            show this help message and exit\n  --jobs-db PATH        Override path to jobs.db (default:\n                        <repo_root>/tasks/jobs.db).\n";

fn codepoints(bytes: &[u8]) -> Vec<u32> {
    let mut out = Vec::new();
    let mut rest = bytes;
    loop {
        match std::str::from_utf8(rest) {
            Ok(text) => {
                out.extend(text.chars().map(u32::from));
                break;
            }
            Err(error) => {
                out.extend(
                    String::from_utf8_lossy(&rest[..error.valid_up_to()])
                        .chars()
                        .map(u32::from),
                );
                let count = error
                    .error_len()
                    .unwrap_or(rest.len() - error.valid_up_to());
                out.extend(
                    rest[error.valid_up_to()..error.valid_up_to() + count]
                        .iter()
                        .map(|b| 0xdc00 + u32::from(*b)),
                );
                rest = &rest[error.valid_up_to() + count..];
            }
        }
    }
    out
}
fn os_text(value: &OsStr) -> String {
    #[cfg(unix)]
    {
        use std::os::unix::ffi::OsStrExt;
        points_text(&codepoints(value.as_bytes()))
    }
    #[cfg(not(unix))]
    {
        value.to_string_lossy().into_owned()
    }
}
fn points_text(points: &[u32]) -> String {
    points
        .iter()
        .map(|&n| char::from_u32(n).map_or_else(|| format!("\\u{n:04x}"), |c| c.to_string()))
        .collect()
}
fn text_points(text: &str) -> Vec<u32> {
    text.chars().map(u32::from).collect()
}
fn os_points(value: &OsStr) -> Vec<u32> {
    #[cfg(unix)]
    {
        use std::os::unix::ffi::OsStrExt;
        codepoints(value.as_bytes())
    }
    #[cfg(not(unix))]
    {
        value.to_string_lossy().chars().map(u32::from).collect()
    }
}
fn repr_points(points: &[u32]) -> String {
    let mut encoded = String::from("\"");
    for &n in points {
        if let Some(c) = char::from_u32(n) {
            let escaped = serde_json::to_string(&c.to_string()).unwrap_or_else(|_| "\"\"".into());
            encoded.push_str(&escaped[1..escaped.len() - 1]);
        } else {
            encoded.push_str(&format!("\\u{n:04x}"));
        }
    }
    encoded.push('"');
    handoff_packet::python_json::parse(&encoded)
        .map(|v| v.repr())
        .unwrap_or(encoded)
}
fn repr(text: &str) -> String {
    repr_points(&text_points(text))
}
fn inline_value(arg: &OsStr) -> Option<OsString> {
    #[cfg(unix)]
    {
        use std::os::unix::ffi::{OsStrExt, OsStringExt};
        let raw = arg.as_bytes();
        raw.iter()
            .position(|&b| b == b'=')
            .map(|i| OsString::from_vec(raw[i + 1..].to_vec()))
    }
    #[cfg(not(unix))]
    {
        arg.to_str()?
            .split_once('=')
            .map(|(_, value)| OsString::from(value))
    }
}
fn option(arg: &str, name: &str) -> bool {
    arg.len() > 2 && arg.starts_with("--") && name.starts_with(arg)
}
fn jobs_option(arg: &OsStr) -> bool {
    option(os_text(arg).split('=').next().unwrap_or(""), "--jobs-db")
}

/// The first positional after the global database option selects the command.
pub fn owns(raw: &[OsString]) -> bool {
    requested(raw).is_some()
}
fn requested(raw: &[OsString]) -> Option<&'static str> {
    let mut index = 0;
    while index < raw.len() {
        if raw[index] == "status"
            || raw[index] == "result"
            || raw[index] == "list-jobs"
            || raw[index] == "cancel"
        {
            return Some(if raw[index] == "list-jobs" {
                "list-jobs"
            } else if raw[index] == "cancel" {
                "cancel"
            } else if raw[index] == "result" {
                "result"
            } else {
                "status"
            });
        }
        if jobs_option(&raw[index])
            || option(
                os_text(&raw[index]).split('=').next().unwrap_or(""),
                "--repo-root",
            )
        {
            index += if os_text(&raw[index]).contains('=') {
                1
            } else {
                2
            };
        } else if os_text(&raw[index]).starts_with('-') {
            index += 1;
        } else {
            return None;
        }
    }
    None
}
struct Args {
    result: bool,
    list: bool,
    cancel: bool,
    filter: Option<OsString>,
    db: PathBuf,
    root: PathBuf,
    job: OsString,
    help: bool,
    global_help: bool,
    global_final_error: bool,
    unknown: Vec<String>,
    final_error: Option<String>,
}
enum Parse {
    Args(Args),
    Error(String),
    RootError(String),
}
fn negative(text: &str) -> bool {
    // Python's regex $ also matches immediately before one final newline.
    let text = text.strip_suffix('\n').unwrap_or(text);
    regex::Regex::new(r"^-(\d+|\d*\.\d+)$").is_ok_and(|r| r.is_match(text))
}
fn is_value(text: &str) -> bool {
    !text.starts_with('-') || text == "-" || negative(text)
}
fn root_parse_error(raw: &[OsString]) -> Option<String> {
    let mut index = 0;
    while index < raw.len() {
        let arg = os_text(&raw[index]);
        if arg == "--" {
            break;
        }
        let (key, inline) = arg
            .split_once('=')
            .map_or((arg.as_str(), false), |(key, _)| (key, true));
        let name = ["--repo-root", "--jobs-db"]
            .into_iter()
            .find(|name| option(key, name));
        if let Some(name) = name
            && !inline
        {
            if !raw.get(index + 1).is_some_and(|v| is_value(&os_text(v))) {
                return Some(format!("argument {name}: expected one argument"));
            }
            index += 1;
        }
        index += 1;
    }
    None
}
fn parse(raw: &[OsString], cwd: &Path) -> Parse {
    let list_query = requested(raw) == Some("list-jobs");
    let mut db = None;
    let mut root = cwd.to_owned();
    let mut job = None;
    let mut command = false;
    let mut result = false;
    let mut list = false;
    let mut cancel = false;
    let mut filter = None;
    let mut unknown = Vec::new();
    let mut help = false;
    let mut global_help = false;
    let mut global_final_error = false;
    let mut global_ended = false;
    let mut ended = false;
    let mut final_error = None;
    let mut index = 0;
    while index < raw.len() {
        let arg = os_text(&raw[index]);
        if ended {
            unknown.push(arg);
            index += 1;
            continue;
        }
        if arg == "--" && (command || !global_ended) {
            if command {
                ended = true;
                unknown.push(arg);
            } else {
                global_ended = true;
            }
            index += 1;
            continue;
        }
        if !command && matches!(arg.as_str(), "status" | "result" | "list-jobs" | "cancel") {
            command = true;
            result = arg == "result";
            list = arg == "list-jobs";
            cancel = arg == "cancel";
            index += 1;
            continue;
        }
        let (key, inline) = arg
            .split_once('=')
            .map_or((arg.as_str(), None), |(k, v)| (k, Some(v)));
        let name = if !command && !global_ended && option(key, "--jobs-db") {
            Some("--jobs-db")
        } else if command && !list && option(key, "--job-id") {
            Some("--job-id")
        } else if command && list && option(key, "--status") {
            Some("--status")
        } else if command && option(key, "--repo-root") {
            Some("--repo-root")
        } else {
            None
        };
        if let Some(name) = name {
            let value = if inline.is_some() {
                inline_value(&raw[index]).unwrap_or_default()
            } else if raw.get(index + 1).is_some_and(|v| is_value(&os_text(v))) {
                index += 1;
                raw[index].clone()
            } else {
                return Parse::Error(format!("argument {name}: expected one argument"));
            };
            match name {
                "--jobs-db" => db = Some(PathBuf::from(value)),
                "--repo-root" => {
                    root = PathBuf::from(value);
                }
                "--job-id" => job = Some(value),
                "--status" => {
                    if !matches!(
                        value.to_str(),
                        Some("running" | "completed" | "cancelled" | "failed")
                    ) {
                        return Parse::Error(format!(
                            "argument --status: invalid choice: {} (choose from running, completed, cancelled, failed)",
                            repr_points(&os_points(&value))
                        ));
                    }
                    filter = Some(value);
                }
                _ => (),
            }
        } else if (command || !global_ended) && (key.starts_with("-h") || option(key, "--help")) {
            if let Some(value) = inline
                && (!list_query || !(help || global_help))
            {
                global_final_error = !command;
                final_error = Some(format!(
                    "argument -h/--help: ignored explicit argument {}",
                    repr(value)
                ));
            }
            if command {
                help = true;
            } else {
                global_help = true;
            }
        } else if !command && (global_ended || is_value(&arg) || arg.contains(' ')) {
            // argparse treats unknown options containing ASCII spaces as positionals.
            return Parse::RootError(format!(
                "argument subcommand: invalid choice: {} (choose from execute, status, result, cancel, resume, list-jobs, sweep)",
                repr(&arg)
            ));
        } else {
            unknown.push(arg);
        }
        index += 1;
    }
    let job = match job {
        Some(job) => job,
        None if list => OsString::new(),
        None => return Parse::Error("the following arguments are required: --job-id".into()),
    };
    let root = if root.is_absolute() {
        root
    } else {
        cwd.join(root)
    };
    let db = db.unwrap_or_else(|| root.join("tasks/jobs.db"));
    let db = if db.is_absolute() { db } else { cwd.join(db) };
    Parse::Args(Args {
        result,
        list,
        cancel,
        filter,
        db,
        root,
        job,
        help,
        global_help,
        global_final_error,
        unknown,
        final_error,
    })
}

fn resolve(path: &Path) -> Result<PathBuf> {
    enum Part {
        Component(OsString),
        LinkDone(PathBuf),
    }
    let mut output = PathBuf::new();
    let mut parts = path
        .components()
        .map(|c| Part::Component(c.as_os_str().to_owned()))
        .collect::<std::collections::VecDeque<_>>();
    let mut active = std::collections::HashSet::new();
    while let Some(part) = parts.pop_front() {
        let part = match part {
            Part::Component(part) => part,
            Part::LinkDone(link) => {
                active.remove(&link);
                continue;
            }
        };
        if part == ".." {
            output.pop();
            continue;
        }
        if part == "." {
            continue;
        }
        output.push(&part);
        match fs::read_link(&output) {
            Ok(target) => {
                let link = output.clone();
                if !active.insert(link.clone()) {
                    return Err(format!(
                        "RuntimeError: Symlink loop from {}",
                        repr_points(&os_points(output.as_os_str()))
                    ));
                }
                output.pop();
                if target.is_absolute() {
                    output.clear();
                }
                parts.push_front(Part::LinkDone(link));
                for part in target.components().rev() {
                    parts.push_front(Part::Component(part.as_os_str().to_owned()));
                }
            }
            Err(error)
                if matches!(
                    error.kind(),
                    io::ErrorKind::InvalidInput
                        | io::ErrorKind::NotFound
                        | io::ErrorKind::NotADirectory
                ) => {}
            Err(error) => return Err(io_error(error, &output)),
        }
    }
    Ok(handoff_packet::supply::plain(output))
}
fn io_error(error: io::Error, path: &Path) -> String {
    let kind = match error.kind() {
        io::ErrorKind::NotFound => "FileNotFoundError",
        io::ErrorKind::AlreadyExists => "FileExistsError",
        io::ErrorKind::PermissionDenied => "PermissionError",
        io::ErrorKind::NotADirectory => "NotADirectoryError",
        io::ErrorKind::IsADirectory => "IsADirectoryError",
        _ => "OSError",
    };
    let platform_message = handoff_packet::executor_brief_profile::python_os_error_text(&error);
    let message = match error.kind() {
        io::ErrorKind::NotFound => "No such file or directory",
        io::ErrorKind::AlreadyExists => "File exists",
        io::ErrorKind::PermissionDenied if error.raw_os_error() == Some(1) => {
            "Operation not permitted"
        }
        io::ErrorKind::PermissionDenied => "Permission denied",
        io::ErrorKind::NotADirectory => "Not a directory",
        io::ErrorKind::IsADirectory => "Is a directory",
        _ => &platform_message,
    };
    format!(
        "{kind}: [Errno {}] {message}: {}",
        error.raw_os_error().unwrap_or(22),
        repr_points(&os_points(path.as_os_str()))
    )
}
fn sql_error(error: rusqlite::Error) -> String {
    if let rusqlite::Error::SqlInputError { msg, .. } = error {
        return format!("sqlite3.OperationalError: {msg}");
    }
    if let rusqlite::Error::SqliteFailure(code, message) = error {
        let kind = match code.code {
            rusqlite::ErrorCode::DatabaseCorrupt | rusqlite::ErrorCode::NotADatabase => {
                "DatabaseError"
            }
            rusqlite::ErrorCode::ConstraintViolation => "IntegrityError",
            _ => "OperationalError",
        };
        format!(
            "sqlite3.{kind}: {}",
            message.unwrap_or_else(|| code.to_string())
        )
    } else {
        format!("sqlite3.OperationalError: {error}")
    }
}
fn registry_error(error: RegistryError, path: &Path) -> String {
    match error {
        RegistryError::Io(error) => {
            let target = if error.kind() == io::ErrorKind::AlreadyExists {
                path.parent().unwrap_or(path)
            } else {
                path
            };
            io_error(error, target)
        }
        RegistryError::Sql(error) => sql_error(error),
        RegistryError::Shape => format!(
            "ValueError: jobs database must be a regular file: {}",
            os_text(path.as_os_str())
        ),
        RegistryError::Text(error) => format!("ValueError: {error:?}"),
    }
}
fn value_type(value: &Value) -> &'static str {
    match value {
        Value::Null => "NoneType",
        Value::Integer(_) => "int",
        Value::Real(_) => "float",
        Value::Text(_) => "str",
        Value::Blob(_) => "bytes",
    }
}
fn bytes_repr(bytes: &[u8]) -> String {
    let quote = if bytes.contains(&39) && !bytes.contains(&34) {
        '\"'
    } else {
        '\''
    };
    let mut out = format!("b{quote}");
    for &byte in bytes {
        match byte {
            b'\\' => out.push_str("\\\\"),
            b'\n' => out.push_str("\\n"),
            b'\r' => out.push_str("\\r"),
            b'\t' => out.push_str("\\t"),
            b if b == quote as u8 => {
                out.push('\\');
                out.push(quote);
            }
            32..=126 => out.push(char::from(byte)),
            b => out.push_str(&format!("\\x{b:02x}")),
        }
    }
    out.push(quote);
    out
}
fn display(value: &Value, quoted: bool) -> Result<String> {
    Ok(match value {
        Value::Null => "None".into(),
        Value::Text(s) if quoted => repr(s),
        Value::Text(s) => s.clone(),
        Value::Blob(bytes) => bytes_repr(bytes),
        Value::Integer(n) => n.to_string(),
        Value::Real(n) if n.is_nan() => "nan".into(),
        Value::Real(n) if n.is_infinite() => {
            if n.is_sign_positive() {
                "inf".into()
            } else {
                "-inf".into()
            }
        }
        Value::Real(n) => handoff_packet::mir_core::canonical::python_float(*n)
            .map_err(|_| "ValueError: invalid float".to_owned())?,
    })
}
fn truth(value: &Value) -> bool {
    match value {
        Value::Null => false,
        Value::Integer(n) => *n != 0,
        Value::Real(n) => *n != 0.,
        Value::Text(s) => !s.is_empty(),
        Value::Blob(s) => !s.is_empty(),
    }
}
fn boolean(value: &Value) -> &'static str {
    if truth(value) { "True" } else { "False" }
}

fn unicode_decode(bytes: &[u8], encoding: &str, start: usize, end: usize, reason: &str) -> String {
    let position = if end > start + 1 {
        format!("bytes in position {start}-{}", end - 1)
    } else {
        format!(
            "byte 0x{:02x} in position {start}",
            bytes.get(start).copied().unwrap_or(0)
        )
    };
    format!("UnicodeDecodeError: '{encoding}' codec can't decode {position}: {reason}")
}
fn json_bytes(bytes: &[u8]) -> Result<Vec<u32>> {
    let (encoding, width, big, skip) = if bytes.starts_with(&[0, 0, 0xfe, 0xff]) {
        ("utf-32-be", 4, true, 4)
    } else if bytes.starts_with(&[0xff, 0xfe, 0, 0]) {
        ("utf-32-le", 4, false, 4)
    } else if bytes.starts_with(&[0xfe, 0xff]) {
        ("utf-16-be", 2, true, 2)
    } else if bytes.starts_with(&[0xff, 0xfe]) {
        ("utf-16-le", 2, false, 2)
    } else if bytes.len() >= 4 && bytes[0] == 0 && bytes[1] == 0 {
        ("utf-32-be", 4, true, 0)
    } else if bytes.len() >= 4 && bytes[1] == 0 && bytes[2] == 0 && bytes[3] == 0 {
        ("utf-32-le", 4, false, 0)
    } else if bytes.len() >= 2 && bytes[0] == 0 {
        ("utf-16-be", 2, true, 0)
    } else if bytes.len() >= 2 && bytes[1] == 0 {
        ("utf-16-le", 2, false, 0)
    } else {
        (
            "utf-8",
            1,
            false,
            usize::from(bytes.starts_with(&[0xef, 0xbb, 0xbf])) * 3,
        )
    };
    let original = bytes;
    let bytes = &bytes[skip..];
    if width == 1 {
        let mut out = Vec::new();
        let mut offset = 0;
        while offset < bytes.len() {
            match std::str::from_utf8(&bytes[offset..]) {
                Ok(text) => {
                    out.extend(text.chars().map(u32::from));
                    break;
                }
                Err(error) => {
                    if let Ok(text) =
                        std::str::from_utf8(&bytes[offset..offset + error.valid_up_to()])
                    {
                        out.extend(text.chars().map(u32::from));
                    }
                    offset += error.valid_up_to();
                    if bytes.get(offset) == Some(&0xed)
                        && bytes
                            .get(offset + 1)
                            .is_some_and(|b| (0xa0..=0xbf).contains(b))
                        && bytes
                            .get(offset + 2)
                            .is_some_and(|b| (0x80..=0xbf).contains(b))
                    {
                        out.push(
                            0xd000
                                + (u32::from(bytes[offset + 1] & 63) << 6)
                                + u32::from(bytes[offset + 2] & 63),
                        );
                        offset += 3;
                    } else {
                        // Python's utf-8-sig decoder adds this final exception
                        // note, which owns COMMON's last-line error protocol.
                        return Err(if skip == 3 {
                            "decoding with 'utf-8-sig' codec failed".into()
                        } else {
                            unicode_decode(
                                bytes,
                                encoding,
                                offset,
                                offset + error.error_len().unwrap_or(bytes.len() - offset),
                                if error.error_len().is_none() {
                                    "unexpected end of data"
                                } else if (0xc2..=0xf4).contains(&bytes[offset]) {
                                    "invalid continuation byte"
                                } else {
                                    "invalid start byte"
                                },
                            )
                        });
                    }
                }
            }
        }
        return Ok(out);
    }
    let mut units = Vec::new();
    for (index, part) in bytes.chunks(width).enumerate() {
        if part.len() != width {
            return Err(unicode_decode(
                original,
                encoding,
                skip + index * width,
                original.len(),
                "truncated data",
            ));
        }
        let n = if big {
            part.iter().fold(0u32, |n, b| (n << 8) + u32::from(*b))
        } else {
            part.iter()
                .rev()
                .fold(0u32, |n, b| (n << 8) + u32::from(*b))
        };
        if n > 0x10ffff {
            return Err(unicode_decode(
                original,
                encoding,
                skip + index * width,
                skip + index * width + width,
                "code point not in range(0x110000)",
            ));
        }
        units.push(n);
    }
    if width == 4 {
        return Ok(units);
    }
    let mut out = Vec::new();
    let mut index = 0;
    while index < units.len() {
        let n = units[index];
        if (0xd800..=0xdbff).contains(&n)
            && units
                .get(index + 1)
                .is_some_and(|n| (0xdc00..=0xdfff).contains(n))
        {
            out.push(0x10000 + (n - 0xd800) * 0x400 + (units[index + 1] - 0xdc00));
            index += 2;
        } else {
            out.push(n);
            index += 1;
        }
    }
    Ok(out)
}

fn validate_json(value: &Value) -> Result<()> {
    let points = match value {
        Value::Text(text) => text.chars().map(u32::from).collect::<Vec<_>>(),
        Value::Blob(bytes) => json_bytes(bytes)?,
        value => {
            return Err(format!(
                "TypeError: the JSON object must be str, bytes or bytearray, not {}",
                value_type(value)
            ));
        }
    };
    handoff_packet::python_json::parse_codepoints(points)
        .map(|_| ())
        .map_err(|error| {
            let kind = if error.exception == "JSONDecodeError" {
                "json.decoder.JSONDecodeError"
            } else {
                error.exception
            };
            format!("{kind}: {error}")
        })
}
fn blocked(value: &Value) -> Result<Option<String>> {
    if !truth(value) {
        return Ok(None);
    }
    let text = match value {
        Value::Text(text) => text,
        Value::Blob(_) => {
            return Err("TypeError: a bytes-like object is required, not 'str'".into());
        }
        v => {
            return Err(format!(
                "TypeError: argument of type '{}' is not iterable",
                value_type(v)
            ));
        }
    };
    let Some((_, rest)) = text.split_once("blocked_reason=") else {
        return Ok(None);
    };
    let word = rest
        .split(|c: char| c.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&c))
        .find(|s| !s.is_empty())
        .ok_or("IndexError: list index out of range")?;
    Ok(Some(word.to_owned()))
}
fn status(args: &Args) -> Result<(Vec<String>, String, i32)> {
    let db = resolve(&args.db)?;
    let registry = JobRegistry::open(&db).map_err(|e| registry_error(e, &db))?;
    let connection = registry.connection();
    if args.list {
        let sql = if args.filter.is_some() {
            "SELECT * FROM jobs WHERE status = ? ORDER BY started_at DESC"
        } else {
            "SELECT * FROM jobs ORDER BY started_at DESC"
        };
        let mut statement = connection.prepare(sql).map_err(sql_error)?;
        let names = statement
            .column_names()
            .into_iter()
            .map(str::to_owned)
            .collect::<Vec<_>>();
        let mut rows = if let Some(filter) = &args.filter {
            statement.query([os_text(filter)]).map_err(sql_error)?
        } else {
            statement.query([]).map_err(sql_error)?
        };
        let mut records = Vec::new();
        while let Some(row) = rows.next().map_err(sql_error)? {
            records.push(read_values(row, &names, true)?);
        }
        for record in &records {
            validate_record(&names, record, true)?;
        }
        if records.is_empty() {
            let filter = args
                .filter
                .as_ref()
                .map_or_else(String::new, |f| format!(" (status={})", repr(&os_text(f))));
            return Ok((
                vec![format!("[LIST] no jobs found{filter}\n")],
                String::new(),
                0,
            ));
        }
        let mut out = Vec::new();
        for record in &records {
            let (frames, _, _) = render_record(args, &names, record)?;
            out.extend(frames);
        }
        return Ok((out, String::new(), 0));
    }
    let mut statement = connection
        .prepare(if args.cancel {
            "UPDATE jobs SET cancel_requested = 1 WHERE job_id = ?"
        } else {
            "SELECT * FROM jobs WHERE job_id = ?"
        })
        .map_err(sql_error)?;
    let job = os_text(&args.job);
    if os_points(&args.job)
        .iter()
        .any(|n| (0xd800..=0xdfff).contains(n))
    {
        let points = os_points(&args.job);
        let start = points
            .iter()
            .position(|n| (0xd800..=0xdfff).contains(n))
            .unwrap_or(0);
        let end = start
            + points[start..]
                .iter()
                .take_while(|n| (0xd800..=0xdfff).contains(*n))
                .count();
        return Err(encode_error(
            "utf-8",
            &points,
            start,
            end,
            "surrogates not allowed",
        ));
    }
    if args.cancel {
        // The reference uses UPDATE rowcount without decoding any stored row.
        // It neither signals a process nor changes timestamps, status or receipts.
        let found = registry.cancel(&job).map_err(|e| registry_error(e, &db))?;
        return Ok(if found {
            (
                vec![format!("[CANCEL] cancel_requested=True for job_id={job}\n")],
                String::new(),
                0,
            )
        } else {
            (
                Vec::new(),
                format!("[mir_executor] job_id not found: {}\n", repr(&job)),
                1,
            )
        });
    }
    let names = statement
        .column_names()
        .into_iter()
        .map(str::to_owned)
        .collect::<Vec<_>>();
    let mut rows = statement.query([&job]).map_err(sql_error)?;
    let Some(row) = rows.next().map_err(sql_error)? else {
        return Ok((
            Vec::new(),
            format!("[mir_executor] job_id not found: {}\n", repr(&job)),
            1,
        ));
    };
    let values = read_values(row, &names, false)?;
    validate_record(&names, &values, false)?;
    render_record(args, &names, &values)
}
fn read_values(row: &rusqlite::Row<'_>, names: &[String], list: bool) -> Result<Vec<Value>> {
    let mut values = Vec::new();
    for (index, name) in names.iter().enumerate() {
        let value=match row.get_ref(index).map_err(sql_error)? {
            ValueRef::Null => Value::Null, ValueRef::Integer(n) => Value::Integer(n), ValueRef::Real(n) => Value::Real(n), ValueRef::Blob(bytes) => Value::Blob(bytes.to_vec()),
            ValueRef::Text(bytes) => Value::Text(std::str::from_utf8(bytes).map_err(|_| {
                let text = if list { bytes.split(|b| *b == 0).next().unwrap_or(bytes) } else { bytes };
                format!("sqlite3.OperationalError: Could not decode to UTF-8 column '{}' with text {}",name,repr(&String::from_utf8_lossy(text)))
            })?.to_owned()),
        };
        values.push(value);
    }
    Ok(values)
}
fn get_value<'a>(
    names: &[String],
    values: &'a [Value],
    name: &str,
    list: bool,
) -> Result<&'a Value> {
    names
        .iter()
        .position(|n| n == name || (list && n.eq_ignore_ascii_case(name)))
        .map(|i| &values[i])
        .ok_or_else(|| "IndexError: No item with that key".to_owned())
}
fn validate_record(names: &[String], values: &[Value], list: bool) -> Result<()> {
    let get = |name: &str| get_value(names, values, name, list);
    // _row_to_record eagerly decodes both JSON fields, even though status does
    // not display them. Other dynamically typed columns remain Python values.
    for name in ["job_id", "change_id", "category", "family", "repo_root"] {
        get(name)?;
    }
    validate_json(get("codex_args")?)?;
    let ai = get("ai_run_metadata")?;
    if !matches!(ai, Value::Null) {
        validate_json(ai)?;
    }
    for name in [
        "timeout_seconds",
        "status",
        "exit_code",
        "stdout",
        "stderr",
        "duration_seconds",
        "started_at",
        "completed_at",
        "cancel_requested",
    ] {
        get(name)?;
    }
    Ok(())
}
fn render_record(
    args: &Args,
    names: &[String],
    values: &[Value],
) -> Result<(Vec<String>, String, i32)> {
    let get = |name: &str| get_value(names, values, name, args.list);
    if args.list {
        let reason = match blocked(get("stdout")?)? {
            Some(reason) => Some(reason),
            None => blocked(get("stderr")?)?,
        };
        return Ok((
            vec![format!(
                "[JOB] job_id={} status={} change_id={} category={} dispatch_brief_path={} resume_count={} started_at={} blocked_reason={}\n",
                display(get("job_id")?, false)?,
                display(get("status")?, false)?,
                display(get("change_id")?, true)?,
                display(get("category")?, true)?,
                display(get("dispatch_brief_path")?, true)?,
                display(get("resume_count")?, false)?,
                display(get("started_at")?, false)?,
                reason.map_or_else(|| "None".into(), |s| repr(&s)),
            )],
            String::new(),
            0,
        ));
    }
    if args.result {
        if get("status")? == &Value::Text("running".into()) {
            return Ok((
                vec![format!(
                    "[RESULT] job_id={} status=running (not yet completed)\n",
                    display(get("job_id")?, false)?
                )],
                String::new(),
                0,
            ));
        }
        let mut out = vec![
            format!("[RESULT] job_id={}\n", display(get("job_id")?, false)?),
            format!("[RESULT] status={}\n", display(get("status")?, false)?),
            format!(
                "[RESULT] exit_code={}\n",
                display(get("exit_code")?, false)?
            ),
            format!(
                "[RESULT] dispatch_brief_path={}\n",
                display(get("dispatch_brief_path")?, true)?
            ),
            format!(
                "[RESULT] allow_harness_self_modify={}\n",
                boolean(get("allow_harness_self_modify")?)
            ),
            format!(
                "[RESULT] resume_count={} last_resumed_at={}\n",
                display(get("resume_count")?, false)?,
                display(get("last_resumed_at")?, true)?
            ),
            format!(
                "[RESULT] duration_seconds={}\n",
                display(get("duration_seconds")?, false)?
            ),
        ];
        for (column, label) in [("stdout", "STDOUT"), ("stderr", "STDERR")] {
            let value = get(column)?;
            if truth(value) {
                let sliced = match value {
                    Value::Text(text) => Value::Text(text.chars().take(500).collect()),
                    Value::Blob(bytes) => Value::Blob(bytes.iter().take(500).copied().collect()),
                    _ => {
                        return Err(format!(
                            "TypeError: '{}' object is not subscriptable",
                            value_type(value)
                        ));
                    }
                };
                out.push(format!("[{label}] {}\n", display(&sliced, true)?));
            }
        }
        return Ok((out, String::new(), 0));
    }
    let mut out = vec![
        format!("[STATUS] job_id={}\n", display(get("job_id")?, false)?),
        format!("[STATUS] status={}\n", display(get("status")?, false)?),
        format!(
            "[STATUS] change_id={} category={}\n",
            display(get("change_id")?, true)?,
            display(get("category")?, true)?
        ),
        format!(
            "[STATUS] family={} repo_root={}\n",
            display(get("family")?, true)?,
            display(get("repo_root")?, true)?
        ),
        format!(
            "[STATUS] dispatch_brief_path={}\n",
            display(get("dispatch_brief_path")?, true)?
        ),
        format!(
            "[STATUS] allow_harness_self_modify={}\n",
            boolean(get("allow_harness_self_modify")?)
        ),
        format!(
            "[STATUS] resume_count={} last_resumed_at={}\n",
            display(get("resume_count")?, false)?,
            display(get("last_resumed_at")?, true)?
        ),
        format!(
            "[STATUS] started_at={} completed_at={}\n",
            display(get("started_at")?, false)?,
            display(get("completed_at")?, false)?
        ),
        format!(
            "[STATUS] cancel_requested={}\n",
            boolean(get("cancel_requested")?)
        ),
    ];
    let reason = match blocked(get("stdout")?)? {
        Some(reason) => Some(reason),
        None => blocked(get("stderr")?)?,
    };
    if let Some(reason) = reason {
        out.push(format!("[STATUS] blocked_reason={reason}\n"));
    }
    Ok((out, String::new(), 0))
}

fn encode_error(encoding: &str, points: &[u32], start: usize, end: usize, reason: &str) -> String {
    let subject = if end > start + 1 {
        format!("characters in position {start}-{}", end - 1)
    } else {
        format!(
            "character {} in position {start}",
            ascii_repr(&points[start..end])
        )
    };
    format!("UnicodeEncodeError: '{encoding}' codec can't encode {subject}: {reason}")
}
fn ascii_repr(points: &[u32]) -> String {
    let mut out = String::from("'");
    for &n in points {
        if n >= 128 {
            out.push_str(&escaped(n));
        } else if let Some(c) = char::from_u32(n) {
            out.push(c);
        }
    }
    out.push('\'');
    out
}
fn escaped(n: u32) -> String {
    if n <= 0xff {
        format!("\\x{n:02x}")
    } else if n <= 0xffff {
        format!("\\u{n:04x}")
    } else {
        format!("\\U{n:08x}")
    }
}
fn encode(text: &str, error: bool, bom: bool) -> Result<Vec<u8>> {
    if text.is_empty() {
        return Ok(Vec::new());
    }
    let setting = std::env::var_os("PYTHONIOENCODING")
        .map(|s| os_text(&s))
        .unwrap_or_default();
    let (default_encoding, default_handler) =
        setting.split_once(':').unwrap_or((&setting, "strict"));
    let prefix = if error {
        "MIR_EXECUTOR_STDERR"
    } else {
        "MIR_EXECUTOR_STDOUT"
    };
    let encoding_override = std::env::var(format!("{prefix}_ENCODING")).ok();
    let errors_override = std::env::var(format!("{prefix}_ERRORS")).ok();
    let encoding = encoding_override.as_deref().unwrap_or(default_encoding);
    let handler = errors_override.as_deref().unwrap_or(default_handler);
    let normalized = encoding.to_ascii_lowercase().replace(['-', ' ', '_'], "");
    let name = match normalized.as_str() {
        "" | "utf8" | "u8" | "utf" | "utf8sig" => "utf-8",
        "ascii" | "usascii" | "646" | "ansix3.41968" => "ascii",
        "latin1" | "latin" | "iso88591" | "isoir100" | "l1" => "latin-1",
        "cp1252" | "windows1252" => "charmap",
        "utf16" | "utf16le" => "utf-16-le",
        "utf16be" => "utf-16-be",
        "utf32" | "utf32le" => "utf-32-le",
        "utf32be" => "utf-32-be",
        _ => return Err(format!("LookupError: unknown encoding: {encoding}")),
    };
    let handler = if error && errors_override.is_none() {
        "backslashreplace"
    } else if handler.is_empty() {
        "strict"
    } else {
        handler
    };
    let mut out = Vec::new();
    if bom && normalized == "utf8sig" {
        out.extend([0xef, 0xbb, 0xbf]);
    }
    if bom && normalized == "utf16" {
        out.extend([0xff, 0xfe]);
    }
    if bom && normalized == "utf32" {
        out.extend([0xff, 0xfe, 0, 0]);
    }
    {
        let points = text_points(text);
        let mut index = 0;
        while index < points.len() {
            let n = points[index];
            let surrogate = (0xd800..=0xdfff).contains(&n);
            let cp1252 = [
                0x20ac, 0x81, 0x201a, 0x192, 0x201e, 0x2026, 0x2020, 0x2021, 0x2c6, 0x2030, 0x160,
                0x2039, 0x152, 0x8d, 0x17d, 0x8f, 0x90, 0x2018, 0x2019, 0x201c, 0x201d, 0x2022,
                0x2013, 0x2014, 0x2dc, 0x2122, 0x161, 0x203a, 0x153, 0x9d, 0x17e, 0x178,
            ];
            let byte = if name == "charmap" && (128..160).contains(&n) {
                None
            } else if name == "charmap" && n > 255 {
                cp1252.iter().position(|&x| x == n).map(|i| 128 + i as u8)
            } else if n <= 255 {
                Some(n as u8)
            } else {
                None
            };
            let invalid = match name {
                "ascii" => n > 127,
                "latin-1" => n > 255,
                "charmap" => byte.is_none(),
                _ => surrogate && handler != "surrogatepass",
            };
            if invalid {
                let replacement = match handler {
                    "ignore" => String::new(),
                    "replace" => {
                        if name.starts_with("utf") {
                            "\u{fffd}".into()
                        } else {
                            "?".into()
                        }
                    }
                    "backslashreplace" => escaped(n),
                    "xmlcharrefreplace" => format!("&#{n};"),
                    "surrogateescape" if (0xdc80..=0xdcff).contains(&n) => {
                        out.push((n - 0xdc00) as u8);
                        index += 1;
                        continue;
                    }
                    "strict" | "surrogateescape" | "surrogatepass" => {
                        let mut end = index + 1;
                        while end < points.len()
                            && match name {
                                "ascii" => points[end] > 127,
                                "latin-1" => points[end] > 255,
                                "charmap" => {
                                    !(points[end] <= 127
                                        || (160..=255).contains(&points[end])
                                        || (points[end] > 255 && cp1252.contains(&points[end])))
                                }
                                _ => (0xd800..=0xdfff).contains(&points[end]),
                            }
                        {
                            end += 1;
                        }
                        return Err(encode_error(
                            name,
                            &points,
                            index,
                            end,
                            if name == "ascii" {
                                "ordinal not in range(128)"
                            } else if name == "latin-1" {
                                "ordinal not in range(256)"
                            } else if name == "charmap" {
                                "character maps to <undefined>"
                            } else {
                                "surrogates not allowed"
                            },
                        ));
                    }
                    _ => {
                        return Err(format!(
                            "LookupError: unknown error handler name '{}'",
                            handler
                        ));
                    }
                };
                if name.starts_with("utf-16") {
                    for u in replacement.encode_utf16() {
                        out.extend(if name.ends_with("be") {
                            u.to_be_bytes()
                        } else {
                            u.to_le_bytes()
                        });
                    }
                } else if name.starts_with("utf-32") {
                    for c in replacement.chars() {
                        out.extend(if name.ends_with("be") {
                            u32::from(c).to_be_bytes()
                        } else {
                            u32::from(c).to_le_bytes()
                        });
                    }
                } else {
                    out.extend(replacement.as_bytes());
                }
            } else if name.starts_with("utf-16") {
                if n <= 0xffff {
                    let u = n as u16;
                    out.extend(if name.ends_with("be") {
                        u.to_be_bytes()
                    } else {
                        u.to_le_bytes()
                    });
                } else {
                    for u in [
                        0xd800 + ((n - 0x10000) >> 10) as u16,
                        0xdc00 + ((n - 0x10000) & 0x3ff) as u16,
                    ] {
                        out.extend(if name.ends_with("be") {
                            u.to_be_bytes()
                        } else {
                            u.to_le_bytes()
                        });
                    }
                }
            } else if name.starts_with("utf-32") {
                out.extend(if name.ends_with("be") {
                    n.to_be_bytes()
                } else {
                    n.to_le_bytes()
                });
            } else if name == "utf-8" {
                if let Some(c) = char::from_u32(n) {
                    out.extend(c.encode_utf8(&mut [0; 4]).as_bytes());
                } else {
                    out.extend([
                        0xe0 | ((n >> 12) as u8),
                        0x80 | (((n >> 6) & 63) as u8),
                        0x80 | ((n & 63) as u8),
                    ]);
                }
            } else if let Some(b) = byte {
                out.push(b);
            }
            index += 1;
        }
    }
    Ok(out)
}
fn emit(out: String, err: String, code: i32) -> i32 {
    emit_frames(vec![out], err, code)
}
pub fn cwd_failure(error: io::Error) -> i32 {
    let error = io_error(error, Path::new(""));
    emit(
        String::new(),
        format!("{}\n", error.strip_suffix(": ''").unwrap_or(&error)),
        1,
    )
}
fn emit_frames(out: Vec<String>, err: String, code: i32) -> i32 {
    #[cfg(windows)]
    let (out, err) = (
        out.into_iter()
            .map(|frame| frame.replace('\n', "\r\n"))
            .collect::<Vec<_>>(),
        err.replace('\n', "\r\n"),
    );
    let encoded = out
        .iter()
        .enumerate()
        .try_fold(Vec::new(), |mut bytes, (index, frame)| {
            bytes.extend(encode(frame, false, index == 0)?);
            Ok::<_, String>(bytes)
        });
    let (out, err, code) =
        match encoded.and_then(|out| encode(&err, true, true).map(|err| (out, err))) {
            Ok((out, err)) => (out, err, code),
            Err(error) => (
                Vec::new(),
                encode(&format!("{error}\n"), true, true)
                    .unwrap_or_else(|_| format!("{error}\n").into_bytes()),
                1,
            ),
        };
    if io::stdout().lock().write_all(&out).is_err() || io::stderr().lock().write_all(&err).is_err()
    {
        1
    } else {
        code
    }
}
pub fn run(raw: &[OsString], cwd: &Path, home: &Path) -> i32 {
    let command = requested(raw).unwrap_or("status");
    let usage = if command == "list-jobs" {
        format!(
            "usage: {PROG} list-jobs [--status STATUS]\n                                              [--repo-root PATH]\n"
        )
    } else {
        USAGE.replace(" status", &format!(" {command}"))
    };
    let help = if command == "list-jobs" {
        format!(
            "usage: {PROG} list-jobs [-h] [--status STATUS]\n                                              [--repo-root PATH]\n\noptions:\n  -h, --help        show this help message and exit\n  --status STATUS   Filter by status: running / completed / cancelled /\n                    failed.\n  --repo-root PATH  Repository root path (for default jobs.db location).\n"
        )
    } else {
        HELP.replace(" status", &format!(" {command}"))
    };
    // The facade owns the approved legacy compatibility decline. Direct native
    // callers cannot import hooks or start a bridge as a second execution route.
    let disabled = match handoff_packet::executor_local::python_local_hooks_disabled(home) {
        Ok(disabled) => disabled,
        Err(error) => return emit(String::new(), format!("[mir_executor] {error}\n"), 1),
    };
    if home.join("tools/mir_executor/local.py").exists() && !disabled {
        return emit(
            String::new(),
            format!("[mir_executor] legacy {command} hooks require the Python facade\n"),
            2,
        );
    }
    if let Some(error) = root_parse_error(raw) {
        let prog = std::env::var("MIR_EXECUTOR_ARGPARSE_PROG").unwrap_or_else(|_| "-c".into());
        return emit(
            String::new(),
            format!(
                "usage: {prog} [--repo-root REPO_ROOT] [--jobs-db JOBS_DB] [subcommand]\n{prog}: error: {error}\n"
            ),
            2,
        );
    }
    let args = match parse(raw, cwd) {
        Parse::Args(args) => args,
        Parse::Error(error) => {
            return emit(
                String::new(),
                format!("{usage}{PROG} {command}: error: {error}\n"),
                2,
            );
        }
        Parse::RootError(error) => {
            return emit(
                String::new(),
                format!(
                    "usage: {PROG} [--jobs-db PATH]\n                                    {{execute,status,result,cancel,resume,list-jobs,sweep}}\n                                    ...\n{PROG}: error: {error}\n"
                ),
                2,
            );
        }
    };
    let root = match resolve(&args.root) {
        Ok(root) => root,
        Err(error) => return emit(String::new(), format!("{error}\n"), 1),
    };
    if let Err(error) = handoff_packet::executor_local::python_local_hooks_disabled(&root) {
        return emit(String::new(), format!("[mir_executor] {error}\n"), 1);
    }
    // The final parser stops before the second authorization on help or error.
    let passes = if args.help
        || args.global_help
        || args.final_error.is_some()
        || !args.unknown.is_empty()
    {
        1
    } else {
        2
    };
    let mut native_configuration_error = None;
    if root != home
        && let Err(error) = handoff_packet::executor_admission::authorize_command(
            home, cwd, &root, None, true, passes,
        )
    {
        if error
            .windows(b"native local policy configuration error:".len())
            .any(|part| part == b"native local policy configuration error:")
        {
            native_configuration_error = Some(error);
        } else {
            return emit(
                String::new(),
                String::from_utf8_lossy(&error).into_owned(),
                1,
            );
        }
    }
    if let Some(error) = &args.final_error {
        return emit(
            String::new(),
            if args.global_final_error {
                format!(
                    "usage: {PROG} [-h] [--jobs-db PATH]\n                                    {{execute,status,result,cancel,resume,list-jobs,sweep}}\n                                    ...\n{PROG}: error: {error}\n"
                )
            } else {
                format!(
                    "{help_usage}{PROG} {command}: error: {error}\n",
                    help_usage = help.split("\n\n").next().unwrap_or("").to_owned() + "\n"
                )
            },
            2,
        );
    }
    if args.global_help {
        return emit(GLOBAL_HELP.into(), String::new(), 0);
    }
    if args.help {
        return emit(help, String::new(), 0);
    }
    if !args.unknown.is_empty() {
        return emit(
            String::new(),
            format!(
                "usage: {PROG} [-h] [--jobs-db PATH]\n                                    {{execute,status,result,cancel,resume,list-jobs,sweep}}\n                                    ...\n{PROG}: error: unrecognized arguments: {}\n",
                args.unknown.join(" ")
            ),
            2,
        );
    }
    if let Some(error) = native_configuration_error {
        return emit(
            String::new(),
            String::from_utf8_lossy(&error).into_owned(),
            1,
        );
    }
    match status(&args) {
        Ok((out, err, code)) => emit_frames(out, err, code),
        Err(error) => emit(String::new(), format!("{error}\n"), 1),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[cfg(target_os = "macos")]
    #[test]
    fn io_error_preserves_filesystem_exception_classes() {
        for (errno, class) in [
            (92, "OSError"),
            (22, "OSError"),
            (63, "OSError"),
            (62, "OSError"),
            (30, "OSError"),
            (28, "OSError"),
            (13, "PermissionError"),
            (1, "PermissionError"),
            (2, "FileNotFoundError"),
            (17, "FileExistsError"),
            (20, "NotADirectoryError"),
            (21, "IsADirectoryError"),
        ] {
            let error = io_error(
                io::Error::from_raw_os_error(errno),
                Path::new("/tasks/jobs.db"),
            );
            assert!(
                error.starts_with(&format!("{class}: [Errno {errno}] ")),
                "{error}"
            );
        }
    }

    #[test]
    fn io_error_preserves_unmapped_errno_text() {
        for errno in [92, 63] {
            let error = io::Error::from_raw_os_error(errno);
            let display = error.to_string();
            let message = display.rsplit_once(" (os error ").unwrap().0;
            #[cfg(target_os = "macos")]
            assert_eq!(
                message,
                if errno == 92 {
                    "Illegal byte sequence"
                } else {
                    "File name too long"
                }
            );
            assert_eq!(
                io_error(error, Path::new("/tasks/jobs.db")),
                format!("OSError: [Errno {errno}] {message}: '/tasks/jobs.db'")
            );
        }
    }
}
