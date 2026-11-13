//! Explicit Git dispatch worktrees and local evidence. This module does not route execution.
//!
//! Private evidence files use Unix 0600. On Windows, `icacls` resets inherited ACLs,
//! removes inheritance and grants only the current `whoami` account full control
//! before any content is written. A new empty file briefly inherits its parent's
//! ACL; failures to establish or verify the private ACL fail closed. Windows
//! requires those system utilities; Unix requires a supported O_NOFOLLOW constant.
//! Selected roots resolve directory aliases once, including terminal links;
//! descendant checks reject existing symlinks/reparse points. Callers must keep
//! ancestor directories under their control for Git operations. Unix artifact
//! writes reuse descriptor-relative mkdir and private opens so a replaced
//! parent cannot redirect writes outside the selected artifact container.
use crate::executor_local::LocalConfig;
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    ffi::OsStr,
    fmt, fs,
    io::{self, Read, Write},
    path::{Component, Path, PathBuf},
    process::{Command, Output},
    sync::atomic::{AtomicU64, Ordering},
    time::{SystemTime, UNIX_EPOCH},
};

#[derive(Debug)]
pub enum Error {
    Io(io::Error),
    Json(serde_json::Error),
    PathIo {
        kind: &'static str,
        message: String,
        path: PathBuf,
    },
    Git {
        code: Option<i32>,
        stderr: String,
        command: Option<Vec<String>>,
    },
    Invalid(String),
    Local(crate::executor_local::Error),
    Redaction(crate::Error),
}
impl Error {
    pub fn kind(&self) -> &'static str {
        match self {
            Self::Io(_) => "OSError",
            Self::PathIo { kind, .. } => kind,
            Self::Json(_) => "JSONDecodeError",
            Self::Git { .. } => "CalledProcessError",
            Self::Invalid(_) => "ValueError",
            Self::Local(e) => e.kind(),
            Self::Redaction(_) => "ValueError",
        }
    }
}
impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Io(e) => e.fmt(f),
            Self::PathIo { message, path, .. } => write!(
                f,
                "{message}: {}",
                crate::executor_text::repr(&path.to_string_lossy())
            ),
            Self::Json(e) => e.fmt(f),
            Self::Git {
                code,
                stderr,
                command,
                ..
            } => {
                if let Some(command) = command {
                    write!(
                        f,
                        "Command '{}' returned non-zero exit status {}.",
                        crate::executor_execute::list_repr(command),
                        code.unwrap_or(1)
                    )
                } else {
                    write!(f, "git failed ({code:?}): {stderr}")
                }
            }
            Self::Invalid(e) => f.write_str(e),
            Self::Local(e) => e.fmt(f),
            Self::Redaction(e) => write!(f, "redaction failed: {e:?}"),
        }
    }
}
impl std::error::Error for Error {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::Io(e) => Some(e),
            Self::Json(e) => Some(e),
            Self::Local(e) => Some(e),
            Self::Git { .. } | Self::Invalid(_) | Self::Redaction(_) | Self::PathIo { .. } => None,
        }
    }
}
impl From<io::Error> for Error {
    fn from(e: io::Error) -> Self {
        Self::Io(e)
    }
}
impl From<serde_json::Error> for Error {
    fn from(e: serde_json::Error) -> Self {
        Self::Json(e)
    }
}
impl From<crate::Error> for Error {
    fn from(e: crate::Error) -> Self {
        Self::Redaction(e)
    }
}
pub type Result<T> = std::result::Result<T, Error>;

#[derive(Debug, Clone)]
pub struct DispatchWorktree {
    pub dispatch_id: String,
    pub main_repo_root: PathBuf,
    pub path: PathBuf,
    pub branch: String,
    pub base_commit: String,
    pub brief_path: PathBuf,
    pub status_path: PathBuf,
    pub result_path: PathBuf,
    // Ownership is held by the returned handle, never inferred from a pathname.
    auto_temp_base: Option<PathBuf>,
    artifact_selection: Option<DispatchPath>,
    repo: DispatchPath,
    tree: DispatchPath,
}

/// Caller spelling is the source of every displayed descendant. The selected
/// path is pinned once and used only for I/O and containment, never diagnostics.
#[derive(Debug, Clone)]
pub(crate) struct DispatchPath {
    pub(crate) caller: PathBuf,
    pub(crate) io: PathBuf,
}
impl DispatchPath {
    pub(crate) fn root(caller: &Path) -> Result<Self> {
        Ok(Self {
            caller: caller.to_owned(),
            io: selected_root(caller)?,
        })
    }
    pub(crate) fn file(caller: &Path) -> Result<Self> {
        let parent = caller.parent().unwrap_or(Path::new("."));
        let name = caller
            .file_name()
            .ok_or_else(|| Error::Invalid("missing file name".into()))?;
        Ok(Self::root(parent)?.join(name))
    }
    pub(crate) fn join(&self, suffix: impl AsRef<Path>) -> Self {
        Self {
            caller: self.caller.join(&suffix),
            io: self.io.join(suffix),
        }
    }
    fn parent(&self) -> Option<Self> {
        Some(Self {
            caller: self.caller.parent().unwrap_or(&self.caller).to_owned(),
            io: self.io.parent()?.to_owned(),
        })
    }
}
impl DispatchWorktree {
    pub(crate) fn repo(&self) -> &DispatchPath {
        &self.repo
    }
    pub(crate) fn tree(&self) -> &DispatchPath {
        &self.tree
    }
    pub(crate) fn select_artifact_root(&mut self, root: &Path) -> Result<DispatchPath> {
        if let Some(previous) = &self.artifact_selection
            && previous.caller == root
        {
            return Ok(previous.clone());
        }
        let selected = DispatchPath::root(root)?;
        self.artifact_selection = Some(selected.clone());
        Ok(selected)
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MergeOutcome {
    pub merged_files: Vec<String>,
    pub skipped: Vec<String>,
}

pub(crate) fn git(root: &DispatchPath, args: &[&OsStr], check: bool) -> Result<Output> {
    git_with_paths(root, args, args, check)
}
fn git_with_paths(
    root: &DispatchPath,
    args: &[&OsStr],
    caller_args: &[&OsStr],
    check: bool,
) -> Result<Output> {
    let out = Command::new("git")
        .arg("-C")
        .arg(&root.io)
        .args(args)
        .output()?;
    if check && !out.status.success() {
        return Err(Error::Git {
            code: out.status.code(),
            command: Some(git_command(&root.caller, caller_args)?),
            stderr: String::from_utf8(out.stderr)
                .map_err(|e| Error::Local(crate::executor_local::Error::Unicode(e)))?,
        });
    }
    Ok(out)
}
fn git_command(root: &Path, args: &[&OsStr]) -> Result<Vec<String>> {
    std::iter::once(OsStr::new("git"))
        .chain(std::iter::once(OsStr::new("-C")))
        .chain(std::iter::once(root.as_os_str()))
        .chain(args.iter().copied())
        .map(|s| {
            s.to_str()
                .map(str::to_owned)
                .ok_or_else(|| Error::Invalid("non UTF-8 Git argument".into()))
        })
        .collect()
}
pub(crate) fn path_io(error: io::Error, path: &Path) -> Error {
    let Some(errno) = error.raw_os_error() else {
        return Error::Io(error);
    };
    let kind = match error.kind() {
        io::ErrorKind::NotADirectory => "NotADirectoryError",
        io::ErrorKind::IsADirectory => "IsADirectoryError",
        io::ErrorKind::NotFound => "FileNotFoundError",
        io::ErrorKind::PermissionDenied => "PermissionError",
        io::ErrorKind::AlreadyExists => "FileExistsError",
        _ => "OSError",
    };
    let Some(path) = path.to_str() else {
        return Error::Invalid("non UTF-8 evidence path".into());
    };
    let text = error.to_string();
    let message = text.split(" (os error ").next().unwrap_or(&text);
    Error::PathIo {
        kind,
        message: format!("[Errno {errno}] {message}"),
        path: PathBuf::from(path),
    }
}
fn git_text(root: &DispatchPath, args: &[&str]) -> Result<String> {
    let args: Vec<_> = args.iter().map(OsStr::new).collect();
    String::from_utf8(git(root, &args, true)?.stdout)
        .map_err(|_| Error::Invalid("non UTF-8 Git output".into()))
}
fn identifier(id: &str) -> Result<()> {
    if id.is_empty() || id == "." || id == ".." || id.contains(['/', '\\', '\0']) {
        return Err(Error::Invalid(
            "dispatch_id must be a single path component".into(),
        ));
    }
    Ok(())
}
fn absolute(path: &Path) -> Result<PathBuf> {
    let path = if path.is_absolute() {
        path.to_owned()
    } else {
        std::env::current_dir()?.join(path)
    };
    let mut out = PathBuf::new();
    for c in path.components() {
        match c {
            Component::CurDir => {}
            Component::ParentDir => {
                out.pop();
            }
            _ => out.push(c.as_os_str()),
        }
    }
    Ok(out)
}
// Resolve only the caller-selected boundary, preserving checks on descendants.
// A missing root is rebuilt beneath its nearest existing ancestor. Existing
// terminal directory aliases resolve here too; other terminal links retain the
// existing guard refusal.
pub(crate) fn selected_root(path: &Path) -> Result<PathBuf> {
    let path = absolute(path)?;
    let mut ancestor = path.as_path();
    let mut missing = Vec::new();
    loop {
        match fs::symlink_metadata(ancestor) {
            Ok(meta) => {
                #[cfg(windows)]
                let link = {
                    use std::os::windows::fs::MetadataExt;
                    meta.file_attributes() & 0x400 != 0
                };
                #[cfg(not(windows))]
                let link = meta.file_type().is_symlink();
                if missing.is_empty() && link {
                    if let Ok(resolved) = fs::canonicalize(ancestor)
                        && resolved.is_dir()
                    {
                        return Ok(crate::supply::plain(resolved));
                    }
                    return Err(Error::Invalid(format!(
                        "symlink/reparse point rejected: {}",
                        ancestor.display()
                    )));
                }
                let mut resolved = crate::supply::plain(fs::canonicalize(ancestor)?);
                for component in missing.iter().rev() {
                    resolved.push(component);
                }
                return Ok(resolved);
            }
            // A file ancestor does not prevent selecting the path. Like the
            // reference, fail when the event directory is created, after the
            // provider and status hooks; writes still reject replaced links.
            Err(e)
                if matches!(
                    e.kind(),
                    io::ErrorKind::NotFound | io::ErrorKind::NotADirectory
                ) =>
            {
                missing.push(
                    ancestor
                        .file_name()
                        .ok_or_else(|| Error::Invalid("missing selected root ancestor".into()))?
                        .to_owned(),
                );
                ancestor = ancestor
                    .parent()
                    .ok_or_else(|| Error::Invalid("missing selected root parent".into()))?;
            }
            Err(e) => return Err(e.into()),
        }
    }
}

fn reject_links(path: &DispatchPath) -> Result<()> {
    let mut ancestors = vec![path.clone()];
    while let Some(parent) = ancestors.last().and_then(DispatchPath::parent) {
        ancestors.push(parent);
    }
    for ancestor in ancestors.iter().rev() {
        match fs::symlink_metadata(&ancestor.io) {
            Ok(meta) => {
                #[cfg(windows)]
                let link = {
                    use std::os::windows::fs::MetadataExt;
                    meta.file_attributes() & 0x400 != 0
                };
                #[cfg(not(windows))]
                let link = meta.file_type().is_symlink();
                if link {
                    return Err(Error::Invalid(format!(
                        "symlink/reparse point rejected: {}",
                        ancestor.caller.display()
                    )));
                }
            }
            Err(e)
                if matches!(
                    e.kind(),
                    io::ErrorKind::NotFound | io::ErrorKind::NotADirectory
                ) => {}
            Err(e) => return Err(e.into()),
        }
    }
    Ok(())
}
fn ensure_dir(path: &DispatchPath) -> Result<()> {
    reject_links(path)?;
    #[cfg(unix)]
    {
        let selected = absolute(&path.io)?;
        let mut current = PathBuf::from("/");
        for component in selected
            .components()
            .filter(|c| matches!(c, Component::Normal(_)))
        {
            current.push(component.as_os_str());
            match crate::adoption_fs::mkdir(Path::new("/"), &current, 0o777) {
                Ok(()) => {}
                Err(e) if e.kind() == io::ErrorKind::AlreadyExists => {
                    if current == selected && !fs::metadata(&current)?.is_dir() {
                        return Err(path_io(e, &path.caller));
                    }
                }
                Err(e) => return Err(path_io(e, &path.caller)),
            }
        }
    }
    #[cfg(not(unix))]
    fs::create_dir_all(&path.io).map_err(|e| path_io(e, &path.caller))?;
    reject_links(path)
}

#[cfg(unix)]
fn nofollow(options: &mut fs::OpenOptions) -> Result<()> {
    use std::os::unix::fs::OpenOptionsExt;
    #[cfg(any(
        target_os = "macos",
        target_os = "ios",
        target_os = "freebsd",
        target_os = "dragonfly",
        target_os = "openbsd",
        target_os = "netbsd"
    ))]
    const FLAG: i32 = 0x100;
    #[cfg(any(target_os = "linux", target_os = "android"))]
    const FLAG: i32 = 0x20000;
    #[cfg(any(
        target_os = "macos",
        target_os = "ios",
        target_os = "freebsd",
        target_os = "dragonfly",
        target_os = "openbsd",
        target_os = "netbsd",
        target_os = "linux",
        target_os = "android"
    ))]
    {
        options.custom_flags(FLAG).mode(0o600);
        Ok(())
    }
    #[cfg(not(any(
        target_os = "macos",
        target_os = "ios",
        target_os = "freebsd",
        target_os = "dragonfly",
        target_os = "openbsd",
        target_os = "netbsd",
        target_os = "linux",
        target_os = "android"
    )))]
    {
        let _ = options;
        Err(Error::Invalid(
            "O_NOFOLLOW unsupported on this target".into(),
        ))
    }
}
#[cfg(windows)]
fn nofollow(options: &mut fs::OpenOptions) -> Result<()> {
    use std::os::windows::fs::OpenOptionsExt;
    options.custom_flags(0x00200000); // FILE_FLAG_OPEN_REPARSE_POINT
    Ok(())
}
#[cfg(not(any(unix, windows)))]
fn nofollow(_: &mut fs::OpenOptions) -> Result<()> {
    Err(Error::Invalid(
        "private evidence unsupported on this target".into(),
    ))
}

fn private(file: &fs::File, _path: &Path) -> Result<()> {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        file.set_permissions(fs::Permissions::from_mode(0o600))?;
    }
    #[cfg(windows)]
    {
        let _ = file;
        let output = Command::new("whoami").output()?;
        if !output.status.success() {
            return Err(Error::Invalid(
                "cannot identify private evidence owner".into(),
            ));
        }
        let owner = String::from_utf8(output.stdout)
            .map_err(|_| Error::Invalid("non UTF-8 Windows account name".into()))?;
        let owner = owner.trim();
        if owner.is_empty() {
            return Err(Error::Invalid("empty Windows account name".into()));
        }
        let grant = format!("{owner}:(F)");
        for args in [
            vec!["/reset"],
            vec!["/inheritance:r", "/grant:r", grant.as_str()],
            vec!["/verify"],
        ] {
            let output = Command::new("icacls").arg(_path).args(args).output()?;
            if !output.status.success() {
                return Err(Error::Invalid(
                    "cannot establish/verify private Windows evidence ACL".into(),
                ));
            }
        }
    }
    #[cfg(not(any(unix, windows)))]
    {
        let _ = file;
        return Err(Error::Invalid(
            "private evidence unsupported on this target".into(),
        ));
    }
    Ok(())
}
fn read_text(path: &DispatchPath) -> Result<String> {
    reject_links(path)?;
    let mut options = fs::OpenOptions::new();
    options.read(true);
    nofollow(&mut options)?;
    let mut file = options.open(&path.io)?;
    regular_file(&file)?;
    let mut text = String::new();
    file.read_to_string(&mut text)?;
    Ok(text)
}
fn regular_file(file: &fs::File) -> Result<()> {
    let meta = file.metadata()?;
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        if meta.file_attributes() & 0x400 != 0 {
            return Err(Error::Invalid("opened reparse point rejected".into()));
        }
    }
    if !meta.is_file() {
        return Err(Error::Invalid("expected regular evidence file".into()));
    }
    Ok(())
}

// Registry sanitization deliberately truncates job summaries. Evidence redaction
// uses the same credential grammar without that summary-only truncation.
pub fn redact_secret_like_content(text: &str) -> Result<String> {
    fn replace(pattern: &str, text: &str, replacement: &str) -> Result<String> {
        let mut out = String::new();
        let mut end = 0;
        for m in crate::captures(pattern, text, true)? {
            out.push_str(&text[end..m.start]);
            out.push_str(replacement);
            end = m.end;
        }
        out.push_str(&text[end..]);
        Ok(out)
    }
    let mut text = replace(
        r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----(?s:.)*?(?:-----END (?:[A-Z0-9 ]+ )?PRIVATE KEY-----|\z)",
        text,
        "[REDACTED_PRIVATE_KEY]",
    )?;
    let pattern = format!(
        r#"\b({SECRET_NAME})(["']?)(\s*(?:=|:)\s*)("[^"]*"|'[^']*'|(?:(?:bearer|basic)\s+)?[^\s,;]+)"#
    );
    let mut out = String::new();
    let mut end = 0;
    for m in crate::captures(&pattern, &text, true)? {
        out.push_str(&text[end..m.start]);
        let group = |i: usize| m.groups[i].as_deref().unwrap_or("");
        out.push_str(group(1));
        if group(2).is_empty() {
            out.push_str("=[REDACTED]");
        } else {
            out.push_str(group(2));
            out.push_str(group(3));
            let quote = group(4).chars().next().filter(|c| matches!(c, '\'' | '"'));
            if let Some(c) = quote {
                out.push(c);
            }
            out.push_str("[REDACTED]");
            if let Some(c) = quote {
                out.push(c);
            }
        }
        end = m.end;
    }
    out.push_str(&text[end..]);
    text = replace(r"\bbearer\s+[^\s,;]+", &out, "Bearer [REDACTED]")?;
    replace(
        r"\b(?:sk[-_](?:proj[-_]|svcacct[-_]|ant[-_])?[a-z0-9_-]{12,}|(?:gh[pousr]|github_pat)_[a-z0-9_]{20,}|xox[baprs]-[a-z0-9-]{12,}|AKIA[A-Z0-9]{16}|AIza[0-9A-Za-z_-]{20,})",
        &text,
        "[REDACTED_TOKEN]",
    )
}
const SECRET_NAME: &str = r"(?:[a-z0-9]+[_-])*(?:api[_-]?key|access[_-]?key|authorization|bearer|password|secret|token)(?:[_-]?key)?";
pub fn redact_structured_value(value: &Value) -> Result<Value> {
    Ok(match value {
        Value::String(s) => Value::String(redact_secret_like_content(s)?),
        Value::Array(a) => Value::Array(
            a.iter()
                .map(redact_structured_value)
                .collect::<Result<_>>()?,
        ),
        Value::Object(o) => {
            let mut out = serde_json::Map::new();
            for (k, v) in o {
                let secret = v.as_str().is_some_and(|s| !s.is_empty())
                    && crate::has(&format!("^(?:{SECRET_NAME})$"), k, true)?;
                out.insert(
                    k.clone(),
                    if secret {
                        json!("[REDACTED]")
                    } else {
                        redact_structured_value(v)?
                    },
                );
            }
            Value::Object(out)
        }
        _ => value.clone(),
    })
}

pub fn write_private_text(path: &Path, text: &str, redact: bool) -> Result<()> {
    let text = if redact {
        redact_secret_like_content(text)?
    } else {
        text.to_owned()
    };
    private_write(&DispatchPath::file(path)?, &text, false)
}
#[cfg(not(windows))]
fn private_write(path: &DispatchPath, text: &str, append: bool) -> Result<()> {
    if let Some(parent) = path.parent() {
        reject_links(&parent)?;
    }
    let mut options = fs::OpenOptions::new();
    options.write(true).create(true).truncate(false);
    // Do not truncate before checking the opened file and establishing its ACL.
    nofollow(&mut options)?;
    let mut file = options
        .open(&path.io)
        .map_err(|e| path_io(e, &path.caller))?;
    regular_file(&file)?;
    private(&file, &path.io)?;
    if append {
        use std::io::{Seek, SeekFrom};
        file.seek(SeekFrom::End(0))?;
    } else {
        file.set_len(0)?;
    }
    file.write_all(text.as_bytes())?;
    Ok(())
}
#[cfg(windows)]
fn private_write(path: &DispatchPath, text: &str, append: bool) -> Result<()> {
    reject_links(path)?;
    let mut content = String::new();
    if append {
        match read_text(path) {
            Ok(old) => content = old,
            Err(Error::Io(e)) if e.kind() == io::ErrorKind::NotFound => {}
            Err(e) => return Err(e),
        }
    }
    content.push_str(text);
    let parent = path
        .parent()
        .ok_or_else(|| Error::Invalid("missing private evidence parent".into()))?;
    // Reset only a fresh empty file. Existing sensitive evidence retains its
    // protected ACL throughout replacement, including when ACL setup fails.
    for _ in 0..100 {
        let temp = parent.io.join(format!(
            ".mir-private-{}-{}.tmp",
            std::process::id(),
            NEXT_TEMP.fetch_add(1, Ordering::Relaxed)
        ));
        let mut options = fs::OpenOptions::new();
        options.write(true).create_new(true);
        nofollow(&mut options)?;
        let mut file = match options.open(&temp) {
            Ok(file) => file,
            Err(e) if e.kind() == io::ErrorKind::AlreadyExists => continue,
            Err(e) => return Err(e.into()),
        };
        let result = (|| {
            regular_file(&file)?;
            private(&file, &temp)?;
            file.write_all(content.as_bytes())?;
            file.sync_all()?;
            drop(file);
            reject_links(path)?;
            fs::rename(&temp, &path.io)?;
            Ok(())
        })();
        if result.is_err() {
            let _ = fs::remove_file(&temp);
        }
        return result;
    }
    Err(Error::Invalid(
        "cannot allocate private evidence replacement".into(),
    ))
}
pub fn write_json(path: &Path, value: &Value) -> Result<()> {
    write_json_contained(&DispatchPath::file(path)?, value)
}
fn write_json_contained(path: &DispatchPath, value: &Value) -> Result<()> {
    let text = crate::executor_ledger_json::render(
        r#"{"dispatch_id":null,"state":null,"base_commit":null}"#,
        &redact_structured_value(value)?,
    )
    .map_err(Error::Invalid)?;
    private_write(path, &text, false)
}
// The existing validated layout reader retains nested insertion order. Compact
// only whitespace outside strings using Python json.dumps default separators.
pub(crate) fn compact_json(original: &str) -> Result<String> {
    let value = redact_structured_value(&serde_json::from_str(original)?)?;
    let pretty = crate::executor_ledger_json::render(original, &value).map_err(Error::Invalid)?;
    let mut out = String::new();
    let mut quoted = false;
    let mut escaped = false;
    for c in pretty.chars() {
        if quoted {
            out.push(c);
            if escaped {
                escaped = false;
            } else if c == '\\' {
                escaped = true;
            } else if c == '"' {
                quoted = false;
            }
        } else {
            match c {
                '"' => {
                    quoted = true;
                    out.push(c);
                }
                ',' | ':' => {
                    out.push(c);
                    out.push(' ');
                }
                ' ' | '\t' | '\r' | '\n' => {}
                _ => out.push(c),
            }
        }
    }
    Ok(out)
}
pub fn secure_write(path: &Path, text: &str, append: bool) -> Result<()> {
    secure_write_contained(&DispatchPath::file(path)?, text, append)
}

// Callers select the root before mutable hooks; descendants never resolve again.
pub(crate) fn secure_write_contained(path: &DispatchPath, text: &str, append: bool) -> Result<()> {
    reject_links(path)?;
    let text = match path.io.extension().and_then(OsStr::to_str) {
        Some("json") => compact_json(text)? + "\n",
        Some("jsonl") => {
            let mut result = String::new();
            for line in text.lines().filter(|line| !line.trim().is_empty()) {
                result.push_str(&compact_json(line)?);
                result.push('\n');
            }
            result
        }
        _ => redact_secret_like_content(text)?,
    };
    if let Some(parent) = path.parent() {
        ensure_dir(&parent)?;
    }
    #[cfg(unix)]
    {
        // Each traversal refuses replaced ancestors; writes use the pinned
        // descriptor rather than reinterpreting a validated pathname.
        let root = Path::new("/");
        let parent =
            crate::adoption_fs::parent(root, &path.io).map_err(|e| path_io(e, &path.caller))?;
        let mut file = parent
            .open_private(append)
            .map_err(|e| path_io(e, &path.caller))?;
        regular_file(&file)?;
        private(&file, &path.io)?;
        if !append {
            file.set_len(0)?;
        }
        file.write_all(text.as_bytes())?;
        Ok(())
    }
    #[cfg(not(unix))]
    private_write(path, &text, append)
}

static NEXT_TEMP: AtomicU64 = AtomicU64::new(0);
fn temp_base() -> Result<PathBuf> {
    // macOS exposes its OS temporary directory through the /var -> /private/var
    // alias. Resolve that selected root once; descendants still reject links.
    let root = selected_root(&std::env::temp_dir())?;
    reject_links(&DispatchPath {
        caller: root.clone(),
        io: root.clone(),
    })?;
    for _ in 0..100 {
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map_err(|_| Error::Invalid("system clock predates epoch".into()))?
            .as_nanos();
        let path = root.join(format!(
            "mir-wt-{}-{nanos}-{}",
            std::process::id(),
            NEXT_TEMP.fetch_add(1, Ordering::Relaxed)
        ));
        match fs::create_dir(&path) {
            Ok(()) => {
                #[cfg(unix)]
                {
                    use std::os::unix::fs::PermissionsExt;
                    fs::set_permissions(&path, fs::Permissions::from_mode(0o700))?;
                }
                return Ok(path);
            }
            Err(e) if e.kind() == io::ErrorKind::AlreadyExists => {}
            Err(e) => return Err(e.into()),
        }
    }
    Err(Error::Invalid(
        "cannot allocate unique worktree temporary directory".into(),
    ))
}

pub fn create_dispatch_worktree(
    main_repo_root: &Path,
    dispatch_id: &str,
    base_commit: &str,
    brief_text: &str,
    worktrees_root: Option<&Path>,
) -> Result<DispatchWorktree> {
    identifier(dispatch_id)?;
    let root = DispatchPath::root(main_repo_root)?;
    reject_links(&root)?;
    let base_sha = git_text(
        &root,
        &["rev-parse", "--verify", "--end-of-options", base_commit],
    )?
    .trim()
    .to_owned();
    let auto_temp_base = if worktrees_root.is_none() {
        Some(temp_base()?)
    } else {
        None
    };
    let parent = match (worktrees_root, auto_temp_base.as_ref()) {
        (Some(path), _) => DispatchPath::root(path)?,
        (None, Some(path)) => DispatchPath {
            caller: path.clone(),
            io: path.clone(),
        },
        _ => return Err(Error::Invalid("missing worktree root".into())),
    };
    ensure_dir(&parent)?;
    let path = parent.join(dispatch_id);
    reject_links(&path)?;
    let branch = format!("mir-dispatch/{dispatch_id}");
    let args = [
        OsStr::new("worktree"),
        OsStr::new("add"),
        OsStr::new("-b"),
        OsStr::new(&branch),
        path.io.as_os_str(),
        OsStr::new(&base_sha),
    ];
    let caller_args = [
        OsStr::new("worktree"),
        OsStr::new("add"),
        OsStr::new("-b"),
        OsStr::new(&branch),
        path.caller.as_os_str(),
        OsStr::new(&base_sha),
    ];
    if let Err(e) = git_with_paths(&root, &args, &caller_args, true) {
        if let Some(temp) = auto_temp_base {
            let _ = fs::remove_dir_all(temp);
        }
        return Err(e);
    }
    let dispatch_dir = path.join(".mir-dispatch");
    let wt = DispatchWorktree {
        dispatch_id: dispatch_id.to_owned(),
        main_repo_root: root.caller.clone(),
        brief_path: dispatch_dir.caller.join("brief.md"),
        status_path: dispatch_dir.caller.join("status.json"),
        result_path: dispatch_dir.caller.join("result.json"),
        path: path.caller.clone(),
        branch,
        base_commit: base_sha,
        auto_temp_base,
        artifact_selection: None,
        repo: root,
        tree: path,
    };
    let setup = (|| {
        let profile = wt.repo.join(".mir/repo-profile.toml");
        reject_links(&profile)?;
        match fs::metadata(&profile.io) {
            Ok(meta) if meta.is_file() => {
                let destination = wt.tree.join(".mir/repo-profile.toml");
                ensure_dir(
                    &destination
                        .parent()
                        .ok_or_else(|| Error::Invalid("missing profile parent".into()))?,
                )?;
                reject_links(&destination)?;
                // Text is not interpreted; profile bytes and ordinary file permissions survive.
                fs::copy(&profile.io, &destination.io)?;
            }
            Ok(_) => {}
            Err(e) if e.kind() == io::ErrorKind::NotFound => {}
            Err(e) => return Err(e.into()),
        }
        ensure_dir(&dispatch_dir)?;
        private_write(
            &wt.tree.join(".mir-dispatch/brief.md"),
            &redact_secret_like_content(brief_text)?,
            false,
        )?;
        write_json_contained(
            &wt.tree.join(".mir-dispatch/status.json"),
            &json!({"dispatch_id": dispatch_id, "state":"created", "base_commit":wt.base_commit}),
        )
    })();
    setup?;
    Ok(wt)
}

pub fn write_status(worktree: &DispatchWorktree, state: &str, fields: &Value) -> Result<()> {
    let text = match read_text(&worktree.tree.join(".mir-dispatch/status.json")) {
        Ok(text) => text,
        Err(Error::Io(e)) if e.kind() == io::ErrorKind::NotFound => String::new(),
        Err(e) => return Err(e),
    };
    let mut data = if text.trim().is_empty() {
        json!({})
    } else {
        serde_json::from_str(&text)?
    };
    let data_object = data
        .as_object_mut()
        .ok_or_else(|| Error::Invalid("expected JSON object in status".into()))?;
    data_object.insert("state".into(), json!(state));
    for (key, value) in fields
        .as_object()
        .ok_or_else(|| Error::Invalid("status fields must be an object".into()))?
    {
        data_object.insert(key.clone(), value.clone());
    }
    // Preserve the original dictionary order and append newly supplied fields
    // in the order used by the Python state transitions.
    let original = if text.trim().is_empty() {
        "{}"
    } else {
        text.trim()
    };
    let mut layout = original
        .strip_suffix('}')
        .ok_or_else(|| Error::Invalid("expected JSON object in status".into()))?
        .to_owned();
    let mut separator = if layout.trim_end().ends_with('{') {
        ""
    } else {
        ","
    };
    for key in ["state", "reason", "attempt", "attempts"]
        .into_iter()
        .chain(
            fields
                .as_object()
                .into_iter()
                .flat_map(|fields| fields.keys().map(String::as_str)),
        )
    {
        if key == "state" || fields.get(key).is_some() {
            layout.push_str(separator);
            layout.push_str(&serde_json::to_string(key)?);
            layout.push_str(":null");
            separator = ",";
        }
    }
    layout.push('}');
    let text = crate::executor_ledger_json::render(&layout, &redact_structured_value(&data)?)
        .map_err(Error::Invalid)?;
    private_write(
        &worktree.tree.join(".mir-dispatch/status.json"),
        &text,
        false,
    )
}

/// Inspect only the explicitly supplied worktree; no consumer discovery.
pub fn inspect_worktree(worktree: &DispatchWorktree) -> Result<Value> {
    reject_links(&worktree.tree)?;
    Ok(json!({
        "dispatch_id":worktree.dispatch_id, "branch":worktree.branch,
        "base_commit":worktree.base_commit,
        "head":git_text(&worktree.tree, &["rev-parse", "HEAD"])?.trim(),
        "status":git_text(&worktree.tree, &["status", "--porcelain=v1", "-z"])?
    }))
}

pub fn cleanup_worktree(worktree: &DispatchWorktree, delete_branch: bool) -> Result<()> {
    reject_links(&worktree.tree)?;
    let removal = git(
        &worktree.repo,
        &[
            OsStr::new("worktree"),
            OsStr::new("remove"),
            OsStr::new("--force"),
            worktree.tree.io.as_os_str(),
        ],
        false,
    )?;
    if !removal.status.success() && worktree.tree.io.try_exists()? {
        return Err(Error::Git {
            code: removal.status.code(),
            command: Some(git_command(
                &worktree.repo.caller,
                &[
                    OsStr::new("worktree"),
                    OsStr::new("remove"),
                    OsStr::new("--force"),
                    worktree.tree.caller.as_os_str(),
                ],
            )?),
            stderr: String::from_utf8(removal.stderr)
                .map_err(|_| Error::Invalid("non UTF-8 Git error".into()))?,
        });
    }
    git(
        &worktree.repo,
        &[OsStr::new("worktree"), OsStr::new("prune")],
        false,
    )?;
    if delete_branch {
        // Probe the exact ref so absent branches are benign regardless of Git locale.
        let reference = format!("refs/heads/{}", worktree.branch);
        let exists = git(
            &worktree.repo,
            &[
                OsStr::new("show-ref"),
                OsStr::new("--verify"),
                OsStr::new("--quiet"),
                OsStr::new(&reference),
            ],
            false,
        )?;
        if exists.status.success() {
            git_text(&worktree.repo, &["branch", "-D", &worktree.branch])?;
        } else if exists.status.code() != Some(1) {
            return Err(Error::Git {
                code: exists.status.code(),
                command: None,
                stderr: String::from_utf8(exists.stderr)
                    .map_err(|_| Error::Invalid("non UTF-8 Git error".into()))?,
            });
        }
    }
    if let Some(temp) = &worktree.auto_temp_base {
        match fs::remove_dir(temp) {
            Ok(()) => {}
            Err(e)
                if matches!(
                    e.kind(),
                    io::ErrorKind::NotFound | io::ErrorKind::DirectoryNotEmpty
                ) => {}
            Err(e) => return Err(e.into()),
        }
    }
    Ok(())
}

pub fn merge_result(
    worktree: &DispatchWorktree,
    source_commit: Option<&str>,
    approved_files: Option<&[String]>,
    allow_harness_self_modify: bool,
) -> Result<MergeOutcome> {
    let source = match source_commit {
        Some(s) => s.to_owned(),
        None => git_text(&worktree.tree, &["rev-parse", "HEAD"])?
            .trim()
            .to_owned(),
    };
    let changed;
    let files = match approved_files {
        Some(files) => files,
        None => {
            changed = git_text(
                &worktree.repo,
                &[
                    "diff",
                    "--no-renames",
                    "--name-only",
                    "-z",
                    &worktree.base_commit,
                    &source,
                ],
            )?
            .split('\0')
            .filter(|p| !p.is_empty())
            .map(str::to_owned)
            .collect::<Vec<_>>();
            &changed
        }
    };
    let mut outcome = MergeOutcome {
        merged_files: vec![],
        skipped: vec![],
    };
    for path in files {
        let denied = path != "tasks/tdd.json"
            && [".claude/", ".ai-harness/", "config/", "docs/", "tasks/"]
                .iter()
                .any(|prefix| path.starts_with(prefix));
        let lifted = allow_harness_self_modify
            && [".claude/", ".ai-harness/", "config/", "docs/"]
                .iter()
                .any(|prefix| path.starts_with(prefix));
        if path == "tasks/plan.md" || (denied && !lifted) {
            outcome.skipped.push(path.clone());
            continue;
        }
        if Path::new(path).is_absolute()
            || Path::new(path)
                .components()
                .any(|c| matches!(c, Component::ParentDir))
            || path.contains('\0')
        {
            return Err(Error::Invalid(
                "merge path must stay inside repository".into(),
            ));
        }
        let exists = git_text(
            &worktree.repo,
            &[
                "--literal-pathspecs",
                "ls-tree",
                "-z",
                "--name-only",
                &source,
                "--",
                path,
            ],
        )?;
        if exists.is_empty() {
            git_text(&worktree.repo, &["--literal-pathspecs", "rm", "--", path])?;
        } else {
            git_text(
                &worktree.repo,
                &["--literal-pathspecs", "checkout", &source, "--", path],
            )?;
        }
        outcome.merged_files.push(path.clone());
    }
    Ok(outcome)
}

pub fn child_env(
    main_repo_root: &Path,
    source_env: &BTreeMap<String, String>,
    filter_credentials: bool,
) -> Result<BTreeMap<String, String>> {
    let config = LocalConfig::load(main_repo_root).map_err(Error::Local)?;
    if !filter_credentials && !config.child_env_filter() {
        return Ok(source_env.clone());
    }
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
    let mut env: BTreeMap<_, _> = source_env
        .iter()
        .filter(|(k, _)| KEYS.contains(&k.as_str()))
        .map(|(k, v)| (k.clone(), v.clone()))
        .collect();
    if let Some(extras) = config.raw().get("child_env_extra_keys") {
        let extras = match extras {
            Value::Array(a) => a
                .iter()
                .map(|v| {
                    v.as_str().ok_or_else(|| {
                        Error::Invalid("child_env_extra_keys entries must be strings".into())
                    })
                })
                .collect::<Result<Vec<_>>>()?,
            Value::String(s) => {
                for key in s.chars().map(|c| c.to_string()) {
                    if let Some(v) = source_env.get(&key) {
                        env.insert(key, v.clone());
                    }
                }
                return Ok(env);
            }
            Value::Object(o) => o.keys().map(String::as_str).collect(),
            _ => {
                return Err(Error::Invalid(
                    "child_env_extra_keys must be iterable".into(),
                ));
            }
        };
        for key in extras {
            if let Some(value) = source_env.get(key) {
                env.insert(key.to_owned(), value.clone());
            }
        }
    }
    Ok(env)
}
pub fn dispatch_env(
    main_repo_root: &Path,
    source_env: &BTreeMap<String, String>,
    session_id: Option<&str>,
    filter_credentials: bool,
) -> Result<BTreeMap<String, String>> {
    let mut env = child_env(main_repo_root, source_env, filter_credentials)?;
    let path = absolute(&main_repo_root.join("tasks/codex-exec-events.jsonl"))?;
    env.insert(
        "CODEX_EVENTS_FILE".into(),
        path.to_str()
            .ok_or_else(|| Error::Invalid("non UTF-8 event path".into()))?
            .into(),
    );
    if let Some(session) = session_id {
        env.insert("MIR_CODEX_SESSION_ID".into(), session.into());
    }
    Ok(env)
}

pub fn persist_dispatch_artifacts(
    worktree: &DispatchWorktree,
    main_repo_root: &Path,
    artifacts_root: Option<&Path>,
) -> Result<PathBuf> {
    identifier(&worktree.dispatch_id)?;
    let root = match artifacts_root {
        Some(root) => match &worktree.artifact_selection {
            Some(selected) if selected.caller == root => selected.clone(),
            _ => DispatchPath::root(root)?,
        },
        None if main_repo_root == worktree.main_repo_root => worktree.repo.join("tasks/dispatch"),
        None => DispatchPath::root(main_repo_root)?.join("tasks/dispatch"),
    };
    let destination = root.join(&worktree.dispatch_id);
    ensure_dir(&destination)?;
    let source = worktree.tree.join(".mir-dispatch");
    reject_links(&source)?;
    match fs::metadata(&source.io) {
        Err(e) if e.kind() == io::ErrorKind::NotFound => return Ok(destination.caller),
        Err(e) => return Err(e.into()),
        Ok(meta) if !meta.is_dir() => {
            return Err(Error::Invalid(
                "dispatch evidence must be a directory".into(),
            ));
        }
        Ok(_) => {}
    }
    for filename in [
        "reviewer.json",
        "brief.md",
        "status.json",
        "result.json",
        "events.jsonl",
        "dispatch-events.jsonl",
    ] {
        let text = match read_text(&source.join(filename)) {
            Ok(text) => text,
            Err(Error::Io(e)) if e.kind() == io::ErrorKind::NotFound => continue,
            Err(e) => return Err(e),
        };
        secure_write_contained(&destination.join(filename), &text, false)?;
    }
    Ok(destination.caller)
}

#[cfg(all(test, unix))]
mod containment_tests {
    use super::*;
    use std::os::unix::fs::symlink;

    #[test]
    fn artifact_parent_swap_refuses_before_external_effect() {
        let scratch = tempfile::tempdir().unwrap();
        let root = fs::canonicalize(scratch.path()).unwrap();
        let container = root.join("container");
        let outside = root.join("outside");
        fs::create_dir(&container).unwrap();
        fs::create_dir(&outside).unwrap();
        fs::write(outside.join("canary"), "unchanged").unwrap();
        let selected = DispatchPath::root(&container.join("artifacts")).unwrap();
        fs::remove_dir(&container).unwrap();
        symlink(&outside, &container).unwrap();
        let result = secure_write_contained(&selected.join("job/events.jsonl"), "{}", true);
        assert!(result.is_err());
        assert_eq!(
            fs::read_to_string(outside.join("canary")).unwrap(),
            "unchanged"
        );
        assert_eq!(fs::read_dir(&outside).unwrap().count(), 1);
    }
    #[test]
    fn artifact_alias_retarget_keeps_selected_container_for_persistence() {
        let scratch = tempfile::tempdir().unwrap();
        let root = fs::canonicalize(scratch.path()).unwrap();
        let inside = root.join("inside");
        let outside = root.join("outside");
        fs::create_dir(&inside).unwrap();
        fs::create_dir(&outside).unwrap();
        fs::write(outside.join("canary"), "unchanged").unwrap();
        let alias = root.join("artifacts");
        symlink(&inside, &alias).unwrap();
        let mut worktree = DispatchWorktree {
            dispatch_id: "job".into(),
            main_repo_root: root.clone(),
            path: root.join("tree"),
            branch: "unused".into(),
            base_commit: "unused".into(),
            brief_path: root.join("brief"),
            status_path: root.join("status"),
            result_path: root.join("result"),
            auto_temp_base: None,
            artifact_selection: None,
            repo: DispatchPath::root(&root).unwrap(),
            tree: DispatchPath::root(&root.join("tree")).unwrap(),
        };
        worktree.select_artifact_root(&alias).unwrap();
        fs::remove_file(&alias).unwrap();
        symlink(&outside, &alias).unwrap();
        let destination = persist_dispatch_artifacts(&worktree, &root, Some(&alias)).unwrap();
        assert_eq!(destination, alias.join("job"));
        assert!(inside.join("job").is_dir());
        assert_eq!(
            fs::read_to_string(outside.join("canary")).unwrap(),
            "unchanged"
        );
        assert_eq!(fs::read_dir(&outside).unwrap().count(), 1);
    }
}

#[cfg(all(test, unix))]
mod spelling_tests {
    use super::*;

    #[test]
    fn nested_alias_path_errors_survive_all_spelling_boundaries() {
        let root = DispatchPath {
            caller: "/repo/alias".into(),
            io: "/repo".into(),
        };
        for file in [
            "trees/d/.mir-dispatch/brief.md",
            "trees/d/.mir-dispatch/status.json",
            "trees/d/.mir-dispatch/reviewer.json",
            "trees/d/.mir-dispatch/dispatch-events.jsonl",
            "events/explicit.jsonl",
            "artifacts/d/dispatch-events.jsonl",
            "artifacts/d",
        ] {
            let path = root.join(file);
            let error = path_io(io::Error::from_raw_os_error(libc::ENOENT), &path.caller);
            assert_eq!(error.kind(), "FileNotFoundError");
            assert_eq!(
                error.to_string(),
                format!("[Errno 2] No such file or directory: '/repo/alias/{file}'")
            );
        }
    }

    #[test]
    fn nested_alias_git_errors_survive_all_spelling_boundaries() {
        for args in [
            vec!["rev-parse", "HEAD"],
            vec!["commit", "-m", "message"],
            vec!["diff", "base", "source"],
            vec![
                "worktree",
                "add",
                "-b",
                "branch",
                "/repo/alias/trees/d",
                "base",
            ],
            vec!["worktree", "remove", "--force", "/repo/alias/trees/d"],
            vec!["branch", "-D", "branch"],
        ] {
            let args: Vec<_> = args.iter().map(OsStr::new).collect();
            let command = git_command(Path::new("/repo/alias"), &args).unwrap();
            let error = Error::Git {
                code: Some(73),
                stderr: "/repo/raw stderr".into(),
                command: Some(command),
            };
            assert_eq!(error.kind(), "CalledProcessError");
            assert!(error.to_string().contains("'/repo/alias'"));
            assert!(!error.to_string().contains("alias/alias"));
            assert!(
                matches!(error, Error::Git { code: Some(73), stderr, .. } if stderr == "/repo/raw stderr")
            );
        }
    }
}
