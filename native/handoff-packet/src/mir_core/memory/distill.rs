//! Pure distill helpers; frozen Python oracle, no live ingest/search callers.
//! BORROWED-FROM: codenamev/claude_memory@d0e523cd06d6adeae4744d89736f79564d9db41d
//! lib/claude_memory/distill/json_schema.md#schema (MIT).
use super::{predicates, relation_facts as relations, sanitize, store};
use crate::mir_core::audit_log::{AuditLog, now_iso};
use crate::{Result, captures, executor_brief_authority::python_space, executor_execute::repr};
use rusqlite::{Connection, OptionalExtension, params};
use serde_json::Value;
use std::{path::Path, time::SystemTime};

#[derive(Debug)]
pub enum WriteError {
    Store(store::Error),
    Relation(relations::RelationDeclarationError),
    Helper(crate::Error),
    Pattern(crate::executor_verifier::Error),
    Injected(&'static str),
}
impl std::fmt::Display for WriteError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Store(e) => e.fmt(f),
            Self::Relation(e) => e.fmt(f),
            Self::Helper(e) => write!(f, "{e:?}"),
            Self::Pattern(e) => write!(f, "{e:?}"),
            Self::Injected(s) => f.write_str(s),
        }
    }
}
impl std::error::Error for WriteError {}
impl From<store::Error> for WriteError {
    fn from(e: store::Error) -> Self {
        Self::Store(e)
    }
}
impl From<rusqlite::Error> for WriteError {
    fn from(e: rusqlite::Error) -> Self {
        Self::Store(e.into())
    }
}
impl From<std::io::Error> for WriteError {
    fn from(e: std::io::Error) -> Self {
        Self::Store(e.into())
    }
}
impl From<relations::RelationDeclarationError> for WriteError {
    fn from(e: relations::RelationDeclarationError) -> Self {
        Self::Relation(e)
    }
}
impl WriteError {
    pub fn python_class(&self) -> &'static str {
        match self {
            Self::Store(e) => e.python_class(),
            Self::Relation(_) => "RelationDeclarationError",
            Self::Helper(_) | Self::Pattern(_) | Self::Injected(_) => "RuntimeError",
        }
    }
}
type WriteResult<T> = std::result::Result<T, WriteError>;
fn begin_write(conn: &Connection) -> rusqlite::Result<()> {
    if conn.is_autocommit() {
        conn.execute_batch("BEGIN ")?;
    }
    Ok(())
}
pub fn upsert_entity(conn: &Connection, slug: &str, typ: Option<&str>) -> WriteResult<i64> {
    let id = relations::upsert_entity(conn, slug)?;
    if let Some(typ) = typ {
        begin_write(conn)?;
        conn.execute(
            "UPDATE entities SET type = ? WHERE slug = ? AND type IS NULL",
            params![typ, slug],
        )?;
    }
    Ok(id)
}
impl Triple {
    pub fn new(subject: &str, predicate: &str, object: &str) -> Self {
        Self {
            subject_slug: subject.into(),
            predicate: predicate.into(),
            object_literal: object.into(),
            source_content_id: None,
            scope: "global".into(),
            project_path: None,
            polarity: "asserted".into(),
            confidence: 1.0,
            is_list_member: false,
        }
    }
}
pub fn insert_triple(
    conn: &Connection,
    triple: &Triple,
    consent: &str,
    clock: impl Fn() -> SystemTime,
) -> WriteResult<i64> {
    let subject = upsert_entity(conn, &triple.subject_slug, None)?;
    let body =
        sanitize::sanitize(&triple.object_literal, Some(consent)).map_err(WriteError::Helper)?;
    begin_write(conn)?;
    conn.execute(
        "INSERT INTO facts(subject_entity_id,predicate,object_literal,polarity,
        valid_from,status,confidence,created_from,scope,project_path)
        VALUES (?,?,?,?,?,'active',?,?,?,?)",
        params![
            subject,
            predicates::canonicalize(&triple.predicate),
            body,
            triple.polarity,
            now_iso(clock())?,
            triple.confidence,
            triple.source_content_id,
            triple.scope,
            triple.project_path
        ],
    )?;
    Ok(conn.last_insert_rowid())
}
pub struct Supersede<'a> {
    pub subject_id: i64,
    pub predicate: &'a str,
    pub new_object: &'a str,
    pub new_confidence: f64,
    pub new_valid_from: &'a str,
    pub new_fact_id: i64,
    pub current_content_id: Option<i64>,
}
pub fn supersede_existing(
    conn: &Connection,
    input: &Supersede<'_>,
    clock: impl Fn() -> SystemTime,
) -> WriteResult<(usize, Vec<i64>)> {
    let mut stmt = conn.prepare(
        "SELECT id,object_literal,confidence,valid_from FROM facts
        WHERE subject_entity_id=? AND predicate=? AND status='active'
        AND object_entity_id IS NULL AND id != ?
        AND (? IS NULL OR created_from IS NULL OR created_from != ?)",
    )?;
    let rows = stmt
        .query_map(
            params![
                input.subject_id,
                predicates::canonicalize(input.predicate),
                input.new_fact_id,
                input.current_content_id,
                input.current_content_id
            ],
            |r| {
                Ok((
                    r.get::<_, i64>(0)?,
                    r.get::<_, Option<String>>(1)?,
                    r.get::<_, Option<f64>>(2)?,
                    r.get::<_, Option<String>>(3)?,
                ))
            },
        )?
        .collect::<rusqlite::Result<Vec<_>>>()?;
    let mut ids = Vec::new();
    for (id, old, confidence, time) in rows {
        if old.as_deref() == Some(input.new_object) {
            continue;
        }
        let order = input.new_valid_from.cmp(time.as_deref().unwrap_or(""));
        let order = if order.is_eq() {
            input
                .new_confidence
                .partial_cmp(&confidence.unwrap_or(0.0))
                .unwrap_or(std::cmp::Ordering::Equal)
        } else {
            order
        };
        if order.is_eq() {
            continue;
        }
        let loser = if order.is_gt() { id } else { input.new_fact_id };
        begin_write(conn)?;
        conn.execute(
            "UPDATE facts SET status = 'superseded', valid_to = ? WHERE id = ?",
            params![now_iso(clock())?, loser],
        )?;
        ids.push(loser);
        if order.is_lt() {
            break;
        }
    }
    Ok((ids.len(), ids))
}
pub fn audit_supersede(
    conn: &Connection,
    id: i64,
    slug: &str,
    predicate: &str,
    clock: impl Fn() -> SystemTime,
) {
    // Best effort is the frozen Python contract; never commit the caller's transaction.
    let _ = AuditLog::with_clock(conn, clock).audit_append(
        "distill.supersede",
        &serde_json::json!({"fact_id":id,"subject_slug":slug,"predicate":predicate}),
        false,
    );
}
pub fn link_cross_refs(conn: &Connection, raw: &str, subject: i64) -> WriteResult<usize> {
    let targets: std::collections::BTreeSet<_> = links(raw)
        .map_err(WriteError::Helper)?
        .into_iter()
        .collect();
    let latest = |id| {
        conn.query_row(
            "SELECT id FROM facts WHERE subject_entity_id = ?
        AND object_entity_id IS NULL ORDER BY id DESC LIMIT 1",
            [id],
            |r| r.get::<_, i64>(0),
        )
        .optional()
    };
    let mut count = 0;
    for path in targets {
        let target: Option<i64> = conn
            .query_row(
                "SELECT id FROM entities WHERE slug = ?",
                [_adr_slug(&path)],
                |r| r.get(0),
            )
            .optional()?;
        let Some(target) = target.filter(|id| *id != subject) else {
            continue;
        };
        let (Some(from), Some(to)) = (latest(subject)?, latest(target)?) else {
            continue;
        };
        begin_write(conn)?;
        // Python suppresses failures only at the insert boundary.
        if let Ok(n) = conn.execute(
            "INSERT OR IGNORE INTO fact_links
            (from_fact_id,to_fact_id,link_type) VALUES (?,?,'adr-cross-ref')",
            params![from, to],
        ) {
            count += n;
        }
    }
    Ok(count)
}

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
pub struct Triple {
    pub subject_slug: String,
    pub predicate: String,
    pub object_literal: String,
    pub source_content_id: Option<i64>,
    pub scope: String,
    pub project_path: Option<String>,
    pub polarity: String,
    pub confidence: f64,
    pub is_list_member: bool,
}
// Explicit schema serialization avoids a new serde feature/manifest dependency.
impl serde::Serialize for Triple {
    fn serialize<S: serde::Serializer>(
        &self,
        serializer: S,
    ) -> std::result::Result<S::Ok, S::Error> {
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
#[derive(Debug, Default)]
pub struct IngestResult {
    pub facts_inserted: usize,
    pub facts_superseded: usize,
    pub fact_links_added: usize,
    pub file_hash: String,
    pub no_op: bool,
    pub no_op_reason: String,
}
impl serde::Serialize for IngestResult {
    fn serialize<S: serde::Serializer>(
        &self,
        serializer: S,
    ) -> std::result::Result<S::Ok, S::Error> {
        serde_json::json!({"facts_inserted":self.facts_inserted,
            "facts_superseded":self.facts_superseded,"fact_links_added":self.fact_links_added,
            "file_hash":self.file_hash,"no_op":self.no_op,
            "no_op_reason":self.no_op_reason})
        .serialize(serializer)
    }
}
fn skipped(hash: &str, reason: &str) -> IngestResult {
    IngestResult {
        file_hash: hash.into(),
        no_op: true,
        no_op_reason: reason.into(),
        ..IngestResult::default()
    }
}
fn read_markdown(path: &Path) -> std::io::Result<String> {
    let raw = std::fs::read_to_string(path)?;
    Ok(raw
        .strip_prefix('\u{feff}')
        .unwrap_or(&raw)
        .replace("\r\n", "\n")
        .replace('\r', "\n"))
}
fn existing_hash(
    conn: &Connection,
    rel: &str,
    root: &Path,
    declared: bool,
) -> WriteResult<Option<String>> {
    let root = root
        .to_str()
        .ok_or_else(|| std::io::Error::other("non-UTF-8 root"))?;
    Ok(conn
        .query_row(
            "SELECT text_hash FROM content_items WHERE source='self_ingest_md'
        AND json_extract(metadata_json,'$.path')=? AND (?=0 OR
        (json_extract(metadata_json,'$.relation_schema')=? AND
        json_extract(metadata_json,'$.relation_project_path')=?)) ORDER BY id DESC LIMIT 1",
            params![rel, declared, relations::RELATION_SCHEMA, root],
            |r| r.get(0),
        )
        .optional()?)
}
fn insert_content(
    conn: &Connection,
    raw: &str,
    hash: &str,
    rel: &str,
    root: &Path,
    status: &str,
    now: &str,
) -> WriteResult<i64> {
    // json.dumps keeps this insertion order and uses spaces after delimiters.
    let metadata = format!(
        "{{\"path\": {}, \"relation_schema\": {}, \"relation_project_path\": {}, \
         \"relation_document_status\": {}}}",
        serde_json::json!(rel),
        serde_json::json!(relations::RELATION_SCHEMA),
        serde_json::json!(
            root.to_str()
                .ok_or_else(|| std::io::Error::other("non-UTF-8 root"))?
        ),
        serde_json::json!(status)
    );
    conn.execute(
        "INSERT INTO content_items(source,occurred_at,ingested_at,text_hash,
        byte_len,raw_text,metadata_json) VALUES ('self_ingest_md',?,?,?,?,?,?)",
        params![now, now, hash, raw.len() as i64, raw, metadata],
    )?;
    Ok(conn.last_insert_rowid())
}
// Python Path.resolve(strict=False): a missing leaf keeps its resolved existing parents.
fn resolve_lenient(path: &Path) -> std::io::Result<std::path::PathBuf> {
    match path.canonicalize() {
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
            match (path.parent(), path.file_name()) {
                (Some(parent), Some(name)) if !parent.as_os_str().is_empty() => {
                    Ok(resolve_lenient(parent)?.join(name))
                }
                _ => std::path::absolute(path),
            }
        }
        other => other,
    }
}
/// Observer callbacks replay Python's patched failure boundaries. Errors roll back
/// this operation while preserving an outer transaction.
pub fn ingest_with_observer(
    path: &Path,
    conn: &Connection,
    root: &Path,
    globs: &[&str],
    clock: impl Fn() -> SystemTime,
    mut observe: impl FnMut(&str) -> WriteResult<()>,
) -> WriteResult<IngestResult> {
    let root = root.canonicalize()?;
    let resolved = resolve_lenient(path)?;
    let rel = resolved
        .strip_prefix(&root)
        .unwrap_or(path)
        .to_str()
        .ok_or_else(|| std::io::Error::other("non-UTF-8 source"))?
        .replace('\\', "/");
    if _is_never_ingested(&rel) {
        return Ok(skipped("", "archive"));
    }
    if !_matches_whitelist(&rel, globs).map_err(WriteError::Pattern)? {
        return Ok(skipped("", "whitelist"));
    }
    let Ok(rel) = relations::safe_source_relative_path(path, &root) else {
        return Ok(skipped("", "unsafe_path"));
    };
    let raw = read_markdown(path)?;
    let validate_size = |raw: &str| -> WriteResult<()> {
        let size = std::fs::metadata(path)?.len();
        let max = relations::MAX_RELATION_SOURCE_CHARS;
        if relations::has_relation_declaration(raw, (size > max as u64).then_some(max))
            && size > max as u64
        {
            return Err(relations::RelationDeclarationError(
                "invalid memory_relations: source exceeds 1 MiB".into(),
            )
            .into());
        }
        Ok(())
    };
    validate_size(&raw)?;
    let hash = crate::digest::sha256(raw.as_bytes());
    let fm = _parse_frontmatter(&raw).map_err(WriteError::Helper)?;
    let doc = relations::parse_relation_document(&raw)?;
    relations::validate_declarations_for_root(&doc.declarations, &root)?;
    let declared = !doc.declarations.is_empty();
    if existing_hash(conn, &rel, &root, declared)?.as_deref() == Some(&hash) {
        return Ok(skipped(&hash, "unchanged"));
    }
    let outer = !conn.is_autocommit();
    conn.execute_batch(if outer {
        "SAVEPOINT ingest_markdown_relations"
    } else {
        "BEGIN IMMEDIATE"
    })?;
    let result = (|| {
        let locked = read_markdown(path)?;
        if !fm.is_empty() {
            validate_size(&locked)?;
        }
        if crate::digest::sha256(locked.as_bytes()) != hash {
            return Err(relations::RelationDeclarationError(
                "source changed during ingestion; retry".into(),
            )
            .into());
        }
        if !fm.is_empty() && existing_hash(conn, &rel, &root, declared)?.as_deref() == Some(&hash) {
            return Ok(skipped(&hash, "unchanged"));
        }
        let tombstone =
            fm.is_empty() && relations::has_owned_active_relation_facts(conn, &root, &rel)?;
        let content = if !fm.is_empty() || tombstone {
            Some(insert_content(
                conn,
                &raw,
                &hash,
                &rel,
                &root,
                if fm.is_empty() {
                    ""
                } else {
                    &doc.document_status
                },
                &now_iso(clock())?,
            )?)
        } else {
            None
        };
        if !fm.is_empty() {
            observe("content")?;
        }
        let (inserted, superseded) = relations::reconcile_relation_facts(
            conn,
            &relations::Reconcile {
                declarations: if fm.is_empty() {
                    &[]
                } else {
                    &doc.declarations
                },
                content_item_id: if fm.is_empty() { None } else { content },
                project_root: &root,
                source_path: &rel,
                document_status: if fm.is_empty() {
                    ""
                } else {
                    &doc.document_status
                },
            },
            &clock,
        )?;
        if fm.is_empty() {
            let mut result = skipped(&hash, "empty_frontmatter");
            result.facts_superseded = superseded;
            if tombstone {
                result.no_op = false;
                result.no_op_reason.clear();
            }
            return Ok(result);
        }
        let slug = _adr_slug(&rel);
        let typ = fm
            .iter()
            .find(|(k, _)| k == "type")
            .and_then(|(_, v)| v.as_str());
        let subject = upsert_entity(conn, &slug, typ)?;
        let mut result = IngestResult {
            file_hash: hash.clone(),
            facts_inserted: inserted,
            facts_superseded: superseded,
            ..IngestResult::default()
        };
        for mut triple in _frontmatter_to_triples(&slug, &fm) {
            let existing: Option<i64> = conn
                .query_row(
                    "SELECT id FROM facts
                WHERE subject_entity_id=? AND predicate=? AND object_entity_id IS NULL
                AND object_literal=? AND status='active' LIMIT 1",
                    params![
                        subject,
                        predicates::canonicalize(&triple.predicate),
                        triple.object_literal
                    ],
                    |r| r.get(0),
                )
                .optional()?;
            if existing.is_some() {
                continue;
            }
            triple.source_content_id = content;
            let id = insert_triple(conn, &triple, "ephemeral", &clock)?;
            observe("fact")?;
            result.facts_inserted += 1;
            if !triple.is_list_member {
                let time: String =
                    conn.query_row("SELECT valid_from FROM facts WHERE id=?", [id], |r| {
                        r.get(0)
                    })?;
                let (n, ids) = supersede_existing(
                    conn,
                    &Supersede {
                        subject_id: subject,
                        predicate: &triple.predicate,
                        new_object: &triple.object_literal,
                        new_confidence: triple.confidence,
                        new_valid_from: &time,
                        new_fact_id: id,
                        current_content_id: content,
                    },
                    &clock,
                )?;
                result.facts_superseded += n;
                for fid in &ids {
                    audit_supersede(conn, *fid, &slug, &triple.predicate, &clock);
                }
                if ids.contains(&id) {
                    result.facts_inserted -= 1;
                }
            }
        }
        result.fact_links_added = link_cross_refs(conn, &raw, subject)?;
        conn.execute(
            "INSERT OR IGNORE INTO fact_documents(fact_id,document_id)
            SELECT f.id,d.id FROM facts f JOIN external_documents d ON d.relative_path=?
            WHERE f.created_from=?",
            params![rel, content],
        )?;
        Ok(result)
    })();
    match &result {
        Ok(_) => conn.execute_batch(if outer {
            "RELEASE SAVEPOINT ingest_markdown_relations"
        } else {
            "COMMIT"
        })?,
        Err(_) => conn.execute_batch(if outer {
            "ROLLBACK TO SAVEPOINT ingest_markdown_relations;
             RELEASE SAVEPOINT ingest_markdown_relations"
        } else {
            "ROLLBACK"
        })?,
    }
    result
}
pub fn ingest_markdown_file(
    path: &Path,
    conn: &Connection,
    root: &Path,
    globs: &[&str],
    clock: impl Fn() -> SystemTime,
) -> WriteResult<IngestResult> {
    ingest_with_observer(path, conn, root, globs, clock, |_| Ok(()))
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

/// Active ingested documents, ordered by slug; keyword order follows fact IDs.
#[derive(Debug)]
pub struct IngestedIndex {
    pub slug: String,
    pub title: String,
    pub keywords: Vec<String>,
    pub path: String,
}
pub fn recall_ingested_index(conn: &Connection) -> rusqlite::Result<Vec<IngestedIndex>> {
    let mut stmt = conn.prepare(
        "SELECT DISTINCT e.slug, ci.metadata_json FROM entities e
         JOIN facts f ON f.subject_entity_id=e.id
         JOIN content_items ci ON ci.id=f.created_from
         WHERE ci.source='self_ingest_md' AND f.status='active'",
    )?;
    let rows = stmt.query_map([], |r| {
        Ok((r.get::<_, String>(0)?, r.get::<_, Option<String>>(1)?))
    })?;
    let mut seen = std::collections::HashSet::new();
    let mut result = Vec::new();
    for row in rows {
        let (slug, metadata) = row?;
        if !seen.insert(slug.clone()) {
            continue;
        }
        let meta: Value = serde_json::from_str(metadata.as_deref().unwrap_or("{}"))
            .unwrap_or_else(|_| serde_json::json!({}));
        let path = meta
            .get("path")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_owned();
        let title = conn
            .query_row(
                "SELECT object_literal FROM facts
             WHERE subject_entity_id=(SELECT id FROM entities WHERE slug=?)
             AND predicate='title' AND status='active' LIMIT 1",
                [&slug],
                |r| r.get::<_, String>(0),
            )
            .optional()?
            .unwrap_or_default();
        let mut kws = conn.prepare(
            "SELECT object_literal FROM facts
             WHERE subject_entity_id=(SELECT id FROM entities WHERE slug=?)
             AND predicate='keywords' AND status='active' ORDER BY id",
        )?;
        let mut keywords = Vec::new();
        for kw in kws.query_map([&slug], |r| r.get::<_, String>(0))? {
            let kw = kw?;
            if !keywords.contains(&kw) {
                keywords.push(kw);
            }
        }
        result.push(IngestedIndex {
            slug,
            title,
            keywords,
            path,
        });
    }
    result.sort_by(|a, b| a.slug.cmp(&b.slug));
    Ok(result)
}
#[derive(Debug)]
pub struct Lesson {
    pub slug: String,
    pub text: String,
}
/// Lessons retain insertion order, including active facts from earlier ingests.
pub fn recall_lessons(conn: &Connection) -> rusqlite::Result<Vec<Lesson>> {
    conn.prepare(
        "SELECT e.slug, f.object_literal FROM facts f
         JOIN entities e ON e.id=f.subject_entity_id
         WHERE f.predicate='lesson' AND f.status='active' ORDER BY f.id",
    )?
    .query_map([], |r| {
        Ok(Lesson {
            slug: r.get(0)?,
            text: r.get(1)?,
        })
    })?
    .collect()
}

impl serde::Serialize for IngestedIndex {
    fn serialize<S: serde::Serializer>(
        &self,
        serializer: S,
    ) -> std::result::Result<S::Ok, S::Error> {
        serde_json::json!({"slug":self.slug,"title":self.title,
            "keywords":self.keywords,"path":self.path})
        .serialize(serializer)
    }
}
impl serde::Serialize for Lesson {
    fn serialize<S: serde::Serializer>(
        &self,
        serializer: S,
    ) -> std::result::Result<S::Ok, S::Error> {
        serde_json::json!({"slug":self.slug,"text":self.text}).serialize(serializer)
    }
}
