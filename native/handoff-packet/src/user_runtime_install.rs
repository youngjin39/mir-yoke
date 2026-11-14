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

pub const RECEIPT_NAME: &str = "mir-yoke-agent-command-receipt.json";
const MANAGED_BY: &str = "mir-yoke-user-runtime-agent-command-sync";
#[derive(Debug)]
pub struct StaleFile {
    pub source_relative: python_json::Text,
    pub target_relative: PathBuf,
    pub sha256: String,
}
pub(crate) fn quoted(points: &[u32]) -> String {
    let mut out = String::from("\"");
    for &cp in points {
        match cp {
            34 => out.push_str("\\\""),
            92 => out.push_str("\\\\"),
            8 => out.push_str("\\b"),
            9 => out.push_str("\\t"),
            10 => out.push_str("\\n"),
            12 => out.push_str("\\f"),
            13 => out.push_str("\\r"),
            32..=126 => out.push(char::from_u32(cp).unwrap_or_default()),
            0..=0xffff => out.push_str(&format!("\\u{cp:04x}")),
            _ => {
                let n = cp - 0x10000;
                out.push_str(&format!(
                    "\\u{:04x}\\u{:04x}",
                    0xd800 + (n >> 10),
                    0xdc00 + (n & 1023)
                ));
            }
        }
    }
    out.push('"');
    out
}
fn quote(text: &str) -> String {
    quoted(&text.chars().map(u32::from).collect::<Vec<_>>())
}
// Match Path.as_posix() without losing native surrogate code points.
fn posix_path_points(path: &std::ffi::OsStr, separator: char) -> Vec<u32> {
    crate::executor_text::os_points(path)
        .into_iter()
        .map(|cp| if cp == u32::from(separator) { 47 } else { cp })
        .collect()
}
/// Python's sorted, ASCII JSON with two-space indentation and a final newline.
pub fn make_receipt(runtime: &str, source_commit: &str, files: &[ManagedFile]) -> Vec<u8> {
    let sorted: std::collections::BTreeMap<_, _> = files
        .iter()
        .map(|f| (&f.source_relative.codepoints, f))
        .collect();
    let entries=sorted.values().map(|f|format!("    {}: {{\n      \"sha256\": {},\n      \"source\": {},\n      \"target\": {}\n    }}",quoted(&f.source_relative.codepoints),quote(&f.sha256),quoted(&f.source_relative.codepoints),quoted(&posix_path_points(f.target_relative.as_os_str(), std::path::MAIN_SEPARATOR)))).collect::<Vec<_>>();
    let body = if entries.is_empty() {
        "{}".into()
    } else {
        format!("{{\n{}\n  }}", entries.join(",\n"))
    };
    format!("{{\n  \"files\": {body},\n  \"managed_by\": {},\n  \"runtime\": {},\n  \"schema_version\": 1,\n  \"source_commit\": {}\n}}\n",quote(MANAGED_BY),quote(runtime),quote(source_commit)).into_bytes()
}
fn exists(path: &Path) -> Result<bool, Error> {
    Ok(path_metadata(path, true)?.is_some())
}
fn read_target(path: &Path) -> Result<Vec<u8>, Error> {
    fs::read(path).map_err(|e| input_error(json_input::io_error(path, e)))
}
/// Retain unknown receipt fields without recursive destruction of Python-depth JSON.
pub struct Receipt(Value);
impl std::ops::Deref for Receipt {
    type Target = Value;
    fn deref(&self) -> &Value {
        &self.0
    }
}
impl Drop for Receipt {
    fn drop(&mut self) {
        python_json::discard(std::mem::replace(&mut self.0, Value::Null));
    }
}
pub fn load_receipt(home: &Path, runtime: &str) -> Result<(PathBuf, Option<Receipt>), Error> {
    let path = safe_target(home, Path::new(RECEIPT_NAME))?;
    if !exists(&path)? {
        return Ok((path, None));
    }
    let invalid = || sync(format!("unmanaged existing receipt: {}", path.display()));
    let bytes = fs::read(&path).map_err(|_| invalid())?;
    // read_text is strict UTF-8, not json.loads(bytes)' BOM/UTF-16 detection.
    let text = json_input::decode(bytes).map_err(input_error)?;
    let receipt = Receipt(python_json::parse(&text).map_err(|e| {
        if e.exception == "JSONDecodeError" {
            invalid()
        } else {
            Error {
                class: e.exception,
                message: e.to_string(),
            }
        }
    })?);
    if receipt.get("managed_by").and_then(Value::as_str) != Some(MANAGED_BY)
        || receipt.get("runtime").and_then(Value::as_str) != Some(runtime)
        || receipt.get("files").and_then(Value::as_object).is_none()
    {
        return Err(invalid());
    }
    Ok((path, Some(receipt)))
}
pub fn receipt_allows_update(
    receipt: Option<&Receipt>,
    item: &ManagedFile,
    target: &Path,
) -> Result<bool, Error> {
    let recorded = receipt
        .and_then(|r| r.get("files"))
        .and_then(Value::as_object)
        .and_then(|o| {
            o.iter()
                .find(|(k, _)| *k == &item.source_relative)
                .map(|(_, v)| v)
        });
    let Some(recorded) = recorded else {
        return Ok(false);
    };
    if recorded.get("source").and_then(Value::as_text) != Some(&item.source_relative)
        || recorded
            .get("target")
            .and_then(Value::as_text)
            .map(|t| &t.codepoints)
            != Some(&posix_path_points(
                item.target_relative.as_os_str(),
                std::path::MAIN_SEPARATOR,
            ))
    {
        return Ok(false);
    }
    Ok(recorded.get("sha256").and_then(Value::as_str)
        == Some(sha256_bytes(&read_target(target)?).as_str()))
}
pub fn receipt_path_is_safe(
    runtime: &str,
    source: &python_json::Text,
    target: &python_json::Text,
) -> Result<python_json::Text, Error> {
    // A surrogate is a name character; keep its native encoding until filesystem access.
    let spelling: String = source
        .codepoints
        .iter()
        .map(|c| char::from_u32(*c).unwrap_or('\u{e000}'))
        .collect();
    let valid = if runtime == "claude" {
        is_safe_relative(&spelling, ".claude/agents/", ".md")
            || is_safe_relative(&spelling, ".claude/commands/", ".md")
    } else {
        is_safe_relative(&spelling, ".codex/agents/", ".toml")
    };
    let expected = source
        .codepoints
        .iter()
        .position(|c| *c == 47)
        .map(|i| &source.codepoints[i + 1..])
        .unwrap_or(&[]);
    if !valid || target.codepoints != expected {
        return Err(sync(format!(
            "invalid managed receipt entry: {}",
            source.repr()
        )));
    }
    Ok(target.clone())
}
pub fn stale_files(
    home: &Path,
    runtime: &str,
    receipt: Option<&Receipt>,
    files: &[ManagedFile],
) -> Result<Vec<StaleFile>, Error> {
    let Some(entries) = receipt
        .and_then(|r| r.get("files"))
        .and_then(Value::as_object)
    else {
        return Ok(vec![]);
    };
    let mut sorted = entries.iter().collect::<Vec<_>>();
    sorted.sort_by(|a, b| a.0.codepoints.cmp(&b.0.codepoints));
    let mut stale = Vec::new();
    for (source, recorded) in sorted {
        if files.iter().any(|f| &f.source_relative == source) {
            continue;
        }
        if !recorded.is_object() {
            return Err(sync("invalid managed receipt entry"));
        }
        let invalid = || sync(format!("invalid managed receipt entry: {}", source.repr()));
        let target = recorded
            .get("target")
            .and_then(Value::as_text)
            .ok_or_else(invalid)?;
        let digest = recorded
            .get("sha256")
            .and_then(Value::as_str)
            .ok_or_else(invalid)?;
        if recorded.get("source").and_then(Value::as_text) != Some(source)
            || digest.len() != 64
            || !digest
                .bytes()
                .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
        {
            return Err(invalid());
        }
        let relative_text = receipt_path_is_safe(runtime, source, target)?;
        let path = match source_path(home, &relative_text) {
            Ok(path) => path,
            Err(e) if e.class == "UnicodeEncodeError" => {
                // pathlib predicates suppress an unencodable leaf, after checking its parent.
                directory(
                    &home.join(if relative_text.py_str().starts_with("commands/") {
                        "commands"
                    } else {
                        "agents"
                    }),
                )?;
                continue;
            }
            Err(e) => return Err(e),
        };
        let relative = path;
        let path = safe_target(home, &relative)?;
        if exists(&path)? && sha256_bytes(&read_target(&path)?) != digest {
            return Err(sync(format!(
                "diverged stale managed file; refusing removal: {}",
                path.display()
            )));
        }
        if exists(&path)? {
            stale.push(StaleFile {
                source_relative: source.clone(),
                target_relative: relative,
                sha256: digest.into(),
            });
        }
    }
    Ok(stale)
}
pub fn validate_targets(
    home: &Path,
    runtime: &str,
    files: &[ManagedFile],
) -> Result<(PathBuf, Vec<StaleFile>), Error> {
    let (receipt_path, receipt) = load_receipt(home, runtime)?;
    for item in files {
        let target = safe_target(home, &item.target_relative)?;
        if exists(&target)? && sha256_bytes(&read_target(&target)?) != item.sha256 {
            if receipt_allows_update(receipt.as_ref(), item, &target)? {
                continue;
            }
            return Err(sync(format!(
                "{}; refusing overwrite: {}",
                if receipt.is_none() {
                    "unmanaged existing file"
                } else {
                    "diverged managed file"
                },
                target.display()
            )));
        }
    }
    Ok((
        receipt_path,
        stale_files(home, runtime, receipt.as_ref(), files)?,
    ))
}

#[cfg(all(test, unix))]
#[path = "user_runtime_identity_tests.rs"]
mod identity_tests;

#[derive(Debug)]
pub struct HomeIdentity {
    pub path: PathBuf,
    pub canonical_path: PathBuf,
    pub device: u64,
    pub inode: u64,
}
#[cfg(unix)]
#[rustfmt::skip]
pub fn capture_home_identity(home: &Path) -> Result<HomeIdentity, Error> {
    use std::os::unix::fs::MetadataExt;
    if home.as_os_str().as_encoded_bytes().contains(&0) {
        return Err(Error { class:"ValueError", message:"stat: embedded null character in path".into() });
    }
    let details=fs::symlink_metadata(home).map_err(|_|sync(format!("cannot inspect runtime home: {}",crate::executor_text::os_text(home.as_os_str()))))?;
    if !details.is_dir() || details.is_symlink() { return Err(sync(format!("runtime home is not a real directory: {}",crate::executor_text::os_text(home.as_os_str())))); }
    let canonical_path=fs::canonicalize(home).map_err(|e|input_error(json_input::io_error(home,e)))?;
    if canonical_path != home || double_anchor(home) { return Err(sync(format!("symlinked target path is not allowed: {}",crate::executor_text::os_text(home.as_os_str())))); }
    Ok(HomeIdentity {path:home.into(),canonical_path,device:details.dev(),inode:details.ino()})
}
#[cfg(unix)]
#[rustfmt::skip]
pub fn runtime_homes_overlap(claude_home: &HomeIdentity, codex_home: &HomeIdentity) -> bool {
    use std::os::unix::fs::MetadataExt;
    if (claude_home.device,claude_home.inode)==(codex_home.device,codex_home.inode) { return true; }
    for (child,ancestor) in [(claude_home,codex_home),(codex_home,claude_home)] {
        for parent in child.path.ancestors().skip(1) {
            if let Ok(details)=fs::symlink_metadata(parent)
                && (details.dev(),details.ino())==(ancestor.device,ancestor.inode) { return true; }
        }
    }
    false
}
#[cfg(unix)]
#[rustfmt::skip]
pub fn verified_target(identity: &HomeIdentity, relative: &Path) -> Result<PathBuf, Error> {
    use std::os::unix::fs::MetadataExt;
    if identity.path.as_os_str().as_encoded_bytes().contains(&0) {
        return Err(Error { class:"ValueError", message:"stat: embedded null character in path".into() });
    }
    let changed=||sync(format!("runtime home changed during apply: {}",crate::executor_text::os_text(identity.path.as_os_str())));
    let details=fs::symlink_metadata(&identity.path).map_err(|_|changed())?;
    let canonical=fs::canonicalize(&identity.path).map_err(|_|changed())?;
    if !details.is_dir() || details.is_symlink() || canonical!=identity.canonical_path || details.dev()!=identity.device || details.ino()!=identity.inode { return Err(changed()); }
    safe_target(&identity.path,relative)
}
#[cfg(not(unix))]
pub fn capture_home_identity(_home: &Path) -> Result<HomeIdentity, Error> {
    Err(Error {
        class: "Unsupported",
        message: "runtime home identity requires Unix".into(),
    })
}
