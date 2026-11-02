//! Explicit, fail-closed dispatch finalization. A merge stages approved paths;
//! committing the main repository and target-local writer authority remain the
//! embedding caller's responsibility. No provider or repository is discovered.
use crate::{
    executor_dispatch::DispatchOutcome,
    executor_local::LocalConfig,
    executor_registry::JobRegistry,
    executor_review::ReviewEvidence,
    executor_verifier::{self, GateOptions},
    executor_worktree::{self, DispatchWorktree},
};
use serde_json::{Value, json};
use std::{
    collections::BTreeSet,
    fmt, fs, io,
    path::{Path, PathBuf},
    process::{Command, Output},
    thread,
    time::{Duration, Instant},
};

#[derive(Debug)]
pub enum Error {
    Io(io::Error),
    Unicode(std::string::FromUtf8Error),
    Git { code: Option<i32>, stderr: String },
    Local(crate::executor_local::Error),
    Worktree(crate::executor_worktree::Error),
    Verifier(crate::executor_verifier::Error),
    Registry(crate::executor_registry::Error),
    Invalid(String),
}
impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Io(e) => e.fmt(f),
            Self::Unicode(e) => e.fmt(f),
            Self::Git { code, stderr } => write!(f, "git failed ({code:?}): {stderr}"),
            Self::Local(e) => e.fmt(f),
            Self::Worktree(e) => e.fmt(f),
            Self::Verifier(e) => e.fmt(f),
            Self::Registry(e) => write!(f, "registry failed: {e:?}"),
            Self::Invalid(e) => f.write_str(e),
        }
    }
}
impl std::error::Error for Error {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::Io(e) => Some(e),
            Self::Unicode(e) => Some(e),
            Self::Local(e) => Some(e),
            Self::Worktree(e) => Some(e),
            Self::Verifier(e) => Some(e),
            Self::Git { .. } | Self::Registry(_) | Self::Invalid(_) => None,
        }
    }
}
impl From<io::Error> for Error {
    fn from(e: io::Error) -> Self {
        Self::Io(e)
    }
}
impl From<std::string::FromUtf8Error> for Error {
    fn from(e: std::string::FromUtf8Error) -> Self {
        Self::Unicode(e)
    }
}
pub type Result<T> = std::result::Result<T, Error>;
pub type Reviewer<'a> = dyn FnMut(&DispatchWorktree, &[String]) -> Result<ReviewEvidence> + 'a;
pub type Observer<'a> = dyn FnMut(FinalizeStep, &DispatchWorktree) -> Result<()> + 'a;

#[derive(Debug, Clone)]
pub struct FinalizeOptions {
    pub gate: GateOptions,
    pub finalize_lock_timeout: Duration,
    pub require_review: Option<bool>,
    pub artifacts_root: Option<PathBuf>,
}
impl Default for FinalizeOptions {
    fn default() -> Self {
        Self {
            gate: GateOptions::default(),
            finalize_lock_timeout: Duration::from_secs(30),
            require_review: None,
            artifacts_root: None,
        }
    }
}
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FinalizeResult {
    pub action: String,
    pub reason: String,
    pub merged_files: Vec<String>,
}
impl FinalizeResult {
    fn new(action: &str, reason: impl Into<String>, merged_files: Vec<String>) -> Self {
        Self {
            action: action.into(),
            reason: reason.into(),
            merged_files,
        }
    }
    pub fn to_value(&self) -> Value {
        json!({"action":self.action,"reason":self.reason,"merged_files":self.merged_files})
    }
}
/// A narrow synchronous seam for evidence and deterministic fault injection.
/// BeforeRestore failures represent a refused restore command, after reset.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum FinalizeStep {
    AfterReview,
    BeforeMerge,
    AfterMerge,
    BeforeRollback,
    BeforeRestore(String),
    BeforePersist,
    BeforeCleanup,
}

/// The open file owns the OS lock. Drop releases it even while unwinding.
/// Unlike the Python Windows fallback, std's lock is exclusive on both platforms.
pub struct FinalizeLock {
    _file: fs::File,
}
impl FinalizeLock {
    pub fn acquire(main_repo_root: &Path, timeout: Duration) -> Result<Option<Self>> {
        let directory = main_repo_root.join(".mir");
        reject_lock_link(&directory)?;
        fs::create_dir_all(&directory)?;
        let path = directory.join("dispatch-finalize.lock");
        reject_lock_link(&path)?;
        let file = fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(path)?;
        let started = Instant::now();
        loop {
            match file.try_lock() {
                Ok(()) => return Ok(Some(Self { _file: file })),
                Err(fs::TryLockError::WouldBlock) => {
                    let remaining = timeout.saturating_sub(started.elapsed());
                    if remaining.is_zero() {
                        return Ok(None);
                    }
                    thread::sleep(remaining.min(Duration::from_millis(50)));
                }
                Err(fs::TryLockError::Error(e)) => return Err(e.into()),
            }
        }
    }
}
fn reject_lock_link(path: &Path) -> Result<()> {
    match fs::symlink_metadata(path) {
        Ok(meta) => {
            #[cfg(windows)]
            let link = {
                use std::os::windows::fs::MetadataExt;
                meta.file_attributes() & 0x400 != 0
            };
            #[cfg(not(windows))]
            let link = meta.file_type().is_symlink();
            if link {
                return Err(Error::Invalid(
                    "finalize lock symlink/reparse point rejected".into(),
                ));
            }
            Ok(())
        }
        Err(e) if e.kind() == io::ErrorKind::NotFound => Ok(()),
        Err(e) => Err(e.into()),
    }
}

fn git(root: &Path, args: &[&str], check: bool) -> Result<Output> {
    let output = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(args)
        .output()?;
    if check && !output.status.success() {
        return Err(Error::Git {
            code: output.status.code(),
            stderr: String::from_utf8(output.stderr)?,
        });
    }
    Ok(output)
}
fn git_text(root: &Path, args: &[&str]) -> Result<String> {
    Ok(String::from_utf8(git(root, args, true)?.stdout)?)
}
fn head(root: &Path) -> Result<String> {
    Ok(git_text(root, &["rev-parse", "HEAD"])?.trim().into())
}
fn commit_worktree(wt: &DispatchWorktree) -> Result<()> {
    git(&wt.path, &["add", "-A"], true)?;
    git(&wt.path, &["reset", "--", ".mir-dispatch"], false)?;
    if git(&wt.path, &["diff", "--cached", "--quiet"], false)?
        .status
        .code()
        == Some(1)
    {
        git(
            &wt.path,
            &["commit", "-m", &format!("mir-dispatch {}", wt.dispatch_id)],
            true,
        )?;
    }
    Ok(())
}
fn dispatch_dirty(wt: &DispatchWorktree) -> Result<bool> {
    Ok(!git_text(
        &wt.path,
        &[
            "status",
            "--porcelain=v2",
            "-z",
            "--untracked-files=all",
            "--",
            ".",
            ":(exclude).mir-dispatch",
            ":(exclude).mir-dispatch/**",
        ],
    )?
    .is_empty())
}
fn head_tracks(root: &Path, path: &str) -> Result<bool> {
    Ok(!git_text(
        root,
        &[
            "--literal-pathspecs",
            "ls-tree",
            "-z",
            "--name-only",
            "HEAD",
            "--",
            path,
        ],
    )?
    .is_empty())
}
fn head_absent_collision(root: &Path, path: &str) -> Result<bool> {
    if head_tracks(root, path)? {
        return Ok(false);
    }
    match fs::symlink_metadata(root.join(path)) {
        Ok(_) => return Ok(true),
        Err(e) if e.kind() == io::ErrorKind::NotFound => {}
        Err(e) if e.kind() == io::ErrorKind::NotADirectory => {}
        Err(e) => return Err(e.into()),
    }
    let mut parent = root.to_path_buf();
    let mut parts = Path::new(path).components().peekable();
    while let Some(part) = parts.next() {
        if parts.peek().is_none() {
            break;
        }
        parent.push(part);
        match fs::symlink_metadata(&parent) {
            Ok(meta) if meta.file_type().is_symlink() || !meta.is_dir() => return Ok(true),
            Ok(_) => {}
            Err(e) if e.kind() == io::ErrorKind::NotFound => {}
            Err(e) => return Err(e.into()),
        }
    }
    Ok(false)
}
fn targets_dirty(root: &Path, paths: &[String]) -> Result<bool> {
    if paths.is_empty() {
        return Ok(false);
    }
    for path in paths {
        if head_absent_collision(root, path)? {
            return Ok(true);
        }
    }
    let mut args = vec![
        "--literal-pathspecs",
        "status",
        "--porcelain=v2",
        "-z",
        "--untracked-files=all",
        "--ignored=matching",
        "--",
    ];
    args.extend(paths.iter().map(String::as_str));
    Ok(!git_text(root, &args)?.is_empty())
}
fn rollback(
    wt: &DispatchWorktree,
    paths: &[String],
    tracked: &BTreeSet<String>,
    observer: &mut Observer<'_>,
) -> Vec<String> {
    let root = &wt.main_repo_root;
    let mut failures = Vec::new();
    if let Err(e) = observer(FinalizeStep::BeforeRollback, wt) {
        match targets_dirty(root, paths) {
            Ok(true) => failures.push("target-residue".into()),
            Ok(false) => failures.push(format!("rollback-injection:{e}")),
            Err(e) => failures.push(format!("status:{e}")),
        }
        return failures;
    }
    for path in paths {
        match git(root, &["--literal-pathspecs", "reset", "--", path], false) {
            Ok(out) if out.status.success() => {}
            Ok(_) | Err(_) => failures.push(format!("reset:{path}")),
        }
        let (operation, args) = if tracked.contains(path) {
            (
                "restore",
                vec![
                    "--literal-pathspecs",
                    "restore",
                    "--source=HEAD",
                    "--staged",
                    "--worktree",
                    "--",
                    path,
                ],
            )
        } else {
            (
                "clean",
                vec!["--literal-pathspecs", "clean", "-fdx", "--", path],
            )
        };
        if tracked.contains(path)
            && observer(FinalizeStep::BeforeRestore(path.clone()), wt).is_err()
        {
            failures.push(format!("restore:{path}"));
            continue;
        }
        match git(root, &args, false) {
            Ok(out) if out.status.success() => {}
            Ok(_) | Err(_) => failures.push(format!("{operation}:{path}")),
        }
    }
    match targets_dirty(root, paths) {
        Ok(true) => failures.push("target-residue".into()),
        Ok(false) => {}
        Err(e) => failures.push(format!("status:{e}")),
    }
    failures
}
fn persist(
    wt: &DispatchWorktree,
    options: &FinalizeOptions,
    observer: &mut Observer<'_>,
) -> Result<()> {
    observer(FinalizeStep::BeforePersist, wt)?;
    executor_worktree::persist_dispatch_artifacts(
        wt,
        &wt.main_repo_root,
        options.artifacts_root.as_deref(),
    )
    .map_err(Error::Worktree)?;
    Ok(())
}
fn blocked(
    wt: &DispatchWorktree,
    options: &FinalizeOptions,
    observer: &mut Observer<'_>,
    reason: &str,
) -> Result<FinalizeResult> {
    persist(wt, options, observer)?;
    Ok(FinalizeResult::new("blocked", reason, vec![]))
}
fn post_success(
    wt: &DispatchWorktree,
    options: &FinalizeOptions,
    observer: &mut Observer<'_>,
    merged: Option<Vec<String>>,
) -> FinalizeResult {
    let cleanup = (|| {
        persist(wt, options, observer)?;
        observer(FinalizeStep::BeforeCleanup, wt)?;
        executor_worktree::cleanup_worktree(wt, true).map_err(Error::Worktree)
    })();
    let (action, prefix, files) = match merged {
        Some(files) => ("merged", "post-merge-error", files),
        None => ("reviewed", "post-review-error", vec![]),
    };
    match cleanup {
        Ok(()) => FinalizeResult::new(action, "approved", files),
        Err(e) => FinalizeResult::new(
            &format!("{action}-but-cleanup-failed"),
            format!("{prefix}:{e}"),
            files,
        ),
    }
}
fn completed(
    wt: &DispatchWorktree,
    options: &FinalizeOptions,
    mut reviewer: Option<&mut Reviewer<'_>>,
    observer: &mut Observer<'_>,
    config: &LocalConfig,
) -> Result<FinalizeResult> {
    commit_worktree(wt)?;
    let source = head(&wt.path)?;
    let mut gate_options = options.gate.clone();
    gate_options.source_commit = Some(source.clone());
    gate_options.allow_harness_self_modify |=
        executor_verifier::resolve_harness_self_modify(&wt.main_repo_root);
    let gate =
        executor_verifier::evaluate_merge_gate(wt, &gate_options).map_err(Error::Verifier)?;
    if !gate.approved {
        return blocked(wt, options, observer, &gate.reason);
    }
    if options
        .require_review
        .unwrap_or_else(|| config.require_review())
        && reviewer.is_none()
    {
        return blocked(wt, options, observer, "reviewer-missing");
    }
    if let Some(review) = reviewer.as_mut() {
        let evidence = review(wt, &gate.changed_files)?;
        executor_worktree::secure_write(
            &wt.path.join(".mir-dispatch/reviewer.json"),
            &evidence.to_value().to_string(),
            false,
        )
        .map_err(Error::Worktree)?;
        if !evidence.passed {
            return blocked(wt, options, observer, &evidence.reason);
        }
    }
    observer(FinalizeStep::AfterReview, wt)?;
    let Some(_lock) = FinalizeLock::acquire(&wt.main_repo_root, options.finalize_lock_timeout)?
    else {
        return blocked(wt, options, observer, "finalize-lock-timeout");
    };
    if head(&wt.main_repo_root)? != wt.base_commit {
        return blocked(wt, options, observer, "main-moved");
    }
    if head(&wt.path)? != source {
        return blocked(wt, options, observer, "dispatch-moved");
    }
    if dispatch_dirty(wt)? {
        return blocked(wt, options, observer, "dispatch-dirty");
    }
    if gate.changed_files.is_empty() {
        return Ok(post_success(wt, options, observer, None));
    }
    if targets_dirty(&wt.main_repo_root, &gate.changed_files)? {
        return blocked(wt, options, observer, "main-dirty");
    }
    let mut tracked = BTreeSet::new();
    for path in &gate.changed_files {
        if head_tracks(&wt.main_repo_root, path)? {
            tracked.insert(path.clone());
        }
    }
    let merge: Result<executor_worktree::MergeOutcome> = (|| {
        observer(FinalizeStep::BeforeMerge, wt)?;
        let result = executor_worktree::merge_result(
            wt,
            Some(&source),
            Some(&gate.changed_files),
            gate_options.allow_harness_self_modify,
        )
        .map_err(Error::Worktree)?;
        observer(FinalizeStep::AfterMerge, wt)?;
        Ok(result)
    })();
    match merge {
        Ok(result) => Ok(post_success(
            wt,
            options,
            observer,
            Some(result.merged_files),
        )),
        Err(e) => {
            let failures = rollback(wt, &gate.changed_files, &tracked, observer);
            // Preserve the merge/rollback diagnostic even if evidence persistence fails.
            let _ = persist(wt, options, observer);
            let reason = if failures.is_empty() {
                format!("merge-error:{e}")
            } else {
                let items = executor_verifier::changed_repr(&failures).map_err(Error::Verifier)?;
                format!("rollback-failed:merge-error:{e}; failures={items}")
            };
            Ok(FinalizeResult::new("blocked", reason, vec![]))
        }
    }
}

pub fn finalize_dispatch(
    wt: &DispatchWorktree,
    outcome: &DispatchOutcome,
    options: &FinalizeOptions,
    reviewer: Option<&mut Reviewer<'_>>,
    registry: Option<(&JobRegistry, &str)>,
) -> Result<FinalizeResult> {
    finalize_dispatch_with_observer(wt, outcome, options, reviewer, registry, &mut |_, _| Ok(()))
}
/// Validation errors propagate before effects. Operational errors become a
/// blocked result with retained worktree; post-merge cleanup errors stay distinct.
pub fn finalize_dispatch_with_observer(
    wt: &DispatchWorktree,
    outcome: &DispatchOutcome,
    options: &FinalizeOptions,
    reviewer: Option<&mut Reviewer<'_>>,
    registry: Option<(&JobRegistry, &str)>,
    observer: &mut Observer<'_>,
) -> Result<FinalizeResult> {
    let config = LocalConfig::load(&wt.main_repo_root).map_err(Error::Local)?;
    config
        .validate_timeout(options.gate.verify_timeout.as_ref())
        .map_err(Error::Local)?;
    if config.raw().contains_key("timeout_seconds_range") {
        config
            .validate_timeout(Some(&json!(options.finalize_lock_timeout.as_secs_f64())))
            .map_err(Error::Local)?;
    }
    let result = if outcome.status != "completed" {
        persist(wt, options, observer)?;
        FinalizeResult::new(
            "preserved",
            outcome
                .blocked_reason
                .as_deref()
                .filter(|reason| !reason.is_empty())
                .unwrap_or("failed"),
            vec![],
        )
    } else {
        match completed(wt, options, reviewer, observer, &config) {
            Ok(result) => result,
            Err(e) => {
                // Like the reference's exception handler, do not mask the cause.
                let _ = persist(wt, options, observer);
                FinalizeResult::new("blocked", format!("error:{e}"), vec![])
            }
        }
    };
    if let Some((registry, job_id)) = registry {
        project_registry(registry, job_id, wt, outcome, options, &result)?;
    }
    Ok(result)
}
fn project_registry(
    registry: &JobRegistry,
    job_id: &str,
    wt: &DispatchWorktree,
    outcome: &DispatchOutcome,
    options: &FinalizeOptions,
    result: &FinalizeResult,
) -> Result<()> {
    let success = matches!(
        result.action.as_str(),
        "merged" | "merged-but-cleanup-failed" | "reviewed" | "reviewed-but-cleanup-failed"
    );
    let code = if success {
        0
    } else {
        outcome.exit_code.filter(|code| *code != 0).unwrap_or(1)
    };
    let tokens = outcome
        .tokens_used
        .iter()
        .cloned()
        .collect::<std::collections::BTreeMap<_, _>>();
    let previous: Option<String> = registry
        .connection()
        .query_row(
            "SELECT ai_run_metadata FROM jobs WHERE job_id=?",
            [job_id],
            |row| row.get(0),
        )
        .map_err(|e| Error::Registry(e.into()))?;
    let mut metadata: Value = previous
        .map(|text| serde_json::from_str(&text))
        .transpose()
        .map_err(|e| Error::Invalid(e.to_string()))?
        .unwrap_or_else(|| json!({}));
    if !metadata.is_object() {
        metadata = json!({});
    }
    let mut ids = Vec::<String>::new();
    for value in metadata["dispatch_ids"]
        .as_array()
        .into_iter()
        .flatten()
        .chain(std::iter::once(&metadata["dispatch_id"]))
        .chain(std::iter::once(&json!(wt.dispatch_id)))
    {
        if let Some(id) = value.as_str()
            && !ids.iter().any(|item| item == id)
        {
            ids.push(id.into());
        }
    }
    metadata["model_id"] = json!(outcome.model_id);
    metadata["tokens_used"] = json!(tokens);
    metadata["mcp_protocol"] = json!(outcome.mcp_protocol);
    metadata["dispatch_id"] = json!(wt.dispatch_id);
    metadata["dispatch_ids"] = json!(ids);
    registry
        .update_ai_run_metadata(job_id, &metadata)
        .map_err(Error::Registry)?;
    let artifacts = options
        .artifacts_root
        .clone()
        .unwrap_or_else(|| PathBuf::from("tasks/dispatch"))
        .join(&wt.dispatch_id);
    let artifacts = artifacts
        .to_str()
        .ok_or_else(|| Error::Invalid("artifact path is not UTF-8".into()))?;
    let reason = if result.action == "merged-but-cleanup-failed" {
        Some(format!(
            "dispatch_status={} finalize_action={} finalize_reason={}",
            outcome.status, result.action, result.reason
        ))
    } else if !success {
        Some(format!(
            "dispatch_status={} dispatch_reason={} finalize_action={} finalize_reason={} blocked_reason={}",
            outcome.status,
            outcome.blocked_reason.as_deref().unwrap_or("None"),
            result.action,
            result.reason,
            result.reason
        ))
    } else {
        None
    };
    let completed_at: String = registry
        .connection()
        .query_row(
            "SELECT strftime('%Y-%m-%dT%H:%M:%f+00:00','now')",
            [],
            |row| row.get(0),
        )
        .map_err(|e| Error::Registry(e.into()))?;
    registry.update_status(job_id, if success { "completed" } else { "failed" }, &json!({"exit_code":code,"stdout":format!("artifacts={artifacts}"),"stderr":reason,"completed_at":completed_at})).map_err(Error::Registry)
}
