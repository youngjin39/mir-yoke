//! Snapshot and interrupt transitions; all side effects are explicit library calls.
use crate::mir_core::conductor::dispatch_brief::Error;
use crate::tools::run_orchestrator::state_machine::RunState;
use std::{
    env,
    io::Write,
    path::{Path, PathBuf},
    process::Command,
};

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Snapshot {
    pub method: String,
    pub reference: String,
    pub repo_root: PathBuf,
}
#[derive(Clone, Debug)]
pub struct GitResult {
    pub returncode: i32,
    pub stdout: String,
    pub stderr: String,
}
pub fn run_git(args: &[&str], cwd: &Path, check: bool) -> Result<GitResult, Error> {
    let output = Command::new("git").args(args).current_dir(cwd).output()?;
    let text = |bytes| {
        String::from_utf8(bytes)
            .map(|s| s.replace("\r\n", "\n").replace('\r', "\n"))
            .map_err(|e| Error::named("UnicodeDecodeError", e.to_string()))
    };
    let result = GitResult {
        returncode: output.status.code().unwrap_or(-1),
        stdout: text(output.stdout)?,
        stderr: text(output.stderr)?,
    };
    if check && result.returncode != 0 {
        return Err(Error::named(
            "CalledProcessError",
            format!("git exited with {}", result.returncode),
        ));
    }
    Ok(result)
}
pub fn find_repo_root(start: Option<&Path>) -> Result<PathBuf, Error> {
    let start = start
        .map(Path::to_path_buf)
        .map_or_else(env::current_dir, Ok)?;
    let start = fs_resolve(&start)?;
    for candidate in start.ancestors() {
        if candidate.join(".git").exists() {
            return Ok(candidate.into());
        }
    }
    Err(Error::named(
        "InterruptError",
        format!(
            "not inside a git repository (started from {})",
            start.display()
        ),
    ))
}
fn fs_resolve(path: &Path) -> Result<PathBuf, Error> {
    // Python Path.resolve resolves existing prefixes and allows nonexistent suffixes.
    let absolute = if path.is_absolute() {
        path.into()
    } else {
        env::current_dir()?.join(path)
    };
    let Some(parent) = absolute.parent() else {
        return Ok(absolute);
    };
    if absolute.exists() {
        let resolved = std::fs::canonicalize(&absolute)?;
        // std canonicalization adds a verbatim prefix on Windows; Python resolve does not.
        #[cfg(windows)]
        let resolved = {
            let text = resolved.to_str().ok_or_else(|| {
                Error::named("UnicodeError", "repository path is not valid Unicode")
            })?;
            if let Some(unc) = text.strip_prefix(r"\\?\UNC\") {
                PathBuf::from(format!(r"\\{unc}"))
            } else if let Some(drive) = text.strip_prefix(r"\\?\") {
                PathBuf::from(drive)
            } else {
                resolved
            }
        };
        return Ok(resolved);
    }
    let base = fs_resolve(parent)?;
    Ok(absolute
        .file_name()
        .map_or(base.clone(), |name| base.join(name)))
}
pub fn take_snapshot(method: &str, cwd: Option<&Path>, label: &str) -> Result<Snapshot, Error> {
    take_snapshot_with(method, cwd, label, run_git)
}
pub fn take_snapshot_with(
    method: &str,
    cwd: Option<&Path>,
    label: &str,
    mut git: impl FnMut(&[&str], &Path, bool) -> Result<GitResult, Error>,
) -> Result<Snapshot, Error> {
    let root = find_repo_root(cwd)?;
    match method {
        "stash" => {
            let result = git(
                &["stash", "push", "--include-untracked", "--message", label],
                &root,
                false,
            )?;
            let reference = if (result.stdout + &result.stderr).contains("No local changes to save")
            {
                ""
            } else if result.returncode != 0 {
                return Err(Error::named(
                    "InterruptError",
                    format!("git stash failed: {}", result.stderr.trim()),
                ));
            } else {
                "stash@{0}"
            };
            Ok(Snapshot {
                method: "stash".into(),
                reference: reference.into(),
                repo_root: root,
            })
        }
        "worktree" => Err(Error::named(
            "NotImplementedError",
            "worktree method is reserved for R19+ parallel ACT support",
        )),
        _ => Err(Error::named(
            "InterruptError",
            format!("unknown snapshot method: {method}"),
        )),
    }
}
pub fn restore_snapshot(snapshot: &Snapshot) -> Result<(), Error> {
    restore_snapshot_with(snapshot, run_git)
}
pub fn restore_snapshot_with(
    snapshot: &Snapshot,
    mut git: impl FnMut(&[&str], &Path, bool) -> Result<GitResult, Error>,
) -> Result<(), Error> {
    if snapshot.reference.is_empty() {
        return Ok(());
    }
    match snapshot.method.as_str() {
        "stash" => {
            let result = git(
                &["stash", "pop", &snapshot.reference],
                &snapshot.repo_root,
                false,
            )?;
            if result.returncode != 0 {
                return Err(Error::named(
                    "InterruptError",
                    format!("git stash pop failed: {}", result.stderr.trim()),
                ));
            }
        }
        "worktree" => {
            return Err(Error::named(
                "NotImplementedError",
                "worktree method is R19+ work",
            ));
        }
        _ => (),
    }
    Ok(())
}
pub fn handle_interrupt(
    state: RunState,
    snapshot: Option<&Snapshot>,
    transition: impl FnMut(RunState) -> Result<(), Error>,
    stderr: &mut impl Write,
) -> Result<RunState, Error> {
    handle_interrupt_with(
        state,
        snapshot.is_some(),
        transition,
        || snapshot.map_or(Ok(()), restore_snapshot),
        stderr,
    )
}
/// A callback error includes KeyboardInterrupt and is never swallowed.
/// Only InterruptError from restoration is recoverable, exactly as in Python.
pub fn handle_interrupt_with(
    state: RunState,
    has_snapshot: bool,
    mut transition: impl FnMut(RunState) -> Result<(), Error>,
    restore: impl FnOnce() -> Result<(), Error>,
    stderr: &mut impl Write,
) -> Result<RunState, Error> {
    if !matches!(state, RunState::Act | RunState::NeedApproval) {
        return Err(Error::named(
            "InvalidRunTransitionError",
            format!(
                "cannot interrupt from {} \u{2014} interrupt requires ACT or NEED_APPROVAL state",
                state.as_str()
            ),
        ));
    }
    transition(RunState::Cancelling)?;
    transition(RunState::Rollback)?;
    if has_snapshot && let Err(error) = restore() {
        if error.class != "InterruptError" {
            return Err(error);
        }
        writeln!(stderr, "[mir INTERRUPT] restore failed: {error}")?;
    }
    transition(RunState::Interrupted)?;
    Ok(RunState::Interrupted)
}
