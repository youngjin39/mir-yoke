//! Parity port of Yoke's jq-present Bash gate; unknown hook fields are ignored.
#![forbid(unsafe_code)]
use serde_json::Value;
use std::{
    env, fs,
    io::{self, Read, Write},
    path::Path,
};

const BLOCK: &str = "[mir BLOCKED] sub-agent-policy mode=force_codex: Claude Agent/Task sub-agent spawn is blocked. Use the user-scope Codex plugin (codex:codex-rescue or /codex:rescue, with policy --model/--effort) or 'scripts/mir.sh executor execute --background --dispatch ...' (codex app-server) for in-repo code/TDD/review writes. Raw codex exec is banned by ADR-69. To temporarily allow a Claude sub-agent set MIR_R3_FALLBACK=1. The mode comes from the Harness-generated config/model-routing.lock.json policy.delegation.mode (never edit it); change it in Mir Harness config/model-routing and redeploy.\n";
const MALFORMED: &str = "[PreToolUse BLOCK] Malformed PreToolUse payload for filter: .tool_name\n";
const ADVISORY: &str = "[mir ADVISORY] force_codex Agent/Task escape via MIR_R3_FALLBACK=1\n";

fn truthy(value: &Value) -> bool {
    !matches!(value, Value::Null | Value::Bool(false))
}

// jq's object lookup accepts null, but errors on other non-object values.
fn field<'a>(value: &'a Value, key: &str) -> Option<&'a Value> {
    match value {
        Value::Object(map) => Some(map.get(key).unwrap_or(&Value::Null)),
        Value::Null => Some(&Value::Null),
        _ => None,
    }
}

// Bash command substitution removes NUL bytes and trailing newlines.
fn shell_output(value: &str) -> String {
    value.replace('\0', "").trim_end_matches('\n').to_owned()
}

fn read_mode(path: &Path) -> Option<String> {
    let bytes = fs::read(path).ok()?;
    let mut modes = Vec::new();
    for data in serde_json::Deserializer::from_slice(&bytes).into_iter::<Value>() {
        let data = data.ok()?;
        let policy = field(&data, "policy")?;
        let policy = if truthy(policy) { policy } else { &data };
        let nested = field(field(policy, "delegation")?, "mode")?;
        let mode = if truthy(nested) {
            nested
        } else {
            field(&data, "mode")?
        };
        if let Some(mode) = mode.as_str() {
            modes.push(mode.to_owned());
        }
    }
    if modes.is_empty() {
        None
    } else {
        Some(shell_output(&modes.join("\n")))
    }
}

fn resolve_mode(project: &Path) -> String {
    let lock = project.join("config/model-routing.lock.json");
    let local = project.join("config/sub-agent-policy.json");
    let locked = lock.is_file();
    let Some(mut mode) = read_mode(if locked { &lock } else { &local }) else {
        return "force_codex".into();
    };
    if !locked && let Some(overlay) = env::var_os("MIR_SUB_AGENT_POLICY") {
        let overlay = Path::new(&overlay);
        if overlay.is_file() {
            let Some(overlay_mode) = read_mode(overlay) else {
                return "force_codex".into();
            };
            mode = overlay_mode;
        }
    }
    match mode.as_str() {
        "force_codex"
        | "force_claude"
        | "select"
        | "per_project"
        | "unrestricted"
        | "user_command_priority"
        | "obey_user" => mode,
        _ => "force_codex".into(),
    }
}

fn decide(input: &[u8], project: &Path) -> (i32, &'static str) {
    let mut names = Vec::new();
    let mut last_truthy = false;
    for data in serde_json::Deserializer::from_slice(input).into_iter::<Value>() {
        let Ok(data) = data else {
            return (2, MALFORMED);
        };
        let Some(name) = field(&data, "tool_name") else {
            return (2, MALFORMED);
        };
        last_truthy = truthy(name);
        names.push(
            name.as_str()
                .map(str::to_owned)
                .unwrap_or_else(|| name.to_string()),
        );
    }
    if !last_truthy {
        return (2, MALFORMED);
    }
    let name = shell_output(&names.join("\n"));
    if !matches!(name.as_str(), "Agent" | "Task") {
        return (0, "");
    }
    if resolve_mode(project) != "force_codex" {
        return (0, "");
    }
    // The reference's Python json.load requires one document, unlike jq's stream.
    let agent = serde_json::from_slice::<Value>(input)
        .ok()
        .and_then(|data| {
            data.pointer("/tool_input/subagent_type")
                .and_then(Value::as_str)
                .map(shell_output)
        });
    if agent.as_deref() == Some("codex:codex-rescue") {
        return (0, "");
    }
    if env::var("MIR_R3_FALLBACK").as_deref() == Ok("1") {
        return (0, ADVISORY);
    }
    (2, BLOCK)
}

fn main() {
    if env::args().nth(1).as_deref() == Some("--version") {
        println!("delegation-gate 0.1.0");
        return;
    }
    let project = env::var_os("CLAUDE_PROJECT_DIR")
        .filter(|v| !v.is_empty())
        .unwrap_or_else(|| ".".into());
    let mut input = Vec::new();
    let (code, message) = if io::stdin().read_to_end(&mut input).is_ok() {
        decide(&input, Path::new(&project))
    } else {
        (2, MALFORMED)
    };
    let code = if io::stderr().write_all(message.as_bytes()).is_err() {
        2
    } else {
        code
    };
    std::process::exit(code);
}
