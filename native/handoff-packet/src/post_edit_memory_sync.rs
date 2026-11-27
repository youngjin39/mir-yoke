//! PostToolUse durable-memory adapter. The receipt-bound external CLI owns DB writes.
use crate::python_json::{self, Value};
use std::{
    env, fs, io,
    path::{Component, Path, PathBuf},
    process::{Command, Output, Stdio},
    thread,
    time::{Duration, Instant},
};

// Large Write/apply_patch events must still index their durable paths. Bound the
// raw reader at 16 MiB before decoding/allocating JSON, rather than silently
// inheriting the general hook parser's 1 MiB character limit.
pub const MAX_PAYLOAD_BYTES: usize = 16 * 1024 * 1024;

fn diagnostic(reason: &str) -> String {
    format!("[mir-memory] durable edit was not indexed: {reason}\n")
}
fn whitespace(c: char) -> bool {
    c.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&c)
}
fn absolute(path: &Path) -> io::Result<PathBuf> {
    let path = if path.is_absolute() {
        path.to_owned()
    } else {
        env::current_dir()?.join(path)
    };
    let mut result = PathBuf::new();
    for part in path.components() {
        match part {
            Component::CurDir => (),
            Component::ParentDir => {
                result.pop();
            }
            other => result.push(other),
        }
    }
    Ok(result)
}
// Account lookup exists only on Unix; elsewhere only HOME can answer.
#[cfg(unix)]
fn account_home(user: Option<&std::ffi::OsStr>) -> Option<PathBuf> {
    crate::runtime_account_home(user)
}
#[cfg(not(unix))]
fn account_home(_user: Option<&std::ffi::OsStr>) -> Option<PathBuf> {
    None
}
fn expanded(path: &Path) -> io::Result<PathBuf> {
    let Some(text) = path.to_str() else {
        return Ok(path.to_owned());
    };
    if !text.starts_with('~') {
        return Ok(path.to_owned());
    }
    let (user, rest) = text.split_once('/').unwrap_or((text, ""));
    let home = if user == "~" {
        env::var_os("HOME")
            .map(PathBuf::from)
            .or_else(|| account_home(None))
    } else {
        account_home(Some(std::ffi::OsStr::new(&user[1..])))
    }
    .ok_or_else(|| io::Error::other("could not determine home directory"))?;
    Ok(home.join(rest))
}
// Resolve symlinks before '..', including paths whose deleted leaf no longer exists.
fn resolved(path: &Path, depth: usize) -> io::Result<PathBuf> {
    if depth > 40 {
        return Err(io::Error::other("symlink loop"));
    }
    let path = if path.is_absolute() {
        path.to_owned()
    } else {
        env::current_dir()?.join(path)
    };
    let mut result = PathBuf::new();
    for part in path.components() {
        match part {
            Component::CurDir => (),
            Component::ParentDir => {
                result.pop();
            }
            other => {
                result.push(other);
                match fs::symlink_metadata(&result) {
                    Ok(meta) if meta.file_type().is_symlink() => {
                        let target = fs::read_link(&result)?;
                        result.pop();
                        result = resolved(&result.join(target), depth + 1)?;
                    }
                    Ok(_) => (),
                    Err(e)
                        if matches!(
                            e.kind(),
                            io::ErrorKind::NotFound | io::ErrorKind::NotADirectory
                        ) => {}
                    Err(e) => return Err(e),
                }
            }
        }
    }
    Ok(result)
}
fn relevant(raw: &Value, root: &Path) -> io::Result<bool> {
    let Some(raw) = raw.as_str() else {
        return Ok(false);
    };
    let raw = raw.trim_matches(whitespace);
    if raw.is_empty() {
        return Ok(false);
    }
    let path = resolved(&root.join(raw), 0)?;
    let Ok(relative) = path.strip_prefix(root) else {
        return Ok(false);
    };
    let Some(relative) = relative.to_str() else {
        return Ok(false);
    };
    Ok(relative.ends_with(".md")
        && !matches!(relative, "docs/memory-map.md" | "tasks/lessons.md")
        && ["docs/", "tasks/", ".ai-harness/"]
            .iter()
            .any(|prefix| relative.starts_with(prefix)))
}
fn has_relevant(payload: &Value, root: &Path) -> io::Result<bool> {
    let Some(input) = payload.get("tool_input").and_then(Value::as_object) else {
        return Ok(false);
    };
    let mut found = false;
    for field in ["file_path", "path"] {
        found |= relevant(&input.get(field).cloned().unwrap_or(Value::Null), root)?;
    }
    for field in ["command", "patch", "input", "content"] {
        if let Some(body) = input.get(field).and_then(Value::as_str) {
            for line in body.split('\n') {
                for prefix in ["*** Add File: ", "*** Update File: ", "*** Delete File: "] {
                    if let Some(raw) = line.strip_prefix(prefix).filter(|s| !s.is_empty()) {
                        found |= relevant(
                            &Value::String(python_json::Text::new(
                                raw.chars().map(u32::from).collect(),
                            )),
                            root,
                        )?;
                    }
                }
            }
        }
    }
    Ok(found)
}
fn checked_command(
    cli: &Path,
    args: &[std::ffi::OsString],
    root: &Path,
    timeout: Duration,
) -> io::Result<Output> {
    // File-backed capture avoids pipe deadlocks while preserving the 25-second deadline.
    let stdout = tempfile::tempfile()?;
    let stderr = tempfile::tempfile()?;
    let mut command = Command::new(cli);
    command
        .args(args)
        .current_dir(root)
        .stdin(Stdio::null())
        .stdout(stdout.try_clone()?)
        .stderr(stderr.try_clone()?);
    #[cfg(unix)]
    {
        use std::os::unix::process::CommandExt;
        command.process_group(0);
    }
    let mut child = command.spawn()?;
    let started = Instant::now();
    let status = loop {
        if let Some(status) = child.try_wait()? {
            break status;
        }
        if started.elapsed() >= timeout {
            #[cfg(unix)]
            crate::executor_process_unix::signal_group(&child, libc::SIGKILL);
            let _ = child.kill();
            let _ = child.wait();
            return Err(io::Error::new(
                io::ErrorKind::TimedOut,
                "Mir CLI timed out after 25 seconds",
            ));
        }
        thread::sleep(Duration::from_millis(2));
    };
    use std::io::{Read, Seek, SeekFrom};
    fn bytes(mut file: fs::File) -> io::Result<Vec<u8>> {
        file.seek(SeekFrom::Start(0))?;
        let mut result = Vec::new();
        file.read_to_end(&mut result)?;
        Ok(result)
    }
    let stdout = bytes(stdout)?;
    let stderr = bytes(stderr)?;
    if std::str::from_utf8(&stdout).is_err() || std::str::from_utf8(&stderr).is_err() {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "invalid UTF-8 output",
        ));
    }
    Ok(Output {
        status,
        stdout,
        stderr,
    })
}
fn hash_matches(path: &Path, expected: &Value) -> io::Result<bool> {
    let Some(expected) = expected.as_str() else {
        return Ok(false);
    };
    Ok(crate::digest::sha256(&fs::read(path)?) == expected)
}
fn executable(path: &Path) -> bool {
    #[cfg(unix)]
    {
        crate::executor_process_unix::path_access(path, libc::X_OK)
    }
    #[cfg(not(unix))]
    {
        path.is_file()
    }
}
fn sync(root: &Path, timeout: Duration) -> Result<(), String> {
    if !root.join("harness_a.toml").is_file() || !root.join(".mir/memory.db").is_file() {
        return Err(diagnostic("bootstrap memory is not ready"));
    }
    let unavailable = || diagnostic("external Mir CLI is unavailable");
    let receipt_bytes =
        fs::read(root.join(".mir/bootstrap-receipt.json")).map_err(|_| unavailable())?;
    let receipt_text = std::str::from_utf8(&receipt_bytes).map_err(|_| unavailable())?;
    let receipt = python_json::parse(receipt_text).map_err(|_| unavailable())?;
    let cli = receipt
        .get("cli")
        .filter(|v| v.is_object())
        .ok_or_else(unavailable)?;
    let raw = cli
        .get("executable")
        .and_then(Value::as_str)
        .ok_or_else(unavailable)?;
    let cli_path = absolute(&expanded(Path::new(raw)).map_err(|_| unavailable())?)
        .map_err(|_| unavailable())?;
    let resolved_cli = fs::canonicalize(&cli_path).map_err(|_| unavailable())?;
    let expected = cli.get("sha256").ok_or_else(unavailable)?;
    if resolved_cli.starts_with(root) {
        return Err(diagnostic("Mir CLI must be outside the project"));
    }
    if !resolved_cli.is_file() || !executable(&cli_path) {
        return Err(diagnostic("Mir CLI is not executable"));
    }
    if !hash_matches(&cli_path, expected).map_err(|_| unavailable())? {
        return Err(diagnostic("external Mir CLI hash changed"));
    }
    if let Some(manifest_raw) = cli.get("runtime_manifest").filter(|v| v.truthy()) {
        let changed = || diagnostic("external Mir runtime changed");
        let raw = manifest_raw.py_str();
        let runtime_root = cli_path
            .parent()
            .and_then(Path::parent)
            .ok_or_else(changed)?;
        let manifest = resolved(&expanded(Path::new(&raw)).map_err(|_| changed())?, 0)
            .map_err(|_| changed())?;
        if manifest != runtime_root.join("runtime-manifest.json")
            || !manifest.is_file()
            || manifest.is_symlink()
            || !hash_matches(&manifest, &cli["runtime_manifest_sha256"]).map_err(|_| changed())?
        {
            return Err(changed());
        }
        let mut args: Vec<std::ffi::OsString> = vec![
            "runtime-manifest".into(),
            "verify".into(),
            "--runtime-root".into(),
            runtime_root.into(),
            "--manifest".into(),
            manifest.into_os_string(),
        ];
        for (flag, field) in [
            ("--source-url", "source_url"),
            ("--source-commit", "source_commit"),
            ("--constraints-sha256", "constraints_sha256"),
        ] {
            args.push(flag.into());
            args.push(cli.get(field).map(Value::py_str).unwrap_or_default().into());
        }
        let output = checked_command(&cli_path, &args, root, timeout).map_err(|_| changed())?;
        if !output.status.success() {
            return Err(changed());
        }
    }
    let output = checked_command(
        &cli_path,
        &[
            "context".into(),
            "sync".into(),
            "--db".into(),
            root.join(".mir/memory.db").into_os_string(),
        ],
        root,
        timeout,
    )
    .map_err(|e| format!("[mir-memory] durable edit sync failed: {e}\n"))?;
    if !output.status.success() {
        let stderr = std::str::from_utf8(&output.stderr).map_err(|_| {
            "[mir-memory] durable edit sync failed: invalid UTF-8 output\n".to_owned()
        })?;
        let stdout = std::str::from_utf8(&output.stdout).map_err(|_| {
            "[mir-memory] durable edit sync failed: invalid UTF-8 output\n".to_owned()
        })?;
        let stderr = stderr.replace("\r\n", "\n").replace('\r', "\n");
        let stdout = stdout.replace("\r\n", "\n").replace('\r', "\n");
        let detail = [stderr.as_str(), stdout.as_str()]
            .iter()
            .map(|s| s.trim_matches(whitespace))
            .find(|s| !s.is_empty())
            .unwrap_or("unknown failure");
        return Err(format!("[mir-memory] durable edit sync failed: {detail}\n"));
    }
    Ok(())
}
pub fn run(project: &Path, input: &[u8]) -> Result<(), String> {
    let root = resolved(
        &expanded(project).map_err(|e| diagnostic(&e.to_string()))?,
        0,
    )
    .map_err(|e| diagnostic(&e.to_string()))?;
    // External hook payloads intentionally allow unknown fields and malformed JSON is quiet.
    if input.len() > MAX_PAYLOAD_BYTES {
        return Err(diagnostic(
            "payload exceeds 16777216 bytes; repair: scripts/mir.sh project-hooks install --project-root .; retry sync with scripts/mir.sh context sync",
        ));
    }
    let Ok(payload) = python_json::parse_stdin_with_limit(input, MAX_PAYLOAD_BYTES) else {
        return Ok(());
    };
    if !has_relevant(&payload, &root).map_err(|e| diagnostic(&e.to_string()))? {
        return Ok(());
    }
    sync(&root, Duration::from_secs(25))
}
