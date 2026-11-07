//! Explicit project-hook supply using injected provider bytes, installer and probe.
#![forbid(unsafe_code)]
use super::memory::Output;
use crate::mir_core::capabilities::native as native_artifacts;
use serde_json::{Value, json};
use std::{
    fs, io,
    path::{Path, PathBuf},
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
    native_artifacts::validate_artifacts(
        &metadata["native_artifacts"],
        &metadata["plugins"],
        false,
    )?;
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

pub fn write_receipt(path: &Path, pin: &Value) -> Result<(), String> {
    write_receipt_with(path, pin, |source, dest| fs::rename(source, dest))
}

pub fn write_receipt_with(
    path: &Path,
    pin: &Value,
    replace: impl FnOnce(&Path, &Path) -> io::Result<()>,
) -> Result<(), String> {
    let data = format!(
        "{}\n",
        serde_json::to_string_pretty(pin).map_err(|error| error.to_string())?
    );
    if fs::read(path).is_ok_and(|bytes| bytes == data.as_bytes()) {
        return Ok(());
    }
    let parent = path.parent().ok_or("missing receipt parent")?;
    let mut temporary = tempfile::Builder::new()
        .prefix(".project-hooks-")
        .tempfile_in(parent)
        .map_err(|error| error.to_string())?;
    use std::io::Write;
    temporary
        .write_all(data.as_bytes())
        .map_err(|error| error.to_string())?;
    temporary.flush().map_err(|error| error.to_string())?;
    replace(temporary.path(), path).map_err(|error| error.to_string())
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
        .split(|byte| *byte == b'\n')
        .map(|line| line.strip_suffix(b"\r").unwrap_or(line))
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
        if error.kind() == io::ErrorKind::NotFound {
            format!(
                "[Errno 2] No such file or directory: '{}'",
                receipt.display()
            )
        } else {
            error.to_string()
        }
    })?;
    let receipt_value: Value = serde_json::from_slice(&bytes).map_err(|error| error.to_string())?;
    if receipt_value != json!({"path":relative,"sha256":pin["sha256"]}) {
        return Err("project-hooks receipt mismatch".into());
    }
    native_artifacts::verify(&binary, pin)?;
    if !native_artifacts::is_executable(&binary) {
        return Err("project-hooks is not executable".into());
    }
    probe(&binary, root, run)
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
