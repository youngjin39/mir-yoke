//! Optional, lock-verified native placement for an explicitly selected project.
#![forbid(unsafe_code)]

use crate::adoption_fs;
use crate::mir_core::capabilities::native;
use serde_json::{Value, json};
use std::{
    ffi::OsStr,
    fs,
    io::{self, Write},
    path::{Component, Path, PathBuf},
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
    /// Resolve an account without consulting a consumer repository.
    fn account_home(&mut self, name: Option<&OsStr>) -> Option<PathBuf> {
        #[cfg(unix)]
        {
            crate::runtime_account_home(name)
        }
        #[cfg(not(unix))]
        {
            let _ = name;
            None
        }
    }
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
    let (lock, _) = super::bootstrap_adoption::load_json_bytes(
        &lock_path,
        &mut super::bootstrap_adoption::LocalHost,
    )
    .ok()?;
    let records = lock
        .get("native_artifacts")
        .cloned()
        .unwrap_or_else(|| json!({}));
    native::validate_artifacts(&records, lock.get("plugins")?, false).ok()?;
    records.get(name)?.get("targets")?.get(target).cloned()
}

fn expanded(path: &Path, home: Option<&Path>, host: &mut dyn InstallHost) -> Option<PathBuf> {
    // pathlib normalizes separators and dot components before expanduser.
    // Slicing "~//file" as text would join an absolute "/file" to HOME.
    let normalized: PathBuf = path
        .components()
        .filter(|part| !matches!(part, Component::CurDir))
        .collect();
    let mut parts = normalized.components();
    if let Some(Component::Normal(first)) = parts.next()
        && first.as_encoded_bytes().starts_with(b"~")
    {
        let first = first.to_str()?;
        let home = if first == "~" {
            home.map(Path::to_path_buf)
                .or_else(|| host.account_home(None))?
        } else {
            host.account_home(Some(OsStr::new(&first[1..])))?
        };
        return Some(home.join(parts.as_path()));
    }
    Some(normalized)
}

/// Failures preserve an existing destination and prune newly created empty dirs.
pub fn install(
    root: &Path,
    name: &str,
    options: &InstallOptions<'_>,
    host: &mut dyn InstallHost,
) -> Option<Value> {
    // The public helper accepts a name, but placement always owns one basename.
    if name.is_empty() || name.contains(['/', '\\']) || matches!(name, "." | "..") {
        return None;
    }
    let target = options.target?;
    let windows = target.ends_with("windows-msvc");
    if (windows && name == "bootstrap-gate") || options.native_artifacts == Some("0") {
        return None;
    }
    let root = root.canonicalize().ok()?;
    let relative = format!(".mir/bin/{name}{}", if windows { ".exe" } else { "" });
    let mut created = Vec::new();
    let result = (|| -> Option<Value> {
        let (pin, data) = if let Some(source) = options.local_source {
            let source = expanded(source, options.home, host)?;
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
        let mut parent = root.clone();
        for part in [".mir", "bin"] {
            parent.push(part);
            if parent.is_symlink() {
                return None;
            }
            if !parent.exists() {
                let pinned = adoption_fs::parent(&root, &parent).ok()?;
                adoption_fs::mkdir(&root, &parent, 0o777).ok()?;
                let identity = pinned.object_identity(true).ok()??;
                created.push((pinned, identity));
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
        // Verify the downloaded bytes only after the existing-file fast path,
        // matching the reference's handling of an already valid installation.
        if pin.get("size")?.as_u64()? != data.len() as u64
            || pin.get("sha256")?.as_str()? != crate::digest::sha256(&data)
        {
            return None;
        }
        place(&root, &parent, &destination, name, &data, host)?;
        receipt()
    })();
    for (parent, identity) in created.iter().rev() {
        if parent.object_identity(true).ok().flatten() == Some(*identity) {
            let _ = parent.unlink(&parent.name, true);
        }
    }
    result
}

fn place(
    root: &Path,
    directory: &Path,
    destination: &Path,
    name: &str,
    data: &[u8],
    host: &mut dyn InstallHost,
) -> Option<()> {
    let prefix = format!(".{name}.");
    let temporary = tempfile::Builder::new()
        .prefix(&prefix)
        .make_in(directory, |candidate| {
            adoption_fs::StagedFile::create(root, candidate)
        })
        .ok()?;
    let (mut staged, mut path) = temporary.into_parts();
    path.disable_cleanup(true);
    staged.file.write_all(data).ok()?;
    if staged.contents(data.len()).ok()? != data {
        return None;
    }
    adoption_fs::set_mode(&staged.file, 0o755).ok()?;
    host.before_replace(&staged.path, destination).ok()?;
    if destination.is_symlink() || (destination.exists() && !destination.is_file()) {
        return None;
    }
    if staged.contents(data.len()).ok()? != data {
        return None;
    }
    staged.publish(root, destination).ok()?;
    Some(())
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
