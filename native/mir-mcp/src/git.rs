use crate::guard::Guard;
use serde_json::Value;
use std::io::Read;
use std::process::{Child, Command, ExitStatus, Stdio};
use std::sync::mpsc::{self, SyncSender};
use std::time::{Duration, Instant};

pub enum Query<'a> {
    Head,
    Status,
    Log(&'a str),
    Diff(&'a str),
}

fn relative(value: &str) -> Option<String> {
    let bytes = value.as_bytes();
    if value.is_empty()
        || value.len() > 4096
        || value.starts_with(['/', '-'])
        || value.contains('\\')
        || value.chars().any(|c| c < ' ' || c == '\u{7f}')
        || (bytes.len() >= 2 && bytes[0].is_ascii_alphabetic() && bytes[1] == b':')
        || value.split('/').any(|p| p == "..")
    {
        return None;
    }
    let parts: Vec<_> = value
        .split('/')
        .filter(|p| !p.is_empty() && *p != ".")
        .collect();
    if parts.is_empty() {
        None
    } else {
        Some(parts.join("/"))
    }
}

fn commit(value: &str) -> bool {
    matches!(value.len(), 40 | 64)
        && value
            .bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
}

fn whitespace(c: char) -> bool {
    c.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&c)
}
fn trim(value: &str) -> &str {
    value.trim_matches(whitespace)
}
fn trim_start(value: &str) -> &str {
    value.trim_start_matches(whitespace)
}

// Match the reference's deliberately small Git configuration dialect. Includes,
// executable filters and redirection of repository metadata are refused.
fn config_safe(config: &str) -> bool {
    let mut section = None;
    for line in config.split([
        '\n', '\r', '\u{b}', '\u{c}', '\u{1c}', '\u{1d}', '\u{1e}', '\u{85}', '\u{2028}',
        '\u{2029}',
    ]) {
        let line = trim(line);
        if line.is_empty() || line.starts_with(['#', ';']) {
            continue;
        }
        if line.ends_with('\\') {
            return false;
        }
        if let Some(rest) = line.strip_prefix('[') {
            let rest = trim_start(rest);
            let size = rest
                .bytes()
                .take_while(|c| c.is_ascii_alphanumeric() || matches!(c, b'.' | b'-'))
                .count();
            if size == 0 {
                return false;
            }
            let name = rest[..size].to_ascii_lowercase();
            let after = &rest[size..];
            let mut tail = trim_start(after);
            if tail.starts_with('"') {
                if after.len() == tail.len() {
                    return false;
                }
                let mut chars = tail[1..].char_indices();
                let mut close = None;
                while let Some((i, c)) = chars.next() {
                    if c == '\\' {
                        if chars.next().is_none() {
                            return false;
                        }
                    } else if c == '"' {
                        close = Some(i + 2);
                        break;
                    }
                }
                let Some(end) = close else {
                    return false;
                };
                tail = trim_start(&tail[end..]);
            }
            let Some(tail) = tail.strip_prefix(']') else {
                return false;
            };
            let tail = trim_start(tail);
            if !tail.is_empty() && !tail.starts_with(['#', ';']) {
                return false;
            }
            let name = name.split('.').next().unwrap_or("").to_owned();
            if matches!(
                name.as_str(),
                "include" | "includeif" | "filter" | "submodule"
            ) {
                return false;
            }
            section = Some(name);
        } else {
            let size = line
                .bytes()
                .take_while(|c| c.is_ascii_alphanumeric() || *c == b'-')
                .count();
            if size == 0 || !line.as_bytes()[0].is_ascii_alphabetic() || section.is_none() {
                return false;
            }
            let tail = trim_start(&line[size..]);
            if !tail.is_empty() && !tail.starts_with('=') {
                return false;
            }
            let key = line[..size].to_ascii_lowercase();
            if matches!(
                (section.as_deref(), key.as_str()),
                (Some("core"), "worktree" | "gitdir" | "excludesfile")
                    | (Some("extensions"), "worktreeconfig" | "partialclone")
                    | (Some("remote"), "promisor")
                    | (Some("diff"), "orderfile")
            ) {
                return false;
            }
        }
    }
    true
}

pub fn preflight(io: &mut Guard) -> Result<bool, &'static str> {
    io.tick()?;
    let result = (|| {
        if !io.path(".git", false)?.is_dir() {
            return Ok(false);
        }
        for path in [
            ".git/objects",
            ".git/refs",
            ".git/objects/info",
            ".git/HEAD",
            ".git/index",
            ".git/packed-refs",
            ".git/shallow",
        ] {
            io.path(path, true)?;
        }
        for path in [
            ".git/commondir",
            ".git/objects/info/alternates",
            ".git/objects/info/http-alternates",
            ".git/config.worktree",
            ".git/modules",
            ".gitmodules",
        ] {
            if io.exists(path)? {
                return Ok(false);
            }
        }
        let head = io.read(".git/HEAD")?;
        if !head.is_ascii() {
            return Ok(false);
        }
        let head = trim(std::str::from_utf8(&head).map_err(|_| "E_GIT")?);
        if let Some(head) = head.strip_prefix("ref: ") {
            let Some(reference) = relative(head) else {
                return Ok(false);
            };
            if !reference.starts_with("refs/") {
                return Ok(false);
            }
            io.path(&format!(".git/{reference}"), true)?;
        } else if !commit(head) {
            return Ok(false);
        }
        let config = io.read(".git/config")?;
        let config = std::str::from_utf8(&config).map_err(|_| "E_GIT")?;
        Ok(config_safe(config))
    })();
    match result {
        Err(code @ ("E_LIMIT" | "E_TIMEOUT")) => Err(code),
        Err(_) => Ok(false),
        value => value,
    }
}

enum Output {
    Chunk(bool, Vec<u8>),
    Done,
    Error,
}
fn reader(mut pipe: impl Read + Send + 'static, stdout: bool, sender: SyncSender<Output>) {
    std::thread::spawn(move || {
        loop {
            let mut chunk = vec![0; 8192];
            match pipe.read(&mut chunk) {
                Ok(0) => {
                    let _ = sender.send(Output::Done);
                    break;
                }
                Ok(n) => {
                    chunk.truncate(n);
                    if sender.send(Output::Chunk(stdout, chunk)).is_err() {
                        break;
                    }
                }
                Err(_) => {
                    let _ = sender.send(Output::Error);
                    break;
                }
            }
        }
    });
}

struct Running(Child);
impl Drop for Running {
    fn drop(&mut self) {
        if !matches!(self.0.try_wait(), Ok(Some(_))) {
            let _ = self.0.kill();
        }
        let _ = self.0.wait();
    }
}

fn binary() -> &'static str {
    #[cfg(windows)]
    {
        const MODERN: &str = r"C:\Program Files\Git\ucrt64\bin\git.exe";
        const LEGACY: &str = r"C:\Program Files\Git\mingw64\bin\git.exe";
        if std::path::Path::new(MODERN).is_file() {
            MODERN
        } else if std::path::Path::new(LEGACY).is_file() {
            LEGACY
        } else {
            MODERN
        }
    }
    #[cfg(not(windows))]
    {
        "/usr/bin/git"
    }
}

pub fn run(io: &mut Guard, query: Query<'_>) -> Result<Option<Value>, &'static str> {
    io.tick()?;
    let deadline = io
        .deadline
        .checked_sub(Duration::from_secs(1))
        .ok_or("E_TIMEOUT")?;
    if Instant::now() >= deadline {
        return Err("E_TIMEOUT");
    }
    if let Query::Log(path) | Query::Diff(path) = query
        && (relative(path).as_deref() != Some(path) || io.path(path, true).is_err())
    {
        return Err("E_GIT");
    }
    if !preflight(io)? {
        return Err("E_GIT");
    }
    let suffix: Vec<&str> = match query {
        Query::Head => vec!["rev-parse", "--verify", "HEAD"],
        Query::Status => vec![
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--ignore-submodules=all",
        ],
        Query::Log(path) => vec!["log", "-1", "--format=%H", "--", path],
        Query::Diff(path) => vec![
            "diff",
            "--quiet",
            "--no-ext-diff",
            "--no-textconv",
            "--ignore-submodules=all",
            "HEAD",
            "--",
            path,
        ],
    };
    let mut command = Command::new(binary());
    command
        .args([
            "--no-optional-locks",
            "--literal-pathspecs",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.untrackedCache=false",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "core.attributesFile=/dev/null",
            "-c",
            "submodule.recurse=false",
            "-C",
        ])
        .arg(&io.root)
        .args(suffix)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .env_clear()
        .envs([
            ("GIT_CONFIG_NOSYSTEM", "1"),
            ("GIT_CONFIG_SYSTEM", "/dev/null"),
            ("GIT_CONFIG_GLOBAL", "/dev/null"),
            ("GIT_ATTR_NOSYSTEM", "1"),
            ("GIT_TERMINAL_PROMPT", "0"),
        ]);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }
    let (output, status) = capture(command.spawn().map_err(|_| "E_GIT")?, deadline)?;
    if matches!(query, Query::Diff(_)) {
        return Ok(match status.code() {
            Some(0) => Some(Value::Bool(false)),
            Some(1) => Some(Value::Bool(true)),
            _ => None,
        });
    }
    if !status.success() {
        return Ok(None);
    }
    if matches!(query, Query::Status) {
        return Ok(Some(Value::Bool(!output.is_empty())));
    }
    if !output.is_ascii() {
        return Err("E_GIT");
    }
    let value = trim(std::str::from_utf8(&output).map_err(|_| "E_GIT")?);
    if (matches!(query, Query::Log(_)) && value.is_empty()) || commit(value) {
        Ok(Some(Value::String(value.into())))
    } else {
        Err("E_GIT")
    }
}

fn capture(child: Child, deadline: Instant) -> Result<(Vec<u8>, ExitStatus), &'static str> {
    let mut child = Running(child);
    let stdout = child.0.stdout.take().ok_or("E_GIT")?;
    let stderr = child.0.stderr.take().ok_or("E_GIT")?;
    let (sender, receiver) = mpsc::sync_channel(4);
    reader(stdout, true, sender.clone());
    reader(stderr, false, sender);
    let mut output = Vec::new();
    let (mut total, mut finished) = (0, 0);
    while finished < 2 {
        let remaining = deadline
            .checked_duration_since(Instant::now())
            .ok_or("E_TIMEOUT")?;
        match receiver.recv_timeout(remaining).map_err(|e| match e {
            mpsc::RecvTimeoutError::Timeout => "E_TIMEOUT",
            mpsc::RecvTimeoutError::Disconnected => "E_GIT",
        })? {
            Output::Chunk(stdout, raw) => {
                total += raw.len();
                if total > 65536 {
                    return Err("E_LIMIT");
                }
                if stdout {
                    output.extend_from_slice(&raw);
                }
            }
            Output::Done => finished += 1,
            Output::Error => return Err("E_GIT"),
        }
    }
    let status = loop {
        if Instant::now() >= deadline {
            return Err("E_TIMEOUT");
        }
        if let Some(status) = child.0.try_wait().map_err(|_| "E_GIT")? {
            break status;
        }
        std::thread::sleep(Duration::from_millis(1));
    };
    Ok((output, status))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[cfg(unix)]
    fn shell(source: &str) -> Child {
        Command::new("/bin/sh")
            .args(["-c", source])
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .unwrap_or_else(|_| unreachable!())
    }
    #[cfg(unix)]
    #[test]
    fn capture_bounds_combined_pipes_and_preserves_only_stdout() {
        let deadline = || Instant::now() + Duration::from_secs(2);
        let result = capture(
            shell("printf '%40000s' x; printf '%40000s' x >&2"),
            deadline(),
        );
        assert!(matches!(result, Err("E_LIMIT")));
        let result = capture(shell("printf '%65536s' x"), deadline());
        assert!(
            matches!(result, Ok((ref bytes, ref code)) if bytes.len() == 65536 && code.success())
        );
        let result = capture(
            shell("printf public; printf undisclosed >&2; exit 2"),
            deadline(),
        );
        assert!(
            matches!(result, Ok((ref bytes, ref code)) if bytes == b"public" && code.code() == Some(2))
        );
    }
    #[cfg(unix)]
    #[test]
    fn capture_kills_hanging_child_at_deadline() {
        let started = Instant::now();
        let result = capture(
            shell("while :; do :; done"),
            started + Duration::from_millis(50),
        );
        assert!(matches!(result, Err("E_TIMEOUT")));
        assert!(started.elapsed() < Duration::from_secs(2));
    }
    #[cfg(unix)]
    #[test]
    fn expired_call_refuses_before_git_spawn() -> Result<(), Box<dyn std::error::Error>> {
        let root = std::env::temp_dir().join(format!("git-deadline-{}", std::process::id()));
        std::fs::create_dir_all(&root)?;
        let result = (|| {
            let mut io = Guard::new(root.to_str().ok_or("root encoding")?)?;
            io.deadline = Instant::now() - Duration::from_millis(1);
            assert!(matches!(run(&mut io, Query::Head), Err("E_TIMEOUT")));
            Ok::<_, Box<dyn std::error::Error>>(())
        })();
        std::fs::remove_dir_all(&root)?;
        result
    }
    #[test]
    fn config_dialect_refuses_external_reads() {
        for source in [
            "[include]\npath = x",
            "[core]\nworktree = /x",
            "[remote \"x\"]\npromisor = true",
            "[extensions]\npartialClone = x",
            "[diff]\norderFile = x",
            "[core]\nfoo = x\\",
            "foo = x",
            "[core]extra",
        ] {
            assert!(!config_safe(source), "{source}");
        }
        assert!(config_safe(
            "# comment\n[core]\nrepositoryformatversion = 0\n[remote \"escaped\\\"name\"] ; x\nurl = ignored\n"
        ));
    }
    #[test]
    fn commits_and_paths_are_closed() {
        assert!(commit(&"a".repeat(40)));
        assert!(!commit(&"A".repeat(40)));
        assert_eq!(
            relative("./refs//heads/main"),
            Some("refs/heads/main".into())
        );
        for path in ["../x", "a/../x", "C:x", "-x", "/x", "a\\b", "."] {
            assert!(relative(path).is_none());
        }
    }
}
