//! Two-home transaction; library only. Caller migration is a separate slice.
use crate::{
    adoption_fs,
    user_runtime_install::*,
    user_runtime_mutation::{PendingWrite, remove_with},
};
use std::{
    collections::BTreeMap,
    io::Read,
    path::{Path, PathBuf},
    sync::atomic::{AtomicU64, Ordering},
};

pub struct RuntimePlan {
    pub identity: HomeIdentity,
    pub files: Vec<ManagedFile>,
    pub stale: Vec<StaleFile>,
    pub receipt: Vec<u8>,
    pub created_home: bool,
}
struct Snapshot {
    relative: PathBuf,
    before: Option<Vec<u8>>,
    after: Option<Vec<u8>>,
}
fn sync(message: String) -> Error {
    Error {
        class: "SyncError",
        message,
    }
}
fn io(path: &Path, error: std::io::Error) -> Error {
    io_context(Some(path), error)
}
fn io_context(path: Option<&Path>, error: std::io::Error) -> Error {
    if error.raw_os_error().is_none() {
        let error = crate::mir_cli::bootstrap_adoption::io_error(
            path.unwrap_or_else(|| Path::new("")),
            error,
        );
        return Error {
            class: error.class(),
            message: error.to_string(),
        };
    }
    let rendered = crate::executor_text::io_error(error, path.unwrap_or_else(|| Path::new("")));
    let (class, message) = rendered.split_once(": ").unwrap_or(("OSError", &rendered));
    let mut message = message.to_owned();
    if path.is_none() {
        let suffix = format!(": {}", crate::executor_text::repr(""));
        message.truncate(message.len() - suffix.len());
    }
    Error {
        class: match class {
            "FileNotFoundError" => "FileNotFoundError",
            "FileExistsError" => "FileExistsError",
            "PermissionError" => "PermissionError",
            "IsADirectoryError" => "IsADirectoryError",
            "NotADirectoryError" => "NotADirectoryError",
            _ => "OSError",
        },
        message,
    }
}
fn read(identity: &HomeIdentity, relative: &Path) -> Result<Option<Vec<u8>>, Error> {
    let path = verified_target(identity, relative)?;
    let result: std::io::Result<Vec<u8>> = (|| {
        let parent = adoption_fs::parent(&identity.path, &path)?;
        let mut file = parent.open_file()?;
        let mut bytes = Vec::new();
        file.read_to_end(&mut bytes)?;
        Ok(bytes)
    })();
    match result {
        Ok(bytes) => Ok(Some(bytes)),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(e) => Err(io(&path, e)),
    }
}
fn write(identity: &HomeIdentity, relative: &Path, bytes: &[u8]) -> Result<(), Error> {
    static NEXT: AtomicU64 = AtomicU64::new(0);
    let path = verified_target(identity, relative)?;
    let name = format!(
        ".mir-install-{}-{}",
        std::process::id(),
        NEXT.fetch_add(1, Ordering::Relaxed)
    );
    let pending =
        PendingWrite::prepare_mapped(&identity.path, &path, name.as_ref(), bytes, io_context)?;
    verified_target(identity, relative)?;
    pending
        .publish_with(|_| Ok(()))
        .map_err(|e| rename_error(pending.temporary_path(), &path, e))
}
// Match os.replace at 0754c36 scripts/install_user_runtime_agents.py:380.
// executor_text::io_error renders the source with the same codepoint repr.
fn rename_error(temporary: &Path, path: &Path, e: std::io::Error) -> Error {
    let mut error = io(temporary, e);
    if error.message.starts_with("[Errno ") {
        error.message.push_str(&format!(
            " -> {}",
            crate::executor_text::repr_points(&crate::executor_text::os_points(path.as_os_str()))
        ));
    }
    error
}

pub(crate) fn ordered_desired(
    desired: impl IntoIterator<Item = (PathBuf, Option<Vec<u8>>)>,
) -> Vec<(PathBuf, Option<Vec<u8>>)> {
    let mut merged = BTreeMap::new();
    for (path, value) in desired {
        let entry = merged
            .entry(adoption_fs::path_key(&path))
            .or_insert((path, None));
        entry.1 = value;
    }
    merged.into_values().collect()
}
fn snapshot(plan: &RuntimePlan) -> Result<Vec<Snapshot>, Error> {
    let mut desired = Vec::new();
    for item in &plan.files {
        desired.push((item.target_relative.clone(), Some(item.content.clone())));
    }
    for item in &plan.stale {
        desired.push((item.target_relative.clone(), None));
    }
    desired.push((RECEIPT_NAME.into(), Some(plan.receipt.clone())));
    ordered_desired(desired)
        .into_iter()
        .map(|(relative, after)| {
            Ok(Snapshot {
                before: read(&plan.identity, &relative)?,
                relative,
                after,
            })
        })
        .collect()
}
fn restore(plan: &RuntimePlan, snap: &Snapshot) -> Result<(), Error> {
    let current = read(&plan.identity, &snap.relative)?;
    if snap.before.is_none() && current.is_none() || snap.before.is_some() && current == snap.before
    {
        return Ok(());
    }
    if current.is_some() && current != snap.after {
        return Err(sync(format!(
            "rollback found unexpected file: {}",
            plan.identity.path.join(&snap.relative).display()
        )));
    }
    match &snap.before {
        Some(bytes) => write(&plan.identity, &snap.relative, bytes),
        None => {
            let path = verified_target(&plan.identity, &snap.relative)?;
            remove_with(&plan.identity.path, &path, false, || Ok(())).map_err(|e| io(&path, e))
        }
    }
}
fn cleanup(plan: &RuntimePlan, snapshots: &[Snapshot]) -> Result<(), Error> {
    if !plan.created_home {
        return Ok(());
    }
    verified_target(&plan.identity, Path::new(RECEIPT_NAME))?;
    let mut dirs: Vec<_> = snapshots
        .iter()
        .filter_map(|s| s.relative.parent())
        .filter(|p| !p.as_os_str().is_empty())
        .map(Path::to_owned)
        .collect();
    dirs.sort();
    dirs.dedup();
    dirs.sort_by_key(|p| std::cmp::Reverse(p.components().count()));
    for dir in dirs {
        let path = plan.identity.path.join(dir);
        if !path.exists() {
            continue;
        }
        let details = std::fs::symlink_metadata(&path).map_err(|e| io(&path, e))?;
        if details.is_symlink() || !details.is_dir() {
            return Err(sync(format!(
                "rollback found unsafe directory: {}",
                path.display()
            )));
        }
        remove_with(&plan.identity.path, &path, true, || Ok(())).map_err(|e| io(&path, e))?;
    }
    verified_target(&plan.identity, Path::new(RECEIPT_NAME))?;
    let root = &plan.identity.path;
    remove_with(
        root.parent()
            .ok_or_else(|| sync("runtime home has no parent".into()))?,
        root,
        true,
        || Ok(()),
    )
    .map_err(|e| io(root, e))
}
pub fn apply_transaction(plans: &[RuntimePlan]) -> Result<(), Error> {
    transaction_with(plans, |_, _, _| Ok(()))
}
pub(crate) fn transaction_with(
    plans: &[RuntimePlan],
    mut hook: impl FnMut(&str, usize, &Path) -> Result<(), Error>,
) -> Result<(), Error> {
    let snapshots: Vec<_> = plans
        .iter()
        .enumerate()
        .map(|(i, p)| {
            hook("snapshot", i, Path::new(""))?;
            snapshot(p)
        })
        .collect::<Result<_, _>>()?;
    let result = (|| {
        for (i, plan) in plans.iter().enumerate() {
            for item in &plan.files {
                hook("payload", i, &item.target_relative)?;
                write(&plan.identity, &item.target_relative, &item.content)?;
            }
            for item in &plan.stale {
                hook("stale", i, &item.target_relative)?;
                if let Some(bytes) = read(&plan.identity, &item.target_relative)? {
                    if sha256_bytes(&bytes) != item.sha256 {
                        return Err(sync(format!(
                            "diverged stale managed file; refusing removal: {}",
                            plan.identity.path.join(&item.target_relative).display()
                        )));
                    }
                    let path = verified_target(&plan.identity, &item.target_relative)?;
                    remove_with(&plan.identity.path, &path, false, || Ok(()))
                        .map_err(|e| io(&path, e))?;
                }
            }
            hook("receipt", i, Path::new(RECEIPT_NAME))?;
            write(&plan.identity, Path::new(RECEIPT_NAME), &plan.receipt)?;
        }
        Ok(())
    })();
    let Err(error) = result else {
        return Ok(());
    };
    let mut errors = vec![];
    for (i, plan) in plans.iter().enumerate().rev() {
        let result = (|| {
            for snap in snapshots[i].iter().rev() {
                hook("restore", i, &snap.relative)?;
                restore(plan, snap)?;
            }
            hook("cleanup", i, Path::new(""))?;
            cleanup(plan, &snapshots[i])
        })();
        if let Err(e) = result {
            errors.push(e.message);
        }
    }
    if !errors.is_empty() {
        return Err(sync(format!(
            "apply failed; rollback incomplete: {}; {}",
            error,
            errors.join("; ")
        )));
    }
    if matches!(
        error.class,
        "KeyboardInterrupt" | "SystemExit" | "BaseException"
    ) {
        return Err(error);
    }
    Err(sync(format!("apply failed; rollback complete: {error}")))
}
#[cfg(all(test, unix))]
#[path = "user_runtime_transaction_tests.rs"]
mod tests;

#[cfg(all(test, windows))]
#[rustfmt::skip]
pub(crate) fn windows_core_order_test() {
    let desired = BTreeMap::from([
        (PathBuf::from("agents/Z.md"), Some(vec![1])),
        (PathBuf::from("agents/a.md"), Some(vec![2])),
        (PathBuf::from("agents/z.MD"), Some(vec![3])),
    ]);
    assert_eq!(ordered_desired(desired), vec![
        (PathBuf::from("agents/a.md"), Some(vec![2])),
        (PathBuf::from("agents/Z.md"), Some(vec![3])),
    ]);
}

#[cfg(all(test, windows))]
#[path = "user_runtime_windows_oracle_tests.rs"]
mod user_runtime_windows_oracle_tests;
