//! Tool evidence and recipient accounting; never executes received code.
use crate::{
    Error, Result, SHELL, captures, code_shell_calls, has, json, lines, owner_sections, restricted,
    split, sub, tool_kind,
};
use serde_json::Value;
use std::{
    collections::{BTreeSet, HashMap},
    path::{Component, Path, PathBuf},
};

pub(crate) const BASE_PINS: &[&str] = &[
    "repository_root",
    "head",
    "mapping.identity",
    "mapping.version",
    "mapping.digest",
    "contract.identity",
    "contract.version",
    "contract.digest",
];
pub(crate) const PIN_KEY: &str = r"(?:repository_root|head|(?:mapping|contract)\.(?:identity|version|digest)|sources\[\d+\]\.(?:digest|sha256|revision))";
const NON_PIN_NAMES: &[&str] = &[
    "lifecycle",
    "temporal",
    "epistemic",
    "verification",
    "evidence",
    "unknowns",
    "pin",
    "pins",
    "provenance",
    "label",
    "reason",
    "reasons",
    "\u{c774}\u{c720}",
    "sha256",
    "revision",
];
const CITED: &str = r"(?<![\w./~:-])\.?[\w-][\w.-]*(?:/[\w.-]+)*\.[A-Za-z0-9]+(?![A-Za-z0-9_/-])";
pub(crate) type ToolCall = (String, Value);
pub(crate) type TurnTools = (Vec<ToolCall>, Vec<String>, Vec<String>);

fn field<'a>(v: &'a Value, key: &str, default: &'a str) -> Result<&'a str> {
    v.as_object()
        .ok_or(Error::Shape)?
        .get(key)
        .map_or(Ok(default), |v| v.as_str().ok_or(Error::Shape))
}
fn argument<'a>(v: &'a Value, keys: &[&str]) -> Result<&'a str> {
    let m = v.as_object().ok_or(Error::Shape)?;
    for key in keys {
        if let Some(v) = m.get(*key) {
            return v.as_str().ok_or(Error::Shape);
        }
    }
    Ok("")
}
fn full(pat: &str, text: &str, insensitive: bool) -> Result<bool> {
    has(&format!(r"\A(?:{pat})\z"), text, insensitive)
}
fn group(m: &crate::Capture, i: usize) -> &str {
    m.groups.get(i).and_then(Option::as_deref).unwrap_or("")
}
fn unique(values: impl IntoIterator<Item = String>) -> Vec<String> {
    let mut out = Vec::new();
    for v in values {
        if !out.contains(&v) {
            out.push(v);
        }
    }
    out
}

pub(crate) fn tool_calls(rows: &[Value]) -> Result<Vec<ToolCall>> {
    let mut calls = Vec::new();
    for row in rows {
        let empty = json!({});
        let kind = field(row, "type", "")?;
        if kind == "assistant" {
            let message = row.get("message").unwrap_or(&empty);
            if let Some(content) = message.get("content").and_then(Value::as_array) {
                for item in content {
                    if field(item, "type", "")? == "tool_use" {
                        calls.push((
                            field(item, "name", "")?.to_owned(),
                            item.get("input").cloned().unwrap_or(json!({})),
                        ));
                    }
                }
            }
        }
        let payload = row.get("payload").unwrap_or(&empty);
        if kind == "response_item" && field(payload, "type", "")? == "function_call" {
            let mut args = payload.get("arguments").cloned().unwrap_or(json!({}));
            if let Some(text) = args.as_str() {
                args = serde_json::from_str(text)?;
            }
            calls.push((field(payload, "name", "")?.to_owned(), args));
        } else if kind == "response_item"
            && field(payload, "type", "")? == "custom_tool_call"
            && tool_kind(field(payload, "name", "")?)? == "exec"
        {
            calls.push((
                field(payload, "name", "")?.to_owned(),
                json!({"input": field(payload, "input", "")?}),
            ));
        }
    }
    for (name, args) in calls.clone() {
        if tool_kind(&name)? == "exec" {
            calls.extend(code_shell_calls(argument(&args, &["input", "code"])?)?);
        }
    }
    Ok(calls)
}

pub(crate) fn assertion_text(text: &str) -> Result<String> {
    Ok(lines(text)
        .filter(|line| !line.trim_start().starts_with('>'))
        .collect::<Vec<_>>()
        .join("\n"))
}
pub(crate) fn pin_claims(text: &str) -> Result<Vec<(String, String)>> {
    let plain = sub(r"[*`]", &assertion_text(text)?, "")?;
    let mut claims = captures(r"(?m)(?<![\w.=-])(?:pin )?([\w.\[\]-]+)[ \t]*[=:][ \t]*(?:[^\n;:=]+:[ \t]*)?(verified-in-repo|parent-supplied|unavailable)(?![A-Za-z0-9_-])", &plain, true)?.iter().map(|m| (group(m,1).to_owned(),group(m,2).to_owned())).collect::<Vec<_>>();
    let mut parents: Vec<(usize, String)> = Vec::new();
    for line in lines(&plain) {
        if !line.trim().is_empty() {
            let indent = line.chars().count() - line.trim_start().chars().count();
            while parents.last().is_some_and(|p| indent <= p.0) {
                parents.pop();
            }
            if let Some(m) = captures(
                r"\A\s*(?:provenance|label):\s*(verified-in-repo|parent-supplied|unavailable)\s*\z",
                line,
                true,
            )?
            .first()
                && let Some(parent) = parents.last()
            {
                claims.push((parent.1.clone(), group(m, 1).to_owned()));
            }
            if let Some(m) = captures(r"\A\s*([\w.\[\]-]+):\s*\z", line, false)?.first() {
                parents.push((indent, group(m, 1).to_owned()));
            }
        }
        if !line.contains('|') {
            continue;
        }
        let cells = line
            .trim()
            .trim_matches('|')
            .split('|')
            .map(str::trim)
            .collect::<Vec<_>>();
        let mut names = Vec::new();
        let mut labels = Vec::new();
        for cell in cells {
            if full(PIN_KEY, cell, true)? {
                names.push(cell.to_owned());
            }
            if let Some(m) = captures(
                r"\A(?:verified-in-repo|parent-supplied|unavailable)(?![A-Za-z0-9_-])",
                cell,
                true,
            )?
            .first()
            {
                labels.push(group(m, 0).to_owned());
            }
        }
        if names.len() == 1 && labels.len() == 1 {
            claims.push((names.remove(0), labels.remove(0)));
        }
    }
    Ok(claims
        .into_iter()
        .filter(|(name, _)| !NON_PIN_NAMES.contains(&name.to_lowercase().as_str()))
        .collect())
}
pub(crate) fn claimed_paths(text: &str) -> Result<Vec<String>> {
    let mut plain = String::new();
    let mut end = 0;
    for m in captures(r"(?<![\w:/])([\w.-]+):([\w./-]+)", text, false)? {
        plain.push_str(&text[end..m.start]);
        // Python str.isdigit also accepts compatibility digits outside Nd.
        if full(
            r"[\d\x{b2}-\x{b3}\x{b9}\x{1369}-\x{1371}\x{19da}\x{2070}\x{2074}-\x{2079}\x{2080}-\x{2089}\x{2460}-\x{2468}\x{2474}-\x{247c}\x{2488}-\x{2490}\x{24ea}\x{24f5}-\x{24fd}\x{24ff}\x{2776}-\x{277e}\x{2780}-\x{2788}\x{278a}-\x{2792}\x{10a40}-\x{10a43}\x{10e60}-\x{10e68}\x{11052}-\x{1105a}\x{1f100}-\x{1f10a}]+",
            group(&m, 2),
            false,
        )? {
            plain.push_str(group(&m, 0));
        }
        end = m.end;
    }
    plain.push_str(&text[end..]);
    let pattern = format!(r"(?<![\w./-]){PIN_KEY}(?![\w./-])");
    let mut replaced = String::new();
    let mut end = 0;
    for m in captures(&pattern, &plain, true)? {
        replaced.push_str(&plain[end..m.start]);
        end = m.end;
    }
    replaced.push_str(&plain[end..]);
    plain = replaced;
    let mut out = Vec::new();
    for m in captures(CITED, &plain, false)? {
        let v = group(&m, 0);
        if !full(r"v?\d+(?:\.\d+)+(?:[-+][\w.-]+)?", v, true)? {
            out.push(v.to_owned());
        }
    }
    Ok(out)
}
pub(crate) fn received_data(text: &str) -> Result<Value> {
    if let Some(m) = captures(r"\b(?:handoff )?pins:\s*(?:```(?:json)?\s*)?", text, true)?.first() {
        let mut stream = serde_json::Deserializer::from_str(&text[m.end..]).into_iter::<Value>();
        if let Some(Ok(v)) = stream.next()
            && v.is_object()
        {
            return Ok(v);
        }
    }
    Ok(json!({}))
}
pub(crate) fn pin_paths(text: &str, data: &Value) -> Result<HashMap<String, String>> {
    let mut paths = HashMap::new();
    let mapping = field(data, "mapping_path", ".mir/ontology-map.json")?;
    for key in ["identity", "version", "digest"] {
        paths.insert(format!("mapping.{key}"), mapping.to_owned());
    }
    let contract = match data.get("contract_path") {
        None | Some(Value::Null) => "",
        Some(v) => v.as_str().ok_or(Error::Shape)?,
    };
    let found = captures(r#"contract_path\s*:\s*[`\"]?([^\s`\"]+)"#, text, true)?;
    let contract = if contract.is_empty() {
        found.first().map(|m| group(m, 1)).unwrap_or("")
    } else {
        contract
    };
    if !contract.is_empty() {
        for key in ["identity", "version", "digest"] {
            paths.insert(format!("contract.{key}"), contract.to_owned());
        }
    }
    if let Some(sources) = data.get("sources") {
        for (index, source) in sources.as_array().ok_or(Error::Shape)?.iter().enumerate() {
            for key in ["digest", "revision"] {
                paths.insert(
                    format!("sources[{index}].{key}"),
                    field(source, "path", "")?.to_owned(),
                );
            }
        }
    }
    Ok(paths)
}
pub(crate) fn turn_tools(event: &Value) -> Result<TurnTools> {
    let (_, rows) = crate::transcript::current_turn(event)?;
    let calls = tool_calls(&rows)?
        .into_iter()
        .map(|(name, args)| Ok((tool_kind(&name)?, args)))
        .collect::<Result<Vec<_>>>()?;
    let mut reads = Vec::new();
    let mut commands = Vec::new();
    for (name, args) in &calls {
        if ["read", "grep", "glob"].contains(&name.as_str()) {
            reads.push(argument(args, &["file_path", "path", "pattern"])?.to_owned());
        }
        if SHELL.contains(&name.as_str()) {
            commands.push(argument(args, &["command", "cmd"])?.to_owned());
        }
    }
    Ok((calls, reads, commands))
}
fn abspath(root: &Path, value: &str) -> PathBuf {
    let mut out = PathBuf::new();
    for part in root.join(value).components() {
        match part {
            Component::CurDir => {}
            Component::ParentDir => {
                out.pop();
            }
            p => out.push(p),
        }
    }
    out
}
pub(crate) fn path_referenced(
    path: &str,
    reads: &[String],
    commands: &[String],
    root: &Path,
) -> bool {
    let paths = reads
        .iter()
        .filter(|p| !p.is_empty())
        .map(|p| abspath(root, p))
        .collect::<BTreeSet<_>>();
    if Path::new(path).file_name().and_then(|p| p.to_str()) == Some(path) {
        let matches = paths
            .iter()
            .filter(|p| p.file_name().and_then(|p| p.to_str()) == Some(path))
            .count();
        return matches == 1 || (matches == 0 && commands.iter().any(|cmd| cmd.contains(path)));
    }
    paths.contains(&abspath(root, path)) || commands.iter().any(|cmd| cmd.contains(path))
}

// POSIX shlex.split with comments disabled, as used by the reference.
fn shell_words(command: &str) -> Option<Vec<String>> {
    let mut chars = command.chars().peekable();
    let mut out = Vec::new();
    let mut word = String::new();
    let mut quote = None;
    let mut started = false;
    while let Some(c) = chars.next() {
        match quote {
            Some('\'') => {
                if c == '\'' {
                    quote = None;
                } else {
                    word.push(c);
                }
            }
            Some('"') => {
                if c == '"' {
                    quote = None;
                } else if c == '\\' {
                    let next = chars.next()?;
                    if !['"', '\\'].contains(&next) {
                        word.push('\\');
                    }
                    word.push(next);
                } else {
                    word.push(c);
                }
            }
            Some(_) => return None,
            None => {
                if c == '\'' || c == '"' {
                    quote = Some(c);
                    started = true;
                } else if c == '\\' {
                    word.push(chars.next()?);
                    started = true;
                } else if [' ', '\t', '\r', '\n'].contains(&c) {
                    if started {
                        out.push(std::mem::take(&mut word));
                        started = false;
                    }
                } else {
                    word.push(c);
                    started = true;
                }
            }
        }
    }
    if quote.is_some() {
        return None;
    }
    if started {
        out.push(word);
    }
    Some(out)
}
fn relative(root: &Path, value: &str) -> Result<String> {
    let target = abspath(root, value);
    let left = root.components().collect::<Vec<_>>();
    let right = target.components().collect::<Vec<_>>();
    let same = left.iter().zip(&right).take_while(|(a, b)| a == b).count();
    let mut out = PathBuf::new();
    for _ in same..left.len() {
        out.push("..");
    }
    for p in &right[same..] {
        out.push(p);
    }
    if out.as_os_str().is_empty() {
        return Ok(".".into());
    }
    Ok(out.to_str().ok_or(Error::Shape)?.to_owned())
}
pub(crate) fn absence_defects(body: &str, calls: &[ToolCall], root: &Path) -> Result<Vec<String>> {
    let claim = concat!(
        r"\b(?:not found|does not exist|absent|missing)\s+(?:anywhere\b|(?:in|from)\s+(?:the\s+)?(?:repo|repository|codebase)\b)|",
        r"\b(?:there (?:is|are)|has) no\b[^.\n]{0,60}\bin (?:the\s+)?(?:repo|repository|codebase)\b|",
        r"(?:\uc800\uc7a5\uc18c|\ub808\ud3ec|\ucf54\ub4dc\ubca0\uc774\uc2a4)\s*(?:\uc804\uccb4)?\s*(?:\uc5d0\ub294|\uc5d0\uc11c\ub294|\uc5d0\uc11c\ub3c4|\uc5d0\ub3c4|\uc5d0\uc11c|\uc5d0)\s*(?:[^\s.]+\s+){0,2}(?:\uc5c6|\uc874\uc7ac\ud558\uc9c0\s*\uc54a|\ucc3e\uc9c0\s*\ubabb)|",
        r"\uc5b4\ub514\uc5d0\ub3c4\s*(?:\uc5c6|\uc874\uc7ac\ud558\uc9c0\s*\uc54a)"
    );
    let bounded =
        r"\b(?:within|under|searched)\b|\ubc94\uc704|\uc548\uc5d0\uc11c|\uc5d0\uc11c\ub9cc";
    let searched = r"\bsearch(?:ed|es)?\b|\bno (?:matches|hits)\b|\uac80\uc0c9|0\s*\uac74|\ubd80\uc7ac\s*(?:\ud310\ub2e8|\uc8fc\uc7a5)";
    let mut unbounded = false;
    for line in lines(&assertion_text(body)?) {
        if has(searched, line, true)? {
            continue;
        }
        for clause in split(r"(?<=[.!?])\s+|[,;|]", line)? {
            if !has(claim, &clause, true)?
                || has(
                    r"\b(?:do not|don.t|cannot) conclude\b|\uacb0\ub860[^.]*\ub0b4\ub9ac\uc9c0\s*\uc54a",
                    &clause,
                    true,
                )?
            {
                continue;
            }
            if !has(bounded, &clause, true)?
                && !has(r"(?:repo|repository|codebase)\s+[`\w./-]+/", &clause, true)?
            {
                unbounded = true;
            }
        }
    }
    if !unbounded {
        return Ok(vec![]);
    }
    let mut scopes = Vec::new();
    for (name, args) in calls {
        if ["grep", "glob"].contains(&name.as_str()) {
            let path = field(args, "path", "")?;
            let at_root = path.is_empty() || abspath(root, path) == root;
            let glob = field(args, "glob", "")?;
            if name == "glob" {
                let pattern = field(args, "pattern", "")?;
                if at_root && glob.is_empty() && ["**/*", "**"].contains(&pattern) {
                    return Ok(vec![]);
                }
                if !glob.is_empty() {
                    scopes.push(glob.to_owned());
                }
                let rel = relative(root, if path.is_empty() { "." } else { path })?;
                let joined = Path::new(&rel).join(if pattern.is_empty() {
                    "[unspecified pattern]"
                } else {
                    pattern
                });
                let scope = joined.to_str().ok_or(Error::Shape)?.replace('\\', "/");
                scopes.push(scope.strip_prefix("./").unwrap_or(&scope).to_owned());
            } else {
                if glob.is_empty() && at_root {
                    return Ok(vec![]);
                }
                scopes.push(if glob.is_empty() {
                    relative(root, path)?
                } else {
                    glob.to_owned()
                });
            }
        } else if SHELL.contains(&name.as_str()) {
            let command = argument(args, &["command", "cmd"])?;
            let Some(words) = shell_words(command) else {
                continue;
            };
            if words.is_empty() || !["rg", "grep"].contains(&words[0].as_str()) {
                continue;
            }
            if words[0] == "grep"
                && !words[1..]
                    .iter()
                    .any(|w| ["-r", "-R", "--recursive"].contains(&w.as_str()))
            {
                continue;
            }
            scopes.push(command.to_owned());
            if words[1..].iter().any(|w| {
                [
                    "-g", "--glob", "-e", "-f", "--file", "--regexp", ";", "|", "&&",
                ]
                .contains(&w.as_str())
                    || w.starts_with("--glob=")
                    || w.starts_with("--include=")
                    || w.starts_with("--exclude=")
            }) {
                continue;
            }
            let operands = words[1..]
                .iter()
                .filter(|w| !w.starts_with('-'))
                .collect::<Vec<_>>();
            if operands.iter().skip(1).any(|p| abspath(root, p) == root) {
                return Ok(vec![]);
            }
        }
    }
    if scopes.is_empty() {
        scopes.push("no searches".into());
    }
    Ok(vec![format!(
        "repository-wide absence claimed after searches limited to: {}; name the searched scope or search the repository root",
        unique(scopes).join(", ")
    )])
}

pub(crate) fn verification_defects(
    text: &str,
    body: &str,
    event: &Value,
    no_commands: bool,
) -> Result<Vec<String>> {
    let paths = pin_paths(text, &received_data(text)?)?;
    let (calls, reads, commands) = turn_tools(event)?;
    let root = crate::supply::repository_root(event)?;
    let mut defects = absence_defects(body, &calls, &root)?;
    let plain = sub(r"[*`]", body, "")?;
    let command_tools = calls
        .iter()
        .map(|(name, _)| name)
        .filter(|name| SHELL.contains(&name.as_str()))
        .cloned()
        .collect::<BTreeSet<_>>();
    if no_commands && !command_tools.is_empty() {
        let mut stated = false;
        let names = command_tools
            .iter()
            .map(|name| regex::escape(name))
            .collect::<Vec<_>>()
            .join("|");
        for line in lines(&plain) {
            if has(
                r"compliance failure|\uc9c0\uc2dc\s*\uc704\ubc18|\uc900\uc218\s*\uc2e4\ud328",
                line,
                true,
            )? && has(
                &format!(
                    r"interpreter|shell|command|\uc778\ud130\ud504\ub9ac\ud130|\uba85\ub839|{names}"
                ),
                line,
                true,
            )? {
                stated = true;
                break;
            }
        }
        if !stated {
            defects.push(format!(
                "command-ban compliance failure must be stated for tool calls: {}",
                command_tools.into_iter().collect::<Vec<_>>().join(", ")
            ));
        }
    }
    let mut verified_paths = BTreeSet::new();
    let claims = pin_claims(&plain)?;
    for (name, label) in &claims {
        if label.to_lowercase() != "verified-in-repo" {
            continue;
        }
        if name == "repository_root" {
            let root_string = root.to_str().ok_or(Error::Shape)?;
            let referenced = reads
                .iter()
                .filter(|v| !v.is_empty())
                .any(|v| abspath(&root, v).starts_with(&root))
                || (!no_commands && {
                    let mut found = false;
                    for command in &commands {
                        if command.contains(root_string)
                            || has(r"\bmapping\s+--handoff\b", command, false)?
                        {
                            found = true;
                        }
                    }
                    found
                });
            if !referenced {
                defects.push(format!(
                    "verified-in-repo pin lacks this-turn tool reference: {name}"
                ));
            }
            continue;
        }
        let mut path = paths.get(name).cloned();
        let line = lines(&plain)
            .find(|line| line.contains(name) && line.to_lowercase().contains("verified-in-repo"))
            .unwrap_or("");
        let explicit = claimed_paths(line)?
            .into_iter()
            .filter(|v| v != name)
            .collect::<Vec<_>>();
        if ["contract.identity", "contract.version"].contains(&name.as_str()) {
            let mapping = paths.get("mapping.identity").ok_or(Error::Shape)?;
            if claimed_paths(&plain)?.contains(mapping) {
                path = Some(mapping.clone());
            }
        }
        if path.is_none() && !explicit.is_empty() {
            path = explicit.first().cloned();
        }
        if no_commands {
            if name.ends_with(".digest") || name.ends_with(".sha256") {
                defects.push(format!("verified-in-repo digest needs a this-turn computation; a value read from a file is parent-supplied or unchecked: {name}"));
                continue;
            }
            let mut pin_reads = reads.clone();
            if name == "head" {
                path = Some(".git/HEAD".into());
                pin_reads = Vec::new();
                for (tool, args) in &calls {
                    if tool == "read" {
                        pin_reads.push(argument(args, &["file_path", "path"])?.to_owned());
                    }
                }
            }
            if !path
                .as_ref()
                .is_some_and(|p| path_referenced(p, &pin_reads, &[], &root))
            {
                defects.push(format!(
                    "verified-in-repo pin lacks this-turn tool reference: {name}"
                ));
            }
            continue;
        }
        let typed = name == "head"
            || [".digest", ".revision", ".sha256"]
                .iter()
                .any(|s| name.ends_with(s));
        let mut computed = false;
        for command in &commands {
            let runner = has(r"\bmapping\s+--handoff\b", command, false)?;
            let referenced = path.as_ref().is_some_and(|p| command.contains(p));
            if (runner && (BASE_PINS.contains(&name.as_str()) || referenced))
                || (name == "head" && has(r"\bgit\s+rev-parse\b", command, false)?)
                || (referenced
                    && name.ends_with(".revision")
                    && has(r"\bgit\s+(?:log|rev-list)\b", command, false)?)
                || (referenced
                    && (name.ends_with(".digest") || name.ends_with(".sha256"))
                    && has(
                        r"\bsha256sum\b|\bshasum\s+[^\n;|]*?(?:-a\s*256|--algorithm[= ]256)\b|\bopenssl\s+dgst\s+[^\n;|]*?-sha256\b|\bhashlib\.sha256\s*\(",
                        command,
                        false,
                    )?)
            {
                computed = true;
            }
        }
        if typed && !computed {
            defects.push(format!(
                "verified-in-repo pin lacks this-turn computation: {name}"
            ));
        } else if !typed && let Some(path) = path {
            verified_paths.insert(path);
        }
    }
    let names = claims.iter().map(|(name, _)| name).collect::<BTreeSet<_>>();
    for line in lines(&assertion_text(&plain)?) {
        if line.to_lowercase().contains("verified-in-repo") {
            for path in claimed_paths(line)? {
                if !names.contains(&path) && !full(PIN_KEY, &path, true)? {
                    verified_paths.insert(path);
                }
            }
        }
    }
    for path in verified_paths {
        let referenced = path_referenced(
            &path,
            &reads,
            if no_commands { &[] } else { &commands },
            &root,
        ) || (!no_commands
            && path == ".mir/ontology-map.json"
            && commands.iter().any(|cmd| cmd.contains("mapping --handoff")));
        if !referenced {
            defects.push(format!(
                "verified-in-repo path lacks this-turn tool reference: {path}"
            ));
        }
    }
    Ok(defects)
}

pub(crate) fn abbreviated_hex(body: &str) -> Result<Vec<String>> {
    let mut defects = Vec::new();
    let plain = sub(r##"[*`\"#]"##, body, "")?;
    let pattern = r"(?<![\w.])([\w.\[\]-]*(?:head|revision|commit|digest|sha256))\s*(?:[:=@]|is)?\s*([0-9a-f]{7,39})(?![\w])|([\w./-]+)@([0-9a-f]{7,39})(?![\w])";
    let mut columns = Vec::new();
    for line in lines(&plain) {
        for m in captures(pattern, line, true)? {
            let name = if group(&m, 1).is_empty() {
                group(&m, 3)
            } else {
                group(&m, 1)
            };
            let inventory = format!(
                r"(?<![\w.])(?:pin )?{}\s*[=:]\s*abbreviated\b",
                regex::escape(name)
            );
            if !has(r"\babbreviated\b", line, true)? && !has(&inventory, &plain, true)? {
                defects.push(format!("abbreviated hex value: {name}"));
            }
        }
        if !line.contains('|') {
            columns.clear();
            continue;
        }
        let cells = line
            .trim()
            .trim_matches('|')
            .split('|')
            .map(str::trim)
            .collect::<Vec<_>>();
        let mut found = Vec::new();
        for (i, cell) in cells.iter().enumerate() {
            if has(r"head|revision|commit|digest|sha256", cell, true)? {
                found.push(i);
            }
        }
        if !found.is_empty() {
            columns = found;
        } else if !has(r"\babbreviated\b", line, true)? {
            for i in &columns {
                if let Some(cell) = cells.get(*i)
                    && full(r"[0-9a-f]{7,39}", cell, true)?
                {
                    defects.push("abbreviated hex value in pins table".into());
                }
            }
        }
    }
    Ok(defects)
}

pub(crate) fn no_command_check(prompt: &str, body: &str, event: &Value) -> Result<Vec<String>> {
    let mut defects = crate::stop::authority_defects(body, &owner_sections(prompt)?)?;
    defects.extend(abbreviated_hex(body)?);
    defects.extend(verification_defects(body, body, event, true)?);
    defects.extend(crate::stop::namespace_defects(
        body,
        &crate::supply::repository_root(event)?,
    )?);
    Ok(defects)
}
pub(crate) fn recipient_check(prompt: &str, body: &str, event: &Value) -> Result<Vec<String>> {
    let mut defects =
        crate::stop::namespace_defects(body, &crate::supply::repository_root(event)?)?;
    let data = received_data(prompt)?;
    let mut names = BASE_PINS
        .iter()
        .map(|s| (*s).to_owned())
        .collect::<Vec<_>>();
    if let Some(inventory) = data.get("pin_inventory") {
        for entry in inventory.as_array().ok_or(Error::Shape)? {
            names.push(field(entry, "pin", "")?.to_owned());
        }
    }
    if let Some(sources) = data.get("sources") {
        for (index, _) in sources.as_array().ok_or(Error::Shape)?.iter().enumerate() {
            names.extend([
                format!("sources[{index}].digest"),
                format!("sources[{index}].revision"),
            ]);
        }
    }
    names.extend(pin_claims(prompt)?.into_iter().map(|(name, _)| name));
    for m in captures(r"\bpin\s+([\w.\[\]-]+)\s*[=:]", prompt, true)? {
        let name = group(&m, 1);
        if !NON_PIN_NAMES.contains(&name.to_lowercase().as_str()) {
            names.push(name.to_owned());
        }
    }
    if data.as_object().is_some_and(|m| m.is_empty()) {
        for line in lines(prompt) {
            if let Some(m) =
                captures(r"^\s*(?:[-*]\s*)?`?([\w./\[\]-]+)`?\s*:", line, false)?.first()
            {
                let name = group(m, 1);
                if !NON_PIN_NAMES.contains(&name.to_lowercase().as_str())
                    && has(r"sha256[^\n]*[0-9a-f]{64}", line, true)?
                {
                    names.push(name.to_owned());
                }
            }
        }
    }
    let labels = pin_claims(body)?
        .into_iter()
        .map(|(name, label)| (name, label.to_lowercase()))
        .collect::<HashMap<_, _>>();
    for name in unique(names) {
        if !labels.contains_key(&name) {
            defects.push(format!("missing recipient pin label: {name}"));
        }
    }
    let restricted = restricted(prompt)?;
    defects.extend(verification_defects(prompt, body, event, restricted)?);
    let plain = sub(r"[*`]", body, "")?;
    let (calls, reads, _) = turn_tools(event)?;
    if !restricted
        && calls.is_empty()
        && !has(
            r"no (?:local (?:check|verification)|(?:local )?tools?)[^\n]*|(?:not|could not|unable to) verif[^\n]*locally|(?:\ub85c\uceec|\ub3c4\uad6c)[^\n]*(?:\uc54a|\ubabb|\uc5c6|\uc548|\ud558\uc9c0)",
            &plain,
            true,
        )?
    {
        defects.push("no local check and no stated limitation".into());
    }
    if restricted
        && !reads.iter().any(|s| !s.is_empty())
        && !calls.iter().any(|(name, _)| SHELL.contains(&name.as_str()))
    {
        let english = has(
            r"commands?[^\n]*(?:forbidden|prohibited|not (?:run|allowed))",
            &plain,
            true,
        )? && has(
            r"no (?:non-command )?reader[^\n]*(?:used|available)",
            &plain,
            true,
        )?;
        let korean = has(
            concat!(
                r"\uba85\ub839[^.\n]*(?:\uae08\uc9c0|\uc2e4\ud589\ud558\uc9c0|\uc2e4\ud589\s*\uc5c6\uc774)|",
                r"\uba85\ub839[^.\n]*(?:\uc2e4\ud589|\uc218\ud589)[^.\n]*\ud558\uc9c0\s*\uc54a|",
                r"(?:\uc15c|\uc178|shell|\uc778\ud130\ud504\ub9ac\ud130)[^.\n]*(?:\ud638\ucd9c|\uc2e4\ud589)\ud558\uc9c0\s*\uc54a"
            ),
            &plain,
            true,
        )? && has(
            r"(?:\uc77d\uae30\s*\ub3c4\uad6c|\ub9ac\ub354|reader|(?:\ud30c\uc77c|\uc18c\uc2a4|\ud14d\uc2a4\ud2b8)[^.\n]*\uc77d[^.\n]*\ub3c4\uad6c)[^.\n]*(?:\uc5c6|\uc0ac\uc6a9\ud558\uc9c0|\ubabb)",
            &plain,
            true,
        )?;
        if !english && !korean {
            defects.push(
                "state commands forbidden and no non-command reader was used/available".into(),
            );
        }
    }
    Ok(defects)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reference_pin_and_path_claims() -> Result<()> {
        assert_eq!(
            pin_claims(
                "head: verified-in-repo\nmapping:\n  digest:\n    provenance: parent-supplied"
            )?,
            vec![
                ("head".into(), "verified-in-repo".into()),
                ("digest".into(), "parent-supplied".into())
            ]
        );
        assert_eq!(
            pin_claims(
                "| mapping.digest | verified-in-repo |\n> head: unavailable\nreason: unavailable"
            )?,
            vec![("mapping.digest".into(), "verified-in-repo".into())]
        );
        assert_eq!(
            claimed_paths(
                "mapping.digest v1.2.3 repo:file.py src/file.py file.md:12 head: verified-in-repo"
            )?,
            vec!["src/file.py", "file.md"]
        );
        assert_eq!(
            abbreviated_hex("head abcdef0\n| digest |\n| abcdef0 |")?,
            vec![
                "abbreviated hex value: head",
                "abbreviated hex value in pins table"
            ]
        );
        assert!(abbreviated_hex("head abcdef0\npin head: abbreviated")?.is_empty());
        Ok(())
    }

    #[test]
    fn reference_tools_and_absence_scopes() -> Result<()> {
        assert_eq!(
            shell_words("rg 'two words' \"escaped\\\"quote\" src/"),
            Some(vec![
                "rg".into(),
                "two words".into(),
                "escaped\"quote".into(),
                "src/".into()
            ])
        );
        assert_eq!(shell_words("rg 'unfinished"), None);
        assert_eq!(
            shell_words("rg \"keep\\q\" src/"),
            Some(vec!["rg".into(), "keep\\q".into(), "src/".into()])
        );
        let calls = tool_calls(&[
            json!({"type":"response_item","payload":{"type":"custom_tool_call","name":"functions.exec","input":"await tools.exec_command({cmd: 'rg token src/'})"}}),
        ])?;
        assert_eq!(calls.len(), 2);
        assert_eq!(
            calls[1],
            ("exec_command".into(), json!({"command":"rg token src/"}))
        );
        let root = Path::new("/repo");
        assert_eq!(
            absence_defects("It does not exist in the repository.", &calls, root)?,
            vec![
                "repository-wide absence claimed after searches limited to: rg token src/; name the searched scope or search the repository root"
            ]
        );
        assert!(
            absence_defects(
                "It does not exist in the repository.",
                &[("grep".into(), json!({"path":"."}))],
                root
            )?
            .is_empty()
        );
        assert!(
            absence_defects(
                "It does not exist in the repository under src/.",
                &calls,
                root
            )?
            .is_empty()
        );
        assert!(!path_referenced(
            "a.py",
            &["src/a.py".into(), "lib/a.py".into()],
            &["cat a.py".into()],
            root
        ));
        Ok(())
    }

    #[test]
    fn reference_received_json_and_unicode_labels() -> Result<()> {
        assert_eq!(claimed_paths("notes.md:²")?, vec!["notes.md"]);
        assert_eq!(
            received_data("Pins: ```json\n{\"contract_path\":null} trailing")?,
            json!({"contract_path":null})
        );
        assert_eq!(
            pin_paths(
                "contract_path: `contract.json`",
                &json!({"contract_path":null})
            )?
            .get("contract.digest")
            .map(String::as_str),
            Some("contract.json")
        );
        assert_eq!(
            pin_claims("mapp\u{131}ng.d\u{130}gest: ver\u{131}f\u{130}ed-in-repo")?,
            vec![(
                "mapp\u{131}ng.d\u{130}gest".into(),
                "ver\u{131}f\u{130}ed-in-repo".into()
            )]
        );
        Ok(())
    }

    #[test]
    fn reference_checker_accounting() -> Result<()> {
        let cwd = Path::new(env!("CARGO_MANIFEST_DIR"));
        let transcript = cwd
            .join("target")
            .join(format!("stop-tools-unit-{}.jsonl", std::process::id()));
        std::fs::write(
            &transcript,
            b"{\"type\":\"user\",\"message\":{\"content\":\"Review\"}}\n",
        )?;
        let event = json!({"cwd":cwd,"transcript_path":transcript});
        let verified = verification_defects("", "mapping.digest: verified-in-repo", &event, false);
        let no_command = no_command_check(
            "Commands are forbidden.",
            "mapping.digest: verified-in-repo",
            &event,
        );
        let recipient = recipient_check(
            "Pins: {\"pin_inventory\":[{\"pin\":\"extra\"}]}",
            "No local tools used.",
            &event,
        );
        std::fs::remove_file(transcript)?;
        assert_eq!(
            verified?,
            vec!["verified-in-repo pin lacks this-turn computation: mapping.digest"]
        );
        assert!(no_command?.contains(&"verified-in-repo digest needs a this-turn computation; a value read from a file is parent-supplied or unchecked: mapping.digest".into()));
        assert!(recipient?.contains(&"missing recipient pin label: extra".into()));
        Ok(())
    }
}
