//! Library-only admission; callers remain on the Python reference.
use crate::{
    digest,
    mir_cli::bootstrap_adoption as json_input,
    python_json::{self, Value},
};
use std::{
    collections::BTreeSet,
    fs, io,
    path::{Component, Path, PathBuf},
};
#[derive(Debug)]
pub struct Error {
    pub class: &'static str,
    pub message: String,
}
impl std::fmt::Display for Error {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.message)
    }
}
impl std::error::Error for Error {}
fn sync(message: impl Into<String>) -> Error {
    Error {
        class: "SyncError",
        message: message.into(),
    }
}
fn input_error(e: json_input::Error) -> Error {
    Error {
        class: e.class(),
        message: e.to_string(),
    }
}
#[derive(Debug)]
pub struct ManagedFile {
    pub source_relative: python_json::Text,
    pub target_relative: PathBuf,
    pub content: Vec<u8>,
    pub sha256: String,
}
pub fn sha256_bytes(bytes: &[u8]) -> String {
    digest::sha256(bytes)
}
pub fn is_safe_relative(path: &str, prefix: &str, suffix: &str) -> bool {
    let parts: Vec<_> = path.split('/').collect();
    path.starts_with(prefix)
        && path.ends_with(suffix)
        && !Path::new(path).is_absolute()
        && parts.len() == 3
        && parts
            .iter()
            .all(|p| !p.is_empty() && *p != "." && *p != "..")
}
#[rustfmt::skip]
fn source_with(root: &Path, path: &Path, stat: impl FnOnce(&Path)->io::Result<fs::Metadata>, read: impl FnOnce(&Path)->io::Result<Vec<u8>>) -> Result<Vec<u8>,Error> {
    if path.as_os_str().as_encoded_bytes().contains(&0) {
        return Err(Error { class: "ValueError", message: "stat: embedded null character in path".into() });
    }
    let relative=path.strip_prefix(root).map_err(|_|sync("source must be inside provider root"))?;
    let mode=stat(path).map_err(|_|sync(format!("missing source file: {}",crate::executor_text::os_text(relative.as_os_str()))))?;
    if !mode.is_file() { return Err(sync(format!("source is not a regular file: {}",crate::executor_text::os_text(relative.as_os_str())))); }
    read(path).map_err(|e| {
        if e.raw_os_error().is_none() { Error {class:if e.kind()==io::ErrorKind::PermissionDenied {"PermissionError"} else {"OSError"},message:e.to_string()} }
        else {input_error(json_input::io_error(path,e))}
    })
}
pub fn regular_source(root: &Path, path: &Path) -> Result<Vec<u8>, Error> {
    source_with(root, path, |p| fs::symlink_metadata(p), |p| fs::read(p))
}
pub fn load_sources(root: &Path) -> Result<(Vec<ManagedFile>, Vec<ManagedFile>), Error> {
    let bytes = regular_source(root, &root.join("config/capability-sources.json"))?;
    sources_from_bytes(root, &bytes)
}
fn sources_from_bytes(
    root: &Path,
    bytes: &[u8],
) -> Result<(Vec<ManagedFile>, Vec<ManagedFile>), Error> {
    let points = json_input::json_bytes_codepoints(bytes).map_err(input_error)?;
    let config = python_json::parse_codepoints(points).map_err(|e| {
        if e.exception == "JSONDecodeError" {
            sync("invalid capability source allowlists")
        } else {
            Error {
                class: e.exception,
                message: e.to_string(),
            }
        }
    })?;
    let invalid = || sync("invalid capability source allowlists");
    let agents = config
        .get("agents")
        .and_then(|v| v.get("allowlist"))
        .and_then(Value::as_array)
        .ok_or_else(invalid)?;
    let commands = config
        .get("commands")
        .and_then(|v| v.get("allowlist"))
        .and_then(Value::as_object)
        .ok_or_else(invalid)?;
    let packs = config
        .get("profiles")
        .and_then(|v| v.get("packs"))
        .and_then(Value::as_object)
        .ok_or_else(invalid)?;
    let mut selected = [BTreeSet::new(), BTreeSet::new()];
    for (name, pack) in packs.iter() {
        if !pack.is_object() {
            return Err(sync("invalid capability profile pack"));
        }
        let pack_invalid = || {
            sync(format!(
                "invalid capability profile pack: {}",
                name.py_str()
            ))
        };
        let entries = [
            pack.get("agents")
                .and_then(Value::as_array)
                .ok_or_else(pack_invalid)?,
            pack.get("commands")
                .and_then(Value::as_array)
                .ok_or_else(pack_invalid)?,
        ];
        for (i, entries) in entries.into_iter().enumerate() {
            for relative in entries {
                let allowed = relative.as_text().is_some_and(|s| {
                    if i == 0 {
                        agents.iter().any(|v| v.as_text() == Some(s))
                    } else {
                        commands.keys().any(|k| k == s)
                    }
                });
                if !allowed {
                    return Err(sync(format!(
                        "profile {} is not allowlisted: {}",
                        if i == 0 { "agent" } else { "command" },
                        relative.repr()
                    )));
                }
                selected[i].insert(
                    relative
                        .as_text()
                        .map(|s| s.codepoints.clone())
                        .ok_or_else(invalid)?,
                );
            }
        }
    }
    let mut claude = Vec::new();
    let mut codex = Vec::new();
    let file = |relative: python_json::Text| -> Result<ManagedFile, Error> {
        let path = source_path(root, &relative)?;
        let content = regular_source(root, &root.join(&path)).map_err(|mut e| {
            if e.class == "SyncError"
                && let Some((prefix, _)) = e.message.split_once(": ")
            {
                e.message = format!("{prefix}: {}", relative.py_str());
            }
            e
        })?;
        Ok(ManagedFile {
            target_relative: path.components().skip(1).collect(),
            sha256: sha256_bytes(&content),
            content,
            source_relative: relative,
        })
    };
    for (i, entries) in selected.into_iter().enumerate() {
        for codes in entries {
            let text = python_json::Text::new(codes);
            let spelling: String = text
                .codepoints
                .iter()
                .map(|c| char::from_u32(*c).unwrap_or('\u{e000}'))
                .collect();
            let relative = spelling.as_str();
            if !is_safe_relative(
                relative,
                if i == 0 {
                    ".claude/agents/"
                } else {
                    ".claude/commands/"
                },
                ".md",
            ) {
                return Err(sync(format!(
                    "unsafe {} allowlist path: {}",
                    if i == 0 { "agent" } else { "command" },
                    text.repr()
                )));
            }
            if i == 0 {
                let mut codes: Vec<u32> = ".codex/agents/".chars().map(u32::from).collect();
                codes.extend(&text.codepoints[15..text.codepoints.len() - 3]);
                codes.extend(".toml".chars().map(u32::from));
                claude.push(file(text)?);
                codex.push(file(python_json::Text::new(codes))?);
            } else {
                claude.push(file(text)?);
            }
        }
    }
    Ok((claude, codex))
}
// Keep the filesystem encoding cases together; Text retains surrogateescape names.
#[rustfmt::skip]
fn source_path(root: &Path, text: &python_json::Text) -> Result<PathBuf, Error> {
    let mut points = crate::executor_text::os_points(root.as_os_str());
    points.push(47); points.extend(&text.codepoints);
    if let Some(start) = points.iter().position(|c| (0xd800..=0xdfff).contains(c) && !(0xdc80..=0xdcff).contains(c)) {
        let end = start + points[start..].iter().take_while(|c| (0xd800..=0xdfff).contains(*c)).count();
        return Err(Error { class: "UnicodeEncodeError", message: crate::executor_text::encode_error(
            "utf-8", &points, start, end, "surrogates not allowed").replacen("UnicodeEncodeError: ", "", 1) });
    }
    #[cfg(unix)] {
        use std::os::unix::ffi::OsStringExt;
        let mut bytes=Vec::new();
        for cp in &text.codepoints {
            if (0xdc80..=0xdcff).contains(cp) {bytes.push((cp-0xdc00) as u8);}
            else if let Some(c)=char::from_u32(*cp) {bytes.extend(c.to_string().as_bytes());}
        }
        Ok(PathBuf::from(std::ffi::OsString::from_vec(bytes)))
    }
    #[cfg(not(unix))] { Ok(PathBuf::from(text.py_str())) }
}
fn normalized(path: &Path) -> PathBuf {
    let mut out = PathBuf::new();
    for part in path.components() {
        match part {
            Component::CurDir => (),
            Component::ParentDir => {
                out.pop();
            }
            p => out.push(p.as_os_str()),
        }
    }
    if double_anchor(path) {
        let mut anchor = std::ffi::OsString::from("/");
        anchor.push(out);
        PathBuf::from(anchor)
    } else {
        out
    }
}
fn double_anchor(path: &Path) -> bool {
    let b = path.as_os_str().as_encoded_bytes();
    b.starts_with(b"//") && !b.starts_with(b"///")
}
// pathlib suppresses only these stat errors (and non-encodable paths).
fn path_metadata(path: &Path, follow: bool) -> Result<Option<fs::Metadata>, Error> {
    if path.as_os_str().as_encoded_bytes().contains(&0) {
        return Ok(None);
    }
    let result = if follow {
        fs::metadata(path)
    } else {
        fs::symlink_metadata(path)
    };
    match result {
        Ok(metadata) => Ok(Some(metadata)),
        Err(e)
            if e.raw_os_error().is_some_and(|code| {
                [libc::ENOENT, libc::ENOTDIR, libc::EBADF, libc::ELOOP].contains(&code)
            }) =>
        {
            Ok(None)
        }
        Err(e) => {
            let errno = e.raw_os_error();
            let text = e.to_string();
            let mut error = input_error(json_input::io_error(path, e));
            if error.class == "OSError"
                && let Some(errno) = errno
            {
                let message = text
                    .rsplit_once(" (os error ")
                    .map_or(text.as_str(), |(message, _)| message);
                error.message = format!(
                    "[Errno {errno}] {message}: {}",
                    crate::executor_execute::repr(&crate::executor_text::os_text(path.as_os_str()))
                );
            }
            Err(error)
        }
    }
}
fn directory(path: &Path) -> Result<(), Error> {
    if path_metadata(path, false)?.is_some_and(|m| m.is_symlink()) {
        return Err(sync(format!(
            "symlinked target path is not allowed: {}",
            path.display()
        )));
    }
    let metadata = path_metadata(path, true)?;
    if metadata.as_ref().is_some_and(|m| !m.is_dir()) {
        return Err(sync(format!(
            "target path component is not a directory: {}",
            path.display()
        )));
    }
    // Reuse descriptor containment for existing ancestors. This API never writes.
    #[cfg(unix)]
    if metadata.is_some_and(|m| m.is_dir()) {
        let p = normalized(path);
        crate::adoption_fs::parent(Path::new("/"), &p)
            .map_err(|e| input_error(json_input::io_error(path, e)))?;
    }
    Ok(())
}
pub fn require_safe_home(path: &Path) -> Result<PathBuf, Error> {
    let norm = normalized(path);
    if !path.is_absolute() || norm.parent().is_none() {
        return Err(sync(
            "runtime homes must be explicit absolute non-root paths",
        ));
    }
    let mut current = PathBuf::from(if double_anchor(path) { "//" } else { "/" });
    for part in path.components().skip(1) {
        current.push(part.as_os_str());
        directory(&current)?;
    }
    Ok(norm)
}
pub fn safe_target(home: &Path, relative: &Path) -> Result<PathBuf, Error> {
    let relative: PathBuf = relative
        .components()
        .filter(|p| !matches!(p, Component::CurDir))
        .collect();
    let target = if relative.as_os_str().is_empty() {
        home.to_path_buf()
    } else {
        home.join(&relative)
    };
    let mut current = home.to_path_buf();
    let mut parts = relative.components().peekable();
    while let Some(part) = parts.next() {
        if parts.peek().is_none() {
            break;
        }
        current.push(part.as_os_str());
        directory(&current)?;
    }
    if path_metadata(&target, false)?.is_some_and(|m| m.is_symlink()) {
        return Err(sync(format!(
            "symlinked target path is not allowed: {}",
            target.display()
        )));
    }
    if path_metadata(&target, true)?.is_some_and(|m| !m.is_file()) {
        return Err(sync(format!(
            "target is not a regular file: {}",
            target.display()
        )));
    }
    Ok(target)
}
#[cfg(all(test, unix))]
#[path = "user_runtime_install_tests.rs"]
mod tests;
