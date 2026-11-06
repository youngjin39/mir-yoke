//! Library-only parity with engine/memory/relation_facts.py.
use super::store;
use crate::mir_core::{audit_log::AuditLog, relations as r, yaml};
use rusqlite::{Connection, OptionalExtension, params};
use serde::Serialize;
use serde_json::{Value, json};
use std::{collections::BTreeSet, fmt, path::Path, time::SystemTime};

pub const RELATION_SCHEMA: &str = "mir-memory-relations/v1";
pub const RELATION_PREDICATES: &[&str] =
    &["realized_by", "implemented_in", "verified_by", "depends_on"];
pub const MAX_RELATIONS_PER_DOCUMENT: usize = 64;
pub const MAX_RELATION_VALUE_CHARS: usize = 1024;
pub const MAX_RELATION_NOTE_CHARS: usize = 240;
pub const MAX_PROVENANCE_QUOTE_CHARS: usize = 4096;
pub const MAX_RELATION_SOURCE_CHARS: usize = 1024 * 1024;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RelationDeclarationError(pub String);
impl fmt::Display for RelationDeclarationError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}
impl std::error::Error for RelationDeclarationError {}
pub type Result<T> = std::result::Result<T, RelationDeclarationError>;
fn error(message: &str) -> RelationDeclarationError {
    RelationDeclarationError(format!("invalid memory_relations: {message}"))
}
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RelationDeclaration {
    pub subject: String,
    pub predicate: String,
    pub object: String,
    pub quote: String,
    pub summary: Option<String>,
    pub reason: Option<String>,
    pub source_line: Option<usize>,
}
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ParsedRelationDocument {
    pub declarations: Vec<RelationDeclaration>,
    pub document_status: String,
    pub has_frontmatter: bool,
}
impl Serialize for RelationDeclaration {
    fn serialize<S: serde::Serializer>(
        &self,
        serializer: S,
    ) -> std::result::Result<S::Ok, S::Error> {
        json!({"subject":self.subject,"predicate":self.predicate,"object":self.object,
            "quote":self.quote,"summary":self.summary,"reason":self.reason,
            "source_line":self.source_line})
        .serialize(serializer)
    }
}
impl Serialize for ParsedRelationDocument {
    fn serialize<S: serde::Serializer>(
        &self,
        serializer: S,
    ) -> std::result::Result<S::Ok, S::Error> {
        json!({"declarations":self.declarations,"document_status":self.document_status,
            "has_frontmatter":self.has_frontmatter})
        .serialize(serializer)
    }
}
fn trim(s: &str) -> &str {
    s.trim_matches(crate::executor_brief_authority::python_space)
}
fn split_lines(text: &str, keepends: bool) -> Vec<&str> {
    let mut lines = Vec::new();
    let mut start = 0;
    let mut chars = text.char_indices().peekable();
    while let Some((index, c)) = chars.next() {
        if matches!(
            c,
            '\n' | '\r' | '\u{b}' | '\u{c}' | '\u{1c}'
                ..='\u{1e}' | '\u{85}' | '\u{2028}' | '\u{2029}'
        ) {
            let mut end = index + c.len_utf8();
            if c == '\r' && chars.peek().is_some_and(|(_, c)| *c == '\n') {
                chars.next();
                end += 1;
            }
            lines.push(&text[start..if keepends { end } else { index }]);
            start = end;
        }
    }
    if start < text.len() {
        lines.push(&text[start..]);
    }
    lines
}
pub fn frontmatter(raw: &str) -> Option<String> {
    if !raw.starts_with("---\n") && !raw.starts_with("---\r\n") {
        return None;
    }
    let lines = split_lines(raw, true);
    let end = lines.iter().skip(1).position(|s| trim(s) == "---")? + 1;
    Some(lines[1..end].concat())
}
fn scalar(node: &yaml::NodeData) -> Option<&str> {
    if let yaml::Kind::Scalar(s) = &node.kind {
        Some(s)
    } else {
        None
    }
}
pub fn node_string(node: &yaml::NodeData, label: &str) -> Result<String> {
    string(node, label, MAX_RELATION_VALUE_CHARS)
}
pub fn note_string(node: &yaml::NodeData, label: &str) -> Result<String> {
    string(node, label, MAX_RELATION_NOTE_CHARS)
}
fn string(node: &yaml::NodeData, label: &str, limit: usize) -> Result<String> {
    let value = scalar(node)
        .filter(|_| node.tag == "tag:yaml.org,2002:str")
        .ok_or_else(|| error(&format!("{label} must be a string")))?;
    if value.is_empty() || value.chars().count() > limit || r::has_control_characters(value) {
        return Err(error(&format!("{label} is unsafe or too long")));
    }
    Ok(value.into())
}
pub fn is_relation_declaration_key(key: &str) -> bool {
    let Ok(Some(doc)) = yaml::compose(yaml::Input::Text(&format!("{key}: null\n"))) else {
        return false;
    };
    let yaml::Kind::Mapping(pairs) = &doc.arena[doc.root].kind else {
        return false;
    };
    pairs.len() == 1 && scalar(&doc.arena[pairs[0].0]) == Some("memory_relations")
}
pub fn frontmatter_declares_relations(text: &str, max: Option<usize>) -> bool {
    if max.is_some_and(|n| text.chars().count() > n) {
        return true;
    }
    if let Ok(Some(doc)) = yaml::compose(yaml::Input::Text(text)) {
        return match &doc.arena[doc.root].kind {
            yaml::Kind::Mapping(pairs) => pairs
                .iter()
                .any(|(k, _)| scalar(&doc.arena[*k]) == Some("memory_relations")),
            _ => false,
        };
    }
    // Same candidate-key fallback as the reference's anchored regular expression.
    text.split('\n').any(|line| {
        let Some(first) = line.chars().next() else {
            return false;
        };
        if first.is_whitespace() || matches!(first, ':' | '#') {
            return false;
        }
        line.split_once(':')
            .is_some_and(|(key, _)| is_relation_declaration_key(key.trim_end()))
    })
}
pub fn has_relation_declaration(raw: &str, max: Option<usize>) -> bool {
    frontmatter(raw).is_some_and(|text| frontmatter_declares_relations(&text, max))
}
pub fn parse_relation_document(raw: &str) -> Result<ParsedRelationDocument> {
    let mut result = ParsedRelationDocument {
        declarations: vec![],
        document_status: String::new(),
        has_frontmatter: false,
    };
    let Some(text) = frontmatter(raw) else {
        return Ok(result);
    };
    result.has_frontmatter = true;
    if !frontmatter_declares_relations(&text, Some(MAX_RELATION_SOURCE_CHARS)) {
        for line in split_lines(&text, false) {
            if let Some((key, value)) = line.split_once(':')
                && trim(key) == "status"
            {
                result.document_status = trim(value)
                    .trim_matches('"')
                    .trim_matches('\'')
                    .to_lowercase();
                break;
            }
        }
        return Ok(result);
    }
    let doc =
        yaml::compose(yaml::Input::Text(&text)).map_err(|_| error("malformed YAML frontmatter"))?;
    let doc = doc.ok_or_else(|| error("frontmatter must be a mapping"))?;
    let yaml::Kind::Mapping(pairs) = &doc.arena[doc.root].kind else {
        return Err(error("frontmatter must be a mapping"));
    };
    let mut declaration = None;
    let mut status_seen = false;
    for (k, v) in pairs {
        match scalar(&doc.arena[*k]) {
            Some("memory_relations") => {
                if declaration.replace(*v).is_some() {
                    return Err(error("duplicate declaration"));
                }
            }
            Some("status") => {
                if status_seen {
                    return Err(error("duplicate status"));
                }
                status_seen = true;
                let status = scalar(&doc.arena[*v])
                    .filter(|_| doc.arena[*v].tag == "tag:yaml.org,2002:str")
                    .ok_or_else(|| error("status must be a string"))?;
                result.document_status = trim(status).to_lowercase();
            }
            _ => {}
        }
    }
    let Some(id) = declaration else {
        return Ok(result);
    };
    let yaml::Kind::Sequence(edges) = &doc.arena[id].kind else {
        return Err(error("value must be a list"));
    };
    if edges.len() > MAX_RELATIONS_PER_DOCUMENT {
        return Err(error("more than 64 relations"));
    }
    let lines = split_lines(&text, false);
    let mut seen = BTreeSet::new();
    for id in edges {
        let edge = &doc.arena[*id];
        let (mut summary, mut reason) = (None, None);
        let values = match &edge.kind {
            yaml::Kind::Sequence(items) => {
                if items.len() != 3 {
                    return Err(error("each item must be a three-string list"));
                }
                [
                    node_string(&doc.arena[items[0]], "subject")?,
                    node_string(&doc.arena[items[1]], "predicate")?,
                    node_string(&doc.arena[items[2]], "object")?,
                ]
            }
            yaml::Kind::Mapping(pairs) => {
                let mut fields = std::collections::BTreeMap::new();
                for (k, v) in pairs {
                    let key = scalar(&doc.arena[*k])
                        .filter(|_| doc.arena[*k].tag == "tag:yaml.org,2002:str")
                        .ok_or_else(|| error("relation mapping key must be a string"))?;
                    if !["subject", "predicate", "object", "summary", "reason"].contains(&key) {
                        return Err(error(&format!(
                            "unknown relation mapping field {}",
                            crate::executor_execute::repr(key)
                        )));
                    }
                    if fields.insert(key, *v).is_some() {
                        return Err(error(&format!(
                            "duplicate relation mapping field {}",
                            crate::executor_execute::repr(key)
                        )));
                    }
                }
                if ["subject", "predicate", "object"]
                    .iter()
                    .any(|k| !fields.contains_key(k))
                {
                    return Err(error(
                        "relation mapping requires subject, predicate, and object",
                    ));
                }
                summary = fields
                    .get("summary")
                    .map(|i| note_string(&doc.arena[*i], "summary"))
                    .transpose()?;
                reason = fields
                    .get("reason")
                    .map(|i| note_string(&doc.arena[*i], "reason"))
                    .transpose()?;
                [
                    node_string(&doc.arena[fields["subject"]], "subject")?,
                    node_string(&doc.arena[fields["predicate"]], "predicate")?,
                    node_string(&doc.arena[fields["object"]], "object")?,
                ]
            }
            yaml::Kind::Scalar(_) => {
                return Err(error("each item must be a three-string list or mapping"));
            }
        };
        let [subject, predicate, object] = values;
        if !RELATION_PREDICATES.contains(&predicate.as_str()) {
            return Err(error(&format!(
                "unsupported predicate {}",
                crate::executor_execute::repr(&predicate)
            )));
        }
        if !seen.insert((subject.clone(), predicate.clone(), object.clone())) {
            return Err(error("duplicate relation"));
        }
        for endpoint in [&subject, &object] {
            if let Some(path) = r::endpoint_path(endpoint, false) {
                r::safe_relative_path(&json!(path), "anchor").map_err(|e| {
                    error(&format!(
                        "unsafe endpoint: anchor unsafe path endpoint: {e}"
                    ))
                })?;
            }
        }
        let end = (edge.end_line + 1).min(lines.len());
        let quote = lines[edge.line..end].join("\n");
        if quote.is_empty() || quote.chars().count() > MAX_PROVENANCE_QUOTE_CHARS {
            return Err(error("supporting quote is too long"));
        }
        result.declarations.push(RelationDeclaration {
            subject,
            predicate,
            object,
            quote,
            summary,
            reason,
            source_line: Some(edge.line + 2),
        });
    }
    Ok(result)
}
pub fn validate_declarations_for_root(
    declarations: &[RelationDeclaration],
    root: &Path,
) -> Result<()> {
    let protections = r::profile_protections(root).map_err(|e| error(&e.0))?;
    for d in declarations {
        for (value, force) in [
            (&d.subject, false),
            (
                &d.object,
                matches!(d.predicate.as_str(), "implemented_in" | "verified_by"),
            ),
        ] {
            if let Some(message) = r::validate_endpoint(value, root, force, &protections) {
                return Err(error(&message));
            }
        }
    }
    Ok(())
}
pub fn safe_source_relative_path(path: &Path, root: &Path) -> Result<String> {
    let unsafe_path = || error("unsafe source path");
    let root = root.canonicalize().map_err(|_| unsafe_path())?;
    let resolved = path.canonicalize().map_err(|_| unsafe_path())?;
    let relative = resolved.strip_prefix(&root).map_err(|_| unsafe_path())?;
    let text = relative
        .to_str()
        .ok_or_else(unsafe_path)?
        .replace('\\', "/");
    let safe = r::safe_relative_path(&json!(text), "source").map_err(|_| unsafe_path())?;
    let protections = r::profile_protections(&root).map_err(|_| unsafe_path())?;
    if r::protected(&safe, &protections) {
        return Err(error("protected source path"));
    }
    Ok(safe)
}
pub fn relation_status_is_active(_predicate: &str, status: &str) -> bool {
    let status = trim(status).to_lowercase();
    !([
        "candidate",
        "draft",
        "proposed",
        "archived",
        "rejected",
        "applied-ledger-v1",
        "done",
    ]
    .contains(&status.as_str())
        || status.starts_with("historical")
        || status.starts_with("superseded"))
}
fn project_path(root: &Path) -> std::result::Result<String, store::Error> {
    // resolve(strict=False), including a missing suffix.
    if !root.is_absolute() {
        return project_path(&std::env::current_dir()?.join(root));
    }
    let resolved = if root.exists() {
        root.canonicalize()?
    } else {
        let parent = root
            .parent()
            .ok_or(store::Error::Snapshot("path has no parent"))?;
        let parent = std::path::PathBuf::from(project_path(parent)?);
        if root.components().next_back() == Some(std::path::Component::ParentDir) {
            parent.parent().unwrap_or(&parent).to_path_buf()
        } else {
            parent.join(root.file_name().unwrap_or_default())
        }
    };
    resolved
        .to_str()
        .map(str::to_owned)
        .ok_or(store::Error::Snapshot("non-UTF-8 project path"))
}
pub fn relation_metadata(
    path: &str,
    root: &Path,
    status: &str,
) -> std::result::Result<Value, store::Error> {
    Ok(json!({"path":path, "relation_schema":RELATION_SCHEMA,
        "relation_project_path":project_path(root)?, "relation_document_status":status}))
}
pub fn upsert_entity(conn: &Connection, slug: &str) -> std::result::Result<i64, store::Error> {
    if let Some(id) = conn
        .query_row("SELECT id FROM entities WHERE slug = ?", [slug], |r| {
            r.get(0)
        })
        .optional()?
    {
        return Ok(id);
    }
    begin(conn)?;
    conn.execute(
        "INSERT INTO entities(type, canonical_name, slug) VALUES (NULL, ?, ?)",
        params![slug, slug],
    )?;
    Ok(
        conn.query_row("SELECT id FROM entities WHERE slug = ?", [slug], |r| {
            r.get(0)
        })?,
    )
}
pub type OwnedRow = (i64, String, String, String);
pub fn owned_active_rows(
    conn: &Connection,
    project: &str,
    source: &str,
) -> std::result::Result<Vec<OwnedRow>, store::Error> {
    let mut statement = conn.prepare(
        "SELECT f.id, subject.slug, f.predicate, object.slug FROM facts f
         JOIN entities subject ON subject.id = f.subject_entity_id
         JOIN entities object ON object.id = f.object_entity_id
         JOIN content_items ci ON ci.id = f.created_from
         WHERE f.status = 'active' AND f.object_entity_id IS NOT NULL
         AND f.object_literal IS NULL AND f.scope = 'project' AND f.project_path = ?
         AND ci.source = 'self_ingest_md'
         AND json_extract(ci.metadata_json, '$.relation_schema') = ?
         AND json_extract(ci.metadata_json, '$.relation_project_path') = ?
         AND json_extract(ci.metadata_json, '$.path') = ?",
    )?;
    Ok(statement
        .query_map(params![project, RELATION_SCHEMA, project, source], |r| {
            Ok((r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?))
        })?
        .collect::<std::result::Result<Vec<_>, _>>()?)
}
pub fn has_owned_active_relation_facts(
    conn: &Connection,
    root: &Path,
    source: &str,
) -> std::result::Result<bool, store::Error> {
    Ok(!owned_active_rows(conn, &project_path(root)?, source)?.is_empty())
}
fn begin(conn: &Connection) -> std::result::Result<(), store::Error> {
    if conn.is_autocommit() {
        conn.execute_batch("BEGIN ")?;
    }
    Ok(())
}
pub struct Reconcile<'a> {
    pub declarations: &'a [RelationDeclaration],
    pub content_item_id: Option<i64>,
    pub project_root: &'a Path,
    pub source_path: &'a str,
    pub document_status: &'a str,
}
pub fn reconcile_relation_facts(
    conn: &Connection,
    input: &Reconcile<'_>,
    clock: impl Fn() -> SystemTime,
) -> std::result::Result<(usize, usize), store::Error> {
    let audit = AuditLog::with_clock(conn, &clock);
    reconcile_with_audit(conn, input, &clock, |event, payload| {
        audit.audit_append(event, payload, false).map(|_| ())
    })
}
/// Injection retains the Python audit failure boundary and caller-owned rollback.
pub fn reconcile_with_audit(
    conn: &Connection,
    input: &Reconcile<'_>,
    clock: impl Fn() -> SystemTime,
    mut audit: impl FnMut(&str, &Value) -> std::result::Result<(), store::Error>,
) -> std::result::Result<(usize, usize), store::Error> {
    let project = project_path(input.project_root)?;
    let owned = owned_active_rows(conn, &project, input.source_path)?;
    for (id, _, _, _) in &owned {
        begin(conn)?;
        conn.execute(
            "UPDATE facts SET status = 'superseded', valid_to = ? WHERE id = ?",
            params![crate::mir_core::audit_log::now_iso(clock())?, id],
        )?;
        audit(
            "memory_relation.superseded",
            &json!({"fact_id":id,"source_path":input.source_path}),
        )?;
    }
    let Some(cid) = input.content_item_id else {
        return Ok((0, owned.len()));
    };
    for d in input.declarations {
        let active = relation_status_is_active(&d.predicate, input.document_status);
        let subject = upsert_entity(conn, &d.subject)?;
        let object = upsert_entity(conn, &d.object)?;
        let now = crate::mir_core::audit_log::now_iso(clock())?;
        begin(conn)?;
        conn.execute(
            "INSERT INTO facts(subject_entity_id,predicate,object_entity_id,object_literal,
             polarity,valid_from,valid_to,status,confidence,created_from,scope,project_path)
             VALUES (?,?,?,NULL,'asserted',?,?,?,1.0,?,'project',?)",
            params![
                subject,
                d.predicate,
                object,
                now,
                if active { None } else { Some(&now) },
                if active { "active" } else { "superseded" },
                cid,
                project
            ],
        )?;
        let id = conn.last_insert_rowid();
        audit(
            "memory_relation.ingested",
            &json!({"fact_id":id,"source_path":input.source_path}),
        )?;
        conn.execute(
            "INSERT INTO provenance(fact_id,content_item_id,quote,
            attribution_entity_id,strength) VALUES (?,?,?,NULL,'stated')",
            params![id, cid, d.quote],
        )?;
    }
    Ok((input.declarations.len(), owned.len()))
}
