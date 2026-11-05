//! Deterministic merge admission and isolated local verifier execution.
//!
//! Callers supply the dispatch, environment and scratch boundary explicitly. This
//! library never merges, commits, discovers repositories or launches a provider.
//! Verifiers execute argv directly in a detached checkout of the selected commit.
//! A timeout kills and reaps the immediate child, like Python subprocess.run;
//! descendant process groups are not part of that contract.
//! Dispatch metadata and profile paths remain caller-owned trusted inputs, as in
//! the Python oracle: profile copying follows symlinks and is not a sandbox.
use crate::{executor_local::LocalConfig, executor_worktree::DispatchWorktree};
use serde_json::Value;
use std::{
    collections::BTreeMap,
    ffi::OsStr,
    fmt, fs,
    io::{self, Read},
    path::{Path, PathBuf},
    process::{Command, Output, Stdio},
    sync::atomic::{AtomicU64, Ordering},
    thread,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

#[derive(Debug)]
pub enum Error {
    Io(io::Error),
    Unicode(std::string::FromUtf8Error),
    Git { code: Option<i32>, stderr: String },
    Local(crate::executor_local::Error),
    Worktree(crate::executor_worktree::Error),
    Invalid(String),
    Type(String),
    Pattern(crate::Error),
}
impl Error {
    pub fn kind(&self) -> &'static str {
        match self {
            Self::Io(e) => match e.kind() {
                io::ErrorKind::NotFound => "FileNotFoundError",
                io::ErrorKind::PermissionDenied => "PermissionError",
                io::ErrorKind::NotADirectory => "NotADirectoryError",
                io::ErrorKind::IsADirectory => "IsADirectoryError",
                io::ErrorKind::AlreadyExists => "FileExistsError",
                _ => "OSError",
            },
            Self::Unicode(_) => "UnicodeDecodeError",
            Self::Git { .. } => "CalledProcessError",
            Self::Local(e) => e.kind(),
            Self::Worktree(e) => e.kind(),
            Self::Invalid(_) | Self::Pattern(_) => "ValueError",
            Self::Type(_) => "TypeError",
        }
    }
}
impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Io(e) => e.fmt(f),
            Self::Unicode(e) => e.fmt(f),
            Self::Git { code, stderr } => write!(f, "git failed ({code:?}): {stderr}"),
            Self::Local(e) => e.fmt(f),
            Self::Worktree(e) => e.fmt(f),
            Self::Invalid(e) | Self::Type(e) => f.write_str(e),
            Self::Pattern(e) => write!(f, "pattern failed: {e:?}"),
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
            Self::Git { .. } | Self::Invalid(_) | Self::Type(_) | Self::Pattern(_) => None,
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

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MergeGate {
    pub approved: bool,
    pub reason: String,
    pub changed_files: Vec<String>,
}

#[derive(Debug, Clone)]
pub struct GateOptions {
    pub allowlist: Vec<String>,
    pub verification_commands: Vec<String>,
    /// JSON preserves the reference timeout validator, including booleans and
    /// fractional seconds. None means no timeout.
    pub verify_timeout: Option<Value>,
    pub allow_harness_self_modify: bool,
    pub expect_changes: bool,
    pub source_commit: Option<String>,
    pub scratch_root: PathBuf,
    pub source_env: BTreeMap<String, String>,
}
impl Default for GateOptions {
    fn default() -> Self {
        Self {
            allowlist: Vec::new(),
            verification_commands: Vec::new(),
            verify_timeout: None,
            allow_harness_self_modify: false,
            expect_changes: true,
            source_commit: None,
            scratch_root: std::env::temp_dir(),
            source_env: BTreeMap::new(),
        }
    }
}

fn git(root: &Path, args: &[&OsStr], check: bool) -> Result<Output> {
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
    let args: Vec<_> = args.iter().map(OsStr::new).collect();
    Ok(String::from_utf8(git(root, &args, true)?.stdout)?)
}
fn dirty(root: &Path) -> Result<bool> {
    Ok(!git_text(
        root,
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
fn denied(path: &str, self_modify: bool) -> bool {
    if path == "tasks/tdd.json" {
        return false;
    }
    let liftable = [".claude/", ".ai-harness/", "config/", "docs/"];
    if self_modify && liftable.iter().any(|prefix| path.starts_with(prefix)) {
        return false;
    }
    liftable.iter().any(|prefix| path.starts_with(prefix)) || path.starts_with("tasks/")
}

/// Only an explicitly declared meta-harness profile enables self-modification.
/// Missing, unreadable, malformed and differently shaped profiles deny it.
pub fn resolve_harness_self_modify(main_repo_root: &Path) -> bool {
    fs::read_to_string(main_repo_root.join(".mir/repo-profile.toml"))
        .ok()
        .and_then(|text| text.parse::<toml::Value>().ok())
        .and_then(|profile| {
            profile
                .get("repo")?
                .get("repository_type")?
                .as_str()
                .map(str::to_owned)
        })
        .is_some_and(|kind| kind == "meta_harness")
}

// Python fnmatchcase accepts slashes in '*', literal unmatched '[' and reversed
// ranges. Keep the same translator as the lifecycle gate's pinned implementation.
pub(crate) fn matches(pattern: &str, text: &str) -> Result<bool> {
    let chars: Vec<char> = pattern.chars().collect();
    let mut out = String::from("\\A(?s:");
    let mut i = 0;
    while i < chars.len() {
        match chars[i] {
            '*' => out.push_str(".*"),
            '?' => out.push('.'),
            '[' => {
                let mut j = i + 1;
                if chars.get(j) == Some(&'!') {
                    j += 1;
                }
                if chars.get(j) == Some(&']') {
                    j += 1;
                }
                while j < chars.len() && chars[j] != ']' {
                    j += 1;
                }
                if j >= chars.len() {
                    out.push_str("\\[");
                } else {
                    let mut chunks: Vec<Vec<char>> = Vec::new();
                    let mut start = i + 1;
                    let mut k = start + if chars[start] == '!' { 2 } else { 1 };
                    while let Some(offset) = chars[k.min(j)..j].iter().position(|c| *c == '-') {
                        k += offset;
                        chunks.push(chars[start..k].to_vec());
                        start = k + 1;
                        k += 3;
                    }
                    if start < j {
                        chunks.push(chars[start..j].to_vec());
                    } else if let Some(last) = chunks.last_mut() {
                        last.push('-');
                    }
                    for index in (1..chunks.len()).rev() {
                        if chunks[index - 1].last() > chunks[index].first() {
                            let next = chunks.remove(index);
                            chunks[index - 1].pop();
                            chunks[index - 1].extend(next.into_iter().skip(1));
                        }
                    }
                    let negate = chunks.first().and_then(|s| s.first()) == Some(&'!');
                    if negate {
                        chunks[0].remove(0);
                    }
                    if chunks.iter().all(Vec::is_empty) {
                        out.push_str(if negate { "." } else { "(?!)" });
                    } else {
                        out.push('[');
                        if negate {
                            out.push('^');
                        }
                        for (index, chunk) in chunks.iter().enumerate() {
                            if index > 0 {
                                out.push('-');
                            }
                            for c in chunk {
                                if matches!(c, '\\' | '-' | '[' | ']' | '^' | '&' | '~' | '|') {
                                    out.push('\\');
                                }
                                out.push(*c);
                            }
                        }
                        out.push(']');
                    }
                    i = j;
                }
            }
            c => out.push_str(&regex::escape(&c.to_string())),
        }
        i += 1;
    }
    out.push_str(")\\z");
    crate::has(&out, text, false).map_err(Error::Pattern)
}
fn path_allowed(path: &str, allowlist: &[String]) -> Result<bool> {
    for allowed in allowlist {
        if path == allowed
            || path.starts_with(&format!("{}/", allowed.trim_end_matches('/')))
            || matches(allowed, path)?
        {
            return Ok(true);
        }
    }
    Ok(false)
}
fn secret_patterns(repo: &Path) -> Result<Vec<String>> {
    // Missing, unreadable and malformed profiles are all explicitly ignored by
    // the Python profile-secret helper; unrelated errors elsewhere propagate.
    let Ok(bytes) = fs::read(repo.join(".mir/repo-profile.toml")) else {
        return Ok(Vec::new());
    };
    let text = String::from_utf8(bytes)?;
    let Ok(profile) = text.parse::<toml::Value>() else {
        return Ok(Vec::new());
    };
    Ok(profile
        .get("boundaries")
        .and_then(|v| v.get("secrets"))
        .and_then(toml::Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(toml::Value::as_str)
        .map(str::to_owned)
        .collect())
}
fn is_secret(path: &str, patterns: &[String]) -> Result<bool> {
    for pattern in patterns {
        if pattern.contains('/') {
            if matches(pattern, path)? {
                return Ok(true);
            }
        } else {
            for part in path.split('/') {
                if matches(pattern, part)? {
                    return Ok(true);
                }
            }
        }
    }
    Ok(false)
}
fn repr(text: &str) -> Result<String> {
    let nonprintable =
        regex::Regex::new(r"[\p{C}\p{Z}]").map_err(|e| Error::Invalid(e.to_string()))?;
    let quote = if text.contains('\'') && !text.contains('"') {
        '"'
    } else {
        '\''
    };
    let mut out = quote.to_string();
    for c in text.chars() {
        match c {
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if c == quote => {
                out.push('\\');
                out.push(c);
            }
            c if c != ' ' && nonprintable.is_match(c.encode_utf8(&mut [0; 4])) => {
                let n = c as u32;
                out.push_str(&if n <= 0xff {
                    format!("\\x{n:02x}")
                } else if n <= 0xffff {
                    format!("\\u{n:04x}")
                } else {
                    format!("\\U{n:08x}")
                });
            }
            c => out.push(c),
        }
    }
    out.push(quote);
    Ok(out)
}
pub(crate) fn changed_repr(changed: &[String]) -> Result<String> {
    Ok(format!(
        "[{}]",
        changed
            .iter()
            .map(|s| repr(s))
            .collect::<Result<Vec<_>>>()?
            .join(", ")
    ))
}

static NEXT_TEMP: AtomicU64 = AtomicU64::new(0);
struct TempDir(PathBuf, bool);
impl TempDir {
    fn create(root: &Path, prefix: &str) -> Result<Self> {
        fs::create_dir_all(root)?;
        let root = crate::supply::plain(fs::canonicalize(root)?);
        for _ in 0..100 {
            let stamp = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .map_err(|_| Error::Invalid("system clock predates epoch".into()))?
                .as_nanos();
            let path = root.join(format!(
                "{prefix}{}-{stamp}-{}",
                std::process::id(),
                NEXT_TEMP.fetch_add(1, Ordering::Relaxed)
            ));
            #[cfg(unix)]
            let builder = {
                use std::os::unix::fs::DirBuilderExt;
                let mut builder = fs::DirBuilder::new();
                builder.mode(0o700);
                builder
            };
            #[cfg(not(unix))]
            let builder = fs::DirBuilder::new();
            match builder.create(&path) {
                Ok(()) => return Ok(Self(path, true)),
                Err(e) if e.kind() == io::ErrorKind::AlreadyExists => {}
                Err(e) => return Err(e.into()),
            }
        }
        Err(Error::Invalid(
            "cannot allocate verifier temporary directory".into(),
        ))
    }

    fn close(&mut self) -> Result<()> {
        match fs::remove_dir_all(&self.0) {
            Ok(()) => {}
            Err(e) if e.kind() == io::ErrorKind::NotFound => {}
            Err(e) => return Err(e.into()),
        }
        self.1 = false;
        Ok(())
    }
}
impl Drop for TempDir {
    fn drop(&mut self) {
        if self.1 {
            let _ = fs::remove_dir_all(&self.0);
        }
    }
}

fn verifier_env(
    repo: &Path,
    options: &GateOptions,
) -> Result<(BTreeMap<String, String>, Option<TempDir>)> {
    let config = LocalConfig::load(repo).map_err(Error::Local)?;
    if config.verifier_env().map_err(Error::Local)? == "inherit" {
        return Ok((
            crate::executor_worktree::dispatch_env(repo, &options.source_env, None, true)
                .map_err(Error::Worktree)?,
            None,
        ));
    }
    let mut keys = vec!["PATH".to_owned(), "LANG".into(), "TMPDIR".into()];
    if let Some(extras) = config.raw().get("child_env_extra_keys") {
        match extras {
            Value::Array(values) => {
                for value in values {
                    match value {
                        Value::String(s) => keys.push(s.clone()),
                        Value::Array(_) => {
                            return Err(Error::Type("unhashable type: 'list'".into()));
                        }
                        Value::Object(_) if value.get(config.numeric_tag()).is_none() => {
                            return Err(Error::Type("unhashable type: 'dict'".into()));
                        }
                        _ => {}
                    }
                }
            }
            Value::Object(values) if extras.get(config.numeric_tag()).is_none() => {
                keys.extend(values.keys().cloned())
            }
            Value::String(s) => keys.extend(s.chars().map(|c| c.to_string())),
            _ => return Err(Error::Type("child_env_extra_keys must be iterable".into())),
        }
    }
    let mut env: BTreeMap<_, _> = options
        .source_env
        .iter()
        .filter(|(k, _)| keys.contains(k) || k.starts_with("LC_"))
        .map(|(k, v)| (k.clone(), v.clone()))
        .collect();
    let home = TempDir::create(&options.scratch_root, "mir-verifier-")?;
    let cache = home.0.join("uv-cache");
    fs::create_dir(&cache)?;
    env.insert(
        "HOME".into(),
        home.0
            .to_str()
            .ok_or_else(|| Error::Invalid("non UTF-8 verifier home".into()))?
            .into(),
    );
    env.insert(
        "UV_CACHE_DIR".into(),
        cache
            .to_str()
            .ok_or_else(|| Error::Invalid("non UTF-8 verifier cache".into()))?
            .into(),
    );
    Ok((env, Some(home)))
}

fn timeout_duration(value: Option<&Value>) -> Result<Option<Duration>> {
    match value.filter(|v| !v.is_null()) {
        None => Ok(None),
        Some(value) => {
            let seconds = if value == &Value::Bool(true) {
                1.0
            } else {
                value
                    .as_f64()
                    .ok_or_else(|| Error::Invalid("unrepresentable timeout".into()))?
            };
            Duration::try_from_secs_f64(seconds)
                .map(Some)
                .map_err(|_| Error::Invalid("unrepresentable timeout".into()))
        }
    }
}

enum Verification {
    Success,
    Failed,
    Timeout,
}
fn run_verifier(
    argv: &[String],
    root: &Path,
    env: &BTreeMap<String, String>,
    timeout: Option<Duration>,
) -> Result<Verification> {
    // Drain both pipes immediately, including descriptors inherited by a
    // verifier's descendants, like subprocess.communicate. Every exit path joins
    // both readers after reaping the child; no reader threads are detached.
    let program = argv
        .first()
        .ok_or_else(|| Error::Invalid("empty verifier argv".into()))?;
    let mut command = Command::new(program);
    command
        .args(&argv[1..])
        .current_dir(root)
        .env_clear()
        .envs(env)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    let mut child = command.spawn()?;
    let started = Instant::now();
    let Some(stdout) = child.stdout.take() else {
        let _ = child.kill();
        let _ = child.wait();
        return Err(Error::Invalid("missing verifier stdout pipe".into()));
    };
    let Some(stderr) = child.stderr.take() else {
        let _ = child.kill();
        let _ = child.wait();
        return Err(Error::Invalid("missing verifier stderr pipe".into()));
    };
    let stdout_reader = match thread::Builder::new()
        .name("verifier-stdout".into())
        .spawn(move || read_pipe(stdout))
    {
        Ok(reader) => reader,
        Err(e) => {
            let _ = child.kill();
            let _ = child.wait();
            return Err(e.into());
        }
    };
    let stderr_reader = match thread::Builder::new()
        .name("verifier-stderr".into())
        .spawn(move || read_pipe(stderr))
    {
        Ok(reader) => reader,
        Err(e) => {
            let _ = child.kill();
            let _ = child.wait();
            let _ = finish_reader(stdout_reader);
            return Err(e.into());
        }
    };
    let mut child_status = None;
    let outcome = loop {
        match child.try_wait() {
            Ok(Some(status)) => child_status = Some(status),
            Ok(None) => {}
            Err(e) => {
                let _ = child.kill();
                let _ = child.wait();
                break Err(e.into());
            }
        }
        if stdout_reader.is_finished()
            && stderr_reader.is_finished()
            && let Some(status) = child_status
        {
            break Ok(if status.success() {
                Verification::Success
            } else {
                Verification::Failed
            });
        }
        if timeout.is_some_and(|limit| started.elapsed() >= limit) {
            // Always reap, even when the process exits between the poll and kill.
            let kill = child.kill();
            let status = child.wait();
            break status.map_err(Error::Io).and_then(|_| {
                if let Err(e) = kill
                    && e.kind() != io::ErrorKind::InvalidInput
                {
                    return Err(e.into());
                }
                Ok(Verification::Timeout)
            });
        }
        let pause = timeout.map_or(Duration::from_millis(5), |limit| {
            limit
                .saturating_sub(started.elapsed())
                .min(Duration::from_millis(5))
        });
        thread::sleep(pause);
    };
    let stdout = finish_reader(stdout_reader);
    let stderr = finish_reader(stderr_reader);
    match outcome? {
        Verification::Timeout => Ok(Verification::Timeout),
        completed => {
            String::from_utf8(stdout?)?;
            String::from_utf8(stderr?)?;
            Ok(completed)
        }
    }
}

fn read_pipe(mut pipe: impl Read) -> io::Result<Vec<u8>> {
    let mut bytes = Vec::new();
    pipe.read_to_end(&mut bytes)?;
    Ok(bytes)
}

fn finish_reader(reader: thread::JoinHandle<io::Result<Vec<u8>>>) -> Result<Vec<u8>> {
    reader
        .join()
        .map_err(|_| Error::Invalid("verifier output reader panicked".into()))?
        .map_err(Error::Io)
}

fn isolated(
    wt: &DispatchWorktree,
    source: &str,
    commands: &[Vec<String>],
    options: &GateOptions,
) -> Result<String> {
    let mut temp = TempDir::create(&options.scratch_root, "mir-verify-")?;
    let root = temp.0.join("worktree");
    git(
        &wt.main_repo_root,
        &[
            OsStr::new("worktree"),
            OsStr::new("add"),
            OsStr::new("--detach"),
            root.as_os_str(),
            OsStr::new(source),
        ],
        true,
    )?;
    let result = (|| {
        let profile = wt.path.join(".mir/repo-profile.toml");
        if profile.is_file() {
            let target = root.join(".mir/repo-profile.toml");
            fs::create_dir_all(
                target
                    .parent()
                    .ok_or_else(|| Error::Invalid("missing profile parent".into()))?,
            )?;
            fs::copy(profile, target)?;
        }
        for (id, argv) in options.verification_commands.iter().zip(commands) {
            let (env, mut home) = verifier_env(&wt.main_repo_root, options)?;
            let result = timeout_duration(options.verify_timeout.as_ref())
                .and_then(|timeout| run_verifier(argv, &root, &env, timeout));
            // The isolated-home context exits even on spawn errors or timeout;
            // unlike worktree scratch cleanup, its failures must propagate.
            if let Some(home) = home.as_mut() {
                home.close()?;
            }
            match result? {
                Verification::Timeout => return Ok("verification-timeout".into()),
                Verification::Failed => return Ok(format!("verification-failed:{id}")),
                Verification::Success => {}
            }
        }
        Ok("approved".into())
    })();
    let removed = git(
        &wt.main_repo_root,
        &[
            OsStr::new("worktree"),
            OsStr::new("remove"),
            OsStr::new("--force"),
            root.as_os_str(),
        ],
        false,
    );
    if !removed.is_ok_and(|output| output.status.success()) {
        let _ = git(
            &wt.main_repo_root,
            &[OsStr::new("worktree"), OsStr::new("prune")],
            false,
        );
        if root.exists() {
            // Preserve failed-cleanup evidence; do not delete a still registered
            // worktree behind Git's back. Ownership passes to the caller.
            temp.1 = false;
        }
        return Ok("verification-cleanup-failed".into());
    }
    result
}

/// Preserve gate ordering: timeout policy, pinned diff, harness/secrets/allowlist,
/// verifier definitions, dispatch cleanliness, isolated execution and cleanup,
/// then dispatch cleanliness again. Cleanup failure overrides verifier outcomes.
pub fn evaluate_merge_gate(wt: &DispatchWorktree, options: &GateOptions) -> Result<MergeGate> {
    let config = LocalConfig::load(&wt.main_repo_root).map_err(Error::Local)?;
    config
        .validate_timeout(options.verify_timeout.as_ref())
        .map_err(Error::Local)?;
    let source = match &options.source_commit {
        Some(source) => source.clone(),
        None => git_text(&wt.path, &["rev-parse", "HEAD"])?
            .trim()
            .to_owned(),
    };
    let changed: Vec<String> = git_text(
        &wt.path,
        &[
            "diff",
            "--no-renames",
            "--name-only",
            "-z",
            &wt.base_commit,
            &source,
        ],
    )?
    .split('\0')
    .filter(|p| !p.is_empty())
    .map(str::to_owned)
    .collect();
    let gate = |reason: String| MergeGate {
        approved: reason == "approved",
        reason,
        changed_files: changed.clone(),
    };
    if options.expect_changes && changed.is_empty() {
        return Ok(gate("empty-diff fail-closed".into()));
    }
    for path in &changed {
        if denied(path, options.allow_harness_self_modify) {
            return Ok(gate(format!(
                "denied-harness:{path}; changed={}",
                changed_repr(&changed)?
            )));
        }
    }
    let secrets = secret_patterns(&wt.main_repo_root)?;
    for path in &changed {
        if is_secret(path, &secrets)? {
            return Ok(gate(format!("secret-path:{path}")));
        }
    }
    for path in &changed {
        if !path_allowed(path, &options.allowlist)? {
            return Ok(gate(format!("out-of-allowlist:{path}")));
        }
    }
    if options.verification_commands.is_empty() {
        return Ok(gate("no-verification-commands (fail-closed)".into()));
    }
    let ids: Vec<_> = options
        .verification_commands
        .iter()
        .map(String::as_str)
        .collect();
    let commands = match config.verifier_commands(&ids) {
        Ok(commands) => commands,
        Err(crate::executor_local::Error::Invalid(reason))
            if reason.starts_with("unknown-verifier:")
                || reason.starts_with("invalid-verifier:") =>
        {
            return Ok(gate(reason));
        }
        Err(e) => return Err(Error::Local(e)),
    };
    if dirty(&wt.path)? {
        return Ok(gate("dispatch-dirty".into()));
    }
    let reason = isolated(wt, &source, &commands, options)?;
    if reason != "approved" {
        return Ok(gate(reason));
    }
    if dirty(&wt.path)? {
        return Ok(gate("dispatch-dirty".into()));
    }
    Ok(gate("approved".into()))
}
