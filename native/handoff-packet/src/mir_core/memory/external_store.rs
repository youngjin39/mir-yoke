//! Library-only archive helpers; Python remains the live reference.
use super::distill::_parse_frontmatter;
use crate::{captures, digest::sha256, executor_development_packet::render};
use serde::Serialize;
use serde_json::Value;
use std::path::{Path, PathBuf};
pub const DEFAULT_CHUNK_SIZE: i64 = 800;
pub const DEFAULT_CHUNK_OVERLAP: i64 = 100;
pub const DEFAULT_EMBED_DIM: usize = 1024;
pub const CURRENT_METADATA_VERSION: &str = "5";
pub const ARCHIVE_METADATA_VERSION_PREFIX: &str = "schema_metadata_version:archive:";
pub const ARCHIVE_CONTENT_REINDEX_PREFIX: &str = "force_content_reindex:archive:";
pub const EMBEDDING_FINGERPRINT_KEY: &str = "external_embedding_fingerprint";
pub const SENTENCE_BOUNDARY: &str = r"(?<=[.!?\u3002!?])\s+";
pub const PARAGRAPH_BOUNDARY: &str = "\n\n";
pub const METADATA_ROOTS: &[&str] = &["docs", "tasks", ".ai-harness"];
pub const TASK_HISTORY_RE: &str = concat!(
    r"^tasks/(?:handoffs|sessions|dispatch|runner|archive)(?:/|$)",
    r"|^tasks/plan[-_]archive(?:[-/._]|$)"
);
pub const HISTORICAL_STATUSES: &[&str] = &[
    "superseded",
    "deprecated",
    "rejected",
    "archived",
    "historical",
];
pub const FIRST_HEADING_RE: &str = r"(?m)^\#\s+(.+)";
#[derive(Debug)]
pub struct HelperError {
    pub kind: &'static str,
    pub message: String,
}
impl std::fmt::Display for HelperError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.message)
    }
}
impl std::error::Error for HelperError {}
impl Serialize for Chunk {
    fn serialize<S: serde::Serializer>(
        &self,
        serializer: S,
    ) -> std::result::Result<S::Ok, S::Error> {
        use serde::ser::SerializeStruct;
        let mut s = serializer.serialize_struct("Chunk", 5)?;
        s.serialize_field("chunk_index", &self.chunk_index)?;
        s.serialize_field("text", &self.text)?;
        s.serialize_field("byte_start", &self.byte_start)?;
        s.serialize_field("byte_end", &self.byte_end)?;
        s.serialize_field("text_hash", &self.text_hash)?;
        s.end()
    }
}
fn regex_error(error: impl std::fmt::Display) -> HelperError {
    HelperError {
        kind: "error",
        message: error.to_string(),
    }
}
type Result<T> = std::result::Result<T, HelperError>;
#[derive(Debug, PartialEq, Eq)]
pub struct Chunk {
    pub chunk_index: usize,
    pub text: String,
    pub byte_start: usize,
    pub byte_end: usize,
    pub text_hash: String,
}
pub fn chunk_text(raw: &str, size: i64, overlap: i64) -> Result<Vec<Chunk>> {
    if size <= 0 || overlap < 0 || overlap >= size {
        return Err(HelperError {
            kind: "ValueError",
            message: format!("invalid chunk params size={size} overlap={overlap}"),
        });
    }
    let (size, overlap) = (size as usize, overlap as usize);
    let mut offsets: Vec<_> = raw.char_indices().map(|(i, _)| i).collect();
    offsets.push(raw.len());
    let total = offsets.len() - 1;
    let mut chunks = Vec::new();
    let mut start = 0;
    while start < total {
        let mut end = start.saturating_add(size).min(total);
        if end < total {
            let window = &raw[offsets[start]..offsets[end]];
            let paragraph = window
                .rfind(PARAGRAPH_BOUNDARY)
                .map(|i| window[..i].chars().count());
            if let Some(p) = paragraph.filter(|p| *p > overlap) {
                end = start + p + PARAGRAPH_BOUNDARY.len();
            } else if let Some(m) = captures(SENTENCE_BOUNDARY, window, false)
                .map_err(|e| regex_error(format!("{e:?}")))?
                .last()
            {
                let count = window[..m.end].chars().count();
                if count > overlap {
                    end = start + count;
                }
            }
        }
        let text = &raw[offsets[start]..offsets[end]];
        chunks.push(Chunk {
            chunk_index: chunks.len(),
            text: text.into(),
            byte_start: offsets[start],
            byte_end: offsets[end],
            text_hash: sha256(text.as_bytes()),
        });
        if end >= total {
            break;
        }
        start = end.saturating_sub(overlap);
    }
    Ok(chunks)
}
pub fn compile_globs(spec: Option<&str>) -> Vec<String> {
    spec.unwrap_or_default()
        .split(',')
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .map(str::to_owned)
        .collect()
}
pub fn matches_any(rel: &str, patterns: &[String]) -> Result<bool> {
    for p in patterns {
        // fnmatch normalizes case and path separators on Windows.
        let (p, rel) = if cfg!(windows) {
            (
                p.replace('/', "\\").to_lowercase(),
                rel.replace('/', "\\").to_lowercase(),
            )
        } else {
            (p.clone(), rel.to_owned())
        };
        if crate::executor_verifier::matches(&p, &rel).map_err(regex_error)? {
            return Ok(true);
        }
    }
    Ok(false)
}
pub fn logical_metadata_path(archive_root: &str, rel: &str) -> String {
    if METADATA_ROOTS
        .iter()
        .any(|r| rel == *r || rel.starts_with(&format!("{r}/")))
    {
        return rel.into();
    }
    let name = Path::new(archive_root)
        .file_name()
        .and_then(|s| s.to_str())
        .unwrap_or("");
    if METADATA_ROOTS.contains(&name) {
        if rel.is_empty() {
            name.into()
        } else {
            format!("{name}/{rel}")
        }
    } else {
        rel.into()
    }
}
pub fn is_history_path(rel: &str) -> bool {
    rel.contains("/_archive/")
        || rel.starts_with("docs/_archive/")
        || rel.starts_with("_archive/")
        || captures(TASK_HISTORY_RE, rel, false).is_ok_and(|m| !m.is_empty())
}
pub fn is_within_path_scope(rel: &str, scope: &str) -> Result<bool> {
    let normalized = scope.trim().replace('\\', "/");
    let mut normalized = normalized.as_str();
    while let Some(rest) = normalized.strip_prefix("./") {
        normalized = rest;
    }
    if normalized.is_empty()
        || normalized.starts_with('/')
        || normalized.split('/').any(|p| p == "..")
    {
        return Ok(false);
    }
    if normalized.contains(['*', '?', '[']) {
        return matches_any(rel, &[normalized.into()]);
    }
    let base = normalized.trim_end_matches('/');
    Ok(rel == base || rel.starts_with(&format!("{base}/")))
}
pub fn derive_doc_category(rel: &str) -> Option<&'static str> {
    if is_history_path(rel) {
        return Some("archive");
    }
    [
        ("docs/decisions/", "decision"),
        (".ai-harness/", "harness-rule"),
        ("tasks/", "task"),
        ("docs/", "doc"),
    ]
    .into_iter()
    .find_map(|(prefix, value)| rel.starts_with(prefix).then_some(value))
}
pub fn derive_layer(rel: &str) -> Option<&'static str> {
    if is_history_path(rel) {
        return Some("episodic");
    }
    [
        ("docs/", "semantic"),
        (".ai-harness/", "procedural"),
        ("tasks/", "working"),
    ]
    .into_iter()
    .find_map(|(prefix, value)| rel.starts_with(prefix).then_some(value))
}
pub fn glob_to_regex(pattern: &str) -> Result<String> {
    let mut out = String::from("^");
    let mut chars = pattern.chars().peekable();
    while let Some(c) = chars.next() {
        if c == '*' && chars.peek() == Some(&'*') {
            chars.next();
            if chars.peek() == Some(&'/') {
                chars.next();
                out.push_str("(?:.*/)?");
            } else {
                out.push_str(".*");
            }
        } else {
            match c {
                '*' => out.push_str("[^/]*"),
                '?' => out.push_str("[^/]"),
                '.' | '+' | '^' | '$' | '(' | ')' | '{' | '}' | '|' | '\\' => {
                    out.push('\\');
                    out.push(c);
                }
                _ => out.push(c),
            }
        }
    }
    out.push('$');
    // Compile now, like re.compile; retain Python's diagnostic for an unclosed class.
    if let Err(error) = captures(&out, "", false) {
        if let Some(i) = out.find('[').filter(|i| !out[*i..].contains(']')) {
            return Err(regex_error(format!(
                "unterminated character set at position {i}"
            )));
        }
        return Err(regex_error(format!("{error:?}")));
    }
    Ok(out)
}
pub fn compile_pattern_set(patterns: &[String]) -> Result<Vec<String>> {
    patterns.iter().map(|p| glob_to_regex(p)).collect()
}
pub fn matches_regex_any(rel: &str, compiled: &[String]) -> Result<bool> {
    for p in compiled {
        if captures(p, rel, false)
            .map_err(|e| regex_error(format!("{e:?}")))?
            .iter()
            .any(|m| m.start == 0)
        {
            return Ok(true);
        }
    }
    Ok(false)
}
fn rglob(root: &Path, out: &mut Vec<PathBuf>) {
    // pathlib suppresses directory listing errors, and does not recurse through symlinks.
    let Ok(entries) = std::fs::read_dir(root) else {
        return;
    };
    let entries: Vec<_> = entries.filter_map(std::result::Result::ok).collect();
    out.extend(entries.iter().map(|e| e.path()));
    for entry in entries {
        if entry.file_type().is_ok_and(|t| t.is_dir()) {
            rglob(&entry.path(), out);
        }
    }
}
pub fn walk_archive(root: &Path, include: &[String], exclude: &[String]) -> Result<Vec<String>> {
    walk_archive_with(root, include, exclude, |root| {
        let mut paths = Vec::new();
        rglob(root, &mut paths);
        Ok(paths)
    })
}
/// Inject the Path.rglob listing boundary, preserving its supplied order.
pub fn walk_archive_with(
    root: &Path,
    include: &[String],
    exclude: &[String],
    listing: impl FnOnce(&Path) -> std::io::Result<Vec<PathBuf>>,
) -> Result<Vec<String>> {
    if !root.is_dir() {
        return Ok(Vec::new());
    }
    let root = root.canonicalize().map_err(regex_error)?;
    let inc = compile_pattern_set(include)?;
    let exc = compile_pattern_set(exclude)?;
    let mut out = Vec::new();
    for path in listing(&root).map_err(regex_error)? {
        if !path.is_file() {
            continue;
        }
        let rel = path
            .strip_prefix(&root)
            .map_err(regex_error)?
            .to_str()
            .ok_or_else(|| regex_error("archive path is not UTF-8"))?
            .split(std::path::MAIN_SEPARATOR)
            .collect::<Vec<_>>()
            .join("/");
        if !inc.is_empty() && !matches_regex_any(&rel, &inc)? {
            continue;
        }
        if !exc.is_empty() && matches_regex_any(&rel, &exc)? {
            continue;
        }
        out.push(rel);
    }
    Ok(out)
}
pub fn int_ver(value: &Value) -> i64 {
    match value {
        Value::Bool(b) => i64::from(*b),
        Value::Number(n) => n
            .as_i64()
            .or_else(|| n.as_f64().map(|f| f as i64))
            .unwrap_or(-1),
        Value::String(s) => {
            // Python int accepts Unicode decimal digits and single intervening underscores.
            let mut normalized = String::new();
            for c in s.trim().chars() {
                let digit = captures(r"^\d$", &c.to_string(), false).is_ok_and(|m| !m.is_empty());
                if digit {
                    let mut zero = c as u32;
                    while char::from_u32(zero.saturating_sub(1)).is_some_and(|p| {
                        captures(r"^\d$", &p.to_string(), false).is_ok_and(|m| !m.is_empty())
                    }) {
                        zero -= 1;
                    }
                    normalized.push(char::from(b'0' + ((c as u32 - zero) % 10) as u8));
                } else {
                    normalized.push(c);
                }
            }
            let bytes = normalized.as_bytes();
            if bytes.iter().enumerate().any(|(i, b)| {
                *b == b'_'
                    && (i == 0
                        || i + 1 == bytes.len()
                        || !bytes[i - 1].is_ascii_digit()
                        || !bytes[i + 1].is_ascii_digit())
            }) {
                return -1;
            }
            normalized.replace('_', "").parse().unwrap_or(-1)
        }
        _ => -1,
    }
}
pub fn extract_title_and_frontmatter(text: &str) -> (Option<String>, Option<String>) {
    let Ok(fm) = _parse_frontmatter(text) else {
        return (None, None);
    };
    // Render each ordered field with the existing Python JSON text helper.
    let encoded = (!fm.is_empty()).then(|| {
        format!(
            "{{{}}}",
            fm.iter()
                .map(|(k, v)| format!("{}: {}", render(&Value::String(k.clone())), render(v)))
                .collect::<Vec<_>>()
                .join(", ")
        )
    });
    let title = fm
        .iter()
        .find(|(k, _)| k == "title")
        .and_then(|(_, v)| v.as_str())
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .map(str::to_owned)
        .or_else(|| {
            captures(FIRST_HEADING_RE, text, false)
                .ok()?
                .first()?
                .groups
                .get(1)?
                .as_deref()
                .map(str::trim)
                .filter(|s| !s.is_empty())
                .map(str::to_owned)
        });
    (title, encoded)
}
pub fn doc_created_ordinal(frontmatter: Option<&str>) -> i64 {
    fn ordinal(s: &str) -> Option<i64> {
        let s: String = s.chars().take(10).collect();
        if !s.is_ascii() || s.len() < 8 {
            return None;
        }
        let year: i64 = s.get(..4)?.parse().ok()?;
        if !(1..=9999).contains(&year) {
            return None;
        }
        let before = |y: i64| {
            let n = y - 1;
            365 * n + n / 4 - n / 100 + n / 400
        };
        let leap = |y: i64| y % 4 == 0 && (y % 100 != 0 || y % 400 == 0);
        if s.get(4..6) == Some("-W") || s.get(4..5) == Some("W") {
            let compact = s.replace('-', "");
            if compact.len() != 8 {
                return None;
            }
            let week: i64 = compact.get(5..7)?.parse().ok()?;
            let day: i64 = compact.get(7..8)?.parse().ok()?;
            let jan4 = before(year) + 4;
            let max = if (before(year) % 7 == 3) || (before(year) % 7 == 2 && leap(year)) {
                53
            } else {
                52
            };
            if !(1..=max).contains(&week) || !(1..=7).contains(&day) {
                return None;
            }
            return Some(jan4 - (jan4 - 1) % 7 + (week - 1) * 7 + day - 1);
        }
        let compact = if s.len() == 10 && &s[4..5] == "-" && &s[7..8] == "-" {
            s.replace('-', "")
        } else if s.len() == 8 {
            s
        } else {
            return None;
        };
        let month: usize = compact.get(4..6)?.parse().ok()?;
        let day: i64 = compact.get(6..8)?.parse().ok()?;
        let mut months = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
        months[1] += i64::from(leap(year));
        if !(1..=12).contains(&month) || !(1..=months[month - 1]).contains(&day) {
            return None;
        }
        Some(before(year) + months[..month - 1].iter().sum::<i64>() + day)
    }
    let Some(fm) = frontmatter.and_then(|s| serde_json::from_str::<Value>(s).ok()) else {
        return 0;
    };
    let Some(created) = fm.get("created") else {
        return 0;
    };
    let text = created
        .as_str()
        .map(str::to_owned)
        .unwrap_or_else(|| created.to_string());
    ordinal(&text).unwrap_or(0)
}
