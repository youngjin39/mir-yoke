//! Portable marked-snapshot validation and bounded canonical recovery.
//! The shell hooks remain the live callers; these primitives perform no writes.
use std::{fs, io, path::Path};

pub const BEGIN: &str = "<!-- mir:runtime-snapshot:begin -->";
pub const END: &str = "<!-- mir:runtime-snapshot:end -->";
pub const HEADER: &str = "=== MIR COMPACTION RECOVERY CONTEXT ===\ncanonical_source: tasks/handoffs/session-handoff-LATEST.md\n\n";
pub const FOOTER: &str = "\n=== END MIR COMPACTION RECOVERY CONTEXT ===\n";
pub const TRUNCATION: &str = "\n[mir] recovery context truncated at 8192 bytes\n";
pub const MAX_CONTEXT_BYTES: usize = 8192;

/// Match Python's UTF-8 text reader, including universal newline translation.
pub fn read_handoff(path: &Path) -> Result<String, String> {
    let bytes = fs::read(path).map_err(|error| {
        if error.kind() == io::ErrorKind::NotFound {
            "canonical handoff is missing".to_owned()
        } else {
            let class = match error.kind() {
                io::ErrorKind::PermissionDenied => "PermissionError",
                io::ErrorKind::IsADirectory => "IsADirectoryError",
                io::ErrorKind::NotADirectory => "NotADirectoryError",
                _ => "OSError",
            };
            format!("canonical handoff is unreadable: {class}")
        }
    })?;
    String::from_utf8(bytes)
        .map(|body| body.replace("\r\n", "\n").replace('\r', "\n"))
        .map_err(|_| "canonical handoff is unreadable: UnicodeDecodeError".into())
}

/// Return only the marked body, rejecting duplicate, missing or reversed markers.
/// No additional header schema is imposed: PostCompact validates markers only.
pub fn parse(body: &str) -> Result<&str, String> {
    let begin_count = body.matches(BEGIN).count();
    let end_count = body.matches(END).count();
    if begin_count != 1 || end_count != 1 {
        return Err(format!(
            "runtime snapshot markers must appear exactly once (begin={begin_count}, end={end_count})"
        ));
    }
    if let (Some(begin), Some(end)) = (body.find(BEGIN), body.find(END)) {
        if begin > end {
            return Err("runtime snapshot begin marker must precede the end marker".into());
        }
        return Ok(&body[begin + BEGIN.len()..end]);
    }
    Err("runtime snapshot markers are missing".into())
}

pub fn recovery(body: &str) -> String {
    // Python str.strip additionally recognizes the four ASCII record separators.
    let body = body.trim_matches(|c: char| c.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&c));
    if HEADER.len() + body.len() + FOOTER.len() <= MAX_CONTEXT_BYTES {
        return format!("{HEADER}{body}{FOOTER}");
    }
    let mut end = MAX_CONTEXT_BYTES - HEADER.len() - TRUNCATION.len() - FOOTER.len();
    while !body.is_char_boundary(end) {
        end -= 1;
    }
    format!("{HEADER}{}{TRUNCATION}{FOOTER}", &body[..end])
}

pub fn compact_resume(path: &Path, input: &[u8]) -> String {
    // Hook JSON is external: unknown fields and non-object payloads are tolerated.
    let source = serde_json::from_slice::<serde_json::Value>(input)
        .ok()
        .and_then(|value| value.get("source")?.as_str().map(str::to_owned));
    if !source.is_some_and(|source| source.replace('\0', "").trim_end_matches('\n') == "compact") {
        return String::new();
    }
    let body = read_handoff(path).unwrap_or_else(|error| {
        if error == "canonical handoff is missing" {
            "[mir] canonical handoff is missing; inspect repository state before continuing.".into()
        } else {
            let class = error.strip_prefix("canonical handoff is unreadable: ").unwrap_or("OSError");
            format!("[mir] canonical handoff is unreadable ({class}); inspect repository state before continuing.")
        }
    });
    recovery(&body)
}

pub fn post_compact(path: &Path) -> String {
    let error = match read_handoff(path) {
        Ok(body) => parse(&body).err(),
        Err(error) => Some(error),
    };
    match error {
        None => String::new(),
        Some(error) => {
            let warning =
                format!("[mir] PostCompact degraded: session-handoff-LATEST.md — {error}");
            // Python json.dumps uses these spaces and preserves non-ASCII bytes.
            format!(
                "{{\"continue\": true, \"systemMessage\": {}}}\n",
                serde_json::Value::String(warning)
            )
        }
    }
}
