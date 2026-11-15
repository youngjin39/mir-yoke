//! Explicit project-hook supply using injected provider bytes, installer and probe.
#![forbid(unsafe_code)]
use super::memory::Output;
use crate::mir_core::capabilities::native as native_artifacts;
use serde_json::Value;
#[cfg(not(unix))]
use std::io::{Seek, SeekFrom};
use std::{
    fs, io,
    io::{Read, Write},
    path::{Path, PathBuf},
    process::{Command, Stdio},
    thread,
    time::{Duration, Instant},
};

const USAGE: &str = "usage: mir project-hooks [-h] --project-root PROJECT_ROOT {install,check}\n";
const READY: &str = "project-hooks: ready (verified binary, receipt and capability probe)\n";

pub struct ProbeOutput {
    pub returncode: i32,
    pub stdout: Vec<u8>,
}

pub struct ProbeRequest<'a> {
    pub argv: [String; 2],
    pub stdin: i32,
    pub capture_output: bool,
    pub timeout: u64,
    pub check: bool,
    pub cwd: &'a Path,
}

pub fn provider_pin(
    metadata: &Value,
    target: Option<&str>,
    disabled: bool,
) -> Result<(String, Value), String> {
    let schema = metadata
        .get("schema_version")
        .and_then(Value::as_i64)
        .ok_or("invalid provider metadata")?;
    if schema != 1 {
        return Err("unsupported provider metadata schema".into());
    }
    let artifacts = metadata
        .get("native_artifacts")
        .ok_or("'native_artifacts'")?;
    let plugins = metadata.get("plugins").ok_or("'plugins'")?;
    native_artifacts::validate_artifacts(artifacts, plugins, false)?;
    let target = target.ok_or("unsupported host")?;
    if disabled {
        return Err("native artifacts disabled".into());
    }
    let record = &metadata["native_artifacts"]["project-hooks"];
    let pin = record
        .get("targets")
        .and_then(|targets| targets.get(target))
        .ok_or("no published host pin in provider package")?;
    let revision = metadata["provider_revision"].as_str().unwrap_or("");
    if record["plugin"] != "mir-lifecycle-hooks"
        || record["install_path"] != "bin/project-hooks"
        || revision.len() != 40
        || !revision
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    {
        return Err("invalid project-hooks provider identity".into());
    }
    Ok((target.to_owned(), pin.clone()))
}

/// Decline sizes whose read(size + 1) overflows the reference's index-sized bound.
pub fn unsupported_read_size(pin: &Value) -> bool {
    let Some(size) = pin.get("size") else {
        return false;
    };
    // The shared reader preserves unbounded integers as numeric-tag objects.
    // Object sizes are outside this private reader's admitted numeric subset.
    if size.is_object() {
        return true;
    }
    if let Some(size) = size.as_u64() {
        return size >= isize::MAX as u64;
    }
    size.as_f64().is_some_and(|size| size >= isize::MAX as f64)
}

pub fn unsupported_provider_read_size(root: &Path, name: &str, target: Option<&str>) -> bool {
    let Some(target) = target else {
        return false;
    };
    let lock = root.join(".mir/capability-lock.json");
    if lock.is_symlink() || lock.parent().is_some_and(Path::is_symlink) {
        return false;
    }
    match super::bootstrap_adoption::load_json_bytes(
        &lock,
        &mut super::bootstrap_adoption::LocalHost,
    ) {
        Ok((lock, _)) => unsupported_read_size(&lock["native_artifacts"][name]["targets"][target]),
        Err(error) => error.to_string().contains("number out of range"),
    }
}

pub fn project_path(root: &Path, relative: &str) -> Result<PathBuf, String> {
    let mut current = root.to_path_buf();
    for part in Path::new(relative).components() {
        current.push(part);
        if fs::symlink_metadata(&current).is_ok_and(|meta| meta.file_type().is_symlink()) {
            return Err("linked project-hook path".into());
        }
    }
    Ok(current)
}

/// Publish and clean up through pinned parents even if the layout changes.
pub fn write_receipt(path: &Path, pin: &Value) -> Result<(), String> {
    write_receipt_with(path, pin, |_, _| Ok(()))
}

/// The callback is a pre-placement boundary for deterministic layout/failure tests.
/// It must not perform the replacement; the descriptor-relative move owns it.
pub fn write_receipt_with(
    path: &Path,
    pin: &Value,
    before_replace: impl FnOnce(&Path, &Path) -> io::Result<()>,
) -> Result<(), String> {
    let data = format!(
        "{}\n",
        serde_json::to_string_pretty(pin).map_err(|error| error.to_string())?
    );
    if path.is_file() && fs::read(path).is_ok_and(|bytes| bytes == data.as_bytes()) {
        return Ok(());
    }
    publish_receipt(path, data.as_bytes(), before_replace)
}

fn publish_receipt(
    path: &Path,
    data: &[u8],
    before_replace: impl FnOnce(&Path, &Path) -> io::Result<()>,
) -> Result<(), String> {
    let directory = path.parent().ok_or("missing receipt parent")?;
    let absolute = if directory.is_absolute() {
        directory.to_path_buf()
    } else {
        std::env::current_dir()
            .map_err(|e| e.to_string())?
            .join(directory)
    };
    // Normalize spelling without resolving links. Opening every component with
    // NOFOLLOW below still rejects a layout substitution before placement.
    let mut normalized = PathBuf::new();
    for component in absolute.components() {
        match component {
            std::path::Component::ParentDir => {
                normalized.pop();
            }
            std::path::Component::CurDir => {}
            component => normalized.push(component.as_os_str()),
        }
    }
    let destination = normalized.join(path.file_name().ok_or("missing receipt name")?);
    let directory = normalized.as_path();
    let path = destination.as_path();
    let temporary = tempfile::Builder::new()
        .prefix(".project-hooks-")
        .make_in(directory, |candidate| {
            crate::adoption_fs::StagedFile::create(directory, candidate)
        })
        .map_err(|error| error.to_string())?;
    let (mut staged, mut inert_path) = temporary.into_parts();
    inert_path.disable_cleanup(true);
    staged.file.write_all(data).map_err(|e| e.to_string())?;
    before_replace(&staged.path, path).map_err(|e| e.to_string())?;
    if staged.contents(data.len()).map_err(|e| e.to_string())? != data {
        return Err("receipt changed during publication".into());
    }
    staged
        .publish(directory, path)
        .map(|_| ())
        .map_err(|e| e.to_string())
}

#[cfg(any(unix, test))]
fn probe_timeout_message(argv: &[String; 2], timeout: u64, remaining: Option<f64>) -> String {
    // communicate() hands wait() a float remaining timeout after both pipes
    // reach EOF. TimeoutExpired then reports that value, not the initial integer.
    let timeout = remaining.map_or_else(
        || timeout.to_string(),
        |remaining| {
            crate::mir_core::canonical::python_float(remaining)
                .unwrap_or_else(|_| remaining.to_string())
        },
    );
    format!(
        "Command '{}' timed out after {} seconds",
        crate::executor_execute::list_repr(argv),
        timeout
    )
}

/// Drain both real pipes until EOF, including writers inherited by descendants.
#[cfg(unix)]
pub fn run_probe(request: ProbeRequest<'_>) -> Result<ProbeOutput, String> {
    use std::os::unix::process::ExitStatusExt;
    let mut child = Command::new(&request.argv[0])
        .arg(&request.argv[1])
        .current_dir(request.cwd)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| {
            super::bootstrap_adoption::io_error(Path::new(&request.argv[0]), e).to_string()
        })?;
    let started = Instant::now();
    let result = (|| -> Result<ProbeOutput, String> {
        let deadline = crate::adoption_fs::monotonic_seconds().map_err(|e| e.to_string())?
            + request.timeout as f64;
        let mut stdout = child.stdout.take().ok_or("missing probe stdout pipe")?;
        let mut stderr = child.stderr.take().ok_or("missing probe stderr pipe")?;
        crate::adoption_fs::nonblocking(&stdout).map_err(|e| e.to_string())?;
        crate::adoption_fs::nonblocking(&stderr).map_err(|e| e.to_string())?;
        let mut bytes = Vec::new();
        let mut errors = Vec::new();
        let mut open = [true, true];
        let mut status = None;
        let mut wait_timeout = None;
        loop {
            let mut progress = false;
            for (index, stream, output) in [
                (0, &mut stdout as &mut dyn Read, &mut bytes),
                (1, &mut stderr as &mut dyn Read, &mut errors),
            ] {
                if !open[index] {
                    continue;
                }
                let mut buffer = [0; 65536];
                match stream.read(&mut buffer) {
                    Ok(0) => open[index] = false,
                    Ok(count) => {
                        output.extend_from_slice(&buffer[..count]);
                        progress = true;
                    }
                    Err(error)
                        if matches!(
                            error.kind(),
                            io::ErrorKind::WouldBlock | io::ErrorKind::Interrupted
                        ) => {}
                    Err(error) => return Err(error.to_string()),
                }
            }
            if status.is_none() {
                status = child.try_wait().map_err(|e| e.to_string())?;
            }
            if !open.iter().any(|open| *open)
                && let Some(status) = status
            {
                return Ok(ProbeOutput {
                    returncode: status
                        .code()
                        .unwrap_or_else(|| -status.signal().unwrap_or(1)),
                    stdout: bytes,
                });
            }
            if started.elapsed() >= Duration::from_secs(request.timeout) {
                return Err(probe_timeout_message(
                    &request.argv,
                    request.timeout,
                    wait_timeout,
                ));
            }
            if !open.iter().any(|open| *open) && wait_timeout.is_none() {
                wait_timeout = Some(
                    deadline
                        - crate::adoption_fs::monotonic_seconds().map_err(|e| e.to_string())?,
                );
            }
            if !progress {
                thread::sleep(Duration::from_millis(2));
            }
        }
    })();
    if result.is_err() {
        let _ = child.kill();
        let _ = child.wait();
    }
    result
}

/// Preserve the existing non-Unix host; no Windows execution claim is made.
#[cfg(not(unix))]
pub fn run_probe(request: ProbeRequest<'_>) -> Result<ProbeOutput, String> {
    let mut stdout = tempfile::tempfile().map_err(|e| e.to_string())?;
    let stderr = tempfile::tempfile().map_err(|e| e.to_string())?;
    let mut child = Command::new(&request.argv[0])
        .arg(&request.argv[1])
        .current_dir(request.cwd)
        .stdin(Stdio::null())
        .stdout(stdout.try_clone().map_err(|e| e.to_string())?)
        .stderr(stderr)
        .spawn()
        .map_err(|e| {
            super::bootstrap_adoption::io_error(Path::new(&request.argv[0]), e).to_string()
        })?;
    let started = Instant::now();
    let status = loop {
        match child.try_wait() {
            Ok(Some(status)) => break status,
            Ok(None) if started.elapsed() < Duration::from_secs(request.timeout) => {
                thread::sleep(Duration::from_millis(2));
            }
            Ok(None) => {
                let _ = child.kill();
                let _ = child.wait();
                return Err(format!(
                    "Command '{}' timed out after {} seconds",
                    crate::executor_execute::list_repr(&request.argv),
                    request.timeout
                ));
            }
            Err(error) => {
                let _ = child.kill();
                let _ = child.wait();
                return Err(error.to_string());
            }
        }
    };
    let mut bytes = Vec::new();
    stdout
        .seek(SeekFrom::Start(0))
        .and_then(|_| stdout.read_to_end(&mut bytes))
        .map_err(|e| e.to_string())?;
    #[cfg(unix)]
    let code = {
        use std::os::unix::process::ExitStatusExt;
        status
            .code()
            .unwrap_or_else(|| -status.signal().unwrap_or(1))
    };
    #[cfg(not(unix))]
    let code = status.code().unwrap_or(1);
    Ok(ProbeOutput {
        returncode: code,
        stdout: bytes,
    })
}

fn probe(
    binary: &Path,
    root: &Path,
    run: &mut impl FnMut(ProbeRequest<'_>) -> Result<ProbeOutput, String>,
) -> Result<(), String> {
    let output = run(ProbeRequest {
        argv: [binary.to_string_lossy().into_owned(), "capabilities".into()],
        stdin: -3,
        capture_output: true,
        timeout: 2,
        check: false,
        cwd: root,
    })?;
    let lines: Vec<_> = output
        .stdout
        .split(|byte| matches!(*byte, b'\n' | b'\r'))
        .collect();
    if output.returncode != 0
        || ![
            b"mir-project-hooks-v1".as_slice(),
            b"mir-project-hooks-compact-v1".as_slice(),
        ]
        .iter()
        .all(|token| lines.contains(token))
    {
        return Err("project-hooks capability probe failed".into());
    }
    Ok(())
}

fn check(
    root: &Path,
    relative: &str,
    pin: &Value,
    run: &mut impl FnMut(ProbeRequest<'_>) -> Result<ProbeOutput, String>,
) -> Result<(), String> {
    let binary = project_path(root, relative)?;
    let receipt = project_path(root, ".mir/bin/project-hooks.json")?;
    let bytes = fs::read(&receipt).map_err(|error| {
        let message = super::bootstrap_adoption::io_error(&receipt, error).to_string();
        // a61c3013 project_hooks.py:61: read_text uses str(Path), not as_posix.
        // Preserve the shared errno mapping; replace only its filename repr.
        let filename = receipt.to_string_lossy();
        let filename = filename.strip_prefix(r"\\?\").unwrap_or(&filename);
        message.replace(
            &crate::executor_execute::repr(&super::bootstrap_adoption::wire(&receipt)),
            &crate::executor_execute::repr(filename),
        )
    })?;
    let points = super::bootstrap_adoption::json_bytes_codepoints(&bytes)
        .map_err(|error| error.to_string())?;
    let receipt_value =
        crate::python_json::parse_codepoints(points).map_err(|error| error.to_string())?;
    // Compare actual Python strings, including lone surrogates, without a lossy
    // serde conversion. Receipt fields contain only the exact ASCII path/hash.
    let matches = receipt_value
        .as_object()
        .is_some_and(|object| object.len() == 2)
        && receipt_value
            .get("path")
            .and_then(crate::python_json::Value::as_str)
            == Some(relative)
        && receipt_value
            .get("sha256")
            .and_then(crate::python_json::Value::as_str)
            == pin["sha256"].as_str();
    drop_receipt(receipt_value);
    if !matches {
        return Err("project-hooks receipt mismatch".into());
    }
    native_artifacts::verify(&binary, pin)?;
    if !native_artifacts::is_executable(&binary) {
        return Err("project-hooks is not executable".into());
    }
    probe(&binary, root, run)
}

fn drop_receipt(value: crate::python_json::Value) {
    // The shared parser accepts deeply nested Python JSON; avoid recursive drop
    // when such a valid value is unequal to the small expected receipt.
    let mut pending = vec![value];
    while let Some(value) = pending.pop() {
        match value {
            crate::python_json::Value::Array(items) => pending.extend(items),
            crate::python_json::Value::Object(items) => {
                pending.extend(items.into_entries().into_iter().map(|(_, value)| value));
            }
            _ => {}
        }
    }
}

pub fn main(
    argv: &[&str],
    metadata: &Value,
    target: Option<&str>,
    disabled: bool,
    install: impl FnOnce(&Path, &Value) -> Option<Value>,
    mut run: impl FnMut(ProbeRequest<'_>) -> Result<ProbeOutput, String>,
) -> Output {
    if argv.iter().any(|arg| matches!(*arg, "--help" | "-h")) {
        let help = concat!(
            "\npositional arguments:\n  {install,check}\n\noptions:\n",
            "  -h, --help            show this help message and exit\n",
            "  --project-root PROJECT_ROOT\n",
        );
        return (0, format!("{USAGE}{help}").into_bytes(), vec![]);
    }
    let mut operation = None;
    let mut root = None;
    let mut index = 0;
    let mut error = None;
    while index < argv.len() {
        let arg = argv[index];
        if arg == "--project-root" {
            index += 1;
            if let Some(value) = argv.get(index) {
                root = Some(PathBuf::from(value));
            } else {
                error = Some("argument --project-root: expected one argument".to_owned());
                break;
            }
        } else if operation.is_none() && !arg.starts_with('-') {
            if !matches!(arg, "install" | "check") {
                error = Some(format!(
                    "argument operation: invalid choice: '{arg}' (choose from install, check)"
                ));
                break;
            }
            operation = Some(arg);
        } else {
            error = Some(format!(
                "unrecognized arguments: {}",
                argv[index..].join(" ")
            ));
            break;
        }
        index += 1;
    }
    if error.is_none() {
        let missing: Vec<_> = [
            (operation.is_none(), "operation"),
            (root.is_none(), "--project-root"),
        ]
        .into_iter()
        .filter_map(|(absent, name)| absent.then_some(name))
        .collect();
        if !missing.is_empty() {
            error = Some(format!(
                "the following arguments are required: {}",
                missing.join(", ")
            ));
        }
    }
    if let Some(error) = error {
        return (
            2,
            vec![],
            format!("{USAGE}mir project-hooks: error: {error}\n").into_bytes(),
        );
    }
    let result = (|| -> Result<(), String> {
        let root = root.ok_or("project root is required")?;
        let root = if root.is_absolute() {
            root
        } else {
            std::env::current_dir()
                .map_err(|error| error.to_string())?
                .join(root)
        };
        if !root.is_dir()
            || root.ancestors().any(|path| {
                fs::symlink_metadata(path).is_ok_and(|meta| meta.file_type().is_symlink())
            })
        {
            return Err("project root must be an existing directory".into());
        }
        let (target, pin) = provider_pin(metadata, target, disabled)?;
        let relative = if target.ends_with("windows-msvc") {
            ".mir/bin/project-hooks.exe"
        } else {
            ".mir/bin/project-hooks"
        };
        let receipt = project_path(&root, ".mir/bin/project-hooks.json")?;
        if receipt.exists() && !receipt.is_file() {
            return Err("invalid project-hooks receipt path".into());
        }
        if operation == Some("install") {
            let installed =
                install(&root, &pin).ok_or("verified project-hooks placement unavailable")?;
            probe(&project_path(&root, relative)?, &root, &mut run)?;
            write_receipt(&receipt, &installed)?;
        }
        check(&root, relative, &pin, &mut run)
    })();
    match result {
        Ok(()) => (0, READY.as_bytes().to_vec(), vec![]),
        Err(error) => (
            1,
            format!("project-hooks: degraded: {error}\n").into_bytes(),
            vec![],
        ),
    }
}

#[cfg(test)]
mod timeout_tests {
    use super::*;
    #[test]
    fn early_eof_timeout_text_matches_python_frozen_clock() {
        let argv = [
            "<base>/project/.mir/bin/project-hooks".into(),
            "capabilities".into(),
        ];
        assert_eq!(
            probe_timeout_message(&argv, 2, Some(1160082.098542583 - 1160080.152409416)),
            "Command '['<base>/project/.mir/bin/project-hooks', 'capabilities']' timed out after 1.9461331670172513 seconds"
        );
    }
}
