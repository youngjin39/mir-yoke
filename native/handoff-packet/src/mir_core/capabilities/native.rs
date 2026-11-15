//! Reached native-artifact primitives. Network reads belong to an injected host.
#![forbid(unsafe_code)]

use serde_json::Value;
use std::{
    ffi::OsString,
    fs,
    io::{self, Read, Write},
    path::{Path, PathBuf},
    process::{Command, Stdio},
    sync::atomic::{AtomicU64, Ordering},
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
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
            .ok_or("native artifact plugin is unknown")?;
        let known = match plugins {
            Value::Object(values) => values.contains_key(plugin),
            Value::Array(values) => values.iter().any(|v| v.as_str() == Some(plugin)),
            Value::String(value) => value.contains(plugin),
            value => {
                let kind = match value {
                    Value::Null => "NoneType",
                    Value::Bool(_) => "bool",
                    Value::Number(n) if n.is_i64() || n.is_u64() => "int",
                    _ => "float",
                };
                return Err(format!("argument of type '{kind}' is not iterable"));
            }
        };
        if !known {
            return Err("native artifact plugin is unknown".into());
        }
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
            let parsed = parsed_url(url);
            let scheme = scheme(&parsed).to_ascii_lowercase();
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
    let parsed = parsed_url(url);
    let parsed_scheme = scheme(&parsed);
    if parsed_scheme.eq_ignore_ascii_case("http") || parsed_scheme.eq_ignore_ascii_case("https") {
        return Ok(None);
    }
    if parsed_scheme.eq_ignore_ascii_case("file") {
        let (_, rest) = parsed.split_once(':').ok_or("invalid file URL")?;
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

fn parsed_url(url: &str) -> String {
    // urllib.parse.urlsplit strips leading C0 controls/space and removes these
    // three controls throughout. Scheme-less paths still use the original URL.
    url.trim_start_matches(|c: char| c <= '\u{20}')
        .replace(['\t', '\r', '\n'], "")
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
    crate::adoption_fs::is_executable(path)
}

/// These callbacks let the host inject faults without supplying filesystem mutations.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum PlacementMutation {
    CreateDirectory,
    CreateTemporary,
    SetExecutable,
    PublishArtifact,
    PublishMetadata,
    RemoveInstalled,
    RemoveTemporary,
    RemoveDirectory,
}

/// Transport and best-effort warmup remain host-owned; placement itself is local.
pub trait ArtifactHost {
    fn read(&mut self, url: &str, size: u64) -> Result<Vec<u8>, String>;
    fn warm(&mut self, _path: &Path) {}
    fn before_mutation(&mut self, _site: PlacementMutation, _path: &Path) -> io::Result<()> {
        Ok(())
    }
    fn temporary_name(&mut self) -> OsString {
        static COUNTER: AtomicU64 = AtomicU64::new(0);
        let time = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos();
        format!(
            "tmp{:x}{time:x}{:x}",
            std::process::id(),
            COUNTER.fetch_add(1, Ordering::Relaxed)
        )
        .into()
    }
}

/// This host deliberately has no network transport. Callers may inject one.
pub struct LocalArtifactHost;
impl ArtifactHost for LocalArtifactHost {
    fn read(&mut self, url: &str, size: u64) -> Result<Vec<u8>, String> {
        let path =
            local_source(url)?.ok_or("network artifact reader must be supplied by the host")?;
        read(url, size).map_err(|error| placement_io(&error, &path))
    }
    fn warm(&mut self, path: &Path) {
        let Ok(mut child) = Command::new(path)
            .arg("--mir-warmup")
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
        else {
            return;
        };
        let deadline = Instant::now() + Duration::from_secs(30);
        loop {
            match child.try_wait() {
                Ok(Some(_)) => return,
                Ok(None) if Instant::now() < deadline => {
                    std::thread::sleep(Duration::from_millis(10));
                }
                _ => {
                    let _ = child.kill();
                    let _ = child.wait();
                    return;
                }
            }
        }
    }
}

/// A missing target means the caller's host has no supported native target.
pub struct PlacementOptions<'a> {
    pub target: Option<&'a str>,
    pub disabled: bool,
}

#[derive(Debug)]
pub struct PlacementError {
    pub warnings: Vec<String>,
    pub message: String,
}

fn placement_io(error: &io::Error, path: &Path) -> String {
    crate::executor_brief_profile::python_os_error_message(error, path)
}
fn cleanup_io(error: io::Error, path: &Path) -> String {
    let class = match error.kind() {
        io::ErrorKind::NotFound => "FileNotFoundError",
        io::ErrorKind::PermissionDenied => "PermissionError",
        io::ErrorKind::IsADirectory => "IsADirectoryError",
        io::ErrorKind::NotADirectory => "NotADirectoryError",
        _ => "OSError",
    };
    format!("{class}: {}", placement_io(&error, path))
}

fn entries<'a>(
    plugin: &'a str,
    records: &'a crate::python_json::Value,
    target: &'a str,
) -> impl Iterator<Item = (&'a str, PathBuf, Value)> {
    records
        .as_object()
        .into_iter()
        .flat_map(|r| r.iter())
        .filter_map(move |(name, record)| {
            let name = name.as_str()?;
            let record = record.to_serde();
            if record["plugin"].as_str() != Some(plugin) {
                return None;
            }
            let mut relative = record["install_path"].as_str()?.to_owned();
            if target.ends_with("windows-msvc") {
                relative.push_str(".exe");
            }
            Some((
                name,
                PathBuf::from(relative),
                record["targets"][target].clone(),
            ))
        })
}

fn verify_for_warm(root: &Path, path: &Path, pin: &Value) -> io::Result<bool> {
    let mut file = crate::adoption_fs::parent(root, path)?.open_file()?;
    let metadata = file.metadata()?;
    if !metadata.is_file() || Some(metadata.len()) != pin["size"].as_u64() {
        return Ok(false);
    }
    let mut data = Vec::new();
    file.read_to_end(&mut data)?;
    Ok(Some(crate::digest::sha256(&data).as_str()) == pin["sha256"].as_str())
}

/// Only verified Windows cache copies are warmed; failures remain best effort.
pub fn warm_artifacts(
    root: &Path,
    plugin: &str,
    records: &crate::python_json::Value,
    target: Option<&str>,
    host: &mut impl ArtifactHost,
) {
    let Some(target) = target.filter(|t| t.ends_with("windows-msvc")) else {
        return;
    };
    for (_, relative, pin) in entries(plugin, records, target) {
        let path = root.join(relative);
        // Verify through a pinned descriptor, refusing links in every component.
        // Unverifiable files skip warm just like any other verification failure.
        if !pin.is_null() && verify_for_warm(root, &path, &pin).unwrap_or(false) {
            host.warm(&path);
        }
    }
}

struct PlacementTemporary {
    path: PathBuf,
    staged: crate::adoption_fs::StagedFile,
}
fn temporary(
    root: &Path,
    destination: &Path,
    host: &mut impl ArtifactHost,
) -> Result<PlacementTemporary, String> {
    let directory = destination
        .parent()
        .ok_or("native artifact has no parent")?;
    for _ in 0..100 {
        let path = directory.join(host.temporary_name());
        // Use the reference destination directory, pinned by descriptor.
        let staged = match crate::adoption_fs::StagedFile::create_with(root, &path, |actual| {
            host.before_mutation(PlacementMutation::CreateTemporary, actual)
        }) {
            Ok(staged) => staged,
            Err(error) if error.kind() == io::ErrorKind::AlreadyExists => continue,
            Err(error) => return Err(placement_io(&error, &path)),
        };
        return Ok(PlacementTemporary { path, staged });
    }
    Err("No usable temporary file name found".into())
}
fn exists(path: &Path) -> Result<bool, String> {
    match fs::symlink_metadata(path) {
        Ok(_) => Ok(true),
        // pathlib's exists/is_symlink ignore these traversal failures.
        Err(error) if crate::adoption_fs::missing_metadata(&error) => Ok(false),
        Err(error) => Err(placement_io(&error, path)),
    }
}
fn publish(
    root: &Path,
    temporary: &mut PlacementTemporary,
    data: &[u8],
    destination: &Path,
    site: PlacementMutation,
    host: &mut impl ArtifactHost,
) -> Result<crate::adoption_fs::Parent, String> {
    let source = &temporary.path;
    let rename_error = |e: io::Error| {
        format!(
            "{} -> {}",
            placement_io(&e, source),
            crate::executor_execute::repr(&destination.display().to_string())
        )
    };
    host.before_mutation(site, destination)
        .map_err(rename_error)?;
    if temporary
        .staged
        .contents(data.len())
        .map_err(|e| placement_io(&e, source))?
        != data
    {
        return Err(format!(
            "native artifact integrity mismatch: {}",
            source.file_name().unwrap_or_default().to_string_lossy()
        ));
    }
    temporary
        .staged
        .publish(root, destination)
        .map_err(rename_error)
}
fn remove(
    parent: &crate::adoption_fs::Parent,
    path: &Path,
    directory: bool,
    identity: crate::adoption_fs::Identity,
    site: PlacementMutation,
    host: &mut impl ArtifactHost,
) -> Result<(), String> {
    host.before_mutation(site, path)
        .map_err(|e| cleanup_io(e, path))?;
    match parent.object_identity(directory) {
        Ok(Some(current)) if current == identity => (),
        Err(error) if !directory && error.kind() == io::ErrorKind::NotFound => return Ok(()),
        Err(error) => return Err(cleanup_io(error, path)),
        _ => {
            return Err(cleanup_io(
                io::Error::other("source changed during cleanup"),
                path,
            ));
        }
    }
    match parent.unlink(&parent.name, directory) {
        Ok(()) => Ok(()),
        Err(error) if !directory && error.kind() == io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(cleanup_io(error, path)),
    }
}

fn directory_empty(root: &Path, path: &Path) -> Result<bool, String> {
    crate::adoption_fs::parent(root, path)
        .and_then(|parent| parent.directory_empty())
        .map_err(|e| cleanup_io(e, path))
}

fn normalized_root(root: &Path) -> Result<PathBuf, String> {
    let mut normalized = PathBuf::new();
    for component in root.components() {
        match component {
            std::path::Component::ParentDir => {
                normalized.pop();
            }
            std::path::Component::CurDir => (),
            component => {
                normalized.push(component.as_os_str());
                if fs::symlink_metadata(&normalized).is_ok_and(|m| m.is_symlink()) {
                    return Err("linked native artifact parent".into());
                }
            }
        }
    }
    Ok(normalized)
}

/// Return Python warning lines; cleanup exceptions propagate instead of becoming skips.
/// All creation, publication and rollback use descriptor-relative adoption operations.
pub fn place_artifacts(
    root: &Path,
    plugin: &str,
    records: &crate::python_json::Value,
    options: PlacementOptions<'_>,
    host: &mut impl ArtifactHost,
) -> Result<Vec<String>, PlacementError> {
    let mut warnings = Vec::new();
    if options.disabled {
        return Ok(warnings);
    }
    let Some(target) = options.target else {
        return Ok(warnings);
    };
    let absolute_root = if root.is_absolute() {
        root.to_owned()
    } else {
        std::env::current_dir()
            .map_err(|e| PlacementError {
                warnings: vec![],
                message: cleanup_io(e, root),
            })?
            .join(root)
    };
    let normalized = normalized_root(&absolute_root);
    let root = normalized.as_ref().unwrap_or(&absolute_root);
    for (name, relative, pin) in entries(plugin, records, target) {
        let destination = root.join(&relative);
        let mut temporary_file: Option<PlacementTemporary> = None;
        let mut created = Vec::new();
        let mut installed = None;
        let result = (|| -> Result<(), String> {
            if let Err(error) = &normalized {
                return Err(error.clone());
            }
            if pin.is_null() {
                return Err(format!("no target {target}"));
            }
            if exists(&destination)? {
                return Err("install path already exists".into());
            }
            let mut directory = root.clone();
            if let Some(parent) = relative.parent() {
                for part in parent.components() {
                    directory.push(part);
                    match fs::symlink_metadata(&directory) {
                        Ok(metadata) if metadata.is_symlink() => {
                            return Err("linked native artifact parent".into());
                        }
                        Ok(_) => (),
                        Err(error) if error.kind() == io::ErrorKind::NotFound => {
                            let pinned = crate::adoption_fs::parent(root, &directory)
                                .map_err(|e| placement_io(&e, &directory))?;
                            host.before_mutation(PlacementMutation::CreateDirectory, &directory)
                                .map_err(|e| placement_io(&e, &directory))?;
                            crate::adoption_fs::mkdir(root, &directory, 0o777)
                                .map_err(|e| placement_io(&e, &directory))?;
                            let identity = pinned
                                .object_identity(true)
                                .map_err(|e| placement_io(&e, &directory))?
                                .ok_or("native artifact directory changed after creation")?;
                            created.push((directory.clone(), pinned, identity));
                        }
                        Err(error) => return Err(placement_io(&error, &directory)),
                    }
                }
            }
            let data = host.read(
                pin["url"]
                    .as_str()
                    .ok_or("invalid native artifact target pin")?,
                pin["size"]
                    .as_u64()
                    .ok_or("invalid native artifact target pin")?,
            )?;
            let temp = temporary(root, &destination, host)?;
            let temp_path = temp.path.clone();
            temporary_file = Some(temp);
            let temp = temporary_file
                .as_mut()
                .ok_or("missing native artifact temporary")?;
            temp.staged
                .file
                .write_all(&data)
                .map_err(|e| placement_io(&e, &temp_path))?;
            let written = temp
                .staged
                .contents(data.len())
                .map_err(|e| placement_io(&e, &temp_path))?;
            if Some(written.len() as u64) != pin["size"].as_u64()
                || Some(crate::digest::sha256(&written).as_str()) != pin["sha256"].as_str()
            {
                return Err(format!(
                    "native artifact integrity mismatch: {}",
                    temp_path.file_name().unwrap_or_default().to_string_lossy()
                ));
            }
            host.before_mutation(PlacementMutation::SetExecutable, &temp.staged.path)
                .map_err(|e| placement_io(&e, &temp_path))?;
            if temp
                .staged
                .contents(data.len())
                .map_err(|e| placement_io(&e, &temp_path))?
                != data
            {
                return Err(format!(
                    "native artifact integrity mismatch: {}",
                    temp_path.file_name().unwrap_or_default().to_string_lossy()
                ));
            }
            crate::adoption_fs::set_mode(&temp.staged.file, 0o755)
                .map_err(|e| placement_io(&e, &temp_path))?;
            let identity = temp
                .staged
                .identity()
                .map_err(|e| placement_io(&e, &temp_path))?;
            let parent = publish(
                root,
                temp,
                &data,
                &destination,
                PlacementMutation::PublishArtifact,
                host,
            )?;
            installed = Some((parent, identity));
            if plugin == "mir-mcp" && name == "mir-mcp" {
                let metadata = root.join("bin/native-artifacts.json");
                if exists(&metadata)? {
                    return Err("native artifact metadata already exists".into());
                }
                let temp = temporary(root, &metadata, host)?;
                let metadata_temp = temp.path.clone();
                temporary_file = Some(temp);
                let value = serde_json::json!({name:{"sha256":pin["sha256"],"size":pin["size"],"target":target}});
                let body = crate::executor_policy_query::ascii_json_text(
                    &crate::mir_cli::r#loop::json_text(&value),
                );
                let temp = temporary_file
                    .as_mut()
                    .ok_or("missing metadata temporary")?;
                temp.staged
                    .file
                    .write_all(body.as_bytes())
                    .map_err(|e| placement_io(&e, &metadata_temp))?;
                publish(
                    root,
                    temp,
                    body.as_bytes(),
                    &metadata,
                    PlacementMutation::PublishMetadata,
                    host,
                )?;
            }
            if target.ends_with("windows-msvc") {
                host.warm(&destination);
            }
            Ok(())
        })();
        let mut rollback_error = None;
        if let Err(error) = result {
            if let Some((parent, identity)) = installed {
                rollback_error = remove(
                    &parent,
                    &destination,
                    false,
                    identity,
                    PlacementMutation::RemoveInstalled,
                    host,
                )
                .err();
            }
            let behavior = if plugin == "mir-lifecycle-hooks" {
                "; lifecycle native runtime unavailable: SessionStart/UserPromptSubmit stay silent (exit 0), PreToolUse and Stop emit a note (stderr, exit 0)"
            } else {
                "; native runtime unavailable"
            };
            if rollback_error.is_none() {
                warnings.push(format!(
                    "Warning: native artifact {name} skipped: {error}{behavior}"
                ));
            }
        }
        if let Some(temp) = temporary_file {
            let result = host
                .before_mutation(PlacementMutation::RemoveTemporary, &temp.path)
                .and_then(|()| temp.staged.remove());
            temp.staged.keep();
            if let Err(error) = result {
                return Err(PlacementError {
                    warnings,
                    message: cleanup_io(error, &temp.path),
                });
            }
        }
        for (path, parent, identity) in created.iter().rev() {
            let result = directory_empty(root, path).and_then(|empty| {
                if empty {
                    remove(
                        parent,
                        path,
                        true,
                        *identity,
                        PlacementMutation::RemoveDirectory,
                        host,
                    )
                } else {
                    Ok(())
                }
            });
            if let Err(message) = result {
                return Err(PlacementError { warnings, message });
            }
        }
        if let Some(message) = rollback_error {
            return Err(PlacementError { warnings, message });
        }
    }
    Ok(warnings)
}
