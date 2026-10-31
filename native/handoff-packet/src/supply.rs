//! Native UserPromptSubmit and read-only repository pin runner.
use crate::supply_text as t;
use crate::{
    Error, LIMIT, Owner, Result, detect, files_restricted, owner_sections, recipient, restricted,
};
use serde_json::Value;
use std::{
    io::Read,
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::mpsc,
    thread,
    time::{Duration, Instant},
};
pub const UNAVAILABLE: &str = "hook unavailable; allowing turn to continue. Check native payload, explicit transcript tail and repository runner; pins/check unavailable.";
pub struct Output {
    pub context: Option<String>,
    pub warning: Option<&'static str>,
}
fn items(s: &str) -> impl Iterator<Item = &str> {
    s.split([';', '\n'])
        .map(|s| s.trim().trim_start_matches(['-', '*', ' ']).trim())
        .filter(|s| !s.is_empty())
}
pub fn tool_attempt_rule(owner: &Owner) -> Result<String> {
    let mut out = String::new();
    for (rule, active) in [
        (
            t::SHELL_TOOL_RULE,
            restricted(&format!("May not: {}", owner.may_not))?,
        ),
        (t::FILE_TOOL_RULE, files_restricted(owner)?),
    ] {
        if active {
            out.push_str(rule);
            out.push_str(t::ATTEMPT_RULE);
            out.push('\n');
        }
    }
    Ok(out)
}
fn context_text(owner: &Owner, pins: Option<&str>, prompt: Option<&str>) -> Result<String> {
    let mut names: Vec<String> = [
        "repository_root",
        "head",
        "mapping.identity",
        "mapping.version",
        "mapping.digest",
        "contract.identity",
        "contract.version",
        "contract.digest",
    ]
    .map(str::to_owned)
    .to_vec();
    for (i, _) in items(&owner.sources).enumerate() {
        names.extend([
            format!("sources[{i}].digest"),
            format!("sources[{i}].revision"),
        ]);
    }
    let unavailable = format!("unavailable pins: {}", names.join("; "));
    let mut pins = pins.unwrap_or(&unavailable).to_owned();
    if let Some(prompt) = prompt {
        pins.push_str(&format!(
            "\nPrompt SHA256: {}",
            crate::digest::sha256(prompt.as_bytes())
        ));
    }
    let excluded = owner.excluded.join("; ");
    // Split fixed markers so inserted owner strings cannot substitute each other.
    let values = [
        pins.as_str(),
        if owner.may.is_empty() {
            if owner.explicit_authority {
                "unavailable"
            } else {
                "read/inspect only"
            }
        } else {
            &owner.may
        },
        if owner.may_not.is_empty() {
            "unavailable; do not infer authority"
        } else {
            &owner.may_not
        },
        &excluded,
    ];
    let mut text = t::CONTEXT;
    let mut out = String::new();
    for (marker, value) in ["@@PINS@@", "@@MAY@@", "@@MAY_NOT@@", "@@EXCLUDED@@"]
        .into_iter()
        .zip(values)
    {
        let (before, after) = text.split_once(marker).ok_or(Error::Shape)?;
        out.push_str(before);
        out.push_str(value);
        text = after;
    }
    out.push_str(text);
    out.push_str(&tool_attempt_rule(owner)?);
    Ok(out)
}
pub fn exception(event: &Value) -> Result<Output> {
    let context = match event.get("prompt").and_then(Value::as_str) {
        Some(prompt) if detect(prompt)? => {
            Some(context_text(&owner_sections(prompt)?, None, None)?)
        }
        _ => None,
    };
    Ok(Output {
        context,
        warning: Some(UNAVAILABLE),
    })
}
pub fn supply(event: &Value) -> Result<Output> {
    let prompt = match event.get("prompt") {
        None => "",
        Some(v) => v.as_str().ok_or(Error::Shape)?,
    };
    if recipient(prompt)? {
        return Ok(Output {
            context: Some(format!(
                "{}\n{}",
                t::RECEIPT_RULE,
                tool_attempt_rule(&owner_sections(prompt)?)?
            )),
            warning: None,
        });
    }
    if !detect(prompt)? {
        return Ok(Output {
            context: None,
            warning: None,
        });
    }
    let owner = owner_sections(prompt)?;
    if restricted(prompt)? {
        return Ok(Output {
            context: Some(context_text(&owner, None, None)?),
            warning: Some(
                "pins/check unavailable: owner forbids commands; no runner performed. Inventory unavailable pins.",
            ),
        });
    }
    let pins = run_pins(event, &owner, None, Duration::from_secs(5))?;
    Ok(Output {
        context: Some(context_text(&owner, Some(&pins), Some(prompt))?),
        warning: None,
    })
}
pub(crate) fn repository_root(event: &Value) -> Result<PathBuf> {
    let cwd = Path::new(event["cwd"].as_str().ok_or(Error::Shape)?);
    if !cwd.is_absolute() || !cwd.is_dir() {
        return Err(Error::Shape);
    }
    let cwd = cwd.canonicalize()?;
    cwd.ancestors()
        .find(|p| p.join(".git").exists())
        .map(Path::to_owned)
        .ok_or(Error::Shape)
}
// Resolve missing final components like Python Path.resolve(strict=False).
pub(crate) fn resolve(path: &Path) -> Result<PathBuf> {
    let mut out = PathBuf::new();
    for part in path.components() {
        match part {
            std::path::Component::ParentDir => {
                out.pop();
            }
            std::path::Component::CurDir => {}
            other => out.push(other),
        }
        if out
            .symlink_metadata()
            .is_ok_and(|m| m.file_type().is_symlink())
        {
            out = out.canonicalize()?;
        }
    }
    Ok(out)
}
pub(crate) fn source_paths(owner: &Owner, root: &Path) -> Result<Vec<String>> {
    let mut paths = Vec::new();
    for raw in owner.sources.split([';', ',', '\n']) {
        let raw = raw
            .trim()
            .trim_start_matches(['-', '*', ' '])
            .trim()
            .trim_matches('`');
        if raw.is_empty() {
            continue;
        }
        let path = resolve(&root.join(raw))?;
        let relative = path.strip_prefix(root).map_err(|_| Error::Shape)?;
        let value = relative.to_str().ok_or(Error::Shape)?.replace('\\', "/");
        if relative.components().any(|p| {
            p.as_os_str()
                .to_str()
                .is_some_and(|s| s.starts_with(".env") || s == "secrets")
        }) || value.starts_with(".mir/memory.db")
            || owner.excluded.iter().any(|s| raw.contains(s))
        {
            return Err(Error::Shape);
        }
        paths.push(if value.is_empty() { ".".into() } else { value });
    }
    if paths.len() > 16 {
        return Err(Error::Shape);
    }
    Ok(paths)
}
fn bounded_wait(child: &mut Child, timeout: Duration) -> std::io::Result<bool> {
    let start = Instant::now();
    loop {
        if child.try_wait()?.is_some() {
            return Ok(true);
        }
        if start.elapsed() >= timeout {
            return Ok(false);
        }
        thread::sleep(Duration::from_millis(2));
    }
}
fn stop_runner(child: &mut Child) {
    #[cfg(unix)]
    {
        let _ = Command::new("/bin/kill")
            .args(["-KILL", &format!("-{}", child.id())])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
    }
    #[cfg(windows)]
    if let Some(root) = std::env::var_os("SystemRoot") {
        let root = Path::new(&root);
        if root.is_absolute()
            && let Ok(mut killer) = Command::new(root.join("System32/taskkill.exe"))
                .args(["/T", "/F", "/PID", &child.id().to_string()])
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .spawn()
        {
            if !bounded_wait(&mut killer, Duration::from_secs(1)).unwrap_or(false) {
                let _ = killer.kill();
            }
            let _ = killer.wait();
        }
    }
    let _ = child.kill();
    let _ = bounded_wait(child, Duration::from_secs(1));
}
pub(crate) fn run_pins(
    event: &Value,
    owner: &Owner,
    paths: Option<&[String]>,
    timeout: Duration,
) -> Result<String> {
    let root = repository_root(event)?;
    let runner = root.join("scripts/mir_ontology.py");
    if runner.symlink_metadata()?.file_type().is_symlink() || !runner.is_file() {
        return Err(Error::Shape);
    }
    let mut cmd =
        Command::new(std::env::var_os("MIR_HANDOFF_PYTHON").unwrap_or_else(|| "python3".into()));
    cmd.arg(runner)
        .args(["mapping", "--handoff"])
        .args(match paths {
            Some(paths) => paths.to_vec(),
            None => source_paths(owner, &root)?,
        })
        .current_dir(root)
        .env("PYTHONDONTWRITEBYTECODE", "1")
        .env("GIT_OPTIONAL_LOCKS", "0")
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    #[cfg(unix)]
    {
        use std::os::unix::process::CommandExt;
        cmd.process_group(0);
    }
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x00000200);
    }
    let mut child = cmd.spawn()?;
    let (tx, rx) = mpsc::channel();
    for (index, stream) in [
        child
            .stdout
            .take()
            .map(|s| Box::new(s) as Box<dyn Read + Send>),
        child
            .stderr
            .take()
            .map(|s| Box::new(s) as Box<dyn Read + Send>),
    ]
    .into_iter()
    .enumerate()
    {
        let tx = tx.clone();
        let mut stream = stream.ok_or(Error::Shape)?;
        thread::spawn(move || {
            let mut bytes = Vec::new();
            let result = stream.read_to_end(&mut bytes);
            let _ = tx.send((index, result.map(|_| bytes)));
        });
    }
    let start = Instant::now();
    let mut stdout = Vec::new();
    for _ in 0..2 {
        let received = rx.recv_timeout(timeout.saturating_sub(start.elapsed()));
        let Ok((index, data)) = received else {
            stop_runner(&mut child);
            return Err(Error::Shape);
        };
        let data = data?;
        if index == 0 {
            stdout = data;
        }
    }
    if !bounded_wait(&mut child, timeout.saturating_sub(start.elapsed()))? {
        stop_runner(&mut child);
        return Err(Error::Shape);
    }
    if !child.wait()?.success() {
        return Err(Error::Shape);
    }
    // Python pipe decoding explicitly replaces invalid UTF-8 and universal newlines.
    let stdout = String::from_utf8_lossy(&stdout)
        .replace("\r\n", "\n")
        .replace('\r', "\n");
    let (_, body) = stdout.split_once("handoff pins:\n").ok_or(Error::Shape)?;
    if stdout.chars().count() > LIMIT {
        return Err(Error::Shape);
    }
    let pins = format!("handoff pins:\n{}", body.trim_end_matches('\n'));
    if !serde_json::from_str::<Value>(body)?.is_object()
        || owner.excluded.iter().any(|s| pins.contains(s))
    {
        return Err(Error::Shape);
    }
    Ok(pins)
}
