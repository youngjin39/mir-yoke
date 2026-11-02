//! Explicit Git dispatch worktrees and local evidence. This module does not route execution.
//!
//! Private evidence files use Unix 0600. On Windows, `icacls` resets inherited ACLs,
//! removes inheritance and grants only the current `whoami` account full control
//! before any content is written. A new empty file briefly inherits its parent's
//! ACL; failures to establish or verify the private ACL fail closed. Windows
//! requires those system utilities; Unix requires a supported O_NOFOLLOW constant.
//! Selected roots resolve ancestor aliases once; descendant checks reject existing
//! symlinks/reparse points. Callers must keep
//! ancestor directories under their control: std-only checks cannot pin them
//! against concurrent swaps. This differs from Python artifact reads, which pin
//! the dispatch directory with a directory fd before opening its entries.
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
    Git { code: Option<i32>, stderr: String },
    Invalid(String),
    Local(crate::executor_local::Error),
    Redaction(crate::Error),
}
impl Error {
    pub fn kind(&self) -> &'static str {
        match self {
            Self::Io(_) => "OSError",
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
            Self::Json(e) => e.fmt(f),
            Self::Git { code, stderr } => write!(f, "git failed ({code:?}): {stderr}"),
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
            Self::Git { .. } | Self::Invalid(_) | Self::Redaction(_) => None,
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
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MergeOutcome {
    pub merged_files: Vec<String>,
    pub skipped: Vec<String>,
}

fn git(root: &Path, args: &[&OsStr], check: bool) -> Result<Output> {
    let out = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(args)
        .output()?;
    if check && !out.status.success() {
        return Err(Error::Git {
            code: out.status.code(),
            stderr: String::from_utf8(out.stderr)
                .map_err(|_| Error::Invalid("non UTF-8 Git error".into()))?,
        });
    }
    Ok(out)
}
fn git_text(root: &Path, args: &[&str]) -> Result<String> {
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
// A missing root is rebuilt beneath its nearest existing ancestor. Do not hide
// a dangling link (or a reparse point) at the selected root itself.
fn selected_root(path: &Path) -> Result<PathBuf> {
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
            Err(e) if e.kind() == io::ErrorKind::NotFound => {
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

// Standalone file APIs select their containing directory; the file itself is
// still opened with no-follow and checked before content is written.
fn selected_file(path: &Path) -> Result<PathBuf> {
    let path = absolute(path)?;
    let parent = path
        .parent()
        .ok_or_else(|| Error::Invalid("missing file parent".into()))?;
    let name = path
        .file_name()
        .ok_or_else(|| Error::Invalid("missing file name".into()))?;
    Ok(selected_root(parent)?.join(name))
}

fn reject_links(path: &Path) -> Result<()> {
    let path = absolute(path)?;
    let mut current = PathBuf::new();
    for component in path.components() {
        current.push(component.as_os_str());
        match fs::symlink_metadata(&current) {
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
                        current.display()
                    )));
                }
            }
            Err(e) if e.kind() == io::ErrorKind::NotFound => {}
            Err(e) => return Err(e.into()),
        }
    }
    Ok(())
}
fn ensure_dir(path: &Path) -> Result<()> {
    reject_links(path)?;
    fs::create_dir_all(path)?;
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
fn read_text(path: &Path) -> Result<String> {
    reject_links(path)?;
    let mut options = fs::OpenOptions::new();
    options.read(true);
    nofollow(&mut options)?;
    let mut file = options.open(path)?;
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
    private_write(&selected_file(path)?, &text, false)
}
#[cfg(not(windows))]
fn private_write(path: &Path, text: &str, append: bool) -> Result<()> {
    reject_links(path)?;
    let mut options = fs::OpenOptions::new();
    options.write(true).create(true).truncate(false);
    // Do not truncate before checking the opened file and establishing its ACL.
    nofollow(&mut options)?;
    let mut file = options.open(path)?;
    regular_file(&file)?;
    private(&file, path)?;
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
fn private_write(path: &Path, text: &str, append: bool) -> Result<()> {
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
        let temp = parent.join(format!(
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
            fs::rename(&temp, path)?;
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
    let text = serde_json::to_string_pretty(&redact_structured_value(value)?)? + "\n";
    write_private_text(path, &text, false)
}
// The existing validated layout reader retains nested insertion order. Compact
// only whitespace outside strings using Python json.dumps default separators.
fn compact_json(original: &str) -> Result<String> {
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
    let path = selected_file(path)?;
    let path = path.as_path();
    let text = match path.extension().and_then(OsStr::to_str) {
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
        ensure_dir(parent)?;
    }
    private_write(path, &text, append)
}

static NEXT_TEMP: AtomicU64 = AtomicU64::new(0);
fn temp_base() -> Result<PathBuf> {
    // macOS exposes its OS temporary directory through the /var -> /private/var
    // alias. Resolve that selected root once; descendants still reject links.
    let root = selected_root(&std::env::temp_dir())?;
    reject_links(&root)?;
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
    let root = selected_root(main_repo_root)?;
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
        (Some(path), _) => selected_root(path)?,
        (None, Some(path)) => path.clone(),
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
        path.as_os_str(),
        OsStr::new(&base_sha),
    ];
    if let Err(e) = git(&root, &args, true) {
        if let Some(temp) = auto_temp_base {
            let _ = fs::remove_dir_all(temp);
        }
        return Err(e);
    }
    let dispatch_dir = path.join(".mir-dispatch");
    let wt = DispatchWorktree {
        dispatch_id: dispatch_id.to_owned(),
        main_repo_root: root,
        brief_path: dispatch_dir.join("brief.md"),
        status_path: dispatch_dir.join("status.json"),
        result_path: dispatch_dir.join("result.json"),
        path,
        branch,
        base_commit: base_sha,
        auto_temp_base,
    };
    let setup = (|| {
        let profile = wt.main_repo_root.join(".mir/repo-profile.toml");
        reject_links(&profile)?;
        match fs::metadata(&profile) {
            Ok(meta) if meta.is_file() => {
                let destination = wt.path.join(".mir/repo-profile.toml");
                ensure_dir(
                    destination
                        .parent()
                        .ok_or_else(|| Error::Invalid("missing profile parent".into()))?,
                )?;
                reject_links(&destination)?;
                // Text is not interpreted; profile bytes and ordinary file permissions survive.
                fs::copy(&profile, &destination)?;
            }
            Ok(_) => {}
            Err(e) if e.kind() == io::ErrorKind::NotFound => {}
            Err(e) => return Err(e.into()),
        }
        ensure_dir(&dispatch_dir)?;
        write_private_text(&wt.brief_path, brief_text, true)?;
        write_json(
            &wt.status_path,
            &json!({"dispatch_id": dispatch_id, "state":"created", "base_commit":wt.base_commit}),
        )
    })();
    if let Err(e) = setup {
        if let Err(cleanup) = cleanup_worktree(&wt, true) {
            return Err(Error::Invalid(format!("{e}; rollback failed: {cleanup}")));
        }
        return Err(e);
    }
    Ok(wt)
}

pub fn write_status(worktree: &DispatchWorktree, state: &str, fields: &Value) -> Result<()> {
    let text = match read_text(&worktree.status_path) {
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
    write_json(&worktree.status_path, &data)
}

/// Inspect only the explicitly supplied worktree; no consumer discovery.
pub fn inspect_worktree(worktree: &DispatchWorktree) -> Result<Value> {
    reject_links(&worktree.path)?;
    Ok(json!({
        "dispatch_id":worktree.dispatch_id, "branch":worktree.branch,
        "base_commit":worktree.base_commit,
        "head":git_text(&worktree.path, &["rev-parse", "HEAD"])?.trim(),
        "status":git_text(&worktree.path, &["status", "--porcelain=v1", "-z"])?
    }))
}

pub fn cleanup_worktree(worktree: &DispatchWorktree, delete_branch: bool) -> Result<()> {
    reject_links(&worktree.path)?;
    let removal = git(
        &worktree.main_repo_root,
        &[
            OsStr::new("worktree"),
            OsStr::new("remove"),
            OsStr::new("--force"),
            worktree.path.as_os_str(),
        ],
        false,
    )?;
    if !removal.status.success() && worktree.path.try_exists()? {
        return Err(Error::Git {
            code: removal.status.code(),
            stderr: String::from_utf8(removal.stderr)
                .map_err(|_| Error::Invalid("non UTF-8 Git error".into()))?,
        });
    }
    git(
        &worktree.main_repo_root,
        &[OsStr::new("worktree"), OsStr::new("prune")],
        false,
    )?;
    if delete_branch {
        // Probe the exact ref so absent branches are benign regardless of Git locale.
        let reference = format!("refs/heads/{}", worktree.branch);
        let exists = git(
            &worktree.main_repo_root,
            &[
                OsStr::new("show-ref"),
                OsStr::new("--verify"),
                OsStr::new("--quiet"),
                OsStr::new(&reference),
            ],
            false,
        )?;
        if exists.status.success() {
            git_text(
                &worktree.main_repo_root,
                &["branch", "-D", &worktree.branch],
            )?;
        } else if exists.status.code() != Some(1) {
            return Err(Error::Git {
                code: exists.status.code(),
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
        None => git_text(&worktree.path, &["rev-parse", "HEAD"])?
            .trim()
            .to_owned(),
    };
    let changed;
    let files = match approved_files {
        Some(files) => files,
        None => {
            changed = git_text(
                &worktree.main_repo_root,
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
            &worktree.main_repo_root,
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
            git_text(
                &worktree.main_repo_root,
                &["--literal-pathspecs", "rm", "--", path],
            )?;
        } else {
            git_text(
                &worktree.main_repo_root,
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
        Some(root) => selected_root(root)?,
        None => selected_root(main_repo_root)?.join("tasks/dispatch"),
    };
    let destination = root.join(&worktree.dispatch_id);
    ensure_dir(&destination)?;
    let source = worktree.path.join(".mir-dispatch");
    reject_links(&source)?;
    match fs::metadata(&source) {
        Err(e) if e.kind() == io::ErrorKind::NotFound => return Ok(destination),
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
        secure_write(&destination.join(filename), &text, false)?;
    }
    Ok(destination)
}
