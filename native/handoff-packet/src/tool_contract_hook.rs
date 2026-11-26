//! Native leaf and PreToolUse validator. Unknown fields and Python's permissive
//! contract values are retained; malformed container shapes fail with diagnostics.
use handoff_packet::mir_core::structured_error::StructuredError;
use handoff_packet::python_json::{self, Value};
use serde_json::json;
use std::io::{self, Read, Write};

const CONTRACT_REF: &str = "src/mir/core/engine/tool_contract.py";

fn error(kind: &str, summary: &str, details: Option<&str>, output: &mut String) -> u8 {
    // These fixed fields satisfy StructuredError's required schema.
    if let Ok(error) = StructuredError::from_dict(&json!({
        "type": kind, "recoverable": false, "summary": summary, "details_ref": details
    })) {
        output.push_str("[mir CONTRACT] ");
        output.push_str(&error.to_json());
        output.push('\n');
    }
    2
}

fn schema(summary: &str, details: Option<&str>, output: &mut String) -> u8 {
    error("schema", summary, details, output)
}

fn payload(value: &Value, output: &mut String) -> u8 {
    if !value.is_object() {
        return schema("tool_event must be a JSON object", None, output);
    }
    let tool = value.get("tool_name").unwrap_or(&Value::Null);
    if tool.is_array() || tool.is_object() {
        return schema("tool_name must be a string", None, output);
    }
    let Some(tool) = tool
        .as_str()
        .filter(|s| matches!(*s, "Edit" | "Write" | "Bash"))
    else {
        return 0;
    };
    let input = value.get("tool_input");
    if input.is_some_and(|v| !v.is_object()) {
        return schema(
            &format!("tool_input for {tool} must be a JSON object"),
            None,
            output,
        );
    }
    let Some(contract) = input
        .and_then(|v| v.get("_mir_contract"))
        .filter(|v| !v.is_null())
    else {
        return error(
            "precondition",
            &format!("tool {tool} requires _mir_contract field in tool_input"),
            Some("docs/decisions/adr-44-13-state-sm-migration-2026-05-24.md"),
            output,
        );
    };
    let invalid = |message: &str, output: &mut String| {
        schema(
            &format!("invalid ToolContract for {tool}: {message}"),
            Some(CONTRACT_REF),
            output,
        )
    };
    if !contract.is_object() {
        return invalid("_mir_contract must be a JSON object", output);
    }
    for key in [
        "idempotency_key",
        "precondition",
        "dry_run",
        "side_effect_summary",
    ] {
        if contract.get(key).is_none() {
            return invalid(&format!("missing required field: {key}"), output);
        }
    }
    let length = match contract.get("side_effect_summary") {
        Some(Value::String(s)) => s.codepoints.len(),
        Some(Value::Array(a)) => a.len(),
        Some(Value::Object(o)) => o.len(),
        _ => return invalid("side_effect_summary must be a string", output),
    };
    if length > 200 {
        return invalid(
            &format!("side_effect_summary too long: {length} chars (max 200)"),
            output,
        );
    }
    0
}

/// Buffer diagnostics so the enclosing hook can keep its redacted wrapper.
pub fn validate(input: &[u8], output: &mut String) -> u8 {
    if std::str::from_utf8(input).is_ok_and(|s| python_json::python_strip(s).is_empty()) {
        return 0;
    }
    // The retired leaf used sys.stdin.read() without a size limit. The enclosing
    // hook retains its own admission bounds; do not add a new leaf limit here.
    // This script's sys.stdin preserves CRLF on POSIX, unlike the lifecycle
    // TextIOWrapper entrypoints. Keep character offsets and surrogateescape.
    match python_json::parse_codepoints(python_json::stdin_codepoints(input)) {
        Ok(value) => {
            let exit = payload(&value, output);
            python_json::discard(value);
            exit
        }
        Err(error) => schema(
            &format!("tool_event JSON parse failed: {error}"),
            None,
            output,
        ),
    }
}

pub fn run() -> u8 {
    let mut input = Vec::new();
    let mut output = String::new();
    let exit = if io::stdin().lock().read_to_end(&mut input).is_ok() {
        validate(&input, &mut output)
    } else {
        schema("tool_event input could not be read", None, &mut output)
    };
    if io::stderr().lock().write_all(output.as_bytes()).is_err() {
        return 2;
    }
    exit
}
