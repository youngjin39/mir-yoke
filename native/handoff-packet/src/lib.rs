//! Native PreToolUse; unknown external JSON fields are accepted like Python.
#![forbid(unsafe_code)]
#![cfg_attr(
    not(test),
    deny(clippy::unwrap_used, clippy::expect_used, clippy::panic)
)]
mod patterns;
mod python_text;
mod transcript;
use patterns as p;
use serde_json::{Value, json};
use std::{cell::RefCell, collections::HashMap, rc::Rc};
pub const LIMIT: usize = 1024 * 1024;
#[derive(Debug)]
pub enum Error {
    Io(std::io::Error),
    Json(serde_json::Error),
    Regex(regex::Error),
    Fancy(Box<fancy_regex::Error>),
    Shape,
}
pub type Result<T> = std::result::Result<T, Error>;
impl From<std::io::Error> for Error {
    fn from(e: std::io::Error) -> Self {
        Self::Io(e)
    }
}
impl From<serde_json::Error> for Error {
    fn from(e: serde_json::Error) -> Self {
        Self::Json(e)
    }
}
impl From<regex::Error> for Error {
    fn from(e: regex::Error) -> Self {
        Self::Regex(e)
    }
}
impl From<fancy_regex::Error> for Error {
    fn from(e: fancy_regex::Error) -> Self {
        Self::Fancy(Box::new(e))
    }
}
enum Pattern {
    Regular(regex::Regex),
    Fancy(fancy_regex::Regex),
}
thread_local! { static CACHE: RefCell<HashMap<(String,bool,bool), Rc<Pattern>>> = RefCell::new(HashMap::new()); }
// Python word boundaries differ from Rust's combining-mark-inclusive boundaries.
// Their explicit look-around requires fancy-regex; plain patterns use regex.
fn pattern(source: &str, insensitive: bool, ascii: bool) -> Result<Rc<Pattern>> {
    let key = (source.to_owned(), insensitive, ascii);
    // ASCII haystacks have exactly this Python word membership. Unicode text
    // keeps the pinned full table and a separate cache entry.
    let word = if ascii {
        "a-zA-Z0-9_"
    } else {
        python_text::WORD
    };
    if let Some(p) = CACHE.with(|c| c.borrow().get(&key).cloned()) {
        return Ok(p);
    }
    let mut out = if insensitive {
        "(?i)".to_owned()
    } else {
        String::new()
    };
    let chars: Vec<char> = source.chars().collect();
    let mut i = 0;
    let mut class = false;
    while i < chars.len() {
        let ch = chars[i];
        if ch == '\\' && i + 1 < chars.len() {
            i += 1;
            match chars[i] {
                'w' => {
                    if class {
                        out.push_str(word);
                    } else {
                        out.push('[');
                        out.push_str(word);
                        out.push(']');
                    }
                }
                'b' if !class => {
                    let w = format!("[{word}]");
                    out.push_str(&format!("(?:(?<!{w})(?={w})|(?<={w})(?!{w}))"));
                }
                's' => {
                    if class {
                        out.push_str("\\s\\x1c-\\x1f");
                    } else {
                        out.push_str("[\\s\\x1c-\\x1f]");
                    }
                }
                'S' => out.push_str("[^\\s\\x1c-\\x1f]"),
                'u' => {
                    out.push_str("\\x{");
                    for _ in 0..4 {
                        i += 1;
                        out.push(*chars.get(i).ok_or(Error::Shape)?);
                    }
                    out.push('}');
                }
                c => {
                    out.push('\\');
                    out.push(c);
                }
            }
        } else {
            if ch == '[' {
                class = true;
            }
            if ch == ']' {
                class = false;
            }
            if insensitive && !class && matches!(ch, 'i' | 'I') {
                out.push_str("[iİı]");
            } else {
                out.push(ch);
            }
            if insensitive
                && class
                && matches!(
                    (
                        chars.get(i.wrapping_sub(2)),
                        chars.get(i.wrapping_sub(1)),
                        ch
                    ),
                    (Some('A'), Some('-'), 'Z') | (Some('a'), Some('-'), 'z')
                )
            {
                out.push_str("İıſK");
            }
        }
        i += 1;
    }
    let compiled = if out.contains("(?=")
        || out.contains("(?!")
        || out.contains("(?<=")
        || out.contains("(?<!")
    {
        Pattern::Fancy(
            fancy_regex::RegexBuilder::new(&out)
                .backtrack_limit(LIMIT * 64)
                .build()?,
        )
    } else {
        Pattern::Regular(regex::Regex::new(&out)?)
    };
    let compiled = Rc::new(compiled);
    CACHE.with(|c| c.borrow_mut().insert(key, compiled.clone()));
    Ok(compiled)
}
struct Capture {
    start: usize,
    end: usize,
    groups: Vec<Option<String>>,
}
fn captures(source: &str, text: &str, insensitive: bool) -> Result<Vec<Capture>> {
    let pat = pattern(source, insensitive, text.is_ascii())?;
    match pat.as_ref() {
        Pattern::Regular(re) => Ok(re
            .captures_iter(text)
            .map(|c| Capture {
                start: c.get(0).map_or(0, |m| m.start()),
                end: c.get(0).map_or(0, |m| m.end()),
                groups: c.iter().map(|m| m.map(|m| m.as_str().to_owned())).collect(),
            })
            .collect()),
        Pattern::Fancy(re) => re
            .captures_iter(text)
            .map(|c| {
                let c = c?;
                Ok(Capture {
                    start: c.get(0).map_or(0, |m| m.start()),
                    end: c.get(0).map_or(0, |m| m.end()),
                    groups: c.iter().map(|m| m.map(|m| m.as_str().to_owned())).collect(),
                })
            })
            .collect(),
    }
}
fn has(pat: &str, text: &str, insensitive: bool) -> Result<bool> {
    match pattern(pat, insensitive, text.is_ascii())?.as_ref() {
        Pattern::Regular(re) => Ok(re.is_match(text)),
        Pattern::Fancy(re) => Ok(re.is_match(text)?),
    }
}
fn sub(pat: &str, text: &str, replacement: &str) -> Result<String> {
    let mut out = String::new();
    let mut end = 0;
    for m in captures(pat, text, false)? {
        out.push_str(&text[end..m.start]);
        out.push_str(replacement);
        end = m.end;
    }
    out.push_str(&text[end..]);
    Ok(out)
}
fn split(pat: &str, text: &str) -> Result<Vec<String>> {
    let mut out = Vec::new();
    let mut end = 0;
    for m in captures(pat, text, false)? {
        out.push(text[end..m.start].to_owned());
        end = m.end;
    }
    out.push(text[end..].to_owned());
    Ok(out)
}
fn lines(s: &str) -> impl Iterator<Item = &str> {
    let mut result = Vec::new();
    let mut start = 0;
    let mut iter = s.char_indices().peekable();
    while let Some((i, c)) = iter.next() {
        if matches!(
            c,
            '\n' | '\r'
                | '\u{b}'
                | '\u{c}'
                | '\u{1c}'
                | '\u{1d}'
                | '\u{1e}'
                | '\u{85}'
                | '\u{2028}'
                | '\u{2029}'
        ) {
            result.push(&s[start..i]);
            start = i + c.len_utf8();
            if c == '\r' && iter.peek().is_some_and(|(_, c)| *c == '\n') {
                iter.next();
                start += 1;
            }
        }
    }
    if start < s.len() {
        result.push(&s[start..]);
    }
    result.into_iter()
}
fn lower(s: &str) -> String {
    s.to_lowercase()
}
fn normalized(s: &str) -> Result<String> {
    Ok(captures(r"\w+", &python_text::casefold(s), false)?
        .into_iter()
        .filter_map(|m| m.groups.into_iter().next().flatten())
        .collect::<Vec<_>>()
        .join(" "))
}
pub fn detect(prompt: &str) -> Result<bool> {
    let text = sub(p::DETECT[0], prompt, "")?;
    // Every positive branch needs one of these contiguous literals. Use lower
    // exactly like the detector, rather than regex IGNORECASE or casefold.
    let lowered = lower(&text);
    if ![
        "agent",
        "codex",
        "claude",
        "\u{c5d0}\u{c774}\u{c804}\u{d2b8}",
    ]
    .iter()
    .any(|s| lowered.contains(s))
    {
        return Ok(false);
    }
    for line in lines(&text) {
        if line.trim_start().starts_with('>') {
            continue;
        }
        let line = lower(line.trim());
        if has(p::DETECT[1], &line, false)? || has(p::DETECT[2], &line, false)? {
            continue;
        }
        for index in [5, 6, 3, 4] {
            if has(p::DETECT[index], &line, false)? {
                return Ok(true);
            }
        }
    }
    Ok(false)
}
pub fn recipient(prompt: &str) -> Result<bool> {
    if detect(prompt)? {
        return Ok(false);
    }
    let plain = sub(p::RECIPIENT[0], prompt, "")?;
    // All target branches require qualified target or the Korean target word, after stripping
    // markup. Include Python IGNORECASE's extra ASCII-letter folds. Whitespace
    // stays untouched: the English phrase requires a literal space.
    let folded: String = plain
        .chars()
        .map(|c| match c {
            'İ' | 'ı' => 'i',
            'ſ' => 's',
            'K' => 'k',
            c => c.to_ascii_lowercase(),
        })
        .collect();
    if !folded.contains("qualified target") && !folded.contains("\u{b300}\u{c0c1}") {
        return Ok(false);
    }
    let rows: Vec<_> = lines(&plain).collect();
    let label = format!(
        r"^\s*(?:#{{1,6}}\s+(?:\d+[.)]\s*)?{}|(?:[-+]\s*)?{}\s*(?::|$))",
        p::TARGET_NAME,
        p::TARGET_NAME
    );
    let table = format!(
        r"^\s*\|\s*(?:{}|\x{{c815}}\x{{addc}}\x{{d654}}\s+\x{{b300}}\x{{c0c1}})\s*\|[^\n]*[\w.-]+:[\w./-]+",
        p::TARGET_NAME
    );
    let mut target = false;
    for (i, line) in rows.iter().enumerate() {
        if has(&table, line, true)?
            || (has(&label, line, true)?
                && has(
                    p::RECIPIENT[2],
                    &rows[i..(i + 4).min(rows.len())].join("\n"),
                    false,
                )?)
        {
            target = true;
            break;
        }
    }
    let mut fields = 0;
    for pat in [
        r"\b(?:status axes|lifecycle|temporal|epistemic|verification)\b|\x{c0c1}\x{d0dc}",
        r"\bpins\b|\x{d540}",
        r"\bunknowns\b|\x{bbf8}\x{d655}\x{c778}",
        r"\bmay(?:[ -]not)?\s*:|\bauthority\b|\x{d5c8}\x{c6a9}|\x{ae08}\x{c9c0}",
    ] {
        fields += usize::from(has(pat, &plain, true)?);
    }
    Ok(target && (fields >= 2 || has(p::RECIPIENT[1], &plain, true)?))
}
#[derive(Debug, Default)]
pub struct Owner {
    pub may: String,
    pub may_not: String,
    pub sources: String,
    pub excluded: Vec<String>,
    pub explicit_authority: bool,
}
pub fn owner_sections(prompt: &str) -> Result<Owner> {
    let mut values: [Vec<String>; 4] = Default::default();
    let mut active = None;
    let mut fenced = false;
    let mut explicit = false;
    let mut excluded = Vec::new();
    for line in lines(prompt) {
        if line.trim_start().starts_with("```") || line.trim_start().starts_with("~~~") {
            fenced = !fenced;
            active = None;
            continue;
        }
        if fenced || line.trim_start().starts_with('>') {
            continue;
        }
        for literal in captures(p::QUOTED, line, false)? {
            if (has(p::OWNER_SECTIONS[0], &line[..literal.start], true)?
                || has(
                    &format!("^(?:{})", p::OWNER_SECTIONS[1]),
                    &line[literal.end..],
                    false,
                )?)
                && let Some(value) = literal.groups.into_iter().skip(1).flatten().next()
            {
                excluded.push(value);
            }
        }
        for literal in captures(p::UNQUOTED_EXCLUSION, &sub(p::QUOTED, line, " ")?, false)? {
            if let Some(value) = literal.groups.into_iter().skip(1).flatten().next() {
                excluded.push(value);
            }
        }
        if let Some(m) = captures(p::LABEL, line, true)?.first() {
            let label = lower(m.groups[1].as_deref().ok_or(Error::Shape)?);
            let index = match label.as_str() {
                "may" => 0,
                "may not" | "may-not" | "not read" | "protected" => 1,
                "sources" => 2,
                "exclude" | "do not forward" => 3,
                _ => return Err(Error::Shape),
            };
            active = Some(index);
            if index < 2 {
                explicit = true;
            }
            if let Some(value) = m.groups[2].as_ref().filter(|s| !s.is_empty()) {
                values[index].push(value.clone());
            }
        } else if active.is_some() && has(p::OWNER_SECTIONS[2], line, false)? {
            if let Some(index) = active {
                values[index].push(line.to_owned());
            }
        } else {
            active = None;
            for sentence in split(p::OWNER_SECTIONS[3], line)? {
                if has(p::PROHIBITION, &sentence, true)? {
                    values[1].push(sentence.trim().to_owned());
                }
            }
        }
    }
    let mut all = Vec::new();
    for line in &values[3] {
        for item in split(p::OWNER_SECTIONS[4], line)? {
            if !item.trim().is_empty() {
                all.push(item.trim().trim_matches('`').to_owned());
            }
        }
    }
    all.extend(excluded);
    let mut unique = Vec::new();
    for item in all {
        if !unique.contains(&item) {
            unique.push(item);
        }
    }
    Ok(Owner {
        may: values[0].join("\n"),
        may_not: values[1].join("\n"),
        sources: values[2].join("\n"),
        excluded: unique,
        explicit_authority: explicit,
    })
}
pub fn restricted(prompt: &str) -> Result<bool> {
    let owner = owner_sections(prompt)?;
    for clause in split(p::RESTRICTED[0], &sub(p::QUOTED, &owner.may_not, " ")?)? {
        let deny = normalized(&clause)?;
        if has(p::RESTRICTED[1], &deny, false)? {
            continue;
        }
        if has(p::RESTRICTED[2], &deny, false)?
            || has(p::RESTRICTED[3], &python_text::casefold(&clause), false)?
            || has(p::RESTRICTED[4], &clause, false)?
        {
            return Ok(true);
        }
    }
    Ok(false)
}
pub fn files_restricted(owner: &Owner) -> Result<bool> {
    for clause in split(
        p::FILES_RESTRICTED[0],
        &sub(p::QUOTED, &owner.may_not, " ")?,
    )? {
        let deny = normalized(&clause)?;
        if !has(p::FILES_RESTRICTED[1], &deny, false)? && has(p::FILES_RESTRICTED[2], &deny, false)?
        {
            return Ok(true);
        }
    }
    Ok(false)
}
const SHELL: &[&str] = &[
    "bash",
    "shell",
    "shell_command",
    "exec_command",
    "js",
    "js_reset",
    "node_repl",
    "python",
    "python_repl",
    "js_repl",
    "javascript_repl",
];
const WRITE: &[&str] = &["write", "edit", "multiedit", "notebookedit", "apply_patch"];
pub fn tool_kind(name: &str) -> Result<String> {
    let kind = lower(name.rsplit('.').next().ok_or(Error::Shape)?);
    Ok(captures(p::TOOL_KIND[0], &kind, false)?
        .first()
        .and_then(|m| m.groups[1].clone())
        .unwrap_or(kind))
}
pub fn code_shell_calls(code: &str) -> Result<Vec<(String, Value)>> {
    let token = r#"//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`|[\w$]+|[^\s]"#;
    let tokens: Vec<String> = captures(token, code, false)?
        .into_iter()
        .filter_map(|m| m.groups.into_iter().next().flatten())
        .filter(|s| !s.starts_with("//") && !s.starts_with("/*"))
        .collect();
    let mut calls = Vec::new();
    for i in 0..tokens.len().saturating_sub(3) {
        if tokens[i] != "tools"
            || tokens[i + 1] != "."
            || !SHELL.contains(&tool_kind(&tokens[i + 2])?.as_str())
            || tokens[i + 3] != "("
        {
            continue;
        }
        let mut args = json!({});
        if tokens.get(i + 4).map(String::as_str) == Some("{") {
            let mut depth = 1;
            for j in i + 5..tokens.len().saturating_sub(3) {
                if tokens[j] == "}" {
                    depth -= 1;
                } else if tokens[j] == "{" {
                    depth += 1;
                }
                if depth == 0 {
                    break;
                }
                if depth != 1
                    || !["cmd", "command"].contains(&tokens[j].trim_matches(['\'', '"']))
                    || tokens[j + 1] != ":"
                    || ![",", "}"].contains(&tokens[j + 3].as_str())
                {
                    continue;
                }
                let literal = &tokens[j + 2];
                if !literal.starts_with(['\'', '"', '`']) || literal.contains("${") {
                    continue;
                }
                let inner = literal
                    .get(1..literal.len().saturating_sub(1))
                    .unwrap_or("");
                let mut command = String::new();
                let mut end = 0;
                for m in captures(p::CODE_SHELL_CALLS[0], inner, false)? {
                    command.push_str(&inner[end..m.start]);
                    let v = m.groups[1].as_deref().ok_or(Error::Shape)?;
                    if (v.starts_with('u') || v.starts_with('x')) && v.len() > 1 {
                        let n = u32::from_str_radix(&v[1..], 16).map_err(|_| Error::Shape)?;
                        // Lone UTF-16 surrogates cannot inhabit Rust strings. The command
                        // is never emitted or executed here; retain call detection.
                        command.push(char::from_u32(n).unwrap_or(char::REPLACEMENT_CHARACTER));
                    } else {
                        command.push_str(match v {
                            "n" => "\n",
                            "r" => "\r",
                            "t" => "\t",
                            "b" => "\u{8}",
                            "f" => "\u{c}",
                            "v" => "\u{b}",
                            "\n" | "\r\n" => "",
                            other => other,
                        });
                    }
                    end = m.end;
                }
                command.push_str(&inner[end..]);
                args["command"] = Value::String(command);
            }
        }
        calls.push((tokens[i + 2].clone(), args));
    }
    Ok(calls)
}
pub fn pretool(event: &Value) -> Result<Option<&'static str>> {
    let tool = tool_kind(event["tool_name"].as_str().ok_or(Error::Shape)?)?;
    let mut command = SHELL.contains(&tool.as_str());
    if tool == "exec" {
        let empty = json!({});
        let args = event.get("tool_input").unwrap_or(&empty);
        let code = if let Some(s) = args.as_str() {
            s
        } else {
            let m = args.as_object().ok_or(Error::Shape)?;
            m.get("input")
                .or_else(|| m.get("code"))
                .map_or(Ok(""), |v| v.as_str().ok_or(Error::Shape))?
        };
        command = !code_shell_calls(code)?.is_empty();
    }
    if !command && !WRITE.contains(&tool.as_str()) {
        return Ok(None);
    }
    let prompt = match event
        .get("prompt")
        .and_then(Value::as_str)
        .filter(|s| !s.is_empty())
    {
        Some(s) => s.to_owned(),
        None => transcript::transcript_turn(event)?.0,
    };
    if !detect(&prompt)? && !recipient(&prompt)? {
        return Ok(None);
    }
    if command && restricted(&prompt)? {
        return Ok(Some(
            "Owner forbids commands in this handoff turn; shell/interpreter tool denied.",
        ));
    }
    if WRITE.contains(&tool.as_str()) && files_restricted(&owner_sections(&prompt)?)? {
        return Ok(Some(
            "Owner forbids file changes in this handoff turn; file-writing tool denied.",
        ));
    }
    Ok(None)
}
#[cfg(test)]
mod tests;
