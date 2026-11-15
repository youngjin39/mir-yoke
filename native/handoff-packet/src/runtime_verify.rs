//! Installed runtime attestation; legacy admission and complete provider verification.
#![allow(dead_code)] // Also included by runtime-manifest; each binary uses its own entry point.
#![forbid(unsafe_code)]
#![cfg_attr(
    not(test),
    deny(clippy::unwrap_used, clippy::expect_used, clippy::panic)
)]

#[path = "digest.rs"]
mod digest;

use handoff_packet::python_json::{self, Value as PyValue};
use std::collections::BTreeMap;
use std::ffi::OsString;
use std::fs;
use std::io::{self, Write};
use std::path::{Path, PathBuf};

#[derive(Debug)]
pub(crate) enum Failure {
    Finding(&'static str),
    Unsupported,
    Error(String),
    Exception(String),
}

pub(crate) type Result<T> = std::result::Result<T, Failure>;

fn transient(relative: &str) -> bool {
    relative
        .split('/')
        .any(|part| matches!(part, "__pycache__" | ".pytest_cache" | ".ruff_cache"))
        || Path::new(relative)
            .extension()
            .and_then(|s| s.to_str())
            .is_some_and(|s| matches!(s, "pyc" | "pyo"))
}

fn transient_path(relative: &Path) -> bool {
    let text = relative.to_string_lossy();
    if cfg!(windows) {
        transient(&text.replace('\\', "/"))
    } else {
        transient(&text)
    }
}

#[cfg(unix)]
fn mode(_path: &Path, metadata: &fs::Metadata) -> u32 {
    use std::os::unix::fs::MetadataExt;
    metadata.mode() & 0o7777
}

#[cfg(any(windows, test))]
fn windows_mode(path: &Path, readonly: bool, directory: bool) -> u32 {
    let base = if readonly { 0o444 } else { 0o666 };
    // CPython update_st_mode_from_path uses the link's own filename for
    // lstat, and grants execute bits for these four case-insensitive suffixes.
    let executable = path
        .file_name()
        .and_then(|name| name.to_str())
        .and_then(|name| name.rsplit_once('.'))
        .is_some_and(|(_, suffix)| {
            ["exe", "bat", "cmd", "com"]
                .iter()
                .any(|candidate| suffix.eq_ignore_ascii_case(candidate))
        });
    if directory || executable {
        base | 0o111
    } else {
        base
    }
}

#[cfg(windows)]
fn mode(path: &Path, metadata: &fs::Metadata) -> u32 {
    use std::os::windows::fs::MetadataExt;
    windows_mode(
        path,
        metadata.permissions().readonly(),
        metadata.file_attributes() & 0x10 != 0,
    )
}

#[cfg(not(any(unix, windows)))]
fn mode(_path: &Path, _metadata: &fs::Metadata) -> u32 {
    0
}

fn verify(options: &BTreeMap<String, String>) -> Result<()> {
    // The old adapter's special-file admission avoids blocking on a FIFO;
    // runtime-manifest directly uses the complete Python-compatible reader.
    legacy_special_files(Path::new(&options["--runtime-root"]))?;
    verify_paths(
        Path::new(&options["--runtime-root"]),
        Path::new(&options["--manifest"]),
        Some(&options["--source-url"]),
        Some(&options["--source-commit"]),
        Some(&options["--constraints-sha256"]),
    )
}

fn legacy_special_files(root: &Path) -> Result<()> {
    let root = expand_path(root)?;
    let mut pending = vec![root.clone()];
    while let Some(directory) = pending.pop() {
        let Ok(children) = fs::read_dir(directory) else {
            continue;
        };
        for child in children.flatten() {
            let path = child.path();
            if path.strip_prefix(&root).ok().is_some_and(transient_path) {
                continue;
            }
            let Ok(metadata) = fs::symlink_metadata(&path) else {
                continue;
            };
            if metadata.is_dir() {
                pending.push(path);
            } else if !metadata.is_file() && !metadata.file_type().is_symlink() {
                return Err(Failure::Unsupported);
            }
        }
    }
    Ok(())
}

pub(crate) fn verify_paths(
    root: &Path,
    manifest: &Path,
    source_url: Option<&str>,
    source_commit: Option<&str>,
    constraints_sha256: Option<&str>,
) -> Result<()> {
    verify_os(
        root,
        manifest,
        source_url.map(std::ffi::OsStr::new),
        source_commit.map(std::ffi::OsStr::new),
        constraints_sha256.map(std::ffi::OsStr::new),
    )
}

pub(crate) fn verify_os(
    root: &Path,
    manifest: &Path,
    source_url: Option<&std::ffi::OsStr>,
    source_commit: Option<&std::ffi::OsStr>,
    constraints_sha256: Option<&std::ffi::OsStr>,
) -> Result<()> {
    let resolve = |path: &Path| {
        strict_root(path).map_err(|error| match error {
            Failure::Error(_) => Failure::Finding("runtime manifest is unreadable"),
            other => other,
        })
    };
    let root = resolve(&expand_path(root)?)?;
    let manifest = resolve(&expand_path(manifest)?)?;
    if manifest.parent() != Some(root.as_path()) {
        return Err(Failure::Finding(
            "runtime manifest is outside the runtime root",
        ));
    }
    let bytes =
        fs::read(&manifest).map_err(|_| Failure::Finding("runtime manifest is unreadable"))?;
    let text = decode_utf8(&bytes)?;
    let document = python_json::parse(&text).map_err(|error| match error.exception {
        "JSONDecodeError" => Failure::Finding("runtime manifest is unreadable"),
        "ValueError" => Failure::Error(error.to_string()),
        _ => Failure::Exception(format!("{}: {error}", error.exception)),
    })?;
    let result = (|| {
        if !document.is_object()
            || !document
                .get("schema_version")
                .is_some_and(|v| py_equal(v, &PyValue::Bool(true)))
        {
            return Err(Failure::Finding("runtime manifest schema is invalid"));
        }
        for (name, expected) in [
            ("source_url", source_url),
            ("source_commit", source_commit),
            ("constraints_sha256", constraints_sha256),
        ] {
            if let Some(expected) = expected
                && document
                    .get(name)
                    .and_then(PyValue::as_text)
                    .map(|v| &v.codepoints)
                    != Some(&path_codes(Path::new(expected)))
            {
                return Err(Failure::Finding("runtime manifest source evidence differs"));
            }
        }
        let expected = document
            .get("entries")
            .filter(|v| v.is_array())
            .ok_or(Failure::Finding("runtime manifest entries are invalid"))?;
        let actual = PyValue::Array(runtime_entries(&root, &manifest).map_err(
            |error| match error {
                Failure::Error(_) => Failure::Finding("runtime closure is unreadable"),
                other => other,
            },
        )?);
        if !py_equal(&actual, expected) {
            return Err(Failure::Finding("runtime closure differs from manifest"));
        }
        Ok(())
    })();
    drop_json(document);
    result
}

fn drop_json(value: PyValue) {
    let mut pending = vec![value];
    while let Some(value) = pending.pop() {
        match value {
            PyValue::Array(values) => pending.extend(values),
            PyValue::Object(object) => {
                pending.extend(object.into_entries().into_iter().map(|(_, v)| v))
            }
            _ => (),
        }
    }
}

fn py_equal(left: &PyValue, right: &PyValue) -> bool {
    let mut pending = vec![(left, right)];
    while let Some((left, right)) = pending.pop() {
        match (left, right) {
            (PyValue::Array(a), PyValue::Array(b)) if a.len() == b.len() => {
                pending.extend(a.iter().zip(b))
            }
            (PyValue::Object(a), PyValue::Object(b)) if a.len() == b.len() => {
                for (key, value) in a.iter() {
                    let Some((_, other)) = b.iter().find(|(k, _)| *k == key) else {
                        return false;
                    };
                    pending.push((value, other));
                }
            }
            (PyValue::Number(a), PyValue::Number(b)) => {
                // Actual closure numbers are bounded permission bits and schema 1.
                if a.token.parse::<f64>().ok() != b.token.parse::<f64>().ok() {
                    return false;
                }
            }
            (PyValue::Number(n), PyValue::Bool(b)) | (PyValue::Bool(b), PyValue::Number(n)) => {
                if n.token.parse::<f64>().ok() != Some(if *b { 1.0 } else { 0.0 }) {
                    return false;
                }
            }
            _ if left == right => (),
            _ => return false,
        }
    }
    true
}

pub(crate) fn expand_path(path: &Path) -> Result<PathBuf> {
    #[cfg(unix)]
    {
        use std::os::unix::ffi::OsStrExt;
        if path.as_os_str().as_bytes().contains(&0) {
            return Err(Failure::Error("embedded null byte".into()));
        }
    }
    // Preserve surrogateescaped native path bytes throughout filesystem calls.
    let mut components = path.components();
    if components.next().is_some_and(|c| c.as_os_str() == "~") {
        let home = std::env::var_os(if cfg!(windows) { "USERPROFILE" } else { "HOME" });
        #[cfg(unix)]
        let home = home
            .or_else(|| handoff_packet::runtime_account_home(None).map(PathBuf::into_os_string));
        let home = home.ok_or_else(|| {
            Failure::Exception("RuntimeError: Could not determine home directory.".into())
        })?;
        let home = if home.is_empty() {
            PathBuf::from(std::path::MAIN_SEPARATOR.to_string())
        } else {
            PathBuf::from(home)
        };
        return Ok(home.join(components.as_path()));
    }
    if path.as_os_str().to_string_lossy().starts_with('~') {
        #[cfg(unix)]
        {
            use std::os::unix::ffi::{OsStrExt, OsStringExt};
            let bytes = path.as_os_str().as_bytes();
            let end = bytes.iter().position(|b| *b == b'/').unwrap_or(bytes.len());
            let name = std::ffi::OsStr::from_bytes(&bytes[1..end]);
            if let Some(home) = handoff_packet::runtime_account_home(Some(name)) {
                return Ok(home.join(OsString::from_vec(
                    bytes[end..]
                        .iter()
                        .copied()
                        .skip_while(|b| *b == b'/')
                        .collect(),
                )));
            }
        }
        return Err(Failure::Exception(
            "RuntimeError: Could not determine home directory.".into(),
        ));
    }
    Ok(path.to_path_buf())
}

fn decode_utf8(bytes: &[u8]) -> Result<String> {
    let text = std::str::from_utf8(bytes).map_err(|error| {
        let start = error.valid_up_to();
        let len = error.error_len().unwrap_or(bytes.len() - start);
        let reason = match error.error_len() {
            None => "unexpected end of data",
            Some(_) if matches!(bytes[start], 0xc2..=0xf4) => "invalid continuation byte",
            Some(_) => "invalid start byte",
        };
        let portion = if len == 1 {
            format!("byte 0x{:02x} in position {start}", bytes[start])
        } else {
            format!("bytes in position {start}-{}", start + len - 1)
        };
        Failure::Error(format!("'utf-8' codec can't decode {portion}: {reason}"))
    })?;
    Ok(text.replace("\r\n", "\n").replace('\r', "\n"))
}

pub(crate) fn path_codes(path: &Path) -> Vec<u32> {
    #[cfg(unix)]
    {
        use std::os::unix::ffi::OsStrExt;
        let mut codes = Vec::new();
        let mut bytes = path.as_os_str().as_bytes();
        while !bytes.is_empty() {
            match std::str::from_utf8(bytes) {
                Ok(text) => {
                    codes.extend(text.chars().map(u32::from));
                    break;
                }
                Err(error) => {
                    let valid = error.valid_up_to();
                    if let Ok(text) = std::str::from_utf8(&bytes[..valid]) {
                        codes.extend(text.chars().map(u32::from));
                    }
                    let end = valid + error.error_len().unwrap_or(bytes.len() - valid);
                    codes.extend(bytes[valid..end].iter().map(|b| 0xdc00 + u32::from(*b)));
                    bytes = &bytes[end..];
                }
            }
        }
        codes
    }
    #[cfg(windows)]
    {
        use std::os::windows::ffi::OsStrExt;
        char::decode_utf16(path.as_os_str().encode_wide())
            .map(|cp| {
                cp.map(u32::from)
                    .unwrap_or_else(|error| u32::from(error.unpaired_surrogate()))
            })
            .collect()
    }
    #[cfg(not(any(unix, windows)))]
    {
        path.to_string_lossy().chars().map(u32::from).collect()
    }
}

fn quote_codes(codes: &[u32]) -> String {
    let mut output = String::from("\"");
    for cp in codes {
        match *cp {
            34 => output.push_str("\\\""),
            92 => output.push_str("\\\\"),
            8 => output.push_str("\\b"),
            9 => output.push_str("\\t"),
            10 => output.push_str("\\n"),
            12 => output.push_str("\\f"),
            13 => output.push_str("\\r"),
            32..=126 => output.push(char::from_u32(*cp).unwrap_or('?')),
            0..=0xffff => output.push_str(&format!("\\u{cp:04x}")),
            _ => {
                let cp = cp - 0x10000;
                output.push_str(&format!(
                    "\\u{:04x}\\u{:04x}",
                    0xd800 + (cp >> 10),
                    0xdc00 + (cp & 0x3ff)
                ));
            }
        }
    }
    output.push('"');
    output
}

pub(crate) fn quote_path(path: &Path) -> String {
    quote_codes(&path_codes(path))
}

pub(crate) fn path_repr(path: &Path) -> String {
    python_json::parse(&quote_codes(&path_codes(path)))
        .map(|v| v.repr())
        .unwrap_or_else(|_| "''".into())
}

pub(crate) fn strict_root(path: &Path) -> Result<PathBuf> {
    resolve_path(path, true)
}

pub(crate) fn resolve_path(path: &Path, strict: bool) -> Result<PathBuf> {
    let absolute = if path.is_absolute() {
        path.to_path_buf()
    } else {
        std::env::current_dir()
            .map_err(|e| io_failure(path, e))?
            .join(path)
    };
    resolve_components(
        &absolute,
        PathBuf::new(),
        strict,
        &mut std::collections::HashSet::new(),
    )
}

fn resolve_components(
    path: &Path,
    mut resolved: PathBuf,
    strict: bool,
    active: &mut std::collections::HashSet<PathBuf>,
) -> Result<PathBuf> {
    for component in path.components() {
        match component {
            std::path::Component::CurDir => continue,
            std::path::Component::ParentDir => {
                resolved.pop();
                continue;
            }
            std::path::Component::RootDir => {
                resolved.push(component.as_os_str());
                continue;
            }
            std::path::Component::Prefix(_) => {
                resolved.push(component.as_os_str());
                continue;
            }
            std::path::Component::Normal(_) => (),
        }
        resolved.push(component.as_os_str());
        let metadata = match fs::symlink_metadata(&resolved) {
            Ok(metadata) => metadata,
            Err(error) if strict => return Err(io_failure(&resolved, error)),
            Err(_) => continue,
        };
        if metadata.file_type().is_symlink() {
            if !active.insert(resolved.clone()) {
                return Err(Failure::Exception(format!(
                    "RuntimeError: Symlink loop from {}",
                    path_repr(&resolved)
                )));
            }
            let link = resolved.clone();
            let target = fs::read_link(&resolved).map_err(|e| io_failure(&resolved, e))?;
            resolved.pop();
            resolved = resolve_components(&target, resolved, strict, active)?;
            active.remove(&link);
        }
    }
    Ok(resolved)
}

pub(crate) fn io_failure(path: &Path, error: io::Error) -> Failure {
    let message = match error.raw_os_error() {
        Some(code) => {
            let message = match code {
                2 => "No such file or directory",
                13 => "Permission denied",
                20 => "Not a directory",
                21 => "Is a directory",
                1 => "Operation not permitted",
                6 => "Device not configured",
                22 => "Invalid argument",
                36 | 63 => "File name too long",
                _ => return Failure::Error(error.to_string()),
            };
            format!("[Errno {code}] {message}: {}", path_repr(path))
        }
        None => error.to_string(),
    };
    Failure::Error(message)
}

pub(crate) fn runtime_entries(root: &Path, manifest: &Path) -> Result<Vec<PyValue>> {
    let mut pending = vec![root.to_path_buf()];
    let mut entries = Vec::new();
    while let Some(directory) = pending.pop() {
        let Ok(children) = fs::read_dir(directory) else {
            continue;
        };
        let Ok(mut children) = children.collect::<std::io::Result<Vec<_>>>() else {
            continue;
        };
        // os.walk yields sorted directory links before sorted files and descends
        // only after every file in the current directory has been processed.
        children.sort_by_key(|child| {
            (
                !child.path().is_dir(),
                path_codes(Path::new(&child.file_name())),
            )
        });
        let mut subdirectories = Vec::new();
        for child in children {
            let path = child.path();
            let relative = path
                .strip_prefix(root)
                .map_err(|_| Failure::Error("runtime closure is unreadable".into()))?;
            if transient_path(relative) {
                continue;
            }
            let metadata = fs::symlink_metadata(&path).map_err(|e| io_failure(&path, e))?;
            if path.is_dir() && !metadata.file_type().is_symlink() {
                subdirectories.push(path);
                continue;
            }
            if path == manifest {
                continue;
            }
            let mut relative_codes = path_codes(relative);
            if cfg!(windows) {
                for cp in &mut relative_codes {
                    if *cp == u32::from('\\') {
                        *cp = u32::from('/');
                    }
                }
            }
            let mut body = format!(
                "{{\"path\":{},\"mode\":{}",
                quote_codes(&relative_codes),
                mode(&path, &metadata)
            );
            if metadata.file_type().is_symlink() {
                let target = fs::read_link(&path).map_err(|e| io_failure(&path, e))?;
                body.push_str(&format!(
                    ",\"type\":\"symlink\",\"target\":{}}}",
                    quote_codes(&path_codes(&target))
                ));
            } else {
                let contents = fs::read(&path).map_err(|e| io_failure(&path, e))?;
                body.push_str(&format!(
                    ",\"type\":\"file\",\"sha256\":\"{}\"}}",
                    digest::sha256(&contents)
                ));
            }
            entries.push(
                python_json::parse(&body)
                    .map_err(|e| Failure::Exception(format!("{}: {e}", e.exception)))?,
            );
        }
        pending.extend(subdirectories.into_iter().rev());
    }
    entries.sort_by(|a, b| {
        a["path"]
            .as_text()
            .map(|s| &s.codepoints)
            .cmp(&b["path"].as_text().map(|s| &s.codepoints))
    });
    Ok(entries)
}

pub(crate) fn pretty_entries(entries: &[PyValue]) -> String {
    if entries.is_empty() {
        return "[]".into();
    }
    let mut lines = vec!["[".to_owned()];
    for (index, entry) in entries.iter().enumerate() {
        lines.push("  {".into());
        let mut fields: Vec<_> = entry
            .as_object()
            .into_iter()
            .flat_map(|o| o.iter())
            .collect();
        fields.sort_by(|(a, _), (b, _)| a.codepoints.cmp(&b.codepoints));
        for (i, (key, value)) in fields.iter().enumerate() {
            let value = match value {
                PyValue::String(text) => quote_codes(&text.codepoints),
                PyValue::Number(n) => n.token.clone(),
                _ => "null".into(),
            };
            lines.push(format!(
                "    {}: {value}{}",
                quote_codes(&key.codepoints),
                if i + 1 < fields.len() { "," } else { "" }
            ));
        }
        lines.push(format!(
            "  }}{}",
            if index + 1 < entries.len() { "," } else { "" }
        ));
    }
    lines.push("]".into());
    lines.join("\n")
}

fn parse(args: Vec<OsString>) -> Result<BTreeMap<String, String>> {
    let mut options = BTreeMap::new();
    if !args.len().is_multiple_of(2) {
        return Err(Failure::Unsupported);
    }
    for pair in args.as_chunks::<2>().0 {
        let flag = pair[0].to_str().ok_or(Failure::Unsupported)?;
        if !matches!(
            flag,
            "--runtime-root"
                | "--manifest"
                | "--source-url"
                | "--source-commit"
                | "--constraints-sha256"
        ) {
            return Err(Failure::Unsupported);
        }
        let value = pair[1].to_str().ok_or(Failure::Unsupported)?;
        if value.starts_with('-') {
            return Err(Failure::Unsupported);
        }
        options.insert(flag.to_owned(), value.to_owned());
    }
    if options.len() != 5 {
        return Err(Failure::Unsupported);
    }
    Ok(options)
}

fn main() {
    if std::env::args_os().nth(1).as_deref() == Some(std::ffi::OsStr::new("--mir-warmup")) {
        return;
    }
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    if args.len() == 1 && args[0] == "--version" {
        let code = if io::stdout().write_all(b"runtime-verify 0.1.0\n").is_ok() {
            0
        } else {
            64
        };
        std::process::exit(code);
    }
    let code = match parse(args).and_then(|options| verify(&options)) {
        Ok(()) => 0,
        Err(Failure::Unsupported) => 64,
        Err(Failure::Error(message)) => {
            eprintln!("runtime manifest error: {message}");
            2
        }
        Err(Failure::Exception(message)) => {
            eprintln!("{message}");
            1
        }
        Err(Failure::Finding(message)) => {
            let newline = if cfg!(windows) { "\r\n" } else { "\n" };
            let output = format!("runtime manifest error: {message}{newline}");
            if io::stderr().write_all(output.as_bytes()).is_err() {
                64
            } else {
                2
            }
        }
    };
    std::process::exit(code);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn python_numeric_entry_equality() {
        let equal = |left, right| {
            py_equal(
                &python_json::parse(left).unwrap(),
                &python_json::parse(right).unwrap(),
            )
        };
        assert!(equal(r#"{"mode": 1}"#, r#"{"mode": true}"#));
        assert!(equal(r#"{"mode": 420}"#, r#"{"mode": 420.0}"#));
        assert!(equal("true", "1.0"));
        assert!(!equal("420", "true"));
        assert!(!equal("420", r#""420""#));
    }

    #[test]
    fn windows_executable_permissions() {
        for suffix in ["exe", "bat", "cmd", "com", "EXE", "BAT", "CMD", "COM"] {
            let name = format!("tool.{suffix}");
            assert_eq!(windows_mode(Path::new(&name), false, false), 0o777);
            assert_eq!(windows_mode(Path::new(&name), true, false), 0o555);
        }
        assert_eq!(windows_mode(Path::new(".exe"), false, false), 0o777);
        assert_eq!(windows_mode(Path::new("tool.txt"), false, false), 0o666);
        assert_eq!(windows_mode(Path::new("tool.exe.txt"), true, false), 0o444);
        assert_eq!(windows_mode(Path::new("folder"), false, true), 0o777);
    }

    #[test]
    fn transient_boundaries() {
        assert!(transient("folder/__pycache__/file"));
        assert!(transient("a.pyc"));
        assert!(!transient(".pyc"));
        assert!(!transient("a.pyc."));
        assert!(!transient("a.pyc/file"));
    }
}

#[cfg(test)]
mod provider_tests {
    mod unify2_c_recursion {
        include!("../tests/support/unify2_c_recursion.rs");
    }

    use super::*;
    #[test]
    fn provider_python_json_shapes() {
        let directory = tempfile::tempdir().unwrap();
        let manifest = directory.path().join("manifest.json");
        for body in [
            r#"{"schema_version": 1, "entries": [], "extra": NaN}"#,
            r#"{"schema_version": true, "entries": [], "extra": "\ud800"}"#,
            r#"{"schema_version": 1.0, "entries": [], "extra": 1e400}"#,
        ] {
            fs::write(&manifest, body).unwrap();
            assert!(
                verify_paths(directory.path(), &manifest, None, None, None).is_ok(),
                "{body}"
            );
        }
    }
    #[test]
    fn provider_bad_utf8_is_caught_value_error() {
        let directory = tempfile::tempdir().unwrap();
        let manifest = directory.path().join("manifest.json");
        fs::write(&manifest, [0xff]).unwrap();
        assert!(
            matches!(verify_paths(directory.path(), &manifest, None, None, None), Err(Failure::Error(message)) if message == "'utf-8' codec can't decode byte 0xff in position 0: invalid start byte")
        );
    }

    #[cfg(unix)]
    #[test]
    fn provider_closure_bytes_modes_and_surrogate_source() {
        use std::os::unix::{
            ffi::OsStringExt,
            fs::{PermissionsExt, symlink},
        };
        let directory = tempfile::tempdir().unwrap();
        let root = directory.path();
        let file = root.join("file");
        fs::write(&file, [0, 1, 255]).unwrap();
        fs::set_permissions(&file, fs::Permissions::from_mode(0o751)).unwrap();
        symlink("absent", root.join("link")).unwrap();
        fs::create_dir(root.join("directory.pyc")).unwrap();
        fs::write(root.join("directory.pyc/ignored"), "ignored").unwrap();
        let manifest = root.join("manifest.json");
        let source = OsString::from_vec(b"source-\xff".to_vec());
        let entries = runtime_entries(root, &manifest).unwrap();
        assert_eq!(entries.len(), 2);
        fs::write(
            &manifest,
            format!(
                "{{\"schema_version\":1,\"source_url\":{},\"entries\":{}}}",
                quote_path(Path::new(&source)),
                pretty_entries(&entries)
            ),
        )
        .unwrap();
        assert!(verify_os(root, &manifest, Some(&source), None, None).is_ok());
        assert!(matches!(
            verify_os(
                root,
                &manifest,
                Some(std::ffi::OsStr::new("different")),
                None,
                None
            ),
            Err(Failure::Finding("runtime manifest source evidence differs"))
        ));
        fs::set_permissions(&file, fs::Permissions::from_mode(0o750)).unwrap();
        assert!(matches!(
            verify_paths(root, &manifest, None, None, None),
            Err(Failure::Finding("runtime closure differs from manifest"))
        ));
        fs::set_permissions(&file, fs::Permissions::from_mode(0o751)).unwrap();
        fs::write(file, "drift").unwrap();
        assert!(matches!(
            verify_paths(root, &manifest, None, None, None),
            Err(Failure::Finding("runtime closure differs from manifest"))
        ));
    }

    #[cfg(unix)]
    #[test]
    fn provider_long_link_chains_and_actual_cycles() {
        use std::os::unix::fs::symlink;
        let directory = tempfile::tempdir().unwrap();
        let canonical_directory = fs::canonicalize(directory.path()).unwrap();
        let root = canonical_directory.join("runtime");
        fs::create_dir(&root).unwrap();
        let manifest = root.join("manifest.json");
        fs::write(&manifest, r#"{"schema_version":1,"entries":[]}"#).unwrap();
        for index in (0..60).rev() {
            let target = if index == 59 {
                OsString::from("runtime")
            } else {
                OsString::from(format!("chain{}", index + 1))
            };
            symlink(target, directory.path().join(format!("chain{index}"))).unwrap();
        }
        let link = directory.path().join("chain0");
        let canonical_root = fs::canonicalize(&root).unwrap();
        assert_eq!(resolve_path(&link, true).unwrap(), canonical_root);
        assert!(verify_paths(&link, &link.join("manifest.json"), None, None, None).is_ok());
        assert_eq!(
            resolve_path(&link.join("missing/../future.json"), false).unwrap(),
            canonical_root.join("future.json")
        );
        let cycle = canonical_directory.join("cycle");
        symlink("cycle", &cycle).unwrap();
        assert!(
            matches!(verify_paths(&cycle, &manifest, None, None, None), Err(Failure::Exception(message)) if message == format!("RuntimeError: Symlink loop from {}", path_repr(&cycle)))
        );
        assert!(
            matches!(strict_root(&root.join("missing/deeper")), Err(Failure::Error(message)) if message == format!("[Errno 2] No such file or directory: {}", path_repr(&root.join("missing"))))
        );
    }

    #[test]
    fn provider_frozen_python_records() {
        let records: serde_json::Value = serde_json::from_str(include_str!(
            "../../../tests/fixtures/runtime_manifest_verify_1324a3c.json"
        ))
        .unwrap();
        let records = unify2_c_recursion::select(records, "provider", cfg!(windows));
        let directory = tempfile::tempdir().unwrap();
        let manifest = directory.path().join("manifest.json");
        for record in records["records"].as_array().unwrap() {
            let hex = record["body_hex"].as_str().unwrap().as_bytes();
            let bytes: Vec<_> = hex
                .as_chunks::<2>()
                .0
                .iter()
                .map(|pair| u8::from_str_radix(std::str::from_utf8(pair).unwrap(), 16).unwrap())
                .collect();
            fs::write(&manifest, bytes).unwrap();
            let (code, stderr) = match verify_paths(
                directory.path(),
                &manifest,
                Some("url"),
                Some("commit"),
                Some("digest"),
            ) {
                Ok(()) => (0, String::new()),
                Err(Failure::Finding(message)) => {
                    (2, format!("runtime manifest error: {message}\n"))
                }
                Err(Failure::Error(message)) => (2, format!("runtime manifest error: {message}\n")),
                Err(Failure::Exception(message)) => (1, format!("{message}\n")),
                Err(Failure::Unsupported) => (64, String::new()),
            };
            assert_eq!(
                (code, stderr),
                (
                    record["code"].as_i64().unwrap(),
                    record["stderr"].as_str().unwrap().to_owned()
                ),
                "{}",
                record["name"]
            );
        }
    }

    #[cfg(unix)]
    #[test]
    fn provider_non_utf8_paths_and_links() {
        use std::os::unix::{
            ffi::OsStringExt,
            fs::{PermissionsExt, symlink},
        };
        let directory = tempfile::tempdir().unwrap();
        let root = directory
            .path()
            .join(OsString::from_vec(b"runtime-\xff".to_vec()));
        assert_eq!(path_codes(&root).last(), Some(&0xdcff));
        if let Err(error) = fs::create_dir(&root) {
            // APFS rejects surrogateescaped names. The pure encoding assertion
            // still checks the Unix byte boundary on these hosts.
            eprintln!("filesystem cannot create a non-UTF8 name: {error}");
            return;
        }
        let file = root.join(OsString::from_vec(b"file-\xfe".to_vec()));
        fs::write(&file, [0, 1, 255]).unwrap();
        fs::set_permissions(&file, fs::Permissions::from_mode(0o751)).unwrap();
        symlink(
            OsString::from_vec(b"target-\xfd".to_vec()),
            root.join("link"),
        )
        .unwrap();
        let manifest = root.join("manifest.json");
        let entries = runtime_entries(&root, &manifest).unwrap();
        let body = format!(
            "{{\"schema_version\":1,\"entries\":{}}}",
            pretty_entries(&entries)
        );
        assert!(body.contains("\\udcfe"));
        assert!(body.contains("\\udcfd"));
        fs::write(&manifest, body).unwrap();
        assert!(verify_paths(&root, &manifest, None, None, None).is_ok());
        fs::set_permissions(&file, fs::Permissions::from_mode(0o750)).unwrap();
        assert!(matches!(
            verify_paths(&root, &manifest, None, None, None),
            Err(Failure::Finding("runtime closure differs from manifest"))
        ));
    }
}
