//! Native input-stage policy. Unknown payload fields are tolerated, as in jq.
#![forbid(unsafe_code)]
use serde_json::Value;
use std::{
    env, fs,
    io::{self, Read, Write},
    path::{Component, Path, PathBuf},
    process::{Command, Stdio},
    time::Instant,
};

type Gate = Result<(), String>;
fn block(message: impl AsRef<str>) -> String {
    format!("[PreToolUse BLOCK] {}\n", message.as_ref())
}
fn warn(output: &mut String, message: impl AsRef<str>) {
    output.push_str(&format!("[PreToolUse WARN] {}\n", message.as_ref()));
}
fn enabled(key: &str) -> bool {
    env::var(key).is_ok_and(|v| v == "1")
}
fn delegated() -> bool {
    env::var_os("MIR_CODEX_SESSION_ID").is_some_and(|v| !v.is_empty())
}
fn raw(value: &Value) -> String {
    let text = match value {
        Value::String(v) => v.clone(),
        _ => serde_json::to_string_pretty(value).unwrap_or_default(),
    };
    text.replace('\0', "").trim_end_matches('\n').to_owned()
}
// jq processes JSON document streams and keeps the final input's status.
fn stream_extract(documents: &[Value], nested: bool, keys: &[&str]) -> Option<String> {
    let mut output = String::new();
    let mut success = false;
    for document in documents {
        if !document.is_object() && !document.is_null() {
            success = false;
            continue;
        }
        let container = if nested {
            &document["tool_input"]
        } else {
            document
        };
        if !container.is_object() && !container.is_null() {
            success = false;
            continue;
        }
        let value = keys
            .iter()
            .map(|key| &container[*key])
            .find(|v| !v.is_null() && **v != false)
            .unwrap_or_else(|| {
                keys.last()
                    .map(|key| &container[*key])
                    .unwrap_or(&Value::Null)
            });
        success = !value.is_null() && *value != false;
        match value {
            Value::String(s) => output.push_str(s),
            other => output.push_str(&serde_json::to_string_pretty(other).unwrap_or_default()),
        }
        output.push('\n');
    }
    success.then(|| output.replace('\0', "").trim_end_matches('\n').to_owned())
}
// Retain POSIX ERE behavior and error status rather than approximate it with Rust regex.
fn posix(subject: &str, pattern: &str) -> Result<bool, ()> {
    let mut child = Command::new("grep")
        .args(["-qE", pattern])
        .stdin(Stdio::piped())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|_| ())?;
    if let Some(mut stdin) = child.stdin.take() {
        let _ = stdin.write_all(subject.as_bytes());
    }
    match child.wait().map_err(|_| ())?.code() {
        Some(0) => Ok(true),
        Some(1) => Ok(false),
        _ => Err(()),
    }
}
fn safety(subject: &str, pattern: &str) -> Result<bool, String> {
    posix(subject, pattern).map_err(|_| block("safety pattern matching failed"))
}
fn deny(root: &Path, subject: &str, label: &str, output: &mut String) -> Gate {
    let path = root.join(".ai-harness/deny-list.yaml");
    if subject.is_empty() || !path.is_file() {
        return Ok(());
    }
    let text = fs::read_to_string(path).map_err(|_| block("deny-list parsing failed"))?;
    let mut rows: Vec<[String; 4]> = Vec::new();
    let mut row: [String; 4] = Default::default();
    for line in text.lines() {
        let trimmed = line.trim_start_matches(char::is_whitespace);
        let key = if trimmed.strip_prefix('-').is_some_and(|rest| {
            rest.starts_with(char::is_whitespace) && rest.trim_start().starts_with("id:")
        }) {
            Some(0)
        } else if line.starts_with(char::is_whitespace) && !row[0].is_empty() {
            ["pattern:", "severity:", "reason:"]
                .iter()
                .position(|p| trimmed.starts_with(p))
                .map(|i| i + 1)
        } else {
            None
        };
        if let Some(index) = key {
            if index == 0 {
                if !row[0].is_empty() {
                    rows.push(row);
                }
                row = Default::default();
            }
            let field = line
                .split_once(':')
                .map(|(_, s)| s.trim_start_matches(char::is_whitespace))
                .unwrap_or("");
            let field = field.strip_prefix('"').unwrap_or(field);
            let field = field.strip_suffix('"').unwrap_or(field);
            let field = field.strip_prefix('\'').unwrap_or(field);
            let field = field.strip_suffix('\'').unwrap_or(field);
            row[index] = field.into();
        }
    }
    if !row[0].is_empty() {
        rows.push(row);
    }
    for row in rows {
        // Bash read with whitespace IFS collapses empty fields.
        let fields: Vec<_> = row
            .iter()
            .flat_map(|s| s.split('\t'))
            .filter(|s| !s.is_empty())
            .collect();
        let id = fields.first().copied().unwrap_or("");
        let pattern = fields.get(1).copied().unwrap_or("");
        let severity = fields.get(2).copied().unwrap_or("");
        let reason = fields.get(3..).unwrap_or(&[]).join("\t");
        if id.is_empty() || pattern.is_empty() {
            continue;
        }
        let pattern = pattern.replace("\\\\", "\\");
        posix("", &pattern).map_err(|_| {
            block(format!(
                "deny-list[{id}] is not a usable POSIX regex; fix .ai-harness/deny-list.yaml"
            ))
        })?;
        if !posix(subject, &pattern)
            .map_err(|_| block(format!("deny-list[{id}] matching failed")))?
        {
            continue;
        }
        let message = format!("deny-list[{id}] {label}: {reason}");
        match severity {
            "block" => return Err(block(message)),
            "warn" => warn(output, message),
            "suggest" => {
                output.push_str(&format!(
                    "[hook SUGGEST] pre-tool-use/deny-list[{id}]: {message}\n"
                ));
            }
            _ => (),
        }
    }
    Ok(())
}
fn expand(path: &str) -> PathBuf {
    if path == "~" || path.starts_with("~/") {
        if let Some(home) = env::var_os("HOME") {
            let mut expanded = home;
            expanded.push(&path[1..]);
            return PathBuf::from(expanded);
        }
        if let Ok(result) = Command::new("/usr/bin/id")
            .arg("-un")
            .stderr(Stdio::null())
            .output()
            && result.status.success()
            && let Ok(user) = String::from_utf8(result.stdout)
        {
            let user = user.trim_end_matches('\n');
            if !user.is_empty() {
                return expand(&format!(
                    "~{user}/{}",
                    path.strip_prefix("~/").unwrap_or("")
                ));
            }
        }
    }
    if let Some(tail) = path
        .strip_prefix('~')
        .filter(|s| !s.is_empty() && !s.starts_with('/'))
    {
        let (user, rest) = tail.split_once('/').unwrap_or((tail, ""));
        let passwd_home = |text: &str| {
            text.lines().find_map(|line| {
                let fields: Vec<_> = line.split(':').collect();
                if fields.first().copied() == Some(user) {
                    fields
                        .get(if fields.len() >= 10 { 8 } else { 5 })
                        .map(PathBuf::from)
                } else {
                    None
                }
            })
        };
        let home = fs::read_to_string("/etc/passwd")
            .ok()
            .and_then(|s| passwd_home(&s))
            .or_else(|| {
                // Read the platform account database without evaluating shell text.
                for (program, args) in [
                    ("/usr/bin/id", vec!["-P", user]),
                    ("/usr/bin/getent", vec!["passwd", user]),
                ] {
                    if let Ok(result) = Command::new(program)
                        .args(args)
                        .stderr(Stdio::null())
                        .output()
                        && result.status.success()
                        && let Ok(text) = String::from_utf8(result.stdout)
                        && let Some(home) = passwd_home(&text)
                    {
                        return Some(home);
                    }
                }
                None
            });
        if let Some(home) = home {
            let mut expanded = home.into_os_string();
            if tail.contains('/') {
                expanded.push(format!("/{rest}"));
            }
            return PathBuf::from(expanded);
        }
    }
    PathBuf::from(path)
}
fn resolve(path: &Path) -> io::Result<PathBuf> {
    fn inner(path: &Path, links: usize) -> io::Result<PathBuf> {
        if links > 40 {
            return Err(io::Error::other("symlink loop"));
        }
        let path = if path.is_absolute() {
            path.to_path_buf()
        } else {
            env::current_dir()?.join(path)
        };
        let mut result = PathBuf::new();
        for part in path.components() {
            match part {
                Component::ParentDir => {
                    result.pop();
                }
                Component::CurDir => (),
                _ => {
                    result.push(part);
                    match fs::symlink_metadata(&result) {
                        Ok(meta) if meta.file_type().is_symlink() => {
                            let target = fs::read_link(&result)?;
                            result.pop();
                            result = inner(&result.join(target), links + 1)?;
                        }
                        Ok(_) => (),
                        Err(e)
                            if matches!(
                                e.kind(),
                                io::ErrorKind::NotFound | io::ErrorKind::NotADirectory
                            ) => {}
                        Err(e) => return Err(e),
                    }
                }
            }
        }
        Ok(result)
    }
    inner(path, 0)
}
fn secret(name: &str) -> bool {
    matches!(name, ".env" | "credentials" | "id_rsa" | "id_ed25519")
        || name.starts_with(".env.")
        || name.starts_with("credentials.")
        || [".pem", ".key", ".p12"].iter().any(|s| name.ends_with(s))
}
fn root_reason(root: &Path, path: &str) -> Result<Option<&'static str>, ()> {
    let root = resolve(root).map_err(|_| ())?;
    let candidate = expand(path);
    let candidate = resolve(&root.join(candidate)).map_err(|_| ())?;
    let Ok(relative) = candidate.strip_prefix(&root) else {
        return Ok(Some("patch path outside project root"));
    };
    if relative.components().any(|p| p.as_os_str() == ".git") {
        return Ok(Some("patch targets git internal state"));
    }
    Ok(
        if relative
            .file_name()
            .and_then(|n| n.to_str())
            .is_some_and(secret)
        {
            Some("patch targets a secret or credential file")
        } else {
            None
        },
    )
}
fn path_guard(root: &Path, cwd: &str, tool: &str, path: &str, output: &mut String) -> Gate {
    if path.is_empty() {
        return Ok(());
    }
    if matches!(tool, "apply_patch" | "ApplyPatch") {
        if let Some(reason) =
            root_reason(root, path).map_err(|_| block("patch path safety inspection failed"))?
        {
            return Err(block(reason));
        }
        return deny(root, path, "path", output);
    }
    let resolved_root = resolve(root).map_err(|_| block("project path resolution failed"))?;
    let base = resolved_root.join(expand(cwd));
    let resolved =
        resolve(&base.join(expand(path))).map_err(|_| block("project path resolution failed"))?;
    let relative = resolved
        .strip_prefix(&resolved_root)
        .ok()
        .and_then(|p| p.to_str())
        .map(|p| if p.is_empty() { "." } else { p })
        .unwrap_or("");
    if relative.is_empty()
        && [
            "/etc/",
            "/System/",
            "/Library/",
            "/usr/",
            "/bin/",
            "/sbin/",
            "/var/",
            "/private/",
        ]
        .iter()
        .any(|p| path.starts_with(p))
    {
        return Err(block(format!("Write outside project root: {path}")));
    }
    if Path::new(path)
        .file_name()
        .and_then(|n| n.to_str())
        .is_some_and(secret)
    {
        return Err(block(format!("Write to secret/credential file: {path}")));
    }
    if safety(path, r"(^|/)\.git/(config|hooks/|refs/|objects/)")? {
        return Err(block(format!("Write to git internal state: {path}")));
    }
    if delegated() && (path == "tasks/plan.md" || path.ends_with("/tasks/plan.md")) {
        return Err(block(
            "ADR-60 R5: a sub-agent/codex context must not edit the main control-plane cursor tasks/plan.md — the control_plane main owns it (report your result via your final message + the JobRegistry, never plan.md)",
        ));
    }
    deny(
        root,
        if relative.is_empty() { path } else { relative },
        "path",
        output,
    )?;
    if matches!(tool, "Edit" | "Write")
        && let Some(reason) =
            root_reason(root, path).map_err(|_| block("file path safety inspection failed"))?
    {
        return Err(block(reason));
    }
    Ok(())
}
// Python shlex tokenization without shell evaluation.
fn shell_tokens(command: &str) -> Result<Vec<String>, ()> {
    let chars: Vec<char> = command.chars().collect();
    let mut i = 0;
    let mut tokens = Vec::new();
    let punct = ";&|()<>\n";
    while i < chars.len() {
        if " \t\r".contains(chars[i]) {
            i += 1;
            continue;
        }
        if chars[i] == '#' {
            while i < chars.len() && chars[i] != '\n' {
                i += 1;
            }
            if i < chars.len() {
                i += 1;
            }
            continue;
        }
        let mut token = String::new();
        let mut started = false;
        if punct.contains(chars[i]) {
            while i < chars.len() && punct.contains(chars[i]) {
                token.push(chars[i]);
                i += 1;
            }
            tokens.push(token);
            continue;
        }
        while i < chars.len() && !" \t\r".contains(chars[i]) && !punct.contains(chars[i]) {
            let c = chars[i];
            i += 1;
            started = true;
            if c == '#' {
                while i < chars.len() && chars[i] != '\n' {
                    i += 1;
                }
                if i < chars.len() {
                    i += 1;
                }
                break;
            }
            if c == '\\' {
                if i == chars.len() {
                    return Err(());
                }
                token.push(chars[i]);
                i += 1;
            } else if c == '\'' || c == '"' {
                let quote = c;
                let mut closed = false;
                while i < chars.len() {
                    let c = chars[i];
                    i += 1;
                    if c == quote {
                        closed = true;
                        break;
                    }
                    if c == '\\' && quote == '"' {
                        if i == chars.len() {
                            return Err(());
                        }
                        let next = chars[i];
                        i += 1;
                        if next != '"' && next != '\\' {
                            token.push('\\');
                        }
                        token.push(next);
                    } else {
                        token.push(c);
                    }
                }
                if !closed {
                    return Err(());
                }
            } else {
                token.push(c);
            }
        }
        if started {
            tokens.push(token);
        }
    }
    Ok(tokens)
}
fn raw_codex(command: &str) -> Result<bool, ()> {
    let tokens = shell_tokens(command)?;
    let assignment = regex::Regex::new(r"(?s)^[A-Za-z_][A-Za-z0-9_]*=.*$").map_err(|_| ())?;
    let basename = |s: &str| {
        s.trim_end_matches('/')
            .rsplit('/')
            .next()
            .unwrap_or("")
            .to_owned()
    };
    for segment in tokens.split(|t| !t.is_empty() && t.chars().all(|c| ";&|()\n".contains(c))) {
        let mut index = 0;
        while index < segment.len() && assignment.is_match(&segment[index]) {
            index += 1;
        }
        if index < segment.len() && basename(&segment[index]) == "env" {
            index += 1;
            while index < segment.len()
                && (segment[index] == "--"
                    || segment[index].starts_with('-')
                    || assignment.is_match(&segment[index]))
            {
                index += 1;
            }
        }
        if index < segment.len()
            && basename(&segment[index]) == "codex"
            && segment[index + 1..]
                .iter()
                .any(|a| matches!(a.as_str(), "exec" | "e"))
        {
            return Ok(true);
        }
    }
    Ok(false)
}

fn decimal_integer(text: &str) -> Option<String> {
    let text = text.trim();
    let (negative, digits) = if let Some(rest) = text.strip_prefix('-') {
        (true, rest)
    } else {
        (false, text.strip_prefix('+').unwrap_or(text))
    };
    let mut result = String::new();
    let mut previous_digit = false;
    for c in digits.chars() {
        if c == '_' {
            if !previous_digit {
                return None;
            }
            previous_digit = false;
        } else {
            let digit = crate::python_decimal::decimal_digit(c)?;
            result.push(char::from(b'0' + digit as u8));
            previous_digit = true;
        }
    }
    if !previous_digit {
        return None;
    }
    let result = result.trim_start_matches('0');
    Some(if result.is_empty() {
        "0".into()
    } else if negative {
        format!("-{result}")
    } else {
        result.into()
    })
}

// Keep JSON integer tokens intact: Value otherwise rounds integers beyond u64 to f64.
fn phase_equals(raw: &serde_json::value::RawValue, phase: &str) -> bool {
    if let Some(integer) = decimal_integer(raw.get()) {
        return integer == phase;
    }
    match serde_json::from_str::<Value>(raw.get()) {
        Ok(Value::Bool(v)) => phase == if v { "1" } else { "0" },
        Ok(Value::Number(n)) => {
            n.as_f64()
                .filter(|v| v.is_finite() && v.fract() == 0.0)
                .and_then(|v| decimal_integer(&format!("{v:.0}")))
                .as_deref()
                == Some(phase)
        }
        _ => false,
    }
}

fn enabled_phase(config: &[u8], phase: &str) -> Option<bool> {
    type Object = std::collections::HashMap<String, Box<serde_json::value::RawValue>>;
    let config: Object = serde_json::from_slice(config).ok()?;
    let phase = decimal_integer(phase)?;
    let Some(phases) = config.get("enabled_phases") else {
        return Some(false);
    };
    let phases: Vec<Object> = serde_json::from_str(phases.get()).ok()?;
    // Python builds the entire list before testing membership, so a missing key fails.
    let phases = phases
        .iter()
        .map(|p| p.get("phase"))
        .collect::<Option<Vec<_>>>()?;
    Some(phases.iter().any(|p| phase_equals(p, &phase)))
}

fn policy(root: &Path, input: &[u8], output: &mut String) -> Gate {
    let documents = serde_json::Deserializer::from_slice(input)
        .into_iter::<Value>()
        .collect::<Result<Vec<_>, _>>()
        .map_err(|_| block("Malformed PreToolUse payload for filter: .tool_name"))?;
    let value = documents.last().unwrap_or(&Value::Null);
    let tin_extract = |keys: &[&str]| stream_extract(&documents, true, keys);
    let tool = stream_extract(&documents, false, &["tool_name"])
        .ok_or_else(|| block("Malformed PreToolUse payload for filter: .tool_name"))?;
    let cwd = stream_extract(&documents, false, &["cwd"])
        .filter(|v| !v.is_empty())
        .unwrap_or_else(|| root.to_str().unwrap_or(".").into());
    let tin = &value["tool_input"];
    if delegated() {
        if matches!(tool.as_str(), "apply_patch" | "ApplyPatch") {
            let patch =
                tin_extract(&["command", "input", "patch", "content"]).unwrap_or_else(|| raw(tin));
            if safety(
                &patch,
                r"(^|[^[:alnum:]_./-])tasks/plan\.md([^[:alnum:]_]|$)",
            )? {
                return Err(block(
                    "ADR-60 R5: a sub-agent/codex context must not edit the main control-plane cursor tasks/plan.md via apply_patch — the control_plane main owns it (report your result via your final message + the JobRegistry, never plan.md)",
                ));
            }
        } else if tool == "Bash" {
            let command = tin_extract(&["command"]).unwrap_or_default();
            if safety(&command, r"tasks/plan\.md")?
                && safety(
                    &command,
                    r"(>>?|[[:space:]]tee([[:space:]]|$)|sed[[:space:]]+-i|[[:space:]]truncate([[:space:]]|$)|[[:space:]]dd([[:space:]]|$)|[[:space:]]cp([[:space:]]|$)|[[:space:]]mv([[:space:]]|$))",
                )?
            {
                return Err(block(
                    "ADR-60 R5: a sub-agent/codex context must not write the main control-plane cursor tasks/plan.md via Bash — the control_plane main owns it (report your result via your final message + the JobRegistry, never plan.md)",
                ));
            }
        }
    }
    if tool == "Bash" {
        let command = tin_extract(&["command"])
            .ok_or_else(|| block("Malformed PreToolUse payload for filter: .tool_input.command"))?;
        if command.is_empty() {
            return Err(block("Empty Bash command payload"));
        }
        if safety(
            &command,
            r"rm[[:space:]]+(-[rRfF]+[[:space:]]+)+(/|~|\$HOME|\*|\.|\.\./)",
        )? {
            return Err(block("Destructive rm pattern"));
        }
        let push = r"git[[:space:]]+push([[:space:]]+[^[:space:];&|]+)*[[:space:]]+";
        if safety(
            &command,
            &format!("{push}((-f|--force|--force-with-lease)([[:space:]]|[;&|]|$)|[+])"),
        )? && safety(
            &command,
            &format!("{push}[+]?([^[:space:];&|]*/)?(main|master|release)([[:space:]]|[;&|]|$)"),
        )? {
            return Err(block("Force push to protected branch"));
        }
        for (pattern, message) in [
            (
                r"(--no-verify|--no-gpg-sign|-c[[:space:]]+commit\.gpgsign=false)",
                "Hook/signing bypass flag",
            ),
            (
                r"git[[:space:]]+(reset[[:space:]]+--hard[[:space:]]+origin|rebase[[:space:]]+.*main|filter-branch|filter-repo)",
                "History rewrite on shared refs",
            ),
            (
                r"(curl|wget)[^|]*\|[[:space:]]*(bash|sh|zsh|python)",
                "Piped remote install",
            ),
            (
                r"(^|[[:space:];&|(`]|/)sudo([[:space:]]|$)",
                "sudo requires user confirmation, not this hook",
            ),
        ] {
            if safety(&command, pattern)? {
                return Err(block(message));
            }
        }
        match raw_codex(&command) {
            Ok(false) => (),
            Ok(true) => {
                return Err(block(
                    "raw codex exec/e is banned — use the Codex plugin or mir_executor (app-server)",
                ));
            }
            Err(()) => return Err(block("Bash command screening failed")),
        }
        if enabled("MIR_PRE_COMMIT_VERIFY")
            && safety(
                &command,
                r"(^|[[:space:]])git[[:space:]]+commit([[:space:]]|$)",
            )?
        {
            // Preserve continuation order without spawning a second shell hook.
            if crate::pre_commit_verification::run() != 0 {
                return Err(block("pre-commit verification failed for code changes"));
            }
        }
        deny(root, &command, "bash", output)?;
    }
    if matches!(tool.as_str(), "Write" | "Edit" | "NotebookEdit") {
        let path=tin_extract(&["file_path","path","notebook_path"]).ok_or_else(|| block("Malformed PreToolUse payload for filter: .tool_input.file_path // .tool_input.path // .tool_input.notebook_path"))?;
        if path.is_empty() {
            return Err(block("Empty file path payload"));
        }
        path_guard(root, &cwd, &tool, &path, output)?;
    }
    if matches!(tool.as_str(), "apply_patch" | "ApplyPatch") {
        let patch_value = ["command", "input", "patch", "content"]
            .iter()
            .map(|k| &tin[*k])
            .find(|v| !v.is_null() && **v != false);
        let patch = patch_value
            .and_then(Value::as_str)
            .filter(|p| !p.is_empty())
            .ok_or_else(|| block("Malformed apply_patch payload"))?;
        let patch = patch.replace('\0', "");
        for line in patch.split('\n') {
            for prefix in [
                "*** Add File: ",
                "*** Update File: ",
                "*** Delete File: ",
                "*** Move to: ",
            ] {
                if let Some(path) = line.strip_prefix(prefix) {
                    path_guard(root, &cwd, &tool, path, output)?;
                    break;
                }
            }
        }
    }
    let config = root.join("config/bluebrick-paths.json");
    if config.is_file()
        && matches!(tool.as_str(), "Edit" | "Write")
        && let Some(path) = tin_extract(&["file_path", "path"]).filter(|s| !s.is_empty())
    {
        match fs::read(config)
            .ok()
            .and_then(|b| serde_json::from_slice::<Value>(&b).ok())
        {
            Some(Value::Object(mapping)) => {
                let pwd = env::var("PWD").unwrap_or_default();
                let relative = path
                    .strip_prefix(&format!("{pwd}/"))
                    .filter(|_| !pwd.is_empty());
                // serde_json's default map is sorted; recover insertion order from raw pairs below.
                let ordered = fs::read(root.join("config/bluebrick-paths.json"))
                    .ok()
                    .and_then(|b| ordered_mapping(&b).ok())
                    .unwrap_or_else(|| mapping.into_iter().collect());
                if let Some((_, brick)) = ordered.iter().find(|(prefix, _)| {
                    path.starts_with(prefix) || relative.is_some_and(|p| p.starts_with(prefix))
                }) {
                    let brick = match brick {
                        Value::String(s) => s.clone(),
                        v => python_repr(v),
                    };
                    warn(
                        output,
                        format!(
                            "[bluebrick] read docs/bluebricks/{brick}.md before changing {path}"
                        ),
                    );
                }
            }
            _ => warn(output, "bluebrick advisory inspection failed"),
        }
    }
    if enabled("MIR_ENABLED_PHASES_CHECK") {
        let family = env::var("MIR_FAMILY_SLUG")
            .ok()
            .filter(|s| !s.is_empty())
            .unwrap_or_else(|| "your-harness".into());
        let phase = env::var("MIR_ACTIVE_PHASE").unwrap_or_default();
        let config = root.join(format!("config/repos/{family}.json"));
        if !phase.is_empty() && config.is_file() {
            let allowed = fs::read(config)
                .ok()
                .and_then(|b| enabled_phase(&b, &phase));
            match allowed {
                Some(true) => (),
                Some(false) => warn(
                    output,
                    format!(
                        "phase {phase} is not in enabled_phases for family {family} (advisory only)"
                    ),
                ),
                None => warn(output, "enabled-phases advisory inspection failed"),
            }
        }
    }
    if enabled("MIR_TOOL_CONTRACT_REQUIRED") {
        // The enclosing hook suppresses leaf details just as the shell entry
        // does; no Python process or source marker is required.
        let exit = crate::tool_contract_hook::validate(input, &mut String::new());
        if exit != 0 {
            return Err(format!(
                "[mir CONTRACT BLOCK] tool contract validation failed (exit {exit}); inspect project-hooks tool-contract\n"
            ));
        }
    } else if enabled("MIR_TOOL_CONTRACT_LOG") {
        let present = if documents.len() != 1 {
            None
        } else {
            match tin {
                Value::Null if value.get("tool_input").is_none() => Some(false),
                Value::Object(m) => Some(m.contains_key("_mir_contract")),
                Value::Array(a) => Some(a.iter().any(|v| v == "_mir_contract")),
                Value::String(s) => Some(s.contains("_mir_contract")),
                _ => None,
            }
        };
        match present { Some(true)=>(), Some(false)=>output.push_str("[mir TC ADVISORY LOG] tool call missing _mir_contract (advisory only, not enforced)\n"), None=>warn(output,"tool-contract advisory inspection failed") }
    }
    Ok(())
}

fn python_repr(value: &Value) -> String {
    match value {
        Value::Null => "None".into(),
        Value::Bool(v) => if *v { "True" } else { "False" }.into(),
        Value::String(text) => {
            let quote = if text.contains('\'') && !text.contains('"') {
                '"'
            } else {
                '\''
            };
            let mut result = String::from(quote);
            for c in text.chars() {
                match c {
                    '\\' => result.push_str("\\\\"),
                    '\n' => result.push_str("\\n"),
                    '\r' => result.push_str("\\r"),
                    '\t' => result.push_str("\\t"),
                    c if c == quote => {
                        result.push('\\');
                        result.push(c);
                    }
                    c if c.is_control() => result.push_str(&format!("\\x{:02x}", c as u32)),
                    c => result.push(c),
                }
            }
            result.push(quote);
            result
        }
        Value::Array(items) => format!(
            "[{}]",
            items.iter().map(python_repr).collect::<Vec<_>>().join(", ")
        ),
        Value::Object(items) => format!(
            "{{{}}}",
            items
                .iter()
                .map(|(key, v)| format!(
                    "{}: {}",
                    python_repr(&Value::String(key.clone())),
                    python_repr(v)
                ))
                .collect::<Vec<_>>()
                .join(", ")
        ),
        Value::Number(number) => number.to_string(),
    }
}

fn ordered_mapping(bytes: &[u8]) -> Result<Vec<(String, Value)>, serde_json::Error> {
    struct Pairs;
    impl<'de> serde::de::Visitor<'de> for Pairs {
        type Value = Vec<(String, Value)>;
        fn expecting(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
            f.write_str("object")
        }
        fn visit_map<M: serde::de::MapAccess<'de>>(
            self,
            mut map: M,
        ) -> Result<Self::Value, M::Error> {
            let mut pairs = Vec::new();
            while let Some(pair) = map.next_entry()? {
                pairs.push(pair);
            }
            Ok(pairs)
        }
    }
    let mut deserializer = serde_json::Deserializer::from_slice(bytes);
    serde::de::Deserializer::deserialize_map(&mut deserializer, Pairs)
}

pub fn run() -> u8 {
    let root = PathBuf::from(
        env::var_os("CLAUDE_PROJECT_DIR")
            .filter(|p| !p.is_empty())
            .unwrap_or_else(|| ".".into()),
    );
    let mut input = Vec::new();
    let _ = io::stdin().read_to_end(&mut input);
    // Bash command substitution strips trailing LF before all consumers.
    while input.last() == Some(&b'\n') {
        input.pop();
    }
    input.retain(|b| *b != 0);
    let (message, code) = handoff_packet::bootstrap_enforce::enforce(&input, &root);
    if code != 0 {
        let _ = io::stderr().write_all(message.as_bytes());
        if code != 2 {
            let _ = io::stderr().write_all(block("bootstrap gate enforcement failed").as_bytes());
        }
        return 2;
    }
    let started = Instant::now();
    let mut output = String::new();
    let code = match policy(&root, &input, &mut output) {
        Ok(()) => 0,
        Err(message) => {
            output.push_str(&message);
            2
        }
    };
    let _ = io::stderr().write_all(output.as_bytes());
    crate::checkpoint::telemetry(&root, "pre-tool-use", i32::from(code), started);
    code
}

#[cfg(test)]
mod phase_tests {
    use super::{decimal_integer, enabled_phase};

    #[test]
    fn python_integer_grammar_and_normalization() {
        for (input, expected) in [
            ("  +000_12  ", "12"),
            ("\u{2003}-\u{ff11}_\u{662}\u{a0}", "-12"),
            ("-\u{1d7ce}", "0"),
            ("\u{1e5f1}", "0"),
            (
                "\t123456789012345678901234567890\n",
                "123456789012345678901234567890",
            ),
        ] {
            assert_eq!(
                decimal_integer(input).as_deref(),
                Some(expected),
                "{input:?}"
            );
        }
        for input in [
            "", " ", "+", "_1", "1_", "1__2", "+ 1", "1 2", "\u{b2}", "\u{1c}1", "1.0",
        ] {
            assert_eq!(decimal_integer(input), None, "{input:?}");
        }
    }

    #[test]
    fn config_integer_tokens_preserve_precision_and_python_equality() {
        let config = br#"{"enabled_phases":[{"phase":123456789012345678901234567890}]}"#;
        assert_eq!(
            enabled_phase(config, "+123_456789012345678901234567890"),
            Some(true)
        );
        assert_eq!(
            enabled_phase(config, "123456789012345678901234567889"),
            Some(false)
        );
        assert_eq!(
            enabled_phase(
                br#"{"enabled_phases":[{"phase":-123456789012345678901234567890}]}"#,
                "-123456789012345678901234567890"
            ),
            Some(true)
        );
        for (token, phase, expected) in [
            ("true", "1", true),
            ("2.0", "2", true),
            ("2.9", "2", false),
            ("2e1", "20", true),
            ("\"2\"", "2", false),
        ] {
            let config = format!("{{\"enabled_phases\":[{{\"phase\":{token}}}]}}");
            assert_eq!(enabled_phase(config.as_bytes(), phase), Some(expected));
        }
        assert_eq!(
            enabled_phase(br#"{"enabled_phases":[{"phase":1},{}]}"#, "1"),
            None
        );
    }
}
