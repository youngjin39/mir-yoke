//! Portable checkpoint capture; registrations still use the shell reference.
use crate::compact_snapshot::{BEGIN, END, read_handoff};
use regex::Regex;
use std::{
    fs,
    io::{self, Read, Seek, Write},
    path::{Path, PathBuf},
    process::{Command, Output, Stdio},
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

const SCAFFOLD: &str = "# Session Handoff — Current\n\n## Completed Work\n- Add only completed outcomes useful to the next session.\n\n## Decisions\n- Add only durable decisions needed by the next session.\n\n## Unresolved Issues\n- Add only unresolved work or blockers.\n\n## Next Actions\n- Add only the next actions needed to resume.\n\n## Modified Files\n- Add only files or groups needed to understand the handoff.\n\n## Verification Results\n- Add the checks run and their observed results.\n\n## Key Risks\n- Add only risks that remain relevant to the next session.\n";

// Preserve the result unchanged; diagnostics exist only in the unit-test binary.
macro_rules! checkpoint_io {
    ($stage:expr, $path:expr, $result:expr) => {{
        let result = $result;
        #[cfg(test)]
        if let Err(error) = &result {
            crate::compact_snapshot::trace_io_error($stage, $path, error);
        }
        result
    }};
}

pub fn replace_section(body: &str, snapshot: &str) -> Result<String, (usize, &'static str)> {
    let count = body.matches(BEGIN).count();
    if count != body.matches(END).count() {
        return Err((15, "runtime snapshot markers are unbalanced"));
    }
    if count == 0 {
        let separator = if body.ends_with("\n\n") {
            ""
        } else if body.ends_with('\n') {
            "\n"
        } else {
            "\n\n"
        };
        return Ok(format!("{body}{separator}{}\n", snapshot.trim()));
    }
    let mut rendered = String::new();
    let mut cursor = 0;
    for index in 0..count {
        let begin = body[cursor..].find(BEGIN).map(|offset| cursor + offset);
        let end = begin.and_then(|begin| {
            body[begin + BEGIN.len()..]
                .find(END)
                .map(|offset| begin + BEGIN.len() + offset)
        });
        let (Some(begin), Some(end)) = (begin, end) else {
            return Err((25, "runtime snapshot markers are malformed"));
        };
        rendered.push_str(&body[cursor..begin]);
        if index == 0 {
            rendered.push_str(snapshot.trim());
        }
        cursor = end + END.len();
    }
    rendered.push_str(&body[cursor..]);
    Ok(rendered)
}

/// tempfile creates 0600 on Unix and persists with atomic replacement on Windows.
/// The callback is the final fallible step before commit, also used for fault tests.
pub fn atomic_write(
    path: &Path,
    body: &[u8],
    before_commit: impl FnOnce() -> io::Result<()>,
) -> io::Result<()> {
    let parent = path
        .parent()
        .ok_or_else(|| io::Error::other("missing parent"))?;
    let mut temp = checkpoint_io!(
        "tempfile",
        path,
        tempfile::Builder::new()
            .prefix(".session-handoff-LATEST.md.")
            .tempfile_in(parent)
    )?;
    checkpoint_io!("write", path, temp.write_all(body))?;
    checkpoint_io!("flush", path, temp.flush())?;
    checkpoint_io!("before_commit", path, before_commit())?;
    checkpoint_io!(
        "persist",
        path,
        temp.persist(path).map_err(|error| error.error)
    )?;
    Ok(())
}

// One shared budget for both Git commands and recursive runner/dispatch discovery.
const COLLECTION_BUDGET: Duration = Duration::from_secs(2);

fn git(project: &Path, args: &[&str], deadline: Instant) -> io::Result<Output> {
    if Instant::now() >= deadline {
        return Err(io::ErrorKind::TimedOut.into());
    }
    // File-backed capture avoids pipe-buffer deadlock while polling the child.
    let mut stdout = tempfile::tempfile()?;
    let mut stderr = tempfile::tempfile()?;
    let mut child = Command::new("git")
        .arg("-C")
        .arg(project)
        .args(args)
        .stdin(Stdio::null())
        .stdout(stdout.try_clone()?)
        .stderr(stderr.try_clone()?)
        .spawn()?;
    let status = loop {
        match child.try_wait() {
            Ok(Some(status)) => break status,
            Ok(None) if Instant::now() < deadline => std::thread::sleep(Duration::from_millis(5)),
            result => {
                let _ = child.kill();
                let _ = child.wait();
                return Err(result
                    .err()
                    .unwrap_or_else(|| io::ErrorKind::TimedOut.into()));
            }
        }
    };
    stdout.rewind()?;
    stderr.rewind()?;
    let (mut out, mut err) = (Vec::new(), Vec::new());
    stdout.read_to_end(&mut out)?;
    stderr.read_to_end(&mut err)?;
    Ok(Output {
        status,
        stdout: out,
        stderr: err,
    })
}

fn files(root: &Path, extension: &str, output: &mut Vec<PathBuf>, deadline: Instant) {
    if Instant::now() >= deadline {
        return;
    }
    if let Ok(entries) = fs::read_dir(root) {
        for entry in entries.flatten() {
            if Instant::now() >= deadline {
                break;
            }
            let path = entry.path();
            // Do not follow directory symlinks, matching find without -L.
            if let Ok(kind) = entry.file_type() {
                if kind.is_dir() {
                    files(&path, extension, output, deadline);
                } else if kind.is_file() && path.extension().is_some_and(|ext| ext == extension) {
                    output.push(path);
                }
            }
        }
    }
}

fn snapshot(project: &Path, deadline: Instant) -> (String, String) {
    let mut body = format!("{BEGIN}\n## Runtime Snapshot (Generated)\n\n### Active Plan Items\n");
    if let Ok(plan) = fs::read_to_string(project.join("tasks/plan.md")) {
        let pattern = Regex::new(
            r"(?i)^- \[ \]|^Step [0-9]+:[\t\r\x0b\x0c ]*(in[\t\r\x0b\x0c _-]*progress|pending|blocked|active|running|todo)([\t\r\x0b\x0c ]|$)",
        );
        let items: Vec<_> = plan
            .lines()
            .filter(|line| pattern.as_ref().is_ok_and(|re| re.is_match(line)))
            .take(10)
            .map(|line| {
                if let Some(tail) = line.strip_prefix("- [ ] ") {
                    format!("- {tail}")
                } else if let Some(tail) = line.strip_prefix("Step ") {
                    format!("- Step {tail}")
                } else {
                    line.into()
                }
            })
            .collect();
        body.push_str(&if items.is_empty() {
            "- No open plan items.".into()
        } else {
            items.join("\n")
        });
    } else {
        body.push_str("- No active plan cursor.");
    }
    body.push_str("\n\n### Working Tree\n");
    let status = git(project, &["rev-parse", "--is-inside-work-tree"], deadline)
        .ok()
        .filter(|output| output.status.success())
        .and_then(|_| {
            git(
                project,
                &["status", "--short", "--untracked-files=all"],
                deadline,
            )
            .ok()
        });
    if let Some(output) = status {
        let count = output.stdout.iter().filter(|byte| **byte == b'\n').count();
        if count == 0 {
            body.push_str("- Working tree clean.\n");
        } else {
            body.push_str(&format!(
                "- Working tree dirty ({count} paths; inspect git status --short).\n"
            ));
        }
    } else {
        body.push_str("- Git status unavailable.\n");
    }
    let mut runners = Vec::new();
    files(&project.join("tasks/runner"), "md", &mut runners, deadline);
    runners.sort_by(|a, b| b.cmp(a));
    let active = Regex::new(
        r"(?i)^- status:[\t\r\x0b\x0c ]*`?(active|running|in_progress)`?[\t\r\x0b\x0c ]*$",
    );
    let runner = runners.into_iter().find_map(|path| {
        if Instant::now() >= deadline {
            return None;
        }
        let text = fs::read_to_string(&path).ok()?;
        text.lines()
            .any(|line| active.as_ref().is_ok_and(|re| re.is_match(line)))
            .then_some((path, text))
    });
    let mut warning = String::new();
    if let Some((path, text)) = runner {
        body.push_str(&format!(
            "\n### Runner State\n- Ledger: {}\n",
            path.strip_prefix(project).unwrap_or(&path).display()
        ));
        for line in text.lines().filter(|line| {
            [
                "- stage:",
                "- status:",
                "- last_checked_at:",
                "- resume_command:",
            ]
            .iter()
            .any(|prefix| line.starts_with(prefix))
        }) {
            body.push_str(line);
            body.push('\n');
        }
        let mut dispatches = Vec::new();
        files(
            &project.join("tasks/dispatch"),
            "json",
            &mut dispatches,
            deadline,
        );
        dispatches.sort_by(|a, b| b.cmp(a));
        if let Some(path) = dispatches.first() {
            body.push_str(&format!(
                "\n### Dispatch Brief\n- Brief: {}\n",
                path.strip_prefix(project).unwrap_or(path).display()
            ));
            let value = fs::read(path)
                .ok()
                .and_then(|data| serde_json::from_slice::<serde_json::Value>(&data).ok());
            if let Some(value) = value.filter(|v| v.is_object()) {
                for key in ["task_id", "slice_id", "target_agent", "resume_state_ref"] {
                    let field = value
                        .get(key)
                        .map(python_value)
                        .unwrap_or_else(|| "unknown".into());
                    body.push_str(&format!("- {key}: `{field}`\n"));
                }
            } else {
                body.push_str(
                    "- Dispatch brief unavailable (invalid JSON or Python unavailable).\n",
                );
                warning.push_str("[PreCompact] WARNING: Dispatch brief unavailable; runtime snapshot is partial.\n");
            }
        }
    }
    body.push_str(END);
    (body, warning)
}

fn python_value(value: &serde_json::Value) -> String {
    match value {
        serde_json::Value::String(text) => text.clone(),
        serde_json::Value::Null => "None".into(),
        serde_json::Value::Bool(true) => "True".into(),
        serde_json::Value::Bool(false) => "False".into(),
        _ => value.to_string(),
    }
}

pub fn pre_compact(project: &Path) -> (String, String) {
    let start = Instant::now();
    let result = checkpoint(project, start + COLLECTION_BUDGET);
    telemetry(project, "pre-compact", 0, start);
    result
}

fn checkpoint(project: &Path, deadline: Instant) -> (String, String) {
    let dir = project.join("tasks/handoffs");
    let path = dir.join("session-handoff-LATEST.md");
    if checkpoint_io!("mkdir", &dir, fs::create_dir_all(&dir)).is_err() {
        return (
            format!("[PreCompact] ERROR: Cannot create {}\n", dir.display()),
            String::new(),
        );
    }
    if !path.is_file() {
        let _ = checkpoint_io!("scaffold", &path, fs::write(&path, SCAFFOLD));
    }
    let (snapshot, mut stderr) = snapshot(project, deadline);
    let rendered = read_handoff(&path)
        .map_err(|_| (0, "canonical handoff is unreadable"))
        .and_then(|body| replace_section(&body, &snapshot));
    match rendered {
        Ok(body) if atomic_write(&path, body.as_bytes(), || Ok(())).is_ok() => (
            format!(
                "[PreCompact] Canonical handoff updated: {}\n",
                path.display()
            ),
            stderr,
        ),
        Err((line, message)) => {
            stderr.push_str(&format!("Traceback (most recent call last):\n  File \"<stdin>\", line {line}, in <module>\nValueError: {message}\n"));
            (
                "[PreCompact] ERROR: Failed to refresh canonical handoff.\n".into(),
                stderr,
            )
        }
        _ => (
            "[PreCompact] ERROR: Failed to refresh canonical handoff.\n".into(),
            stderr,
        ),
    }
}

pub fn telemetry(project: &Path, name: &str, exit: i32, started: Instant) {
    let dir = project.join(".mir/runtime");
    if fs::create_dir_all(&dir).is_err() {
        return;
    }
    let seconds = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs();
    let z = (seconds / 86400) as i64 + 719468;
    let era = z / 146097;
    let doe = z - era * 146097;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let day = doy - (153 * mp + 2) / 5 + 1;
    let month = mp + if mp < 10 { 3 } else { -9 };
    let year = yoe + era * 400 + i64::from(month <= 2);
    let ts = format!(
        "{year:04}-{month:02}-{day:02}T{:02}:{:02}:{:02}Z",
        seconds / 3600 % 24,
        seconds / 60 % 60,
        seconds % 60
    );
    let row = format!(
        "{{\"ts\":\"{ts}\",\"kind\":\"hook\",\"name\":{},\"exit_code\":{exit},\"duration_ms\":{}}}\n",
        serde_json::Value::String(name.into()),
        started.elapsed().as_millis()
    );
    if let Ok(mut file) = fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(dir.join("hook-invocations.jsonl"))
    {
        let _ = file.write_all(row.as_bytes());
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn diagnostics_preserve_real_read_error() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("tasks/handoffs/session-handoff-LATEST.md");
        fs::create_dir_all(&path).unwrap();
        let error = fs::read(&path).unwrap_err();
        crate::compact_snapshot::IO_DIAGNOSTICS.with(|log| log.borrow_mut().clear());
        let (stdout, stderr) = checkpoint(dir.path(), Instant::now());
        assert_eq!(
            stdout,
            "[PreCompact] ERROR: Failed to refresh canonical handoff.\n"
        );
        assert!(stderr.contains("ValueError: canonical handoff is unreadable\n"));
        crate::compact_snapshot::IO_DIAGNOSTICS.with(|log| {
            let log = log.borrow();
            assert!(
                log.iter().any(|row| row.contains("stage=read")
                    && row.contains(&format!("raw_os_error={:?}", error.raw_os_error()))),
                "{log:?}"
            );
        });
    }

    #[test]
    fn diagnostics_preserve_real_persist_error() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("handoff.md");
        fs::create_dir(&path).unwrap();
        fs::write(path.join("original"), "curated").unwrap();
        crate::compact_snapshot::IO_DIAGNOSTICS.with(|log| log.borrow_mut().clear());
        let error = atomic_write(&path, b"replacement", || Ok(())).unwrap_err();
        assert!(error.raw_os_error().is_some());
        crate::compact_snapshot::IO_DIAGNOSTICS.with(|log| {
            let log = log.borrow();
            assert!(
                log.iter().any(|row| row.contains("stage=persist")
                    && row.contains(&format!("raw_os_error={:?}", error.raw_os_error()))),
                "{log:?}"
            );
        });
        assert_eq!(
            fs::read_to_string(path.join("original")).unwrap(),
            "curated"
        );
        assert_eq!(fs::read_dir(dir.path()).unwrap().count(), 1);
    }

    #[cfg(windows)]
    #[test]
    fn windows_read_persist_overlap() {
        use std::{os::windows::fs::OpenOptionsExt, sync::Barrier};
        use windows_sys::Win32::Storage::FileSystem::{FILE_SHARE_READ, FILE_SHARE_WRITE};

        for no_delete_share in [false, true] {
            let dir = tempfile::tempdir().unwrap();
            let path = dir.path().join("handoff.md");
            fs::write(&path, "curated original").unwrap();
            let held = Barrier::new(2);
            let finished = Barrier::new(2);
            // Hold a real reader across the entire persist, without sleeps/retries.
            let result = std::thread::scope(|scope| {
                let reader = scope.spawn(|| -> io::Result<String> {
                    let mut options = fs::OpenOptions::new();
                    options.read(true);
                    if no_delete_share {
                        options.share_mode(FILE_SHARE_READ | FILE_SHARE_WRITE);
                    }
                    let opened = options.open(&path);
                    held.wait();
                    finished.wait();
                    let mut file = opened?;
                    let mut body = String::new();
                    file.read_to_string(&mut body)?;
                    Ok(body)
                });
                held.wait();
                let result = atomic_write(&path, b"replacement", || Ok(()));
                finished.wait();
                assert_eq!(reader.join().unwrap().unwrap(), "curated original");
                result
            });
            eprintln!("read/persist overlap: no_delete_share={no_delete_share} result={result:?}");
            // The explicit restricted handle is a negative control, not a claim
            // that read_handoff uses this share mode. Print the default outcome.
            if no_delete_share {
                let error = result.as_ref().unwrap_err();
                assert!(error.raw_os_error().is_some());
            }
            assert_eq!(
                fs::read_to_string(&path).unwrap(),
                if result.is_ok() {
                    "replacement"
                } else {
                    "curated original"
                }
            );
            assert_eq!(fs::read_dir(dir.path()).unwrap().count(), 1);
        }
    }

    #[test]
    fn curated_text_survives_replacement_and_duplicate_collapse() {
        let original = format!(
            "curated before\n{BEGIN}old{END}\ncurated between\n{BEGIN}old{END}\ncurated after\n"
        );
        let rendered = replace_section(&original, &format!("{BEGIN}new{END}")).unwrap();
        assert_eq!(
            rendered,
            format!("curated before\n{BEGIN}new{END}\ncurated between\n\ncurated after\n")
        );
    }

    #[test]
    fn failure_before_rename_keeps_original_and_cleans_temp() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("handoff.md");
        fs::write(&path, "curated original").unwrap();
        let result = atomic_write(&path, b"replacement", || {
            Err(io::Error::other("injected before rename"))
        });
        assert!(result.is_err());
        assert_eq!(fs::read_to_string(&path).unwrap(), "curated original");
        assert_eq!(fs::read_dir(dir.path()).unwrap().count(), 1);
    }

    #[test]
    fn unwritable_destination_keeps_original() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("handoff.md");
        fs::create_dir(&path).unwrap();
        fs::write(path.join("original"), "curated").unwrap();
        assert!(atomic_write(&path, b"replacement", || Ok(())).is_err());
        assert_eq!(
            fs::read_to_string(path.join("original")).unwrap(),
            "curated"
        );
        assert_eq!(fs::read_dir(dir.path()).unwrap().count(), 1);
    }

    #[test]
    fn concurrent_events_leave_complete_checkpoint_and_jsonl() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("tasks/handoffs/session-handoff-LATEST.md");
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(&path, "curated\n").unwrap();
        std::thread::scope(|scope| {
            for _ in 0..16 {
                let project = dir.path();
                scope.spawn(move || {
                    let result = pre_compact(project);
                    assert!(result.0.contains("Canonical handoff updated"), "{result:?}");
                });
            }
        });
        let body = fs::read_to_string(path).unwrap();
        assert!(body.starts_with("curated\n"));
        assert!(crate::compact_snapshot::parse(&body).is_ok());
        let log =
            fs::read_to_string(dir.path().join(".mir/runtime/hook-invocations.jsonl")).unwrap();
        assert_eq!(log.lines().count(), 16);
        for line in log.lines() {
            let value: serde_json::Value = serde_json::from_str(line).unwrap();
            assert_eq!(value["exit_code"], 0);
            assert_eq!(value["name"], "pre-compact");
        }
    }
}
