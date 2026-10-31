#![forbid(unsafe_code)]
#![deny(clippy::unwrap_used, clippy::expect_used, clippy::panic)]
use handoff_packet::{LIMIT, pretool};
use std::io::{self, Read, Write};
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
    if let Some(event) = parsed.as_ref()
        && event.get("hook_event_name").and_then(|v| v.as_str()) == Some("UserPromptSubmit")
    {
        let output = handoff_packet::supply::supply(event)
            .or_else(|_| handoff_packet::supply::exception(event));
        if let Ok(output) = output {
            let mut fields = Vec::new();
            if let Some(message) = output.warning {
                let message = format!("Mir handoff WARNING: {message}");
                write!(io::stderr(), "{message}{EOL}")?;
                fields.push(format!("\"systemMessage\": {}", ascii_json(&message)?));
            }
            if let Some(context) = output.context {
                fields.push(format!("\"hookSpecificOutput\": {{\"hookEventName\": \"UserPromptSubmit\", \"additionalContext\": {}}}", ascii_json(&context)?));
            }
            if !fields.is_empty() {
                write!(io::stdout(), "{{{}}}{EOL}", fields.join(", "))?;
            }
        }
        return Ok(0);
    }
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
    if let Some(event) = parsed.as_ref() {
        if !event.is_object() {
            return warning();
        }
        if event.get("hook_event_name").and_then(|v| v.as_str()) == Some("Stop") {
            match handoff_packet::stop::stop(event) {
                Ok(output) => {
                    if let Some(message) = output.warning {
                        let message = message.replace('\n', EOL);
                        write!(io::stderr(), "Mir handoff WARNING: {message}{EOL}")?;
                    }
                    if let Some(output) = output.output {
                        write!(io::stdout(), "{output}{EOL}")?;
                    }
                    return Ok(0);
                }
                Err(_) => return warning(),
            }
        }
        return Ok(0);
    }
    warning()
}
fn ascii_json(text: &str) -> io::Result<String> {
    let quoted = serde_json::to_string(text).map_err(io::Error::other)?;
    let mut out = String::new();
    for ch in quoted.chars() {
        if ch.is_ascii() && ch != '\u{7f}' {
            out.push(ch);
        } else {
            for unit in ch.encode_utf16(&mut [0; 2]) {
                out.push_str(&format!("\\u{unit:04x}"));
            }
        }
    }
    Ok(out)
}
fn main() {
    std::process::exit(run().unwrap_or(0));
}
