//! Byte-compatible installed runtime attestation; unsupported inputs request Python.
#![forbid(unsafe_code)]
#![deny(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

mod digest;

use serde_json::{Value, json};
use std::collections::BTreeMap;
use std::ffi::OsString;
use std::fs;
use std::io::{self, Write};
use std::path::{Path, PathBuf};

#[derive(Debug)]
enum Failure {
    Finding(&'static str),
    Unsupported,
}

type Result<T> = std::result::Result<T, Failure>;

fn expand(path: &str) -> Result<PathBuf> {
    if path == "~" || path.starts_with("~/") || cfg!(windows) && path.starts_with("~\\") {
        let home = std::env::var_os(if cfg!(windows) { "USERPROFILE" } else { "HOME" })
            .ok_or(Failure::Unsupported)?;
        if home.is_empty() {
            return Err(Failure::Unsupported);
        }
        Ok(PathBuf::from(home).join(path.get(2..).unwrap_or("")))
    } else if path.starts_with('~') {
        // Named-user expansion is host-specific; let the reference resolve it.
        Err(Failure::Unsupported)
    } else {
        Ok(PathBuf::from(path))
    }
}

fn transient(relative: &str) -> bool {
    relative
        .split('/')
        .any(|part| matches!(part, "__pycache__" | ".pytest_cache" | ".ruff_cache"))
        || Path::new(relative)
            .extension()
            .and_then(|s| s.to_str())
            .is_some_and(|s| matches!(s, "pyc" | "pyo"))
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

fn entry(path: &Path, relative: &str, metadata: &fs::Metadata) -> Result<Value> {
    let mut value = json!({"path": relative, "mode": mode(path, metadata)});
    if metadata.file_type().is_symlink() {
        let target =
            fs::read_link(path).map_err(|_| Failure::Finding("runtime closure is unreadable"))?;
        value["type"] = json!("symlink");
        value["target"] = json!(target.to_str().ok_or(Failure::Unsupported)?);
    } else if metadata.is_file() {
        let contents =
            fs::read(path).map_err(|_| Failure::Finding("runtime closure is unreadable"))?;
        value["type"] = json!("file");
        value["sha256"] = json!(digest::sha256(&contents));
    } else {
        // Reading devices or FIFOs can block; the reference owns exotic entries.
        return Err(Failure::Unsupported);
    }
    Ok(value)
}

fn walk(root: &Path, current: &Path, manifest: &Path, entries: &mut Vec<Value>) -> Result<()> {
    let directory = match fs::read_dir(current) {
        Ok(directory) => directory,
        // os.walk silently skips directories whose scandir fails.
        Err(_) => return Ok(()),
    };
    let mut children = Vec::new();
    for child in directory {
        // Python's scandir iteration can discard a directory on error. Fallback
        // rather than attest a partial directory under uncertain I/O behavior.
        children.push(child.map_err(|_| Failure::Unsupported)?.path());
    }
    children.sort();
    let mut directories = Vec::new();
    let mut files = Vec::new();
    for path in children {
        let relative = path.strip_prefix(root).map_err(|_| Failure::Unsupported)?;
        let text = relative.to_str().ok_or(Failure::Unsupported)?;
        let relative = if cfg!(windows) {
            text.replace('\\', "/")
        } else {
            text.to_owned()
        };
        if transient(&relative) {
            continue;
        }
        let metadata = fs::symlink_metadata(&path)
            .map_err(|_| Failure::Finding("runtime closure is unreadable"))?;
        #[cfg(windows)]
        {
            use std::os::windows::fs::MetadataExt;
            // Rust normalizes absolute link namespaces and classifies junctions
            // differently from Python. Let Python attest every reparse entry.
            if metadata.file_attributes() & 0x400 != 0 {
                return Err(Failure::Unsupported);
            }
        }
        if path.is_dir() {
            if metadata.file_type().is_symlink() {
                entries.push(entry(&path, &relative, &metadata)?);
            } else {
                directories.push(path);
            }
        } else {
            files.push((path, relative, metadata));
        }
    }
    for (path, relative, metadata) in files {
        if path != manifest {
            entries.push(entry(&path, &relative, &metadata)?);
        }
    }
    for path in directories {
        walk(root, &path, manifest, entries)?;
    }
    Ok(())
}

// Python equality admits true == 1 == 1.0, including nested manifest entries.
fn python_equal(left: &Value, right: &Value) -> bool {
    match (left, right) {
        (Value::Array(a), Value::Array(b)) => {
            a.len() == b.len() && a.iter().zip(b).all(|(a, b)| python_equal(a, b))
        }
        (Value::Object(a), Value::Object(b)) => {
            a.len() == b.len()
                && a.iter()
                    .all(|(key, value)| b.get(key).is_some_and(|b| python_equal(value, b)))
        }
        (Value::Number(a), Value::Number(b)) => {
            // The native side contains only schema 1 and permission bits, so
            // its integers are exactly representable by an IEEE-754 double.
            a.as_f64() == b.as_f64()
        }
        (Value::Bool(a), Value::Number(b)) | (Value::Number(b), Value::Bool(a)) => {
            b.as_f64() == Some(if *a { 1.0 } else { 0.0 })
        }
        _ => left == right,
    }
}

fn verify(options: &BTreeMap<String, String>) -> Result<()> {
    let root = expand(&options["--runtime-root"])?;
    let manifest = expand(&options["--manifest"])?;
    let canonical = |path| {
        fs::canonicalize(path).map_err(|error| match error.kind() {
            io::ErrorKind::NotFound
            | io::ErrorKind::PermissionDenied
            | io::ErrorKind::NotADirectory => Failure::Finding("runtime manifest is unreadable"),
            // Python versions differ on symlink-loop and invalid-path exception
            // classes. The reference owns errors outside the ordinary closure.
            _ => Failure::Unsupported,
        })
    };
    let root = canonical(root)?;
    let manifest = canonical(manifest)?;
    if manifest.parent() != Some(root.as_path()) {
        return Err(Failure::Finding(
            "runtime manifest is outside the runtime root",
        ));
    }
    let bytes =
        fs::read(&manifest).map_err(|_| Failure::Finding("runtime manifest is unreadable"))?;
    let text = std::str::from_utf8(&bytes).map_err(|_| Failure::Unsupported)?;
    let document: Value = serde_json::from_str(text).map_err(|error| {
        // Python accepts non-finite numbers, arbitrary integers and lone
        // surrogates; serde cannot represent all of them. Preserve fallback.
        if error.is_data()
            || text.contains("\\u")
            || text.contains("NaN")
            || text.contains("Infinity")
            || error.to_string().contains("recursion limit")
            || error.to_string().contains("number out of range")
        {
            Failure::Unsupported
        } else {
            Failure::Finding("runtime manifest is unreadable")
        }
    })?;
    if !document.is_object()
        || !document
            .get("schema_version")
            .is_some_and(|v| python_equal(v, &json!(1)))
    {
        return Err(Failure::Finding("runtime manifest schema is invalid"));
    }
    for (argument, field) in [
        ("--source-url", "source_url"),
        ("--source-commit", "source_commit"),
        ("--constraints-sha256", "constraints_sha256"),
    ] {
        if document.get(field) != Some(&json!(options[argument])) {
            return Err(Failure::Finding("runtime manifest source evidence differs"));
        }
    }
    let expected = document
        .get("entries")
        .filter(|v| v.is_array())
        .ok_or(Failure::Finding("runtime manifest entries are invalid"))?;
    let mut entries = Vec::new();
    walk(&root, &root, &manifest, &mut entries)?;
    entries.sort_by(|a, b| a["path"].as_str().cmp(&b["path"].as_str()));
    if !python_equal(&Value::Array(entries), expected) {
        return Err(Failure::Finding("runtime closure differs from manifest"));
    }
    Ok(())
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
        assert!(python_equal(&json!({"mode": 1}), &json!({"mode": true})));
        assert!(python_equal(&json!({"mode": 420}), &json!({"mode": 420.0})));
        assert!(python_equal(&json!(true), &json!(1.0)));
        assert!(!python_equal(&json!(420), &json!(true)));
        assert!(!python_equal(&json!(420), &json!("420")));
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
