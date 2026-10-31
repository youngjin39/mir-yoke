#![forbid(unsafe_code)]
#![deny(clippy::unwrap_used, clippy::expect_used, clippy::panic)]
use handoff_packet::{LIMIT, pretool};
use std::{
    io::{self, Read, Write},
    process::{Command, Stdio},
};
const WARNING: &str = "Mir handoff WARNING: hook unavailable; allowing turn to continue. Check native payload, explicit transcript tail and repository runner; pins/check unavailable.";
// Python text streams translate LF on Windows; compare raw pipe bytes unchanged.
const EOL: &str = if cfg!(windows) { "\r\n" } else { "\n" };
fn warning() -> io::Result<i32> {
    write!(io::stderr(), "{WARNING}{EOL}")?;
    write!(io::stdout(), "{{\"systemMessage\": \"{WARNING}\"}}{EOL}")?;
    Ok(0)
}
fn run() -> io::Result<i32> {
    let mut raw = Vec::new();
    io::stdin()
        .lock()
        .take((LIMIT + 1) as u64 * 4)
        .read_to_end(&mut raw)?;
    // Match sys.stdin.read(LIMIT + 1): oversize prevents event determination.
    let within_limit = std::str::from_utf8(&raw).is_ok_and(|s| s.chars().count() <= LIMIT);
    let parsed = if within_limit {
        serde_json::from_slice::<serde_json::Value>(&raw).ok()
    } else {
        None
    };
    let is_pretool = parsed
        .as_ref()
        .and_then(|e| e.get("hook_event_name"))
        .and_then(|v| v.as_str())
        == Some("PreToolUse");
    if is_pretool {
        if let Some(event) = parsed
            && let Ok(Some(reason)) = pretool(&event)
        {
            write!(
                io::stdout(),
                "{{\"hookSpecificOutput\": {{\"hookEventName\": \"PreToolUse\", \"permissionDecision\": \"deny\", \"permissionDecisionReason\": \"{reason}\"}}}}{EOL}"
            )?;
            write!(io::stderr(), "{reason}{EOL}")?;
            return Ok(2);
        }
        return Ok(0);
    }
    let Some(reference) = std::env::args_os().nth(1) else {
        return warning();
    };
    io::stdin().lock().read_to_end(&mut raw)?;
    // Match hooks.json by default; explicit callers may select their Python.
    let python = std::env::var_os("MIR_HANDOFF_PYTHON").unwrap_or_else(|| "python3".into());
    let child = Command::new(python)
        .arg(reference)
        .stdin(Stdio::piped())
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit())
        .spawn();
    let Ok(mut child) = child else {
        return warning();
    };
    if let Some(mut stdin) = child.stdin.take()
        && let Err(e) = stdin.write_all(&raw)
        && e.kind() != io::ErrorKind::BrokenPipe
    {
        return Err(e);
    }
    let status = child.wait()?;
    #[cfg(unix)]
    {
        use std::os::unix::process::ExitStatusExt;
        if let Some(signal) = status.signal() {
            return Ok(128 + signal);
        }
    }
    Ok(status.code().unwrap_or(0))
}
fn main() {
    std::process::exit(run().unwrap_or(0));
}
