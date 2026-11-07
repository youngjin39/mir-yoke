//! Reached native-artifact primitives. Network reads belong to an injected host.
#![forbid(unsafe_code)]

use serde_json::Value;
use std::{
    fs,
    io::{self, Read},
    path::{Path, PathBuf},
};

pub fn host_target(system: &str, machine: &str) -> Option<String> {
    let machine = machine.to_lowercase();
    let arch = match machine.as_str() {
        "arm64" | "aarch64" => "aarch64",
        "amd64" | "x86_64" => "x86_64",
        _ => return None,
    };
    let suffix = match system {
        "Darwin" => "apple-darwin",
        "Linux" => "unknown-linux-gnu",
        "Windows" if arch == "x86_64" => "pc-windows-msvc",
        _ => return None,
    };
    Some(format!("{arch}-{suffix}"))
}

fn drive(path: &str) -> bool {
    path.starts_with("\\\\")
        || (path.as_bytes().get(1) == Some(&b':') && path.as_bytes()[0].is_ascii_alphabetic())
}

fn scheme(url: &str) -> &str {
    match url.split_once(':') {
        Some((head, _))
            if head.starts_with(|c: char| c.is_ascii_alphabetic())
                && head
                    .chars()
                    .all(|c| c.is_ascii_alphanumeric() || matches!(c, '+' | '-' | '.')) =>
        {
            head
        }
        _ => "",
    }
}

/// External records preserve unknown target names but reject unknown record fields.
pub fn validate_artifacts(records: &Value, plugins: &Value, portable: bool) -> Result<(), String> {
    let records = records
        .as_object()
        .ok_or("native artifacts must be an object")?;
    let mut paths: Vec<(&str, &str)> = Vec::new();
    for (name, record) in records {
        let record = record
            .as_object()
            .filter(|_| !name.is_empty())
            .ok_or("invalid native artifact entry")?;
        if record.len() != 3
            || !["plugin", "install_path", "targets"]
                .iter()
                .all(|k| record.contains_key(*k))
        {
            return Err("invalid native artifact fields".into());
        }
        let plugin = record["plugin"]
            .as_str()
            .filter(|p| match plugins {
                Value::Object(values) => values.contains_key(*p),
                Value::Array(values) => values.iter().any(|v| v.as_str() == Some(*p)),
                Value::String(value) => value.contains(*p),
                _ => false,
            })
            .ok_or("native artifact plugin is unknown")?;
        let path = record["install_path"]
            .as_str()
            .filter(|p| {
                !p.is_empty()
                    && !p.contains('\\')
                    && !drive(p)
                    && !p.starts_with('/')
                    && !p.ends_with(".exe")
                    && !p.split('/').any(|s| matches!(s, "" | "." | ".."))
            })
            .ok_or("unsafe native artifact install_path")?;
        if paths.iter().any(|(p, s)| {
            *p == plugin
                && (*s == path
                    || s.starts_with(&format!("{path}/"))
                    || path.starts_with(&format!("{s}/")))
        }) {
            return Err("overlapping native artifact install paths".into());
        }
        paths.push((plugin, path));
        let targets = record["targets"]
            .as_object()
            .ok_or("native artifact targets must be an object")?;
        for pin in targets.values() {
            let pin = pin
                .as_object()
                .ok_or("invalid native artifact target pin")?;
            if pin.len() != 3
                || !["url", "sha256", "size"]
                    .iter()
                    .all(|k| pin.contains_key(*k))
            {
                return Err("invalid native artifact target pin".into());
            }
            let url = pin["url"]
                .as_str()
                .filter(|s| !s.is_empty())
                .ok_or("invalid native artifact target pin")?;
            if !pin["sha256"].as_str().is_some_and(|s| {
                s.len() == 64
                    && s.bytes()
                        .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
            }) || !pin["size"].as_u64().is_some_and(|n| n > 0)
            {
                return Err("invalid native artifact target pin".into());
            }
            let scheme = scheme(url).to_ascii_lowercase();
            if !matches!(scheme.as_str(), "" | "file" | "http" | "https") && !drive(url) {
                return Err("unsupported native artifact URL".into());
            }
            if portable
                && (scheme == "file" || url.starts_with('/') || drive(url) || url.contains('\\'))
            {
                return Err("native artifact source is not portable".into());
            }
        }
    }
    Ok(())
}

fn unquote(value: &str) -> String {
    let bytes = value.as_bytes();
    let mut result = Vec::new();
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'%'
            && i + 2 < bytes.len()
            && let (Some(a), Some(b)) = (
                (bytes[i + 1] as char).to_digit(16),
                (bytes[i + 2] as char).to_digit(16),
            )
        {
            result.push((a * 16 + b) as u8);
            i += 3;
            continue;
        }
        result.push(bytes[i]);
        i += 1;
    }
    // urllib.parse.unquote explicitly replaces invalid UTF-8.
    String::from_utf8_lossy(&result).into_owned()
}

/// None denotes a network URL; the caller must supply its own transport.
pub fn local_source(url: &str) -> Result<Option<PathBuf>, String> {
    let parsed_scheme = scheme(url);
    if parsed_scheme.eq_ignore_ascii_case("http") || parsed_scheme.eq_ignore_ascii_case("https") {
        return Ok(None);
    }
    if parsed_scheme.eq_ignore_ascii_case("file") {
        let (_, rest) = url.split_once(':').ok_or("invalid file URL")?;
        let path = if let Some(rest) = rest.strip_prefix("//") {
            let (host, path) = rest.split_once('/').unwrap_or((rest, ""));
            if !matches!(host, "" | "localhost") {
                return Err("native artifact file URL must be local".into());
            }
            format!("/{path}")
        } else {
            rest.to_owned()
        };
        let path = unquote(path.split(['?', '#']).next().unwrap_or(""));
        #[cfg(windows)]
        let path = if path.starts_with('/') && drive(&path[1..]) {
            path[1..].to_owned()
        } else {
            path
        };
        return Ok(Some(PathBuf::from(path)));
    }
    Ok(Some(PathBuf::from(url)))
}

pub fn read(url: &str, size: u64) -> io::Result<Vec<u8>> {
    let path = local_source(url)
        .map_err(io::Error::other)?
        .ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::Unsupported,
                "network artifact reader must be supplied by the host",
            )
        })?;
    let mut data = Vec::new();
    fs::File::open(path)?
        .take(size.saturating_add(1))
        .read_to_end(&mut data)?;
    Ok(data)
}

pub fn verify(path: &Path, pin: &Value) -> Result<(), String> {
    let mismatch = || {
        format!(
            "native artifact integrity mismatch: {}",
            path.file_name().and_then(|s| s.to_str()).unwrap_or("")
        )
    };
    let metadata = match fs::symlink_metadata(path) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Err(mismatch()),
        Err(error) => return Err(error.to_string()),
    };
    if !metadata.is_file() || Some(metadata.len()) != pin["size"].as_u64() {
        return Err(mismatch());
    }
    let data = fs::read(path).map_err(|e| e.to_string())?;
    if Some(crate::digest::sha256(&data).as_str()) != pin["sha256"].as_str() {
        return Err(mismatch());
    }
    Ok(())
}

pub fn is_executable(path: &Path) -> bool {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::metadata(path).is_ok_and(|m| m.permissions().mode() & 0o111 != 0)
    }
    #[cfg(not(unix))]
    {
        path.is_file()
    }
}
