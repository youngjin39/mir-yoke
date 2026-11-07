//! Optional, lock-verified native placement for an explicitly selected project.
#![forbid(unsafe_code)]

use crate::mir_core::capabilities::native;
use serde_json::{Value, json};
use std::{
    fs,
    io::{self, Write},
    path::{Path, PathBuf},
};

/// All ambient choices are explicit; a missing target means unsupported.
#[derive(Default)]
pub struct InstallOptions<'a> {
    pub target: Option<&'a str>,
    pub native_artifacts: Option<&'a str>,
    pub source_root: Option<&'a Path>,
    pub local_source: Option<&'a Path>,
    pub artifact_pin: Option<&'a Value>,
    pub home: Option<&'a Path>,
}

pub trait InstallHost {
    fn read(&mut self, url: &str, size: u64) -> io::Result<Vec<u8>> {
        native::read(url, size)
    }
    /// Runs immediately before the atomic replacement, after byte verification.
    fn before_replace(&mut self, _source: &Path, _destination: &Path) -> io::Result<()> {
        Ok(())
    }
}

pub struct LocalHost;
impl InstallHost for LocalHost {}

pub fn provider_pin(source_root: &Path, name: &str, target: &str) -> Option<Value> {
    let lock_path = source_root.join(".mir/capability-lock.json");
    if lock_path.parent()?.is_symlink() || lock_path.is_symlink() {
        return None;
    }
    let lock: Value = serde_json::from_slice(&fs::read(lock_path).ok()?).ok()?;
    let records = lock
        .get("native_artifacts")
        .cloned()
        .unwrap_or_else(|| json!({}));
    native::validate_artifacts(&records, lock.get("plugins")?, false).ok()?;
    records.get(name)?.get("targets")?.get(target).cloned()
}

fn expanded(path: &Path, home: Option<&Path>) -> Option<PathBuf> {
    match path.to_str() {
        Some("~") => home.map(Path::to_path_buf),
        Some(value) if value.starts_with("~/") => home.map(|home| home.join(&value[2..])),
        _ => Some(path.to_owned()),
    }
}

/// Failures preserve an existing destination and prune newly created empty dirs.
pub fn install(
    root: &Path,
    name: &str,
    options: &InstallOptions<'_>,
    host: &mut dyn InstallHost,
) -> Option<Value> {
    let target = options.target?;
    let windows = target.ends_with("windows-msvc");
    if (windows && name == "bootstrap-gate") || options.native_artifacts == Some("0") {
        return None;
    }
    let relative = format!(".mir/bin/{name}{}", if windows { ".exe" } else { "" });
    let mut created = Vec::new();
    let result = (|| -> Option<Value> {
        let (pin, data) = if let Some(source) = options.local_source {
            let source = expanded(source, options.home)?;
            if source.is_symlink() || !source.is_file() {
                return None;
            }
            let data = fs::read(source).ok()?;
            if data.is_empty() {
                return None;
            }
            (
                json!({"size":data.len(),"sha256":crate::digest::sha256(&data)}),
                data,
            )
        } else {
            let pin = match options.artifact_pin {
                Some(pin) => pin.clone(),
                None => provider_pin(options.source_root?, name, target)?,
            };
            let url = pin.get("url")?.as_str()?;
            if let Some(source) = native::local_source(url).ok()?
                && (source.is_symlink() || !source.is_file())
            {
                return None;
            }
            let data = host.read(url, pin.get("size")?.as_u64()?).ok()?;
            (pin, data)
        };
        let destination = root.join(&relative);
        let mut parent = root.to_path_buf();
        for part in [".mir", "bin"] {
            parent.push(part);
            if parent.is_symlink() {
                return None;
            }
            if !parent.exists() {
                fs::create_dir(&parent).ok()?;
                created.push(parent.clone());
            }
        }
        if destination.is_symlink() || (destination.exists() && !destination.is_file()) {
            return None;
        }
        let receipt = || Some(json!({"path":relative,"sha256":pin.get("sha256")?.as_str()?}));
        if destination.is_file()
            && native::verify(&destination, &pin).is_ok()
            && native::is_executable(&destination)
        {
            return receipt();
        }
        let mut temporary = tempfile::Builder::new()
            .prefix(&format!(".{name}."))
            .tempfile_in(&parent)
            .ok()?;
        temporary.write_all(&data).ok()?;
        native::verify(temporary.path(), &pin).ok()?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            temporary
                .as_file()
                .set_permissions(fs::Permissions::from_mode(0o755))
                .ok()?;
        }
        host.before_replace(temporary.path(), &destination).ok()?;
        // persist replaces atomically and owns cleanup on failure on all targets.
        match temporary.persist(&destination) {
            Ok(_) => receipt(),
            Err(error) => {
                drop(error);
                None
            }
        }
    })();
    for parent in created.iter().rev() {
        if fs::read_dir(parent).is_ok_and(|mut entries| entries.next().is_none()) {
            let _ = fs::remove_dir(parent);
        }
    }
    result
}

pub fn install_evaluator(
    root: &Path,
    options: &InstallOptions<'_>,
    host: &mut dyn InstallHost,
) -> Option<Value> {
    install(root, "bootstrap-gate", options, host)
}
pub fn install_runtime_verifier(
    root: &Path,
    options: &InstallOptions<'_>,
    host: &mut dyn InstallHost,
) -> Option<Value> {
    install(root, "runtime-verify", options, host)
}
pub fn install_executor_query(
    root: &Path,
    options: &InstallOptions<'_>,
    host: &mut dyn InstallHost,
) -> Option<Value> {
    install(root, "executor-query", options, host)
}
pub fn install_delegation_gate(
    root: &Path,
    options: &InstallOptions<'_>,
    host: &mut dyn InstallHost,
) -> Option<Value> {
    install(root, "delegation-gate", options, host)
}
pub fn install_project_hooks(
    root: &Path,
    options: &InstallOptions<'_>,
    host: &mut dyn InstallHost,
) -> Option<Value> {
    install(root, "project-hooks", options, host)
}
