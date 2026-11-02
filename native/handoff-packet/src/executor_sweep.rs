//! Conservative library sweeps. Callers own admission; no providers or CLI routing.
use crate::{executor_local::LocalConfig, executor_registry::JobRegistry};
use rusqlite::{Connection, OpenFlags};
use serde_json::{Value, json};
use std::{
    collections::BTreeSet,
    fs,
    path::{Path, PathBuf},
    process::{Command, Output},
};

type Result<T> = std::result::Result<T, String>;
fn err(e: impl std::fmt::Display) -> String {
    e.to_string()
}
fn wire(path: &Path) -> Result<String> {
    path.to_str()
        .map(str::to_owned)
        .ok_or_else(|| "non-UTF-8 path".into())
}
fn resolved(path: &Path) -> Result<PathBuf> {
    if path.exists() {
        return fs::canonicalize(path)
            .map(crate::supply::plain)
            .map_err(err);
    }
    let parent = path
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    Ok(resolved(parent)?.join(path.file_name().ok_or("missing path name")?))
}
fn git(root: &Path, args: &[&str]) -> std::io::Result<Output> {
    Command::new("git")
        .env("GIT_OPTIONAL_LOCKS", "0")
        .arg("-C")
        .arg(root)
        .args(args)
        .output()
}
fn output(out: Output) -> Result<String> {
    String::from_utf8(out.stdout).map_err(err)
}
fn link(path: &Path) -> bool {
    fs::symlink_metadata(path).is_ok_and(|m| {
        #[cfg(windows)]
        {
            use std::os::windows::fs::MetadataExt;
            m.file_attributes() & 0x400 != 0
        }
        #[cfg(not(windows))]
        {
            m.file_type().is_symlink()
        }
    })
}
struct Ledger {
    writer: Option<JobRegistry>,
    reader: Option<Connection>,
}
impl Ledger {
    fn open(path: &Path, apply: bool) -> Result<Self> {
        if apply {
            return Ok(Self {
                writer: Some(JobRegistry::open(path).map_err(|e| format!("{e:?}"))?),
                reader: None,
            });
        }
        let reader = if path.exists() {
            Some(Connection::open_with_flags(path, OpenFlags::SQLITE_OPEN_READ_ONLY).map_err(err)?)
        } else {
            None
        };
        Ok(Self {
            writer: None,
            reader,
        })
    }
    fn connection(&self) -> Option<&Connection> {
        self.writer
            .as_ref()
            .map(JobRegistry::connection)
            .or(self.reader.as_ref())
    }
    fn jobs(&self) -> Result<Vec<Job>> {
        let Some(db) = self.connection() else {
            return Ok(vec![]);
        };
        // Missing optional metadata is supported by older read-only ledgers.
        let names = db
            .prepare("PRAGMA table_info(jobs)")
            .map_err(err)?
            .query_map([], |r| r.get::<_, String>(1))
            .map_err(err)?
            .collect::<std::result::Result<Vec<_>, _>>()
            .map_err(err)?;
        let metadata = if names.iter().any(|n| n == "ai_run_metadata") {
            "ai_run_metadata"
        } else {
            "NULL"
        };
        db.prepare(&format!("SELECT job_id,status,started_at,completed_at,timeout_seconds,{metadata} FROM jobs ORDER BY started_at DESC")).map_err(err)?.query_map([], |r| Ok(Job { id:r.get(0)?, status:r.get(1)?, started:r.get(2)?, completed:r.get(3)?, timeout:r.get(4)?, metadata:r.get(5)? })).map_err(err)?.collect::<std::result::Result<Vec<_>,_>>().map_err(err)
    }
}
struct Job {
    id: String,
    status: String,
    started: String,
    completed: Option<String>,
    timeout: i64,
    metadata: Option<String>,
}
// Microsecond arithmetic avoids SQLite julianday rounding at strict boundaries.
fn timestamp(text: &str) -> Option<i128> {
    let re = regex::Regex::new(r"^(\d{4})-?(\d{2})-?(\d{2})(?:.(\d{2}):?(\d{2})(?::?(\d{2}))?(?:[.,](\d+))?(Z|[+-]\d{2}:?\d{2})?)?$").ok()?;
    let c = re.captures(text)?;
    let n = |i| {
        c.get(i)
            .map_or(Some(0), |m| m.as_str().parse::<i128>().ok())
    };
    let (mut y, m, d) = (n(1)?, n(2)?, n(3)?);
    let leap = y % 4 == 0 && (y % 100 != 0 || y % 400 == 0);
    let days = match m {
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        4 | 6 | 9 | 11 => 30,
        2 => {
            if leap {
                29
            } else {
                28
            }
        }
        _ => return None,
    };
    if y == 0 || d < 1 || d > days || n(4)? > 23 || n(5)? > 59 || n(6)? > 59 {
        return None;
    }
    y -= i128::from(m <= 2);
    let era = y.div_euclid(400);
    let yo = y - era * 400;
    let mp = m + if m > 2 { -3 } else { 9 };
    let day = era * 146097 + yo * 365 + yo / 4 - yo / 100 + (153 * mp + 2) / 5 + d - 1 - 719468;
    let mut micros = ((day * 24 + n(4)?) * 3600 + n(5)? * 60 + n(6)?) * 1_000_000;
    if let Some(f) = c.get(7) {
        let mut s: String = f.as_str().chars().take(6).collect();
        while s.len() < 6 {
            s.push('0');
        }
        micros += s.parse::<i128>().ok()?;
    }
    if let Some(z) = c.get(8).filter(|z| z.as_str() != "Z") {
        let digits = z.as_str()[1..].replace(':', "");
        let h = digits[..2].parse::<i128>().ok()?;
        let m = digits[2..].parse::<i128>().ok()?;
        if h > 23 || m > 59 {
            return None;
        }
        micros -=
            (h * 3600 + m * 60) * 1_000_000 * if z.as_str().starts_with('-') { -1 } else { 1 };
    }
    Some(micros)
}
// Python normalizes now to UTC before storing the durable receipt.
fn receipt_time(text: &str) -> Result<String> {
    let micros = timestamp(text).ok_or("invalid now")?;
    let seconds = micros.div_euclid(1_000_000);
    let fraction = micros.rem_euclid(1_000_000);
    let day = seconds.div_euclid(86400);
    let z = day + 719468;
    let era = z.div_euclid(146097);
    let doe = z - era * 146097;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let mut year = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = mp + if mp < 10 { 3 } else { -9 };
    year += i128::from(m <= 2);
    if !(1..=9999).contains(&year) {
        return Err("datetime overflow".into());
    }
    let tod = seconds.rem_euclid(86400);
    let frac = if fraction == 0 {
        String::new()
    } else {
        format!(".{fraction:06}")
    };
    Ok(format!(
        "{year:04}-{m:02}-{d:02}T{:02}:{:02}:{:02}{frac}+00:00",
        tod / 3600,
        tod / 60 % 60,
        tod % 60
    ))
}
#[derive(Clone)]
struct Worktree {
    path: PathBuf,
    branch: String,
    id: String,
}
#[derive(PartialEq)]
struct Inspection {
    tip: Option<String>,
    status: Option<String>,
    reasons: Vec<String>,
}
fn inspect(repo: &Path, wt: &Worktree) -> Inspection {
    let mut reasons = vec![];
    let tip = git(repo, &["rev-parse", &wt.branch])
        .ok()
        .filter(|o| o.status.success())
        .and_then(|o| output(o).ok())
        .map(|s| s.trim().to_owned());
    if let Some(tip) = &tip {
        match git(repo, &["merge-base", "--is-ancestor", tip, "HEAD"])
            .ok()
            .and_then(|o| o.status.code())
        {
            Some(0) => (),
            Some(1) => reasons.push("unique-commit".into()),
            _ => reasons.push("inspection-failed:ancestry".into()),
        }
    } else {
        reasons.push("inspection-failed:branch-tip".into());
    }
    let status = |specs: &[&str]| {
        let mut args = vec![
            "status",
            "--porcelain=v2",
            "-z",
            "--untracked-files=all",
            "--ignored=matching",
            "--",
        ];
        args.extend_from_slice(specs);
        git(&wt.path, &args)
            .ok()
            .filter(|o| o.status.success())
            .and_then(|o| output(o).ok())
    };
    let all = status(&["."]);
    let other = status(&[".", ":(exclude).mir-dispatch", ":(exclude).mir-dispatch/**"]);
    if let (Some(_), Some(other)) = (&all, &other) {
        let runtime = wt.path.join(".mir-dispatch");
        if runtime.exists() || link(&runtime) {
            reasons.push("runtime-evidence-present".into());
        }
        if !other.is_empty() {
            reasons.push("worktree-dirty".into());
        }
    } else {
        reasons.push("inspection-failed:status".into());
    }
    Inspection {
        tip,
        status: all,
        reasons,
    }
}
fn list(repo: &Path) -> Result<Vec<Worktree>> {
    let out = git(repo, &["worktree", "list", "--porcelain", "-z"]).map_err(err)?;
    if !out.status.success() {
        return Err(String::from_utf8(out.stderr).map_err(err)?);
    }
    let text = output(out)?;
    let mut result = vec![];
    for record in text.split("\0\0") {
        let fields: Vec<_> = record
            .trim_matches('\0')
            .split('\0')
            .filter_map(|s| s.split_once(' '))
            .collect();
        let get = |key| fields.iter().find(|(k, _)| *k == key).map(|(_, v)| *v);
        if let (Some(path), Some(branch)) = (get("worktree"), get("branch"))
            && let Some(id) = branch.strip_prefix("refs/heads/mir-dispatch/")
        {
            let path = resolved(Path::new(path))?;
            if path != repo {
                result.push(Worktree {
                    path,
                    branch: branch.trim_start_matches("refs/heads/").into(),
                    id: id.into(),
                });
            }
        }
    }
    result.sort_by(|a, b| a.path.cmp(&b.path));
    Ok(result)
}
pub fn sweep_run_state(
    repo: &Path,
    db: &Path,
    now: &str,
    grace_seconds: i64,
    apply: bool,
) -> Result<Value> {
    sweep_run_state_with_observer(repo, db, now, grace_seconds, apply, |_, _| Ok(()))
}
/// Observer errors stop immediately; production callers normally use the wrapper.
pub fn sweep_run_state_with_observer(
    repo: &Path,
    db: &Path,
    now: &str,
    grace_seconds: i64,
    apply: bool,
    mut observer: impl FnMut(&str, &Path) -> Result<()>,
) -> Result<Value> {
    let repo = resolved(repo)?;
    let db = resolved(db)?;
    let ledger = Ledger::open(&db, apply)?;
    let jobs = ledger.jobs()?;
    let now = timestamp(now).ok_or("invalid now")?;
    let mut stale: Vec<_> = jobs
        .iter()
        .filter(|j| {
            j.status == "running"
                && timestamp(&j.started).is_some_and(|t| {
                    now > t + (i128::from(j.timeout) + i128::from(grace_seconds)) * 1_000_000
                })
        })
        .map(|j| j.id.clone())
        .collect();
    stale.sort();
    let mut errors = vec![];
    let worktrees = match list(&repo) {
        Ok(w) => w,
        Err(e) => {
            errors.push(format!("list worktrees: {e}"));
            vec![]
        }
    };
    let orphans: Vec<_> = worktrees
        .into_iter()
        .filter(|w| !jobs.iter().any(|j| j.id == w.id && j.status == "running"))
        .collect();
    let mut removable = vec![];
    let mut preserved = vec![];
    let mut drifted = vec![];
    let mut removed = vec![];
    let inspections: Vec<_> = orphans.iter().map(|w| inspect(&repo, w)).collect();
    for (wt, initial) in orphans.iter().zip(inspections) {
        let path = wire(&wt.path)?;
        if !initial.reasons.is_empty() {
            preserved.push(json!({"path":path,"reasons":initial.reasons}));
            continue;
        }
        if apply {
            observer("before-reinspect", &wt.path)?;
            let repeated = inspect(&repo, wt);
            if repeated != initial || !repeated.reasons.is_empty() {
                let mut reasons = vec!["apply-time-drift".to_owned()];
                reasons.extend(repeated.reasons);
                drifted.push(json!({"path":path,"reasons":reasons}));
                continue;
            }
            observer("before-remove", &wt.path)?;
            let reason = match git(&repo, &["worktree", "remove", &path]) {
                Err(_) => Some("apply-time-drift:remove-inspection-failed"),
                Ok(o) if !o.status.success() => Some("apply-time-drift:remove-refused"),
                Ok(_) => None,
            };
            if let Some(reason) = reason {
                drifted.push(json!({"path":path,"reasons":[reason]}));
                continue;
            }
            removed.push(path.clone());
            let reason = match git(&repo, &["branch", "-d", &wt.branch]) {
                Err(_) => Some("branch-delete-inspection-failed"),
                Ok(o) if !o.status.success() => Some("branch-delete-refused"),
                Ok(_) => None,
            };
            if let Some(reason) = reason {
                errors.push(format!("worktree {path}: {reason}"));
            }
        }
        removable.push(path);
    }
    preserved.extend(drifted);
    Ok(
        json!({"stale_jobs":stale,"orphan_worktrees":orphans.iter().map(|w|wire(&w.path)).collect::<Result<Vec<_>>>()?,"removable_worktrees":removable,"preserved_worktrees":preserved,"reaped_jobs":[],"removed_worktrees":removed,"errors":errors,"apply":apply}),
    )
}
fn identity(text: &str) -> bool {
    text.len() == 32
        && text
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}
fn count(path: &Path) -> Result<(i64, i64)> {
    let mut files = 0;
    let mut bytes = 0;
    for entry in fs::read_dir(path).map_err(err)? {
        let entry = entry.map_err(err)?;
        let path = entry.path();
        if link(&path) {
            continue;
        }
        let meta = entry.metadata().map_err(err)?;
        if meta.is_file() {
            files += 1;
            bytes += i64::try_from(meta.len()).map_err(err)?;
        } else if meta.is_dir() {
            let (f, b) = count(&path)?;
            files += f;
            bytes += b;
        }
    }
    Ok((files, bytes))
}
pub fn sweep_terminal_artifacts(
    repo: &Path,
    db: &Path,
    now: &str,
    retention_days: i64,
    apply: bool,
) -> Result<Value> {
    sweep_terminal_artifacts_with_observer(repo, db, now, retention_days, apply, |_, _| Ok(()))
}
/// Read the repository-owned retention default using the existing native config seam.
pub fn sweep_terminal_artifacts_configured(
    repo: &Path,
    db: &Path,
    now: &str,
    retention_days: Option<&Value>,
    apply: bool,
) -> Result<Value> {
    let config = if retention_days.is_none_or(Value::is_null) {
        LocalConfig::load(repo).map_err(|e| format!("{e:?}"))?
    } else {
        LocalConfig::default()
    };
    let days = config
        .retention_days(retention_days)
        .map_err(|e| format!("{e:?}"))?
        .as_i64()
        .ok_or("retention overflow")?;
    sweep_terminal_artifacts(repo, db, now, days, apply)
}
pub fn sweep_terminal_artifacts_with_observer(
    repo: &Path,
    db: &Path,
    now: &str,
    retention_days: i64,
    apply: bool,
    mut observer: impl FnMut(&str, &Path) -> Result<()>,
) -> Result<Value> {
    if retention_days < 0 {
        return Err("artifact_retention_days must be a non-negative integer".into());
    }
    let repo = resolved(repo)?;
    let db = resolved(db)?;
    let receipt_at = receipt_time(now)?;
    let floor =
        timestamp(now).ok_or("invalid now")? - i128::from(retention_days) * 86400 * 1_000_000;
    let root = repo.join("tasks").join("dispatch");
    let mut expired = vec![];
    let mut removed = vec![];
    let mut errors = vec![];
    if link(&repo.join("tasks")) || link(&root) {
        return Ok(
            json!({"retention_days":retention_days,"expired":[],"removed":[],"errors":["artifact root is a symlink"]}),
        );
    }
    let ledger = Ledger::open(&db, apply)?;
    for job in ledger.jobs()? {
        if job.status == "running" || !identity(&job.id) {
            continue;
        }
        let Some(completed) = job.completed.as_deref().filter(|s| !s.is_empty()) else {
            continue;
        };
        let Some(completed) = timestamp(completed) else {
            errors.push(format!("unparseable completed_at for {}", job.id));
            continue;
        };
        if completed >= floor {
            continue;
        }
        let metadata: Value = job
            .metadata
            .as_deref()
            .map(serde_json::from_str)
            .transpose()
            .map_err(err)?
            .unwrap_or(Value::Null);
        let mut ids = BTreeSet::from([job.id.clone()]);
        if let Some(history) = metadata["dispatch_ids"].as_array() {
            for id in history
                .iter()
                .filter_map(Value::as_str)
                .filter(|s| identity(s))
            {
                ids.insert(id.into());
            }
        }
        if let Some(id) = metadata["dispatch_id"].as_str().filter(|s| identity(s)) {
            ids.insert(id.into());
        }
        for id in ids {
            let path = root.join(&id);
            if link(&path) || !path.is_dir() {
                continue;
            }
            expired.push(id.clone());
            if !apply {
                continue;
            }
            let (files, bytes) = count(&path)?;
            let registry = ledger.writer.as_ref().ok_or("missing writer")?;
            let path_text = wire(&path)?;
            let exists: bool = registry
                .connection()
                .query_row(
                    "SELECT EXISTS(SELECT 1 FROM artifact_sweeps WHERE job_id=?1 AND path=?2)",
                    rusqlite::params![job.id, path_text],
                    |r| r.get(0),
                )
                .map_err(err)?;
            if !exists {
                registry
                    .record_artifact_sweep(&job.id, &path_text, files, bytes, &receipt_at)
                    .map_err(|e| format!("{e:?}"))?;
            }
            observer("after-receipt", &path)?;
            if link(&path) || !path.is_dir() {
                errors.push(format!("remove {id}: shape changed before removal"));
                continue;
            }
            match fs::remove_dir_all(&path) {
                Ok(()) => removed.push(id),
                Err(e) => errors.push(format!("remove {id}: {e}")),
            }
        }
    }
    expired.sort();
    removed.sort();
    Ok(json!({"retention_days":retention_days,"expired":expired,"removed":removed,"errors":errors}))
}
