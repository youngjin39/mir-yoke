//! Read-only advisory scanner matching Yoke's post-edit shell reference.
#![forbid(unsafe_code)]
use regex::bytes::Regex;
use serde_json::Value;
use std::{collections::HashSet, fs, path::Path};

fn field(value: &Value, keys: &[&str]) -> String {
    keys.iter()
        .map(|key| &value["tool_input"][*key])
        .find(|v| !v.is_null() && **v != false)
        .map(|v| match v {
            Value::String(s) => s.clone(),
            other => other.to_string(),
        })
        .unwrap_or_default()
        .trim_end_matches('\n')
        .replace('\0', "")
        .to_owned()
}

pub fn scan(project: &Path, input: &[u8]) -> String {
    let Ok(value) = serde_json::from_slice::<Value>(input) else {
        return String::new();
    };
    let direct = field(&value, &["file_path", "path"]);
    let patch = field(&value, &["command", "input", "patch", "content"]);
    let mut paths: Vec<&str> = direct.split('\n').collect();
    for line in patch.split('\n') {
        for prefix in [
            "*** Add File: ",
            "*** Update File: ",
            "*** Delete File: ",
            "*** Move to: ",
        ] {
            if let Some(path) = line.strip_prefix(prefix) {
                paths.push(path);
                break;
            }
        }
    }
    let credential = Regex::new(r"sk-[a-zA-Z0-9_-]{20,}|ghp_[a-zA-Z0-9]{36}|gho_[a-zA-Z0-9]{36}|AIza[a-zA-Z0-9_-]{35}|xoxb-[0-9]{10,}|AKIA[A-Z0-9]{16}|aws_secret_access_key[\t\n\x0b\x0c\r ]*=").unwrap();
    let javascript = Regex::new(r"console\.log").unwrap();
    let python = Regex::new(r"^[\t\x0b\x0c\r ]*print\(").unwrap();
    let mut seen = HashSet::new();
    let mut output = String::new();
    for raw in paths {
        if raw.trim().is_empty() || !seen.insert(raw) {
            continue;
        }
        // Shell prefix stripping preserves textual path spelling.
        let project = project.to_string_lossy();
        let path = if Path::new(raw).is_absolute() {
            raw.to_owned()
        } else {
            format!("{project}/{raw}")
        };
        if !Path::new(&path).is_file() {
            continue;
        }
        let Ok(bytes) = fs::read(&path) else {
            continue;
        };
        let display = path.strip_prefix(&format!("{project}/")).unwrap_or(&path);
        let ext = path.rsplit('.').next().unwrap_or(&path);
        let debug = match ext {
            "js" | "ts" | "jsx" | "tsx" => Some((&javascript, "console.log")),
            "py" => Some((&python, "print()")),
            _ => None,
        };
        let hits = |regex: &Regex, keep: bool| {
            bytes
                .split(|b| *b == b'\n')
                .enumerate()
                .filter(|(_, line)| {
                    regex.is_match(line) && !(keep && line.windows(6).any(|w| w == b"# keep"))
                })
                .take(3)
                .map(|(n, _)| (n + 1).to_string())
                .collect::<Vec<_>>()
                .join(",")
        };
        if let Some((pattern, label)) = debug {
            let lines = hits(pattern, ext == "py");
            if !lines.is_empty() {
                output.push_str(&format!(
                    "[WARNING] {label} detected in {display} at line(s) {lines}\n"
                ));
            }
        }
        if matches!(
            ext,
            "md" | "json" | "yaml" | "yml" | "sh" | "ts" | "js" | "py" | "env" | "toml" | "cfg"
        ) {
            let lines = hits(&credential, false);
            if !lines.is_empty() {
                output.push_str(&format!("[CRITICAL] Possible credential/API key detected in {display} at line(s) {lines} — value redacted; rotate immediately if real.\n"));
            }
        }
    }
    output
}
