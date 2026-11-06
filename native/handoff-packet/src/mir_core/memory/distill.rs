//! Pure distill helpers; frozen Python oracle, no live ingest/search callers.
//! BORROWED-FROM: codenamev/claude_memory@d0e523cd06d6adeae4744d89736f79564d9db41d
//! lib/claude_memory/distill/json_schema.md#schema (MIT).
use crate::{Result, captures, executor_brief_authority::python_space, executor_execute::repr};
use serde_json::Value;

pub const DEFAULT_WHITELIST: &[&str] = &["docs/decisions/adr-*.md", "docs/**/*.md"];
pub const NEVER_INGEST_PREFIXES: &[&str] = &["docs/_archive/"];
pub const _FTS5_TOKEN_RE: &str = r"[A-Za-z0-9_\u00C0-\uFFFF]+";
pub const _FTS5_QUOTED_PHRASE_RE: &str = r#""([^"]+)""#;
pub const _FRONTMATTER_RE: &str = r"(?s)\A---\r?\n(.*?)\r?\n---\r?\n";
pub const _INLINE_LIST_RE: &str = r"^\[(.*)\]$";
pub const _LINK_RE: &str = r"docs/[A-Za-z0-9_./-]+\.md";
// Ordered pairs preserve Python dict insertion order, including replaced keys.
pub type Frontmatter = Vec<(String, Value)>;
#[derive(Debug)]
#[rustfmt::skip]
pub struct Triple {
    pub subject_slug: String, pub predicate: String, pub object_literal: String,
    pub source_content_id: Option<i64>, pub scope: String, pub project_path: Option<String>,
    pub polarity: String, pub confidence: f64, pub is_list_member: bool,
}
// Explicit schema serialization avoids a new serde feature/manifest dependency.
#[rustfmt::skip]
impl serde::Serialize for Triple {
    fn serialize<S: serde::Serializer>(&self, serializer: S) -> std::result::Result<S::Ok, S::Error> {
        use serde::ser::SerializeStruct;
        let mut s = serializer.serialize_struct("Triple", 9)?;
        s.serialize_field("subject_slug", &self.subject_slug)?;
        s.serialize_field("predicate", &self.predicate)?;
        s.serialize_field("object_literal", &self.object_literal)?;
        s.serialize_field("source_content_id", &self.source_content_id)?;
        s.serialize_field("scope", &self.scope)?;
        s.serialize_field("project_path", &self.project_path)?;
        s.serialize_field("polarity", &self.polarity)?;
        s.serialize_field("confidence", &self.confidence)?;
        s.serialize_field("is_list_member", &self.is_list_member)?;
        s.end()
    }
}
fn strip(s: &str) -> &str {
    s.trim_matches(python_space)
}
fn unquote(s: &str) -> &str {
    s.trim_matches('"').trim_matches('\'')
}
fn findall(pattern: &str, s: &str) -> Result<Vec<String>> {
    Ok(captures(pattern, s, false)?
        .into_iter()
        .filter_map(|m| m.groups.into_iter().next().flatten())
        .collect())
}
pub fn links(s: &str) -> Result<Vec<String>> {
    findall(_LINK_RE, s)
}
pub fn _quote_fts_phrase(raw: &str) -> Result<Option<String>> {
    let tokens = findall(_FTS5_TOKEN_RE, raw)?;
    Ok((!tokens.is_empty()).then(|| format!("\"{}\"", tokens.join(" "))))
}
pub fn sanitize_fts_query(query: &str) -> Result<String> {
    let mut parts = Vec::new();
    let mut cursor = 0;
    for m in captures(_FTS5_QUOTED_PHRASE_RE, query, false)? {
        parts.extend(
            findall(_FTS5_TOKEN_RE, &query[cursor..m.start])?
                .iter()
                .map(|t| format!("\"{t}\"")),
        );
        if let Some(phrase) = _quote_fts_phrase(&query[m.start + 1..m.end - 1])? {
            parts.push(phrase);
        }
        cursor = m.end;
    }
    parts.extend(
        findall(_FTS5_TOKEN_RE, &query[cursor..])?
            .iter()
            .map(|t| format!("\"{t}\"")),
    );
    Ok(if parts.is_empty() {
        "\"__noop__\"".into()
    } else {
        parts.join(" ")
    })
}
pub use sanitize_fts_query as _sanitize_fts_query;

#[derive(Debug)]
pub enum SearchError {
    Sanitize(crate::Error),
    Sql(rusqlite::Error),
}
impl std::fmt::Display for SearchError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Sanitize(e) => write!(f, "{e:?}"),
            Self::Sql(e) => e.fmt(f),
        }
    }
}
impl std::error::Error for SearchError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::Sanitize(_) => None,
            Self::Sql(e) => Some(e),
        }
    }
}
/// Frozen query semantics: active status only; terminal subjects remain visible.
pub fn fts_search(
    conn: &rusqlite::Connection,
    query: &str,
    limit: i64,
    include_history: bool,
) -> std::result::Result<Vec<(i64, String, String)>, SearchError> {
    let safe_query = sanitize_fts_query(query).map_err(SearchError::Sanitize)?;
    let status_clause = if include_history {
        ""
    } else {
        "AND f.status = 'active'"
    };
    let mut statement = conn
        .prepare(&format!(
            "SELECT f.id, f.predicate, f.object_literal FROM facts_fts s
         JOIN facts f ON f.id = s.rowid WHERE facts_fts MATCH ? {status_clause}
         ORDER BY bm25(facts_fts) LIMIT ?"
        ))
        .map_err(SearchError::Sql)?;
    statement
        .query_map(rusqlite::params![safe_query, limit], |r| {
            Ok((r.get(0)?, r.get(1)?, r.get(2)?))
        })
        .map_err(SearchError::Sql)?
        .collect::<std::result::Result<_, _>>()
        .map_err(SearchError::Sql)
}
fn put(out: &mut Frontmatter, key: String, value: Value) {
    if let Some((_, old)) = out.iter_mut().find(|(k, _)| *k == key) {
        *old = value;
    } else {
        out.push((key, value));
    }
}
pub fn _parse_frontmatter(text: &str) -> Result<Frontmatter> {
    let mut out = Vec::new();
    let Some(m) = captures(_FRONTMATTER_RE, text, false)?.into_iter().next() else {
        return Ok(out);
    };
    let raw = m
        .groups
        .get(1)
        .and_then(Option::as_deref)
        .unwrap_or_default();
    let mut pending: Option<(String, Vec<Value>)> = None;
    // Python splitlines includes VT, FF, NEL, separators and CRLF as one break.
    let normalized = raw.replace("\r\n", "\n");
    for line in normalized.split([
        '\n', '\r', '\u{b}', '\u{c}', '\u{1c}', '\u{1d}', '\u{1e}', '\u{85}', '\u{2028}',
        '\u{2029}',
    ]) {
        if let Some((_, items)) = &mut pending
            && (line.starts_with("  - ") || line.starts_with("  -\t"))
        {
            items.push(Value::String(unquote(strip(&line[4..])).into()));
            continue;
        }
        if let Some((key, items)) = pending.take() {
            put(&mut out, key, Value::Array(items));
        }
        let line = strip(line);
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        let Some((key, value)) = line.split_once(':') else {
            continue;
        };
        let (key, value) = (strip(key).to_owned(), strip(value));
        if value.is_empty() {
            pending = Some((key, Vec::new()));
        } else if let Some(m) = captures(_INLINE_LIST_RE, value, false)?.into_iter().next() {
            let body = m
                .groups
                .get(1)
                .and_then(Option::as_deref)
                .unwrap_or_default();
            let items = body
                .split(',')
                .filter(|p| !strip(p).is_empty())
                .map(|p| Value::String(unquote(strip(p)).into()))
                .collect();
            put(&mut out, key, Value::Array(items));
        } else {
            put(&mut out, key, Value::String(unquote(value).into()));
        }
    }
    if let Some((key, items)) = pending {
        put(&mut out, key, Value::Array(items));
    }
    Ok(out)
}
/// Lexical POSIX path stem, matching the frozen Path inputs on both targets.
pub fn _adr_slug(path: &str) -> String {
    let name = path
        .split('/')
        .rev()
        .find(|s| !s.is_empty() && *s != ".")
        .unwrap_or_default();
    match name.rfind('.') {
        Some(i) if i > 0 => name[..i].into(),
        _ => name.into(),
    }
}
pub fn _is_never_ingested(path: &str) -> bool {
    NEVER_INGEST_PREFIXES
        .iter()
        .any(|prefix| path.starts_with(prefix))
}
pub fn _matches_whitelist(
    path: &str,
    globs: &[&str],
) -> std::result::Result<bool, crate::executor_verifier::Error> {
    if _is_never_ingested(path) {
        return Ok(false);
    }
    for glob in globs {
        // Python fnmatch normcase folds slash and case on Windows only.
        #[cfg(windows)]
        let (glob, path) = (
            glob.replace('/', "\\").to_lowercase(),
            path.replace('/', "\\").to_lowercase(),
        );
        #[cfg(windows)]
        let (glob, path) = (glob.as_str(), path.as_str());
        if crate::executor_verifier::matches(glob, path)? {
            return Ok(true);
        }
    }
    Ok(false)
}
fn python_str(value: &Value, nested: bool) -> String {
    match value {
        Value::String(s) => {
            if nested {
                repr(s)
            } else {
                s.clone()
            }
        }
        Value::Null => "None".into(),
        Value::Bool(b) => if *b { "True" } else { "False" }.into(),
        Value::Array(a) => format!(
            "[{}]",
            a.iter()
                .map(|v| python_str(v, true))
                .collect::<Vec<_>>()
                .join(", ")
        ),
        Value::Object(m) => format!(
            "{{{}}}",
            m.iter()
                .map(|(k, v)| format!("{}: {}", repr(k), python_str(v, true)))
                .collect::<Vec<_>>()
                .join(", ")
        ),
        Value::Number(_) => crate::mir_core::canonical::canonical_json(value, Some(&[])),
    }
}
pub fn _frontmatter_to_triples(slug: &str, fm: &Frontmatter) -> Vec<Triple> {
    let mut triples = Vec::new();
    for (key, value) in fm {
        // Frozen reserved-key spellings; YAML relation document parsing is not ported here.
        if unquote(strip(key)) == "memory_relations" {
            continue;
        }
        let member = value.is_array();
        let values = match value {
            Value::Array(a) => a.as_slice(),
            _ => std::slice::from_ref(value),
        };
        for item in values {
            if member && !crate::transcript::truthy(item) {
                continue;
            }
            let text = python_str(item, false);
            let text = if member { text.as_str() } else { strip(&text) };
            if text.is_empty() {
                continue;
            }
            triples.push(Triple {
                subject_slug: slug.into(),
                predicate: key.clone(),
                object_literal: text.into(),
                source_content_id: None,
                scope: "global".into(),
                project_path: None,
                polarity: "asserted".into(),
                confidence: 1.0,
                is_list_member: member,
            });
        }
    }
    triples
}
