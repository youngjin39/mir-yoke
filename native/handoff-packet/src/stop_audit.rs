//! Yoke's own audit-only Stop/StopFailure paths. Callers remain on the shell hooks.
//! CPython exception strings are retired: invalid JSON records `invalid JSON`;
//! non-object JSON creates the sessions directory but writes no log or traceback.
//! Review is an opt-in, separate `mir-stop-review-adapter` executable (override with
//! MIR_STOP_REVIEW_ADAPTER), accepting the reference Python launcher argv verbatim.
use regex::Regex;
use serde::de::{Deserialize, Deserializer, MapAccess, Visitor};
use serde_json::{Value, value::RawValue};
use std::{
    env, fmt,
    fs::{self, File, OpenOptions},
    io::{self, Read, Write},
    path::Path,
    process::{Command, Stdio},
    time::{SystemTime, UNIX_EPOCH},
};

// Keep insertion order, duplicate-key semantics and integer spelling without
// changing serde_json's feature selection for the other binaries in this crate.
#[derive(Clone)]
enum Json {
    Scalar(Value),
    Number(String),
    Array(Vec<Json>),
    Object(Vec<(String, Json)>),
}
struct Object(Vec<(String, Box<RawValue>)>);
impl<'de> Deserialize<'de> for Object {
    fn deserialize<D: Deserializer<'de>>(d: D) -> Result<Self, D::Error> {
        struct Entries;
        impl<'de> Visitor<'de> for Entries {
            type Value = Object;
            fn expecting(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
                f.write_str("an object")
            }
            fn visit_map<A: MapAccess<'de>>(self, mut map: A) -> Result<Object, A::Error> {
                let mut entries = Vec::new();
                while let Some(pair) = map.next_entry()? {
                    entries.push(pair);
                }
                Ok(Object(entries))
            }
        }
        d.deserialize_map(Entries)
    }
}
impl Json {
    fn parse(raw: &str) -> Result<Self, serde_json::Error> {
        let raw: Box<RawValue> = serde_json::from_str(raw)?;
        let text = raw.get();
        Ok(match text.as_bytes().first() {
            Some(b'{') => {
                let mut entries: Vec<(String, Json)> = Vec::new();
                for (key, value) in serde_json::from_str::<Object>(text)?.0 {
                    let value = Self::parse(value.get())?;
                    if let Some(pair) = entries.iter_mut().find(|(k, _)| k == &key) {
                        pair.1 = value;
                    } else {
                        entries.push((key, value));
                    }
                }
                Self::Object(entries)
            }
            Some(b'[') => Self::Array(
                serde_json::from_str::<Vec<Box<RawValue>>>(text)?
                    .iter()
                    .map(|v| Self::parse(v.get()))
                    .collect::<Result<_, _>>()?,
            ),
            Some(b'-' | b'0'..=b'9') => Self::Number(text.into()),
            _ => Self::Scalar(serde_json::from_str(text)?),
        })
    }
    fn string(s: impl Into<String>) -> Self {
        Self::Scalar(Value::String(s.into()))
    }
    fn get(&self, key: &str) -> Option<&Self> {
        match self {
            Self::Object(entries) => entries.iter().find(|(k, _)| k == key).map(|(_, v)| v),
            _ => None,
        }
    }
    fn repr(&self, nonprintable: &Regex) -> String {
        match self {
            Self::Scalar(Value::String(s)) => py_quote(s, nonprintable),
            Self::Scalar(Value::Null) => "None".into(),
            Self::Scalar(Value::Bool(b)) => if *b { "True" } else { "False" }.into(),
            Self::Number(s) => number(s),
            Self::Array(items) => format!(
                "[{}]",
                items
                    .iter()
                    .map(|v| v.repr(nonprintable))
                    .collect::<Vec<_>>()
                    .join(", ")
            ),
            Self::Object(entries) => format!(
                "{{{}}}",
                entries
                    .iter()
                    .map(|(k, v)| format!(
                        "{}: {}",
                        py_quote(k, nonprintable),
                        v.repr(nonprintable)
                    ))
                    .collect::<Vec<_>>()
                    .join(", ")
            ),
            Self::Scalar(v) => v.to_string(),
        }
    }
    fn pretty(&self, depth: usize) -> String {
        let inner = " ".repeat((depth + 1) * 2);
        let outer = " ".repeat(depth * 2);
        match self {
            Self::Scalar(v) => v.to_string(),
            Self::Number(s) => number(s),
            Self::Array(v) if v.is_empty() => "[]".into(),
            Self::Object(v) if v.is_empty() => "{}".into(),
            Self::Array(v) => format!(
                "[\n{}\n{outer}]",
                v.iter()
                    .map(|v| format!("{inner}{}", v.pretty(depth + 1)))
                    .collect::<Vec<_>>()
                    .join(",\n")
            ),
            Self::Object(v) => format!(
                "{{\n{}\n{outer}}}",
                v.iter()
                    .map(|(k, v)| format!(
                        "{inner}{}: {}",
                        Value::String(k.clone()),
                        v.pretty(depth + 1)
                    ))
                    .collect::<Vec<_>>()
                    .join(",\n")
            ),
        }
    }
}

fn number(text: &str) -> String {
    if !text.contains(['.', 'e', 'E']) {
        return text.into();
    }
    let Ok(value) = text.parse::<f64>() else {
        return text.into();
    };
    let raw = format!("{value:?}");
    if let Some((mantissa, exponent)) = raw.split_once('e')
        && let Ok(exponent) = exponent.parse::<i32>()
    {
        return format!("{mantissa}e{exponent:+03}");
    }
    raw
}

fn py_quote(s: &str, nonprintable: &Regex) -> String {
    let quote = if s.contains('\'') && !s.contains('"') {
        '"'
    } else {
        '\''
    };
    let mut out = String::from(quote);
    for c in s.chars() {
        match c {
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            _ if c == quote => {
                out.push('\\');
                out.push(c);
            }
            _ if c != ' ' && nonprintable.is_match(c.encode_utf8(&mut [0; 4])) => {
                let n = c as u32;
                out.push_str(&if n <= 0xff {
                    format!("\\x{n:02x}")
                } else if n <= 0xffff {
                    format!("\\u{n:04x}")
                } else {
                    format!("\\U{n:08x}")
                });
            }
            _ => out.push(c),
        }
    }
    out.push(quote);
    out
}

fn timestamp() -> Option<(String, String)> {
    let now = SystemTime::now().duration_since(UNIX_EPOCH).ok()?;
    let db = rusqlite::Connection::open_in_memory().ok()?;
    let iso: String = db
        .query_row(
            "SELECT strftime('%Y-%m-%dT%H:%M:%S', ?1, 'unixepoch')",
            [i64::try_from(now.as_secs()).ok()?],
            |r| r.get(0),
        )
        .ok()?;
    let compact = iso.replace(['-', ':'], "");
    Some((
        format!("{compact}Z"),
        format!("{iso}.{:06}+00:00", now.subsec_micros()),
    ))
}

/// OS randomness plus create-new: even an existing exact candidate is preserved.
pub(crate) fn create_log(
    dir: &Path,
    prefix: &str,
    ts: &str,
    mut random: impl FnMut() -> io::Result<[u8; 3]>,
) -> Result<(File, std::path::PathBuf), (std::path::PathBuf, io::Error)> {
    for _ in 0..128 {
        let bytes = random().map_err(|e| (dir.to_path_buf(), e))?;
        let path = dir.join(format!(
            "{prefix}-{ts}-{}-{:02x}{:02x}{:02x}.log",
            std::process::id(),
            bytes[0],
            bytes[1],
            bytes[2]
        ));
        match OpenOptions::new().write(true).create_new(true).open(&path) {
            Ok(file) => return Ok((file, path)),
            Err(e) if e.kind() == io::ErrorKind::AlreadyExists => continue,
            Err(e) => return Err((path, e)),
        }
    }
    Err((
        dir.to_path_buf(),
        io::Error::new(
            io::ErrorKind::AlreadyExists,
            "audit filename collision budget exhausted",
        ),
    ))
}

fn audit(project: &Path, raw: &str, failure: bool) -> io::Result<()> {
    let sessions = project.join("tasks/sessions");
    fs::create_dir_all(&sessions)?;
    let event = Json::parse(if raw.trim().is_empty() { "{}" } else { raw });
    if event.as_ref().is_ok_and(|v| !matches!(v, Json::Object(_))) {
        return Ok(());
    }
    let parse_ok = event.is_ok();
    let event = event.unwrap_or_else(|_| Json::Object(Vec::new()));
    let Some((ts, iso)) = timestamp() else {
        return Ok(());
    };
    let nonprintable = Regex::new(r"[\p{C}\p{Z}]").map_err(io::Error::other)?;
    let body = if failure {
        let mut entries = vec![
            ("hook".into(), Json::string("StopFailure")),
            ("ts".into(), Json::string(iso)),
            ("parse_ok".into(), Json::Scalar(Value::Bool(parse_ok))),
            (
                "parse_error".into(),
                Json::string(if parse_ok { "" } else { "invalid JSON" }),
            ),
        ];
        for key in [
            "session_id",
            "error_type",
            "hook_event_name",
            "cwd",
            "transcript_path",
        ] {
            entries.push((
                key.into(),
                event.get(key).cloned().unwrap_or(Json::Scalar(Value::Null)),
            ));
        }
        let mut keys = if let Json::Object(entries) = &event {
            entries.iter().map(|(k, _)| k.clone()).collect::<Vec<_>>()
        } else {
            Vec::new()
        };
        keys.sort();
        entries.push((
            "raw_keys".into(),
            Json::Array(keys.into_iter().map(Json::string).collect()),
        ));
        format!("{}\n", Json::Object(entries).pretty(0))
    } else if !parse_ok {
        format!("timestamp: {iso}\nparse_error: 'invalid JSON'\nstop_hook_active: parse-failure\n")
    } else {
        let empty = Json::string("");
        let cwd = Json::string(env::var("CLAUDE_PROJECT_DIR").unwrap_or_default());
        let hook = Json::string("Stop");
        let message = event.get("last_assistant_message").unwrap_or(&empty);
        let message = match message {
            Json::Scalar(Value::String(s)) => s.clone(),
            _ => message.repr(&nonprintable),
        };
        let message: String = message.chars().take(500).collect();
        format!(
            "timestamp: {iso}\nstop_hook_active: {}\nlast_assistant_message_snippet: {}\ncwd: {}\nhook_event_name: {}\n",
            event
                .get("stop_hook_active")
                .unwrap_or(&empty)
                .repr(&nonprintable),
            py_quote(&message, &nonprintable),
            event.get("cwd").unwrap_or(&cwd).repr(&nonprintable),
            event
                .get("hook_event_name")
                .unwrap_or(&hook)
                .repr(&nonprintable)
        )
    };
    let prefix = if failure { "stop-failure" } else { "stop" };
    // Bundled SQLite uses an OS-seeded ChaCha20 PRNG. Reuse that existing
    // dependency so the frozen W1 Cargo manifest and lockfile stay untouched.
    let random = rusqlite::Connection::open_in_memory().map_err(io::Error::other)?;
    let result = create_log(&sessions, prefix, &ts, || {
        let bytes: Vec<u8> = random
            .query_row("SELECT randomblob(3)", [], |r| r.get(0))
            .map_err(io::Error::other)?;
        bytes
            .try_into()
            .map_err(|_| io::Error::other("invalid random blob length"))
    });
    match result {
        Ok((mut file, path)) => {
            if let Err(error) = file.write_all(body.as_bytes()) {
                write_warning(failure, &path, &error);
            }
        }
        Err((path, error)) => write_warning(failure, &path, &error),
    }
    Ok(())
}

fn write_warning(failure: bool, path: &Path, error: &io::Error) {
    #[cfg(not(windows))]
    let reason = match error.kind() {
        io::ErrorKind::PermissionDenied => "Permission denied",
        io::ErrorKind::NotFound => "No such file or directory",
        _ => "I/O error",
    };
    #[cfg(not(windows))]
    let errno = match error.kind() {
        io::ErrorKind::PermissionDenied => 13,
        io::ErrorKind::NotFound => 2,
        _ => 5,
    };
    let prefix = if failure {
        "[mir stop-failure-audit] cannot write log"
    } else {
        "mir-stop: warning: could not write audit log"
    };
    #[cfg(windows)]
    eprintln!(
        "{prefix}: {}",
        handoff_packet::executor_brief_profile::python_file_error_message(
            error,
            path,
            handoff_packet::executor_text::IoOperation::Write,
            handoff_packet::executor_text::FilenameArgument::Path
        )
    );
    #[cfg(not(windows))]
    eprintln!("{prefix}: [Errno {errno}] {reason}: '{}'", path.display());
}

// SHA-1 is used only for the reference's non-security review change-id prefix.
fn review_hash(input: &[u8]) -> String {
    let mut data = input.to_vec();
    let bits = (data.len() as u64) * 8;
    data.push(0x80);
    while data.len() % 64 != 56 {
        data.push(0);
    }
    data.extend(bits.to_be_bytes());
    let mut h = [
        0x67452301u32,
        0xefcdab89,
        0x98badcfe,
        0x10325476,
        0xc3d2e1f0,
    ];
    for block in data.as_chunks::<64>().0 {
        let mut w = [0u32; 80];
        for (i, bytes) in block.as_chunks::<4>().0.iter().enumerate() {
            w[i] = u32::from_be_bytes([bytes[0], bytes[1], bytes[2], bytes[3]]);
        }
        for i in 16..80 {
            w[i] = (w[i - 3] ^ w[i - 8] ^ w[i - 14] ^ w[i - 16]).rotate_left(1);
        }
        let [mut a, mut b, mut c, mut d, mut e] = h;
        for (i, word) in w.iter().enumerate() {
            let (f, k) = match i {
                0..=19 => ((b & c) | (!b & d), 0x5a827999),
                20..=39 => (b ^ c ^ d, 0x6ed9eba1),
                40..=59 => ((b & c) | (b & d) | (c & d), 0x8f1bbcdc),
                _ => (b ^ c ^ d, 0xca62c1d6),
            };
            let temp = a
                .rotate_left(5)
                .wrapping_add(f)
                .wrapping_add(e)
                .wrapping_add(k)
                .wrapping_add(*word);
            e = d;
            d = c;
            c = b.rotate_left(30);
            b = a;
            a = temp;
        }
        for (slot, value) in h.iter_mut().zip([a, b, c, d, e]) {
            *slot = slot.wrapping_add(value);
        }
    }
    format!("{:08x}{:04x}", h[0], h[1] >> 16)
}

pub fn run(failure: bool) {
    let mut raw = String::new();
    let _ = io::stdin().read_to_string(&mut raw);
    // Bash command substitution removes trailing line feeds before both consumers.
    let raw = raw.trim_end_matches('\n');
    let project = env::var_os("CLAUDE_PROJECT_DIR")
        .filter(|v| !v.is_empty())
        .unwrap_or_else(|| ".".into());
    if let Err(error) = audit(Path::new(&project), raw, failure) {
        // Directory-creation failures stay non-blocking. No CPython traceback.
        if failure {
            eprintln!("[mir stop-failure-audit] cannot create dir: {error}");
        }
    }
    if !failure
        && env::var_os("MIR_REVIEW_GATE").is_some_and(|v| v == "1")
        && let Some((ts, _)) = timestamp()
    {
        let adapter = env::var_os("MIR_STOP_REVIEW_ADAPTER")
            .unwrap_or_else(|| "mir-stop-review-adapter".into());
        let _ = Command::new(adapter)
            .args([
                "-m",
                "tools.mir_executor",
                "execute",
                "--background",
                "--change-id",
                &format!("auto-review-{ts}-{}", review_hash(raw.as_bytes())),
                "--category",
                "review",
                "--codex-args",
                "exec --review",
                "--family",
                "your-harness",
            ])
            .stdin(Stdio::null())
            .stdout(Stdio::inherit())
            .stderr(Stdio::null())
            .status();
    }
}
