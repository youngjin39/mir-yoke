//! Library-only mirror of bootstrap_adoption.py's validator slices.
//! Unknown manifest fields are retained where the Python reference retains them.
#[path = "bootstrap_adoption_main.rs"]
mod entry;
#[path = "bootstrap_adoption_phase2.rs"]
pub(super) mod phase2;
use crate::executor_execute::{list_repr, repr};
pub use entry::{
    JqOutput, JqRequest, ValidationKind, ValidationOutput, ValidationRequest, atomic_write_json,
    emit, evidence_digest, evidence_digests, main,
};
pub use phase2::{
    COUNT_KEYS, LAYER_KEYS, MemoryConnection, REVIEW_KEYS, SqliteRequest, open_memory,
    scan_content_candidates, validate_content_onboarding, validate_memory, validate_phase2,
};
use regex::Regex;
use serde_json::{Map, Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    fmt, fs, io,
    path::{Component, Path, PathBuf},
    process::{Command, Stdio},
    sync::LazyLock,
};

pub const SURFACE_KEYS: [&str; 7] = [
    "bootstrap_start_gate",
    "project_profile",
    "identity_finalize",
    "managed_python_launcher",
    "content_onboarding",
    "memory_acceptance",
    "phase2_spec",
];
pub const LAUNCHER: &str = ".claude/hooks/_lib/run-python.sh";
pub const HOOKS: [&str; 2] = [
    ".claude/hooks/session-start.sh",
    ".claude/hooks/pre-tool-use.sh",
];
pub const GATE_PATHS: [(&str, &str); 5] = [
    ("helper", ".claude/hooks/_lib/bootstrap-gate.sh"),
    ("session", HOOKS[0]),
    ("mutation", HOOKS[1]),
    ("claude_wiring", ".claude/settings.json"),
    ("codex_wiring", ".codex/hooks.json"),
];
pub const DIRECT_PROFILE_MAP: &[(&str, &str)] = &[
    ("code_app", "code_app"),
    ("code_product", "code_app"),
    ("hybrid_pipeline", "hybrid_pipeline"),
    ("content_workspace", "content_workspace"),
    ("infra_runtime", "infra_runtime"),
    ("learning_workspace", "content_workspace"),
    ("meta_harness", "meta_harness"),
    ("template_transitional", "template_transitional"),
    ("public_harness_template", "template_transitional"),
];
pub const ARCHETYPE_PROFILE_MAP: &[(&str, &str)] = &[
    ("app_product_flutter", "code_app"),
    ("code_app", "code_app"),
    ("code_product", "code_app"),
    ("command_memory_heavy_app", "code_app"),
    ("hybrid_pipeline", "hybrid_pipeline"),
    ("infra_runtime", "infra_runtime"),
    ("learning_low_code", "content_workspace"),
    ("ontology_content", "content_workspace"),
    ("meta_harness", "meta_harness"),
    ("template_transitional", "template_transitional"),
];

#[derive(Debug)]
pub struct AdoptionError(pub String);
impl AdoptionError {
    /// Python's AdoptionError inherits ValueError.
    pub fn is_value_error(&self) -> bool {
        true
    }
}
impl fmt::Display for AdoptionError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}
impl std::error::Error for AdoptionError {}

#[derive(Debug)]
pub enum Error {
    SystemExit(i32),
    Adoption(AdoptionError),
    Unicode(String),
    Json(String),
    Io {
        class: &'static str,
        message: String,
    },
}
impl Error {
    pub fn class(&self) -> &'static str {
        match self {
            Self::SystemExit(_) => "SystemExit",
            Self::Adoption(_) => "AdoptionError",
            Self::Unicode(_) => "UnicodeDecodeError",
            Self::Json(_) => "JSONDecodeError",
            Self::Io { class, .. } => class,
        }
    }
}
impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::SystemExit(code) => code.fmt(f),
            Self::Adoption(e) => e.fmt(f),
            Self::Unicode(s) | Self::Json(s) | Self::Io { message: s, .. } => f.write_str(s),
        }
    }
}
impl std::error::Error for Error {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::Adoption(e) => Some(e),
            _ => None,
        }
    }
}
impl From<AdoptionError> for Error {
    fn from(e: AdoptionError) -> Self {
        Self::Adoption(e)
    }
}
fn adoption(message: impl Into<String>) -> Error {
    AdoptionError(message.into()).into()
}
pub(super) fn wire(path: &Path) -> String {
    // Python Path.as_posix() also preserves literal backslashes on Unix.
    #[cfg(windows)]
    {
        path.display()
            .to_string()
            .trim_start_matches("\\\\?\\")
            .replace('\\', "/")
    }
    #[cfg(not(windows))]
    {
        path.display().to_string()
    }
}
pub(super) fn io_error(path: &Path, e: io::Error) -> Error {
    let (class, errno, message) = match e.kind() {
        io::ErrorKind::NotFound => ("FileNotFoundError", 2, "No such file or directory"),
        io::ErrorKind::PermissionDenied => ("PermissionError", 13, "Permission denied"),
        io::ErrorKind::IsADirectory => ("IsADirectoryError", 21, "Is a directory"),
        io::ErrorKind::NotADirectory => ("NotADirectoryError", 20, "Not a directory"),
        _ => {
            return Error::Io {
                class: "OSError",
                message: e.to_string(),
            };
        }
    };
    Error::Io {
        class,
        message: format!("[Errno {errno}] {message}: {}", repr(&wire(path))),
    }
}
pub(super) fn decode(bytes: Vec<u8>) -> Result<String, Error> {
    String::from_utf8(bytes).map_err(|e| {
        let start = e.utf8_error().valid_up_to();
        let len = e
            .utf8_error()
            .error_len()
            .unwrap_or(e.as_bytes().len() - start);
        let reason = match e.utf8_error().error_len() {
            None => "unexpected end of data",
            Some(_) if matches!(e.as_bytes()[start], 0xc2..=0xf4) => "invalid continuation byte",
            Some(_) => "invalid start byte",
        };
        let portion = if len == 1 {
            format!("byte 0x{:02x} in position {start}", e.as_bytes()[start])
        } else {
            format!("bytes in position {start}-{}", start + len - 1)
        };
        Error::Unicode(format!("'utf-8' codec can't decode {portion}: {reason}"))
    })
}

/// The subprocess has no cwd override; -C supplies the project root.
pub struct GitRequest {
    pub argv: Vec<String>,
    pub cwd: Option<String>,
    pub optional_locks: &'static str,
}
pub trait Host {
    fn cwd(&mut self) -> io::Result<PathBuf> {
        std::env::current_dir()
    }
    fn env(&mut self, name: &str) -> Option<String> {
        std::env::var(name).ok()
    }
    fn argv(&mut self) -> Vec<String> {
        std::env::args().collect()
    }
    fn stdout(&mut self, text: &str) -> io::Result<()> {
        use io::Write;
        io::stdout().lock().write_all(text.as_bytes())
    }
    fn stderr(&mut self, text: &str) -> io::Result<()> {
        use io::Write;
        io::stderr().lock().write_all(text.as_bytes())
    }
    fn jq(&mut self, request: &JqRequest) -> io::Result<JqOutput> {
        let output = Command::new(&request.argv[0])
            .args(&request.argv[1..])
            .output()?;
        Ok(JqOutput {
            returncode: output.status.code().unwrap_or(-1),
            stdout: output.stdout,
        })
    }
    /// os.replace semantics on Unix and Windows, including overwriting an existing file.
    fn replace(&mut self, source: &Path, destination: &Path) -> io::Result<()> {
        tempfile::TempPath::try_from_path(source)?
            .persist(destination)
            .map_err(|e| e.error)
    }
    /// Optional observation seam; None runs the real P02/P03 validator.
    fn validation(
        &mut self,
        _request: &ValidationRequest<'_>,
    ) -> Option<Result<ValidationOutput, Error>> {
        None
    }
    fn digest(&mut self, _relative: &str, _path: &Path) -> Option<Result<String, Error>> {
        None
    }
    fn digests(&mut self, _root: &Path, _surfaces: &Value) -> Option<Result<Vec<Value>, Error>> {
        None
    }
    fn install_evaluator(
        &mut self,
        root: &Path,
        source: &Path,
        local: Option<&Path>,
    ) -> Option<Value> {
        entry::install_evaluator(root, source, local, self)
    }
    fn scan_content_candidates(&mut self, root: &Path) -> Result<Vec<Value>, String> {
        scan_content_candidates(root)
    }
    fn sqlite_open(
        &mut self,
        request: &SqliteRequest,
    ) -> Result<Box<dyn MemoryConnection>, String> {
        open_memory(request)
    }
    fn read(&mut self, path: &Path) -> io::Result<Vec<u8>> {
        fs::read(path)
    }
    fn git(&mut self, request: &GitRequest) -> io::Result<bool> {
        let result = Command::new(&request.argv[0])
            .args(&request.argv[1..])
            .env("GIT_OPTIONAL_LOCKS", request.optional_locks)
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()?;
        Ok(result.success())
    }
}
pub struct LocalHost;
impl Host for LocalHost {}
fn read(path: &Path, host: &mut dyn Host) -> Result<Vec<u8>, Error> {
    host.read(path).map_err(|e| io_error(path, e))
}
fn read_text(path: &Path, host: &mut dyn Host) -> Result<String, Error> {
    decode(read(path, host)?).map(|s| s.replace("\r\n", "\n").replace('\r', "\n"))
}
pub(super) fn json_text(text: &str) -> Result<Value, Error> {
    crate::executor_local::LocalConfig::default()
        .parse_argument(text)
        .map_err(|e| Error::Json(e.to_string()))
}
/// Python `json.detect_encoding` followed by `bytes.decode(encoding, "surrogatepass")`.
/// A lone surrogate has no Rust `String` form; it is reported as a decode error instead.
fn json_bytes_text(b: &[u8]) -> Result<String, Error> {
    let starts = |prefix: &[u8]| b.starts_with(prefix);
    if starts(&[0, 0, 0xfe, 0xff]) || starts(&[0xff, 0xfe, 0, 0]) {
        return wide(b, 4, 4, b[0] == 0, "utf-32");
    }
    if starts(&[0xfe, 0xff]) || starts(&[0xff, 0xfe]) {
        return wide(b, 2, 2, b[0] == 0xfe, "utf-16");
    }
    if starts(&[0xef, 0xbb, 0xbf]) {
        // utf-8-sig decodes the remainder, so error positions exclude the BOM.
        return decode(b[3..].to_vec());
    }
    let (unit, be) = match b {
        [0, 0, _, _, ..] => (4, true),
        [0, _, _, _, ..] => (2, true),
        [_, 0, 0, 0, ..] => (4, false),
        [_, 0, _, _, ..] => (2, false),
        [0, _] => (2, true),
        [_, 0] => (2, false),
        _ => return decode(b.to_vec()),
    };
    wide(b, 0, unit, be, if unit == 4 { "utf-32" } else { "utf-16" })
}
/// UTF-16/UTF-32 decoding; positions count from the start of the input, BOM included.
fn wide(b: &[u8], start: usize, unit: usize, be: bool, family: &str) -> Result<String, Error> {
    let codec = format!("{family}-{}", if be { "be" } else { "le" });
    let fail = |s: usize, e: usize, reason: &str| {
        let portion = if e == s {
            format!("byte 0x{:02x} in position {s}", b[s])
        } else {
            format!("bytes in position {s}-{e}")
        };
        Error::Unicode(format!("'{codec}' codec can't decode {portion}: {reason}"))
    };
    let body = &b[start..];
    let whole = body.len() / unit * unit;
    let word = |i: usize| {
        let bytes = &body[i..i + unit];
        let ordered = |k: usize| u32::from(bytes[if be { k } else { unit - 1 - k }]);
        (0..unit).fold(0, |acc, k| acc << 8 | ordered(k))
    };
    let mut out = String::new();
    let mut i = 0;
    while i < whole {
        let at = start + i;
        let value = word(i);
        i += unit;
        if unit == 4 {
            if value > 0x10ffff {
                return Err(fail(at, at + 3, "code point not in range(0x110000)"));
            }
            match char::from_u32(value) {
                Some(c) => out.push(c),
                None => return Err(fail(at, at + 3, "lone surrogate (Python-only)")),
            }
        } else if (0xd800..0xdc00).contains(&value) && i < whole {
            let low = word(i);
            match char::decode_utf16([value as u16, low as u16]).next() {
                Some(Ok(c)) if (0xdc00..0xe000).contains(&low) => {
                    out.push(c);
                    i += unit;
                }
                _ => return Err(fail(at, at + 1, "lone surrogate (Python-only)")),
            }
        } else {
            match char::from_u32(value) {
                Some(c) => out.push(c),
                None => return Err(fail(at, at + 1, "lone surrogate (Python-only)")),
            }
        }
    }
    if whole < body.len() {
        return Err(fail(
            start + whole,
            start + body.len() - 1,
            "truncated data",
        ));
    }
    Ok(out)
}
pub fn load_json_bytes(path: &Path, host: &mut dyn Host) -> Result<(Value, Vec<u8>), Error> {
    let result = (|| {
        let bytes = read(path, host)?;
        let raw = json_text(&json_bytes_text(&bytes)?)?;
        Ok((raw, bytes))
    })();
    let (raw, bytes): (Value, Vec<u8>) = match result {
        Err(e @ (Error::Io { .. } | Error::Json(_))) => {
            return Err(adoption(format!("invalid {}: {e}", wire(path))));
        }
        other => other?,
    };
    if !raw.is_object() {
        return Err(adoption(format!(
            "{} must contain a JSON object",
            wire(path)
        )));
    }
    Ok((raw, bytes))
}

pub fn tracked_path(
    root: &Path,
    relative: &Value,
    label: &str,
) -> Result<(PathBuf, String), Error> {
    let relative = relative
        .as_str()
        .filter(|s| !s.trim().is_empty())
        .ok_or_else(|| adoption(format!("{label} must be a non-empty project-relative path")))?;
    let authored = Path::new(relative);
    if authored.is_absolute() || authored.components().any(|c| c == Component::ParentDir) {
        return Err(adoption(format!(
            "{label} must stay inside the project: {}",
            repr(relative)
        )));
    }
    // Unlike config::resolve_path, this does not expand '~'. Resolve existing
    // prefixes before checking containment, including a symlink to a missing leaf.
    let mut resolved = root.to_path_buf();
    for part in authored.components() {
        if part == Component::CurDir {
            continue;
        }
        resolved.push(part);
        match resolved.canonicalize() {
            Ok(path) => resolved = path,
            Err(e) if e.kind() == io::ErrorKind::NotFound => (),
            Err(e) => return Err(io_error(&resolved, e)),
        }
    }
    let canonical_root = root.canonicalize().map_err(|e| io_error(root, e))?;
    let normalized = resolved
        .strip_prefix(&canonical_root)
        .map_err(|_| adoption(format!("{label} escapes the project: {}", repr(relative))))?;
    let normalized = if normalized.as_os_str().is_empty() {
        ".".into()
    } else {
        wire(normalized)
    };
    Ok((resolved, normalized))
}
pub fn is_git_tracked(root: &Path, relative: &str, host: &mut dyn Host) -> Result<bool, Error> {
    let request = GitRequest {
        argv: vec![
            "git".into(),
            "-C".into(),
            wire(root),
            "ls-files".into(),
            "--error-unmatch".into(),
            "--".into(),
            relative.into(),
        ],
        cwd: None,
        optional_locks: "0",
    };
    host.git(&request)
        .map_err(|e| io_error(Path::new("git"), e))
}

// Regex construction is fallible without panic paths; these constants are
// exercised by the placeholder and raw_python frozen records.
static PLACEHOLDER: LazyLock<Result<Regex, regex::Error>> = LazyLock::new(|| {
    Regex::new(r"(?i)\b(?:describe|placeholder|replace[ -]?me|tbd|todo|unknown)\b")
});
static RESOLVED: LazyLock<Result<Regex, regex::Error>> = LazyLock::new(|| {
    Regex::new(&python_space(
        r#"(?i)["']?(?:tbd|todo)["']?\s*[:=]\s*0\b\s*,?"#,
    ))
});
static RAW_PYTHON: LazyLock<Result<Regex, regex::Error>> = LazyLock::new(|| {
    Regex::new(&python_space(
        r"(?:^|[;&|]\s*|\bexec\s+)(?:/usr/bin/)?python3?(?:\s|$)",
    ))
});
/// Python `\s` and `str.isspace()` also cover the ASCII separators U+001C..U+001F.
fn python_space(pattern: &str) -> String {
    pattern.replace(r"\s", r"[\s\x1c-\x1f]")
}
pub(super) fn is_python_space(c: char) -> bool {
    c.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&c)
}
/// Python `str.splitlines()`: every Unicode line boundary, with "\r\n" as one.
pub(super) fn python_splitlines(body: &str) -> Vec<&str> {
    let mut lines = Vec::new();
    let mut start = 0;
    let mut chars = body.char_indices().peekable();
    while let Some((i, c)) = chars.next() {
        if matches!(
            c,
            '\n' | '\r'
                | '\u{b}'
                | '\u{c}'
                | '\u{1c}'
                | '\u{1d}'
                | '\u{1e}'
                | '\u{85}'
                | '\u{2028}'
                | '\u{2029}'
        ) {
            lines.push(&body[start..i]);
            start = i + c.len_utf8();
            if c == '\r' && chars.peek().is_some_and(|&(_, n)| n == '\n') {
                chars.next();
                start += 1;
            }
        }
    }
    if start < body.len() {
        lines.push(&body[start..]);
    }
    lines
}
fn matches(pattern: &Result<Regex, regex::Error>, text: &str) -> bool {
    pattern.as_ref().is_ok_and(|re| re.is_match(text))
}
pub fn non_placeholder_text(value: &Value, label: &str) -> Result<String, AdoptionError> {
    let value = value
        .as_str()
        .map(|s| s.trim_matches(is_python_space))
        .filter(|s| !s.is_empty())
        .ok_or_else(|| AdoptionError(format!("{label} must be a non-empty string")))?;
    if matches(&PLACEHOLDER, value) {
        return Err(AdoptionError(format!(
            "{label} must not contain placeholder text"
        )));
    }
    Ok(value.into())
}
pub fn contains_unresolved_placeholder(body: &str) -> bool {
    python_splitlines(body).into_iter().any(|line| {
        let clean = RESOLVED
            .as_ref()
            .map_or_else(|_| line.into(), |r| r.replace_all(line, ""));
        matches(&PLACEHOLDER, &clean)
    })
}
pub fn has_raw_python(body: &str) -> bool {
    python_splitlines(body)
        .into_iter()
        .filter(|l| !l.trim_start_matches(is_python_space).starts_with('#'))
        .any(|l| matches(&RAW_PYTHON, l))
}
fn value_repr(v: &Value) -> String {
    match v {
        Value::String(s) => repr(s),
        Value::Null => "None".into(),
        Value::Bool(true) => "True".into(),
        Value::Bool(false) => "False".into(),
        _ => v.to_string(),
    }
}
pub fn validate_profile(
    root: &Path,
    manifest: &Value,
    host: &mut dyn Host,
) -> (Vec<String>, Value) {
    let parsed = (|| -> Result<Value, String> {
        let body =
            read_text(&root.join(".mir/repo-profile.toml"), host).map_err(|e| e.to_string())?;
        let doc: toml::Value = toml::from_str(&body)
            .map_err(|e| crate::mir_core::tomllib::tomllib_error(&e, &body))?;
        serde_json::to_value(doc).map_err(|e| e.to_string())
    })();
    let profile = match parsed {
        Ok(p) => p,
        Err(e) => {
            return (
                vec![format!("invalid .mir/repo-profile.toml: {e}")],
                json!({}),
            );
        }
    };
    let Some(repo) = profile.get("repo").filter(|v| v.is_object()) else {
        return (
            vec![".mir/repo-profile.toml must contain [repo]".into()],
            json!({}),
        );
    };
    let mut errors = Vec::new();
    let slug = &repo["slug"];
    let archetype = &repo["overlay_archetype"];
    let typ = &repo["repository_type"];
    let valid_slug = slug.as_str().is_some_and(|s| {
        !s.is_empty()
            && s.len() <= 64
            && s.bytes().enumerate().all(|(i, c)| {
                c.is_ascii_lowercase() || c.is_ascii_digit() || (i > 0 && b"_-".contains(&c))
            })
    });
    if !valid_slug {
        errors.push("[repo].slug must be a concrete lowercase project slug".into());
    } else if manifest["project_slug"] != *slug {
        errors.push(format!(
            "adoption project_slug {} does not match [repo].slug {}",
            value_repr(&manifest["project_slug"]),
            value_repr(slug)
        ));
    }
    if archetype.as_str().is_none_or(str::is_empty) {
        errors.push("[repo].overlay_archetype must be non-empty".into());
    } else if manifest["repository_archetype"] != *archetype {
        errors.push(format!(
            "adoption repository_archetype does not match \
            [repo].overlay_archetype {}",
            value_repr(archetype)
        ));
    }
    let lookup = |mapping: &[(&str, &str)], value: &Value| {
        mapping
            .iter()
            .find(|(k, _)| value.as_str() == Some(*k))
            .map(|(_, v)| v.to_string())
    };
    let mapped =
        lookup(DIRECT_PROFILE_MAP, typ).or_else(|| lookup(ARCHETYPE_PROFILE_MAP, archetype));
    if let Some(mapped) = &mapped {
        if manifest["profile"] != *mapped {
            errors.push(format!(
                "repository identity maps to profile {}, not {}",
                repr(mapped),
                value_repr(&manifest["profile"])
            ));
        }
    } else {
        errors.push(
            "cannot map [repo].repository_type/[repo].overlay_archetype to an \
            existing-repository adoption profile"
                .into(),
        );
    }
    if let Err(e) = non_placeholder_text(&repo["purpose"], "[repo].purpose") {
        errors.push(e.to_string());
    }
    if let Some(stack) = repo["technology_stack"]
        .as_array()
        .filter(|a| !a.is_empty())
    {
        for (i, item) in stack.iter().enumerate() {
            if let Err(e) = non_placeholder_text(item, &format!("[repo].technology_stack[{i}]")) {
                errors.push(e.to_string());
            }
        }
    } else {
        errors.push("[repo].technology_stack must be a non-empty array".into());
    }
    (
        errors,
        json!({"project_slug":slug,"repository_type":typ,"overlay_archetype":archetype,
        "mapped_profile":mapped,"purpose":repo["purpose"],
        "technology_stack":repo["technology_stack"]}),
    )
}

pub type SurfaceResult = (Vec<String>, Map<String, Value>, Vec<Value>);
pub fn validate_surface_contract(
    root: &Path,
    manifest: &Value,
    host: &mut dyn Host,
) -> Result<SurfaceResult, Error> {
    let Some(surfaces) = manifest.get("surfaces").and_then(Value::as_object) else {
        return Ok((
            vec!["adoption manifest must contain a surfaces object".into()],
            Map::new(),
            vec![],
        ));
    };
    let mut errors = Vec::new();
    let expected: BTreeSet<_> = SURFACE_KEYS.into_iter().collect();
    let actual: BTreeSet<_> = surfaces.keys().map(String::as_str).collect();
    if actual != expected {
        let missing = expected
            .difference(&actual)
            .map(|s| s.to_string())
            .collect::<Vec<_>>();
        let extra = actual
            .difference(&expected)
            .map(|s| s.to_string())
            .collect::<Vec<_>>();
        errors.push(format!(
            "adoption surfaces must be exact; missing={}, extra={}",
            list_repr(&missing),
            list_repr(&extra)
        ));
    }
    let mut normalized = Map::new();
    let mut exceptions = Vec::new();
    for key in SURFACE_KEYS {
        let prefix = format!("surface {}", repr(key));
        let Some(raw) = surfaces.get(key).and_then(Value::as_object) else {
            errors.push(format!("{prefix} must be an object"));
            continue;
        };
        let row = Value::Object(raw.clone());
        let disposition = &raw.get("disposition").unwrap_or(&Value::Null);
        let evidence = &row["evidence_paths"];
        let mut allowed = vec!["disposition", "evidence_paths", "reason", "blockers"];
        if key == "memory_acceptance" {
            allowed.push("queries");
        } else if key == "phase2_spec" {
            allowed.extend([
                "coverage",
                "ai_ready",
                "open_gaps",
                "full_review",
                "native_evidence",
            ]);
        }
        let extra: Vec<_> = raw
            .keys()
            .filter(|k| !allowed.contains(&k.as_str()))
            .cloned()
            .collect();
        if !extra.is_empty() {
            errors.push(format!(
                "{prefix} has unknown fields: {}",
                list_repr(&extra)
            ));
        }
        let Some(disposition) = disposition
            .as_str()
            .filter(|s| ["applied", "repository_owned", "not_applicable", "exception"].contains(s))
        else {
            errors.push(format!(
                "{prefix} has invalid disposition {}",
                value_repr(disposition)
            ));
            continue;
        };
        let Some(evidence) = evidence.as_array().filter(|a| {
            a.iter()
                .all(|v| v.as_str().is_some_and(|s| !s.trim().is_empty()))
        }) else {
            errors.push(format!("{prefix} evidence_paths must be an array of paths"));
            continue;
        };
        let unique: BTreeSet<_> = evidence.iter().filter_map(Value::as_str).collect();
        if unique.len() != evidence.len() {
            errors.push(format!("{prefix} evidence_paths must be unique"));
        }
        if ["applied", "repository_owned", "exception"].contains(&disposition)
            && evidence.is_empty()
        {
            errors.push(format!(
                "{prefix} disposition {} requires evidence_paths",
                repr(disposition)
            ));
        }
        let mut paths = Vec::new();
        for (i, relative) in evidence.iter().enumerate() {
            let (path, normalized_path) =
                match tracked_path(root, relative, &format!("{prefix} evidence_paths[{i}]")) {
                    Ok(p) => p,
                    Err(e @ Error::Adoption(_)) => {
                        errors.push(e.to_string());
                        continue;
                    }
                    Err(e) => return Err(e),
                };
            paths.push(normalized_path.clone());
            if path.is_symlink() || !path.is_file() {
                errors.push(format!(
                    "{prefix} evidence path is missing: {normalized_path}"
                ));
                continue;
            }
            if !is_git_tracked(root, &normalized_path, host)? {
                errors.push(format!(
                    "{prefix} evidence path is not tracked: {normalized_path}"
                ));
            }
            match read(&path, host) {
                Ok(bytes) if bytes.iter().all(u8::is_ascii_whitespace) => errors.push(format!(
                    "{prefix} evidence path is empty: {normalized_path}"
                )),
                Err(e) => errors.push(format!("{prefix} evidence path is unreadable: {e}")),
                _ => (),
            }
        }
        let mut row = row;
        row["evidence_paths"] = json!(paths);
        normalized.insert(key.into(), row.clone());
        if disposition == "exception" {
            let reason = match non_placeholder_text(&row["reason"], &format!("{prefix} reason")) {
                Ok(s) => json!(s),
                Err(e) => {
                    errors.push(e.to_string());
                    row["reason"].clone()
                }
            };
            let blockers =
                if let Some(blockers) = row["blockers"].as_array().filter(|a| !a.is_empty()) {
                    for (i, blocker) in blockers.iter().enumerate() {
                        if let Err(e) =
                            non_placeholder_text(blocker, &format!("{prefix} blockers[{i}]"))
                        {
                            errors.push(e.to_string());
                        }
                    }
                    blockers.clone()
                } else {
                    errors.push(format!("{prefix} exception requires non-empty blockers"));
                    vec![]
                };
            exceptions.push(json!({"surface":key,"reason":reason,"blockers":blockers,
                "evidence_paths":paths}));
        } else if disposition == "not_applicable" {
            if let Err(e) = non_placeholder_text(&row["reason"], &format!("{prefix} reason")) {
                errors.push(e.to_string());
            }
            if key != "content_onboarding" {
                errors.push(format!(
                    "{prefix} cannot be not_applicable; use a documented exception"
                ));
            }
        }
    }
    Ok((errors, normalized, exceptions))
}

pub fn hook_commands(document: &Value) -> Vec<String> {
    let mut commands = Vec::new();
    match document {
        Value::Object(o) => {
            for (key, value) in o {
                if key == "command"
                    && let Some(s) = value.as_str()
                {
                    commands.push(s.into());
                } else {
                    commands.extend(hook_commands(value));
                }
            }
        }
        Value::Array(a) => {
            for value in a {
                commands.extend(hook_commands(value));
            }
        }
        _ => (),
    }
    commands
}
pub fn validate_bootstrap_gate(
    root: &Path,
    host: &mut dyn Host,
) -> Result<(Vec<String>, Value), Error> {
    let mut errors = Vec::new();
    let mut bodies = BTreeMap::new();
    for (label, relative) in GATE_PATHS {
        let path = root.join(relative);
        if !path.is_file() {
            errors.push(format!("bootstrap gate {label} is missing: {relative}"));
            continue;
        }
        match read_text(&path, host) {
            Ok(s) => {
                bodies.insert(label, s);
            }
            Err(e) => errors.push(format!("bootstrap gate {label} is unreadable: {e}")),
        }
    }
    for (label, markers, message) in [
        (
            "helper",
            ["mir_bootstrap_gate_state", "mir_bootstrap_gate_enforce"],
            "bootstrap gate helper does not expose state and enforcement functions",
        ),
        (
            "session",
            ["bootstrap-gate.sh", "mir_bootstrap_gate_state"],
            "bootstrap gate is not wired into SessionStart",
        ),
        (
            "mutation",
            ["bootstrap-gate.sh", "mir_bootstrap_gate_enforce"],
            "bootstrap gate is not wired into the mutation hook",
        ),
    ] {
        let body = bodies.get(label).map(String::as_str).unwrap_or("");
        if markers.iter().any(|m| !body.contains(m)) {
            errors.push(message.into());
        }
    }
    for (runtime, relative) in [("Claude", GATE_PATHS[3].1), ("Codex", GATE_PATHS[4].1)] {
        let path = root.join(relative);
        if !path.is_file() {
            continue;
        }
        let result = read_text(&path, host).and_then(|s| json_text(&s));
        let raw = match result {
            Ok(raw) => raw,
            Err(e @ Error::Unicode(_)) => return Err(e),
            Err(e) => {
                errors.push(format!(
                    "bootstrap gate {runtime} wiring is invalid JSON: {e}"
                ));
                continue;
            }
        };
        let commands = hook_commands(&raw);
        if !commands.iter().any(|c| c.contains("session-start.sh")) {
            errors.push(format!(
                "bootstrap gate SessionStart is not active in {runtime} wiring"
            ));
        }
        if !commands.iter().any(|c| c.contains("pre-tool-use.sh")) {
            errors.push(format!(
                "bootstrap gate mutation hook is not active in {runtime} wiring"
            ));
        }
    }
    let paths: BTreeMap<_, _> = GATE_PATHS.into_iter().collect();
    let evidence = json!({"status":status(&errors),"paths":paths});
    Ok((errors, evidence))
}
fn status(errors: &[String]) -> &'static str {
    if errors.is_empty() { "pass" } else { "fail" }
}
pub fn validate_canonical_applied_helper(
    root: &Path,
    relative: &str,
    label: &str,
    source_root: &Path,
    package_root: &Path,
    host: &mut dyn Host,
) -> (Vec<String>, Value) {
    let source_path = source_root.join(relative);
    let source = if source_path.is_file() {
        read(&source_path, host)
    } else {
        match relative {
            ".claude/hooks/_lib/bootstrap-gate.sh" => read(
                &package_root.join("resources/hooks/bootstrap-gate.sh"),
                host,
            ),
            LAUNCHER => read(&package_root.join("resources/hooks/run-python.sh"), host),
            _ => Err(Error::Io {
                class: "OSError",
                message: format!("no packaged canonical resource for {relative}"),
            }),
        }
    };
    let fail = || json!({"status":"fail","path":relative});
    let source = match source {
        Ok(b) => b,
        Err(e) => {
            return (
                vec![format!(
                    "{label} canonical Mir Yoke source is unreadable: {relative}: {e}"
                )],
                fail(),
            );
        }
    };
    let target = match read(&root.join(relative), host) {
        Ok(b) => b,
        Err(e) => {
            return (
                vec![format!(
                    "{label} applied file is unreadable: {relative}: {e}"
                )],
                fail(),
            );
        }
    };
    let source_hash = crate::digest::sha256(&source);
    let target_hash = crate::digest::sha256(&target);
    let errors = if source_hash == target_hash {
        vec![]
    } else {
        vec![format!(
            "{label} does not match Mir Yoke canonical source: {relative}"
        )]
    };
    let evidence = json!({"status":status(&errors),"path":relative,
        "source_sha256":source_hash,"live_sha256":target_hash});
    (errors, evidence)
}
pub fn required_runtime_paths(surface_name: &str) -> Vec<&'static str> {
    match surface_name {
        "bootstrap_start_gate" => GATE_PATHS.iter().map(|(_, path)| *path).collect(),
        "managed_python_launcher" => vec![LAUNCHER, HOOKS[0], HOOKS[1]],
        _ => vec![],
    }
}
pub fn validate_required_runtime_evidence(surface: &Value, surface_name: &str) -> Vec<String> {
    let paths = surface.get("evidence_paths").and_then(Value::as_array);
    required_runtime_paths(surface_name)
        .into_iter()
        .filter(|p| paths.is_none_or(|a| !a.iter().any(|v| v.as_str() == Some(p))))
        .map(|p| format!("{surface_name} must declare runtime evidence path: {p}"))
        .collect()
}
pub fn validate_python_launcher(root: &Path, host: &mut dyn Host) -> (Vec<String>, Value) {
    let body = match read_text(&root.join(LAUNCHER), host) {
        Ok(s) => s,
        Err(e) => {
            return (
                vec![format!(
                    "managed Python launcher is missing or unreadable: {LAUNCHER}: {e}"
                )],
                json!({}),
            );
        }
    };
    let mut errors = Vec::new();
    for marker in [".venv/bin/python", ".venv/Scripts/python.exe"] {
        if !body.contains(marker) {
            errors.push(format!(
                "managed Python launcher is missing required route {}",
                repr(marker)
            ));
        }
    }
    let uv = body.contains("uv run") && body.contains("--project");
    let external = ["bootstrap-receipt.json", "run-python", "--project-root"]
        .iter()
        .all(|m| body.contains(m));
    if !(uv || external) {
        errors.push(
            "managed Python launcher requires either a project uv route or an \
            external receipt-bound Mir route"
                .into(),
        );
    }
    if has_raw_python(&body.replace("uv run --project", "")) {
        errors.push("managed Python launcher contains a host Python fallback".into());
    }
    let mut wired = Vec::new();
    for hook in HOOKS {
        let body = match read_text(&root.join(hook), host) {
            Ok(s) => s,
            Err(e) => {
                errors.push(format!(
                    "managed Python launcher wiring is unreadable: {hook}: {e}"
                ));
                continue;
            }
        };
        if !body.contains("run-python.sh") {
            errors.push(format!("managed Python launcher is not wired into {hook}"));
        } else {
            wired.push(hook);
        }
        if has_raw_python(&body) {
            errors.push(format!("managed Python launcher bypass found in {hook}"));
        }
    }
    let evidence = json!({"status":status(&errors),"launcher":LAUNCHER,"wired_hooks":wired});
    (errors, evidence)
}

/// argparse's namespace, stdout and stderr without exiting the library caller.
pub fn parse(argv: &[&str], cwd: &Path) -> Value {
    const USAGE: &str = "usage: mir bootstrap-adoption [-h] \
        [--project-root PROJECT_ROOT] [--apply]\n\
        \x20                             [--native-evaluator NATIVE_EVALUATOR] [--json]\n";
    const HELP: &str = "\noptions:\n  -h, --help            show this help message and exit\n\
        \x20 --project-root PROJECT_ROOT\n  --apply               \
        atomically write a ready bootstrap \
        receipt after every\n                        check passes\n\
        \x20 --native-evaluator NATIVE_EVALUATOR\n\
        \x20                       explicit local bootstrap-gate build to copy and hash-\n\
        \x20                       pin during --apply\n  --json\n";
    let mut namespace = json!({"project_root":wire(cwd),"apply":false,
        "native_evaluator":null,"json":false});
    let mut index = 0;
    let mut unknown = Vec::new();
    while index < argv.len() {
        let arg = argv[index];
        if ["-h", "--help"].contains(&arg) {
            return json!([{"error":["SystemExit","0"]},format!("{USAGE}{HELP}"),""]);
        }
        match arg {
            "--apply" => namespace["apply"] = json!(true),
            "--json" => namespace["json"] = json!(true),
            "--project-root" | "--native-evaluator" => {
                index += 1;
                if index >= argv.len() || argv[index].starts_with('-') {
                    let message = format!(
                        "{USAGE}mir bootstrap-adoption: error: \
                        argument {arg}: expected one argument\n"
                    );
                    return json!([{"error":["SystemExit","2"]},"",message]);
                }
                let key = if arg == "--project-root" {
                    "project_root"
                } else {
                    "native_evaluator"
                };
                namespace[key] = json!(argv[index]);
            }
            _ => unknown.push(arg),
        }
        index += 1;
    }
    if !unknown.is_empty() {
        let message = format!(
            "{USAGE}mir bootstrap-adoption: error: \
            unrecognized arguments: {}\n",
            unknown.join(" ")
        );
        return json!([{"error":["SystemExit","2"]},"",message]);
    }
    json!([{"value":namespace},"",""])
}
