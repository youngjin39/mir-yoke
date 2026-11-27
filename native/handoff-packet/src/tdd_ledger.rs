//! Yoke's own ledger contract. Unknown composite category names are intentional.
use handoff_packet::mir_cli::bootstrap_adoption::is_python_space;
use handoff_packet::python_json::{self, Value, python_splitlines, python_strip};
#[cfg(not(unix))]
use std::sync::mpsc;
use std::{
    fs,
    io::{self, Read},
    path::{Path, PathBuf},
    process::{Child, Command, Output, Stdio},
    thread,
    time::{Duration, Instant},
};
const CATEGORIES: &[&str] = &[
    "unit",
    "integration",
    "e2e",
    "browser",
    "edge",
    "architecture",
    "availability",
    "load",
    "soak",
    "security",
    "compatibility",
    "transaction_locking",
];
pub fn implementation(path: &str) -> bool {
    [
        "src/",
        "app/",
        "apps/",
        "packages/",
        "pipelines/",
        "infra/",
        "content/",
        "lib/",
    ]
    .iter()
    .any(|r| path.starts_with(r))
        && [
            ".py", ".js", ".ts", ".jsx", ".tsx", ".rb", ".go", ".rs", ".java", ".kt", ".swift",
            ".c", ".cc", ".cpp", ".h", ".hpp", ".sql",
        ]
        .iter()
        .any(|s| path.ends_with(s))
}
fn normalize(project: &Path, raw: &str) -> String {
    let s = python_strip(raw).replace('\\', "/");
    let s = s.strip_prefix("./").unwrap_or(&s);
    s.strip_prefix(&format!("{}/", project.display()).replace('\\', "/"))
        .unwrap_or(s)
        .into()
}
fn matches(target: &str, path: &str) -> bool {
    let t = python_strip(target);
    !t.is_empty()
        && if t.ends_with('/') {
            path.starts_with(t)
        } else {
            path == t
        }
}
fn find<'a>(data: &'a Value, path: &str) -> Option<&'a Value> {
    data["changes"].as_array()?.iter().find(|c| {
        c["target"].as_str().is_some_and(|t| matches(t, path))
            || c["targets"].as_array().is_some_and(|ts| {
                ts.iter()
                    .any(|t| t.as_str().is_some_and(|t| matches(t, path)))
            })
    })
}
fn py(value: &Value) -> String {
    value.py_str()
}
fn repr(value: &Value) -> String {
    value.repr()
}
fn hashable(value: &Value) -> Result<(), String> {
    if value.is_array() || value.is_object() {
        return Err(format!(
            "TypeError: unhashable type: '{}'",
            value.type_name()
        ));
    }
    Ok(())
}
fn nonempty_string(value: &Value) -> bool {
    value
        .as_text()
        .is_some_and(|s| s.as_str().is_none_or(|s| !python_strip(s).is_empty()))
}
fn validate(c: &Value, phase: &str) -> Result<Vec<Vec<u32>>, String> {
    let prefix = if phase == "prewrite" {
        "[TddGuard BLOCK]"
    } else {
        "[PreCommitVerification BLOCK]"
    };
    let composite = c.get("targets").is_some();
    if !composite {
        for key in ["target", "bluebrick", "design_ref"] {
            if !nonempty_string(&c[key]) {
                return Err(format!("{prefix} Missing '{key}' for target."));
            }
        }
    }
    let Some(cats) = c["categories"].as_object() else {
        return Err(format!(
            "{prefix} Missing 'categories' object for target {}.",
            py(&c["target"])
        ));
    };
    let entries: Vec<(String, &Value)> = if composite {
        cats.iter()
            .map(|(key, value)| (key.py_str(), value))
            .collect()
    } else {
        CATEGORIES
            .iter()
            .map(|key| ((*key).into(), &c["categories"][*key]))
            .collect()
    };
    let label = c
        .get("target")
        .filter(|s| s.truthy())
        .map(py)
        .unwrap_or_else(|| c.get("id").map(py).unwrap_or_else(|| "<unknown>".into()));
    let mut commands = Vec::new();
    for (key, entry) in entries {
        if !entry.is_object() {
            return Err(format!(
                "{prefix} Missing category '{key}' for target {label}."
            ));
        }
        hashable(&entry["status"])?;
        let status = entry["status"].as_str().unwrap_or("");
        if !["pass", "covered_existing", "not_applicable"].contains(&status)
            && !(phase == "prewrite" && status == "planned")
        {
            return Err(if phase == "precommit" && status == "planned" {
                format!("{prefix} Category '{key}' is still planned for target {label}.")
            } else {
                format!(
                    "{prefix} Invalid status '{}' for category '{key}' in target {label}.",
                    py(&entry["status"])
                )
            });
        }
        if status == "not_applicable" && !nonempty_string(&entry["reason"]) {
            return Err(format!(
                "{prefix} Category '{key}' marked not_applicable without reason for target {label}."
            ));
        }
        if ["pass", "covered_existing"].contains(&status) {
            if !nonempty_string(&entry["command"]) {
                return Err(format!(
                    "{prefix} Category '{key}' requires a runnable command for target {label}."
                ));
            }
            if let Some(command) = entry["command"].as_text() {
                let points = &command.codepoints;
                let nonspace = |cp: &u32| !char::from_u32(*cp).is_some_and(is_python_space);
                let start = points.iter().position(nonspace).unwrap_or(points.len());
                let end = points.iter().rposition(nonspace).map_or(start, |i| i + 1);
                commands.push(points[start..end].to_vec());
            }
        }
    }
    Ok(commands)
}
fn load(project: &Path) -> Result<Ledger, String> {
    let path = project.join("tasks/tdd.json");
    if !path.is_file() {
        return Err("[TddGuard BLOCK] Missing tasks/tdd.json. Create the composite TDD ledger before editing code.".into());
    }
    let raw = fs::read_to_string(path).map_err(|e| e.to_string())?;
    // Path.read_text uses universal newline translation before json.loads.
    let raw = raw.replace("\r\n", "\n").replace('\r', "\n");
    let v = python_json::parse(&raw).map_err(|e| {
        if e.exception == "JSONDecodeError" {
            format!("[TddGuard BLOCK] Malformed tasks/tdd.json: {e}")
        } else {
            format!("{}: {e}", e.exception)
        }
    })?;
    let ledger = Ledger { data: v };
    if !ledger.data.is_object() {
        return Err("[TddGuard BLOCK] tasks/tdd.json must contain a JSON object.".into());
    }
    if !ledger.data["changes"].is_array() {
        return Err("[TddGuard BLOCK] tasks/tdd.json must contain a 'changes' array.".into());
    }
    Ok(ledger)
}
fn git_error(error: io::Error) -> String {
    if error.kind() == io::ErrorKind::PermissionDenied {
        "PermissionError: [Errno 13] Permission denied: 'git'".into()
    } else {
        format!("OSError: {error}")
    }
}
fn git_text(bytes: Vec<u8>) -> Result<String, String> {
    String::from_utf8(bytes).map_err(|error| {
        let invalid = error.utf8_error();
        let start = invalid.valid_up_to();
        let (length, reason) = match invalid.error_len() {
            Some(length) => (
                length,
                if error.as_bytes()[start] < 0xc2 || error.as_bytes()[start] > 0xf4 {
                    "invalid start byte"
                } else {
                    "invalid continuation byte"
                },
            ),
            None => (error.as_bytes().len() - start, "unexpected end of data"),
        };
        let position = if length == 1 {
            format!("byte 0x{:02x} in position {start}", error.as_bytes()[start])
        } else {
            format!("bytes in position {start}-{}", start + length - 1)
        };
        format!("UnicodeDecodeError: 'utf-8' codec can't decode {position}: {reason}")
    })
}
#[cfg(unix)]
fn read_git_pipe(
    pipe: &mut Option<impl Read>,
    output: &mut Vec<u8>,
    buffer: &mut [u8],
) -> io::Result<bool> {
    let Some(stream) = pipe else {
        return Ok(false);
    };
    match stream.read(buffer) {
        Ok(0) => {
            *pipe = None;
            Ok(false)
        }
        Ok(count) => {
            output.extend_from_slice(&buffer[..count]);
            Ok(true)
        }
        Err(error)
            if matches!(
                error.kind(),
                io::ErrorKind::WouldBlock | io::ErrorKind::Interrupted
            ) =>
        {
            Ok(false)
        }
        Err(error) => Err(error),
    }
}

#[cfg(unix)]
fn capture_git(child: &mut Child, deadline: Instant) -> Result<Option<Output>, String> {
    use handoff_packet::mir_cli::project_hooks::nonblocking_pipe;

    // Own both read handles here so the timeout closes them before fallback,
    // even if a descendant still owns a write handle after Git exits.
    let mut stdout = child.stdout.take();
    let mut stderr = child.stderr.take();
    if let Some(pipe) = &stdout {
        nonblocking_pipe(pipe).map_err(git_error)?;
    }
    if let Some(pipe) = &stderr {
        nonblocking_pipe(pipe).map_err(git_error)?;
    }

    let mut out = Vec::new();
    let mut err = Vec::new();
    let mut buffer = [0; 8192];
    while Instant::now() < deadline {
        let read_stdout = read_git_pipe(&mut stdout, &mut out, &mut buffer).map_err(git_error)?;
        let read_stderr = read_git_pipe(&mut stderr, &mut err, &mut buffer).map_err(git_error)?;
        if stdout.is_none()
            && stderr.is_none()
            && let Some(status) = child.try_wait().map_err(git_error)?
        {
            return Ok(Some(Output {
                status,
                stdout: out,
                stderr: err,
            }));
        }
        if !read_stdout && !read_stderr {
            thread::sleep(Duration::from_millis(10));
        }
    }
    Ok(None)
}

#[cfg(not(unix))]
fn git_reader(pipe: Option<impl Read + Send + 'static>) -> mpsc::Receiver<io::Result<Vec<u8>>> {
    let (send, receive) = mpsc::channel();
    thread::spawn(move || {
        let mut bytes = Vec::new();
        let result = match pipe {
            Some(mut pipe) => pipe.read_to_end(&mut bytes).map(|_| bytes),
            None => Ok(bytes),
        };
        let _ = send.send(result);
    });
    receive
}
#[cfg(not(unix))]
fn capture_git(child: &mut Child, deadline: Instant) -> Result<Option<Output>, String> {
    // Drain both pipes while waiting, like subprocess.run(capture_output=True).
    let stdout = git_reader(child.stdout.take());
    let stderr = git_reader(child.stderr.take());
    let status = loop {
        if let Some(status) = child.try_wait().map_err(git_error)? {
            break status;
        }
        if Instant::now() >= deadline {
            return Ok(None);
        }
        thread::sleep(Duration::from_millis(10));
    };
    // Git can exit before descendants close inherited pipes. Use the same
    // deadline for the capture and discard partial output on timeout.
    let capture = |reader: mpsc::Receiver<io::Result<Vec<u8>>>| match reader
        .recv_timeout(deadline.saturating_duration_since(Instant::now()))
    {
        Ok(result) => result.map(Some).map_err(git_error),
        Err(mpsc::RecvTimeoutError::Timeout) => Ok(None),
        Err(mpsc::RecvTimeoutError::Disconnected) => {
            Err("RuntimeError: Git output reader failed".into())
        }
    };
    let Some(stdout) = capture(stdout)? else {
        return Ok(None);
    };
    let Some(stderr) = capture(stderr)? else {
        return Ok(None);
    };
    Ok(Some(Output {
        status,
        stdout,
        stderr,
    }))
}

fn git_run(project: &Path, args: &[&str]) -> Result<Option<String>, String> {
    let mut child = match Command::new("git")
        .args(args)
        .current_dir(project)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
    {
        Ok(child) => child,
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(git_error(error)),
    };
    let output = match capture_git(&mut child, Instant::now() + Duration::from_secs(10)) {
        Ok(Some(output)) => output,
        Ok(None) => {
            if child.try_wait().map_err(git_error)?.is_none() {
                child.kill().map_err(git_error)?;
                child.wait().map_err(git_error)?;
            }
            // The Python reference catches TimeoutExpired without decoding its output.
            return Ok(None);
        }
        Err(error) => {
            let _ = child.kill();
            let _ = child.wait();
            return Err(error);
        }
    };
    let stdout = git_text(output.stdout)?;
    git_text(output.stderr)?;
    Ok(output.status.success().then_some(stdout))
}
fn git_changed(project: &Path) -> Result<Vec<String>, String> {
    let lines = |s: String| {
        python_splitlines(&s)
            .into_iter()
            .filter(|s| !python_strip(s).is_empty())
            .map(str::to_owned)
            .collect::<Vec<_>>()
    };
    if let Some(out) = git_run(project, &["diff", "--name-only", "@{upstream}..HEAD"])? {
        if !lines(out.clone()).is_empty() {
            return Ok(lines(out));
        }
        return Ok(git_run(project, &["diff", "--name-only", "HEAD"])?
            .map(lines)
            .unwrap_or_default());
    }
    for reference in ["origin/main..HEAD", "main..HEAD"] {
        if let Some(out) = git_run(project, &["diff", "--name-only", reference])?
            && !python_strip(&out).is_empty()
        {
            return Ok(lines(out));
        }
    }
    Ok(git_run(project, &["diff", "--name-only", "HEAD"])?
        .map(lines)
        .unwrap_or_default())
}
fn meta(p: &str) -> bool {
    [
        "tasks/tdd.json",
        "tasks/plan.md",
        "tasks/checklist.md",
        "tasks/change_log.md",
        "tasks/lessons.md",
        "tasks/cost-log.md",
        "docs/memory-map.md",
    ]
    .contains(&p)
        || ["tasks/sessions/", "tasks/log/", "tasks/handoffs/"]
            .iter()
            .any(|s| p.starts_with(s))
}
fn attribute(value: &Value, name: &str) -> String {
    format!(
        "AttributeError: '{}' object has no attribute '{name}'",
        value.type_name()
    )
}
fn merge_relevant(change: &Value, changed: &[String]) -> Result<bool, String> {
    let Some(targets) = change.get("targets") else {
        return Ok(false);
    };
    let mut code_targets = Vec::new();
    if let Some(targets) = targets.as_array() {
        for target in targets {
            // Python checks set membership before calling startswith.
            hashable(target)?;
            if target.as_text().is_some_and(|text| text.has_surrogates()) {
                // A Python string remains string-typed, but cannot match the
                // strictly decoded Git paths retained by this operation.
                continue;
            }
            let Some(target) = target.as_str() else {
                return Err(attribute(target, "startswith"));
            };
            if !meta(target) {
                code_targets.push(target.to_owned());
            }
        }
    } else if let Some(targets) = targets.as_object() {
        code_targets.extend(
            targets
                .keys()
                .filter_map(|t| t.as_str())
                .filter(|t| !meta(t))
                .map(str::to_owned),
        );
    } else if let Some(targets) = targets.as_text() {
        code_targets.extend(
            targets
                .codepoints
                .iter()
                .filter_map(|cp| char::from_u32(*cp))
                .map(|c| c.to_string())
                .filter(|t| !meta(t)),
        );
    } else {
        return Err(format!(
            "TypeError: '{}' object is not iterable",
            targets.type_name()
        ));
    }
    Ok(code_targets
        .iter()
        .any(|t| changed.iter().filter(|p| !meta(p)).any(|p| matches(t, p))))
}
fn merge(project: &Path, ledger: &Ledger) -> (u8, String, String) {
    let data = &ledger.data;
    let changed = match git_changed(project) {
        Ok(changed) => changed,
        Err(error) => return (1, String::new(), format!("{error}\n")),
    };
    if changed.is_empty() {
        return (0, String::new(), String::new());
    }
    let mut blockers = Vec::new();
    let mut warnings = Vec::new();
    let fail = |message: String| (1, String::new(), format!("{message}\n"));
    if let Some(changes) = data["changes"].as_array() {
        for c in changes {
            if !c.is_object() {
                return fail(attribute(c, "get"));
            }
            let id = c.get("id").map(py).unwrap_or_else(|| "<unnamed>".into());
            let relevant = match merge_relevant(c, &changed) {
                Ok(value) => value,
                Err(error) => return fail(error),
            };
            let mut violations = Vec::new();
            if let Some(categories) = c.get("categories") {
                let Some(cats) = categories.as_object() else {
                    return fail(attribute(categories, "items"));
                };
                for (key, value) in cats.iter() {
                    if !value.is_object() {
                        continue;
                    }
                    if let Err(error) = hashable(&value["status"]) {
                        return fail(error);
                    }
                    if !["pass", "covered_existing", "not_applicable"]
                        .contains(&value["status"].as_str().unwrap_or(""))
                    {
                        violations.push(format!(
                            "{}.status={}",
                            key.py_str(),
                            repr(&value["status"])
                        ));
                    }
                }
            }
            if !violations.is_empty() {
                if relevant {
                    blockers.push(format!("{id}: {}", violations.join(", ")));
                } else {
                    warnings.push(id);
                }
            }
        }
    }
    if let Some(obj) = data.as_object() {
        for (key, v) in obj.iter() {
            let k = key.py_str();
            if k != "version"
                && k != "changes"
                && v.is_object()
                && !v["status"].is_null()
                && let Err(error) = hashable(&v["status"])
            {
                return fail(error);
            }
            if k != "version"
                && k != "changes"
                && v.is_object()
                && !v["status"].is_null()
                && !["closed", "done"].contains(&v["status"].as_str().unwrap_or(""))
            {
                warnings.push(format!("{k}.status={}", repr(&v["status"])));
            }
        }
    }
    let mut err = String::new();
    if !warnings.is_empty() {
        err.push_str(&format!("[pre-merge-gate INFO] legacy/un-touched tdd entries with open categories (grandfathered, not blocking): {}\n",warnings.len()));
    }
    if !blockers.is_empty() {
        err.push_str(&format!(
            "[pre-merge-gate BLOCK] tdd.json has open categories for files in this PR:\n  - {}\n",
            blockers.join("\n  - ")
        ));
    }
    (if blockers.is_empty() { 0 } else { 2 }, String::new(), err)
}
pub fn matrix(args: &[String]) -> (u8, String, String) {
    let fail = |code, msg: String| (code, String::new(), format!("{msg}\n"));
    if args.len() < 2 {
        return fail(2,"usage: tdd-matrix-guard.py <prewrite|precommit|precommit-merge> <project_dir> [<target>]".into());
    }
    let project = fs::canonicalize(&args[1]).unwrap_or_else(|_| PathBuf::from(&args[1]));
    let mode = args[0].as_str();
    if mode != "precommit-merge" && args.len() < 3 {
        return fail(
            2,
            "usage: tdd-matrix-guard.py <prewrite|precommit> <project_dir> <target>".into(),
        );
    }
    if !["prewrite", "precommit", "precommit-merge"].contains(&mode) {
        return fail(2, format!("unknown mode: {mode}"));
    }
    let data = match load(&project) {
        Ok(v) => v,
        Err(e) => return fail(1, e),
    };
    if mode == "precommit-merge" {
        return merge(&project, &data);
    }
    let paths = if mode == "prewrite" {
        vec![normalize(&project, &args[2])]
    } else {
        if !Path::new(&args[2]).is_file() {
            return fail(
                2,
                "[PreCommitVerification BLOCK] Missing changed-file list input.".into(),
            );
        }
        match fs::read_to_string(&args[2]) {
            Ok(s) => python_splitlines(&s)
                .into_iter()
                .map(|p| normalize(&project, p))
                .filter(|p| implementation(p))
                .collect(),
            Err(e) => return fail(1, e.to_string()),
        }
    };
    validate_paths(&data, mode, paths)
}

/// Validate staged implementation paths without a helper process or temporary list.
pub fn precommit(project: &Path, paths: Vec<String>) -> (u8, String, String) {
    match load(project) {
        Ok(data) => validate_paths(&data, "precommit", paths),
        Err(error) => (1, String::new(), format!("{error}\n")),
    }
}

fn validate_paths(data: &Ledger, mode: &str, paths: Vec<String>) -> (u8, String, String) {
    let fail = |code, msg: String| (code, String::new(), format!("{msg}\n"));
    let mut commands = Vec::new();
    for path in paths {
        let Some(c) = find(&data.data, &path) else {
            return fail(
                2,
                format!(
                    "[{} BLOCK] No composite TDD entry found in tasks/tdd.json for {path}.",
                    if mode == "prewrite" {
                        "TddGuard"
                    } else {
                        "PreCommitVerification"
                    }
                ),
            );
        };
        match validate(c, mode) {
            Err(e) => return fail(1, e),
            Ok(cs) => {
                for c in cs {
                    if !commands.contains(&c) {
                        commands.push(c);
                    }
                }
            }
        }
    }
    let mut stdout = String::new();
    if mode == "precommit" {
        for command in commands {
            if let Some(start) = command.iter().position(|cp| char::from_u32(*cp).is_none()) {
                let end = command
                    .iter()
                    .skip(start)
                    .take_while(|cp| char::from_u32(**cp).is_none())
                    .count()
                    + start;
                let position = if end == start + 1 {
                    format!("character '\\u{:04x}' in position {start}", command[start])
                } else {
                    format!("characters in position {start}-{}", end - 1)
                };
                return (
                    1,
                    stdout,
                    format!(
                        "UnicodeEncodeError: 'utf-8' codec can't encode {position}: surrogates not allowed\n"
                    ),
                );
            }
            stdout.extend(command.into_iter().filter_map(char::from_u32));
            stdout.push('\n');
        }
    }
    (0, stdout, String::new())
}
pub fn guard(project: &Path, target: &str) -> (u8, String, String) {
    let path = target.strip_prefix("./").unwrap_or(target);
    let rel = path
        .strip_prefix(&format!("{}/", project.display()))
        .unwrap_or(path);
    if target.is_empty() || !project.is_dir() || !implementation(rel) {
        return (0, String::new(), String::new());
    }
    // The ledger is validated in-process; the retired Python helper and its
    // interpreter route are no longer consulted.
    let err = if matrix(&["prewrite".into(), project.display().to_string(), rel.into()]).0 != 0 {
        format!("[TddGuard WARN] composite TDD evidence is incomplete for {rel} (advisory only)\n")
    } else {
        String::new()
    };
    (0, String::new(), err)
}

struct Ledger {
    data: Value,
}
impl Drop for Ledger {
    fn drop(&mut self) {
        python_json::discard(std::mem::replace(&mut self.data, Value::Null));
    }
}
