//! Library-only immutable memory relation queries. No live callers.
use super::{
    memory::{relation_facts as f, store},
    relations as r,
};
use crate::digest;
use r::{Edge, Options, RelationError, Result};
use rusqlite::{Connection, OptionalExtension, functions::FunctionFlags, params_from_iter};
use serde::Serialize;
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    io::Read,
    path::{Path, PathBuf},
};

pub const MAX_DB_ROWS: usize = 2048;
pub const MAX_SOURCE_BYTES: usize = 1024 * 1024;
pub const MAX_TOTAL_SOURCE_BYTES: usize = 4 * 1024 * 1024;
pub const MAX_METADATA_CHARS: usize = 65536;
pub const MAX_PROVENANCE_PER_EDGE: usize = 8;
const DB: &str = ".mir/memory.db";
const SCOPE: &str = "declared_memory_relations_only";
const INACTIVE: &[&str] = &[
    "inactive",
    "archived",
    "rejected",
    "superseded",
    "superseded-design",
    "historical",
    "historical-snapshot",
    "historical-manual-snapshot",
    "historical-ledger",
    "applied-ledger-v1",
    "done",
    "candidate",
    "draft",
    "proposed",
];
fn error(s: &str) -> RelationError {
    RelationError(s.into())
}
fn db_error(_: impl std::fmt::Display) -> RelationError {
    error("memory database cannot be read safely")
}
#[derive(Clone, Default)]
pub struct SourceValidation {
    pub reason: Option<String>,
    pub source_path: Option<String>,
    pub source_hash: Option<String>,
    pub source_text: Option<String>,
    pub bytes_read: usize,
    pub budget_exhausted: bool,
    pub source_unstable: bool,
}
impl Serialize for SourceValidation {
    fn serialize<S: serde::Serializer>(
        &self,
        serializer: S,
    ) -> std::result::Result<S::Ok, S::Error> {
        json!({"reason":self.reason,"source_path":self.source_path,"source_hash":self.source_hash,
            "source_text":self.source_text,"bytes_read":self.bytes_read,
            "budget_exhausted":self.budget_exhausted,"source_unstable":self.source_unstable})
        .serialize(serializer)
    }
}
fn skip(reason: &str) -> SourceValidation {
    SourceValidation {
        reason: Some(reason.into()),
        ..Default::default()
    }
}
#[derive(Default)]
pub struct SelectionState {
    source_cache: BTreeMap<(String, String), SourceValidation>,
    fact_cache: BTreeMap<i64, (Option<Edge>, Option<String>)>,
    pub selected_fact_ids: BTreeSet<i64>,
    pub source_bytes: usize,
    pub incomplete: bool,
    pub proofs_omitted: usize,
    /// Request-scoped budget, injectable for boundary replay without global mutation.
    pub source_budget: Option<usize>,
}
pub fn metadata_gate(root: &Path, metadata: &Value) -> Option<&'static str> {
    if !metadata.is_object() {
        return Some("invalid relation metadata");
    }
    if metadata["relation_schema"] != f::RELATION_SCHEMA {
        return Some("unsupported relation schema");
    }
    if metadata["relation_project_path"].as_str() != root.to_str() {
        return Some("relation source belongs to another root");
    }
    let Some(status) = metadata["relation_document_status"]
        .as_str()
        .filter(|s| !r::has_control_characters(s))
    else {
        return Some("invalid relation document status");
    };
    if INACTIVE.contains(&status.trim().to_lowercase().as_str()) {
        return Some("inactive relation document");
    }
    None
}
pub fn entity_value(value: &Value) -> Option<&str> {
    value
        .as_str()
        .filter(|s| !s.is_empty() && s.chars().count() <= 4096 && !r::has_control_characters(s))
}
pub fn memory_db_path(root: &Path) -> Result<PathBuf> {
    let candidate = root.join(DB);
    let meta = candidate
        .symlink_metadata()
        .map_err(|_| error("memory database is unavailable"))?;
    let resolved = candidate
        .canonicalize()
        .map_err(|_| error("memory database is unavailable"))?;
    let relative = resolved
        .strip_prefix(root)
        .map_err(|_| error("memory database is unavailable"))?;
    if meta.is_symlink() || !meta.is_file() {
        return Err(error("memory database must be a regular canonical file"));
    }
    if relative != Path::new(DB) {
        return Err(error("memory database escapes its canonical project path"));
    }
    Ok(resolved)
}
pub use store::snapshot_file_state as source_stamp;
pub fn source_text(
    root: &Path,
    metadata: &Value,
    expected: &Value,
    protections: &[String],
    remaining: usize,
) -> SourceValidation {
    if let Some(issue) = metadata_gate(root, metadata) {
        return skip(issue);
    }
    let Ok(relative) = r::safe_relative_path(&metadata["path"], "relation source") else {
        return skip("unsafe relation source");
    };
    if r::protected(&relative, protections) {
        return skip("protected relation source");
    }
    let candidate = root.join(&relative);
    let Ok(meta) = candidate.symlink_metadata() else {
        return skip("unavailable relation source");
    };
    let Ok(resolved) = candidate.canonicalize() else {
        return skip("unavailable relation source");
    };
    let Ok(rel) = resolved.strip_prefix(root) else {
        return skip("unavailable relation source");
    };
    let Some(rel) = rel.to_str() else {
        return skip("unavailable relation source");
    };
    if r::protected(&rel.replace('\\', "/"), protections) {
        return skip("protected relation source");
    }
    if !meta.is_file() {
        return skip("unavailable relation source");
    }
    let Ok(Some(stamp)) = source_stamp(&resolved) else {
        return skip("unavailable relation source");
    };
    let size = stamp.size();
    if size > MAX_SOURCE_BYTES as u64 {
        return skip("relation source exceeds 1 MiB limit");
    }
    if size > remaining as u64 {
        return SourceValidation {
            budget_exhausted: true,
            ..skip("relation source validation byte limit")
        };
    }
    let Ok(mut handle) = fs::File::open(&resolved) else {
        return skip("unavailable relation source");
    };
    let unstable = || SourceValidation {
        source_unstable: true,
        ..skip("relation source changed while reading")
    };
    if store::snapshot_handle_state(&handle).map_or(true, |s| s != stamp) {
        return unstable();
    }
    let mut raw = Vec::new();
    let read = handle.by_ref().take(size).read_to_end(&mut raw);
    if read.is_err() {
        return SourceValidation {
            bytes_read: raw.len(),
            ..skip("unavailable relation source")
        };
    }
    if raw.len() as u64 != size
        || store::snapshot_handle_state(&handle).map_or(true, |s| s != stamp)
        || source_stamp(&resolved).map_or(true, |s| s != Some(stamp))
    {
        return SourceValidation {
            bytes_read: raw.len(),
            ..unstable()
        };
    }
    let bytes = raw.strip_prefix(&[239, 187, 191]).unwrap_or(&raw);
    let Ok(text) = std::str::from_utf8(bytes) else {
        return SourceValidation {
            bytes_read: raw.len(),
            ..skip("relation source is not UTF-8")
        };
    };
    let text = text.replace("\r\n", "\n").replace('\r', "\n");
    let hash = digest::sha256(text.as_bytes());
    if expected.as_str() != Some(&hash) {
        return SourceValidation {
            bytes_read: raw.len(),
            ..skip("stale relation source")
        };
    }
    SourceValidation {
        source_path: Some(relative),
        source_hash: Some(hash),
        source_text: Some(text),
        bytes_read: raw.len(),
        ..Default::default()
    }
}
pub fn provenance_is_current(
    conn: &Connection,
    fact: i64,
    content: i64,
    quote: &str,
) -> Result<bool> {
    conn.query_row(
        "SELECT 1 FROM provenance WHERE fact_id=? AND content_item_id=?
        AND strength='stated' AND quote=? LIMIT 1",
        (fact, content, quote),
        |_| Ok(()),
    )
    .optional()
    .map(|v| v.is_some())
    .map_err(db_error)
}
pub fn inactive_endpoint_sql(entity: &str) -> String {
    format!(
        concat!(
            "\n",
            "       AND NOT EXISTS (\n",
            "            SELECT 1 FROM facts terminal\n",
            "             WHERE terminal.subject_entity_id = {entity}\n",
            "               AND terminal.predicate = 'status'\n",
            "               AND terminal.status = 'active'\n",
            "               AND terminal.polarity = 'asserted'\n",
            "               AND (\n",
            "                    lower(trim(terminal.object_literal)) IN\n",
            "                        ('archived', 'rejected', 'superseded', 'superseded-design',\n",
            "                         'historical', 'historical-snapshot',\n",
            "                         'historical-manual-snapshot', 'historical-ledger',\n",
            "                         'applied-ledger-v1', 'done', 'inactive', ",
            "'candidate', 'draft',\n",
            "                         'proposed')\n",
            "                    OR lower(trim(terminal.object_literal)) LIKE 'historical%'\n",
            "                    OR lower(trim(terminal.object_literal)) LIKE 'superseded%'\n",
            "               )\n",
            "       )\n",
            "    ",
        ),
        entity = entity
    )
}
pub fn locator_path_sql(column: &str) -> String {
    format!("mir_locator_path({column})")
}
pub fn register_locator_normalizer(conn: &Connection) -> Result<()> {
    for name in ["mir_locator_path", "mir_normalized_locator"] {
        conn.create_scalar_function(
            name,
            1,
            FunctionFlags::SQLITE_UTF8 | FunctionFlags::SQLITE_DETERMINISTIC,
            move |ctx| {
                let value = ctx.get::<String>(0)?;
                let normalized = r::normalized_locator(&value);
                Ok(if name == "mir_locator_path" {
                    normalized.split("::").next().unwrap_or("").to_owned()
                } else {
                    normalized
                })
            },
        )
        .map_err(db_error)?;
    }
    Ok(())
}
const JOINS: &str = "FROM facts f JOIN entities subject ON subject.id=f.subject_entity_id
    JOIN entities object ON object.id=f.object_entity_id
    JOIN content_items ci ON ci.id=f.created_from";
fn conditions() -> Result<String> {
    Ok(format!(
        "f.object_literal IS NULL AND f.polarity='asserted' AND f.status='active'
        AND f.valid_to IS NULL AND f.scope='project' AND f.project_path=?
        AND ci.source='self_ingest_md' AND length(ci.metadata_json)<=65536
        AND length(ci.text_hash)<=128 {} {} {}",
        store::current_fact_filter_sql("f").map_err(db_error)?,
        inactive_endpoint_sql("f.subject_entity_id"),
        inactive_endpoint_sql("f.object_entity_id")
    ))
}
pub type MemoryRow = Vec<Value>;
fn rows(conn: &Connection, sql: &str, args: &[rusqlite::types::Value]) -> Result<Vec<MemoryRow>> {
    use rusqlite::types::ValueRef;
    let mut stmt = conn.prepare(sql).map_err(db_error)?;
    let n = stmt.column_count();
    stmt.query_map(params_from_iter(args), |row| {
        (0..n)
            .map(|i| {
                Ok(match row.get_ref(i)? {
                    ValueRef::Null => Value::Null,
                    ValueRef::Integer(v) => json!(v),
                    ValueRef::Real(v) => json!(v),
                    ValueRef::Text(v) => json!(std::str::from_utf8(v).map_err(|e| {
                        rusqlite::Error::FromSqlConversionFailure(
                            i,
                            rusqlite::types::Type::Text,
                            Box::new(e),
                        )
                    })?),
                    ValueRef::Blob(_) => Value::Null,
                })
            })
            .collect()
    })
    .map_err(db_error)?
    .collect::<std::result::Result<_, _>>()
    .map_err(db_error)
}
const COLUMNS: &str =
    "f.id,subject.slug,f.predicate,object.slug,ci.id,ci.text_hash,ci.metadata_json";
fn text(s: &str) -> rusqlite::types::Value {
    s.to_owned().into()
}
/// SQL limit is signed to preserve SQLite's unlimited (-1) boundary semantics.
pub fn relation_rows(
    conn: &Connection,
    root: &Path,
    frontier: &BTreeSet<String>,
    purpose: &str,
    ids: Option<&BTreeSet<i64>>,
    excluded: Option<&BTreeSet<i64>>,
    limit: i64,
) -> Result<Vec<MemoryRow>> {
    if frontier.is_empty() {
        return Ok(vec![]);
    }
    let mut args = vec![text(
        root.to_str().ok_or_else(|| error("root must be a path"))?,
    )];
    let mut directions = vec![];
    for (reverse, column) in [(false, "subject.slug"), (true, "object.slug")] {
        let mut predicates: Vec<_> = f::RELATION_PREDICATES
            .iter()
            .filter(|p| r::allowed(purpose, p, reverse))
            .copied()
            .collect();
        predicates.sort();
        if predicates.is_empty() {
            continue;
        }
        directions.push(format!(
            "({column} IN ({}) AND f.predicate IN ({}))",
            vec!["?"; frontier.len()].join(","),
            vec!["?"; predicates.len()].join(",")
        ));
        args.extend(frontier.iter().map(|s| text(s)));
        args.extend(predicates.iter().map(|s| text(s)));
    }
    if directions.is_empty() {
        return Ok(vec![]);
    }
    let mut clause = String::new();
    let ids = ids.filter(|s| !s.is_empty());
    if let Some(selected) = ids.or(excluded.filter(|s| !s.is_empty())) {
        clause = format!(
            "AND f.id {}IN ({})",
            if ids.is_some() { "" } else { "NOT " },
            vec!["?"; selected.len()].join(",")
        );
        args.extend(selected.iter().map(|i| (*i).into()));
    }
    args.push(limit.into());
    rows(
        conn,
        &format!(
            "SELECT {COLUMNS} {JOINS} WHERE {} AND length(subject.slug)<=4096
        AND length(object.slug)<=4096 AND ({}) {clause} ORDER BY f.id LIMIT ?",
            conditions()?,
            directions.join(" OR ")
        ),
        &args,
    )
}
pub fn eligible_nodes(conn: &Connection, root: &Path, anchor: &str) -> Result<Vec<String>> {
    node_rows(
        conn,
        root,
        "entity.slug=? AND length(entity.slug)<=4096",
        &[text(anchor)],
        1,
    )
}
fn node_rows(
    conn: &Connection,
    root: &Path,
    clause: &str,
    args: &[rusqlite::types::Value],
    limit: i64,
) -> Result<Vec<String>> {
    let mut args = args.to_vec();
    args.push(text(
        root.to_str().ok_or_else(|| error("root must be a path"))?,
    ));
    args.push(limit.into());
    let rows = rows(
        conn,
        &format!(
            "SELECT DISTINCT entity.slug FROM entities entity
        WHERE {clause} AND EXISTS (SELECT 1 {JOINS} WHERE {}
        AND f.predicate IN ('depends_on','implemented_in','realized_by','verified_by')
        AND (f.subject_entity_id=entity.id OR f.object_entity_id=entity.id))
        ORDER BY entity.slug LIMIT ?",
            conditions()?
        ),
        &args,
    )?;
    Ok(rows
        .into_iter()
        .filter_map(|r| r[0].as_str().map(str::to_owned))
        .collect())
}
pub fn locator_nodes(
    conn: &Connection,
    root: &Path,
    anchor: &str,
    max_edges: usize,
) -> Result<Vec<String>> {
    register_locator_normalizer(conn)?;
    let normalized = r::normalized_locator(anchor);
    let path = normalized.split("::").next().unwrap_or("");
    let aliases = node_rows(
        conn,
        root,
        "mir_locator_path(entity.slug)=?
        AND instr(entity.slug,'::')>0 AND (instr(?,'::')=0 OR mir_normalized_locator(entity.slug)=?)
        AND length(entity.slug)<=4096",
        &[text(path), text(&normalized), text(&normalized)],
        max_edges as i64 + 1,
    )?;
    if aliases.is_empty() {
        eligible_nodes(conn, root, &normalized)
    } else {
        Ok(aliases)
    }
}
pub fn implemented_in_rows(conn: &Connection, root: &Path, anchor: &str) -> Result<Vec<MemoryRow>> {
    register_locator_normalizer(conn)?;
    let normal = r::normalized_locator(anchor);
    rows(
        conn,
        &format!(
            "SELECT {COLUMNS} {JOINS} WHERE f.predicate='implemented_in'
        AND mir_locator_path(object.slug)=? AND {} AND length(subject.slug)<=4096
        AND length(object.slug)<=4096 ORDER BY f.id LIMIT 2049",
            conditions()?
        ),
        &[
            text(normal.split("::").next().unwrap_or("")),
            text(root.to_str().ok_or_else(|| error("root must be a path"))?),
        ],
    )
}
pub fn resolve_query_anchor(
    conn: &Connection,
    root: &Path,
    protections: &[String],
    anchor: &str,
) -> Result<Vec<String>> {
    let exact = eligible_nodes(conn, root, anchor)?;
    if r::endpoint_path(anchor, false).is_none() {
        return if exact.is_empty() {
            Err(error("unknown anchor"))
        } else {
            Ok(exact)
        };
    }
    if let Some(issue) = r::validate_endpoint(anchor, root, true, protections) {
        return Err(error(&format!("anchor {issue}")));
    }
    let resolved = locator_nodes(conn, root, anchor, 64)?;
    if resolved.is_empty() {
        Err(error("unknown anchor"))
    } else {
        Ok(resolved)
    }
}
pub fn validate_memory_row(
    conn: &Connection,
    root: &Path,
    protections: &[String],
    row: &[Value],
    state: &mut SelectionState,
) -> Result<(Option<Edge>, Option<String>)> {
    let id = row[0].as_i64().ok_or_else(|| error("invalid fact id"))?;
    if let Some(cached) = state.fact_cache.get(&id) {
        return Ok(cached.clone());
    }
    let result = validate_uncached(conn, root, protections, row, state)?;
    state.fact_cache.insert(id, result.clone());
    Ok(result)
}
fn validate_uncached(
    conn: &Connection,
    root: &Path,
    protections: &[String],
    row: &[Value],
    state: &mut SelectionState,
) -> Result<(Option<Edge>, Option<String>)> {
    let rejected = |reason: &str| Ok((None, Some(reason.into())));
    let (Some(source), Some(target)) = (entity_value(&row[1]), entity_value(&row[3])) else {
        return rejected("invalid relation endpoint");
    };
    let predicate = row[2].as_str().unwrap_or("");
    let path = source.split("::").next().unwrap_or("");
    let issue = if path.contains('/') || path.starts_with('.') {
        r::validate_endpoint(source, root, false, protections)
    } else {
        None
    }
    .or_else(|| r::validate_endpoint(target, root, r::file_relation(predicate), protections));
    if let Some(issue) = issue {
        return rejected(&issue);
    }
    let Ok(metadata) = serde_json::from_str::<Value>(row[6].as_str().unwrap_or("")) else {
        return rejected("invalid relation metadata");
    };
    if let Some(issue) = metadata_gate(root, &metadata) {
        return rejected(issue);
    }
    let key = metadata["path"]
        .as_str()
        .zip(row[5].as_str())
        .map(|(p, h)| (p.to_owned(), h.to_owned()));
    let cached = key
        .as_ref()
        .and_then(|k| state.source_cache.get(k))
        .cloned();
    let validated = match cached {
        Some(v) => v,
        None => {
            let v = source_text(
                root,
                &metadata,
                &row[5],
                protections,
                state
                    .source_budget
                    .unwrap_or(MAX_TOTAL_SOURCE_BYTES)
                    .saturating_sub(state.source_bytes),
            );
            state.source_bytes += v.bytes_read;
            if let Some(key) = key {
                state.source_cache.insert(key, v.clone());
            }
            v
        }
    };
    if let Some(reason) = &validated.reason {
        state.incomplete |= validated.budget_exhausted || validated.source_unstable;
        return rejected(reason);
    }
    let Ok(doc) = f::parse_relation_document(validated.source_text.as_deref().unwrap_or("")) else {
        return rejected("invalid relation declaration");
    };
    if metadata["relation_document_status"] != doc.document_status {
        return rejected("relation document status changed");
    }
    let mut matching = false;
    for d in doc
        .declarations
        .iter()
        .filter(|d| d.subject == source && d.predicate == predicate && d.object == target)
    {
        matching = true;
        if !provenance_is_current(
            conn,
            row[0].as_i64().unwrap_or(0),
            row[4].as_i64().unwrap_or(0),
            &d.quote,
        )? {
            continue;
        }
        let proof = json!({"database":DB,"fact_id":row[0],"content_item_id":row[4],
            "source_path":validated.source_path,"source_hash":validated.source_hash,
            "source_line":d.source_line,
            "summary":d.summary.clone().unwrap_or_else(|| format!("Declared {} relationship.",
                predicate.replace('_', " "))),
            "summary_basis":if d.summary.is_some() {"authored"}
                else {"deterministic predicate description"},
            "reason":d.reason.as_deref().unwrap_or("No authored rationale was supplied."),
            "reason_basis":if d.reason.is_some() {"authored"} else {"no authored rationale"}});
        let mut provenance = json!({});
        for k in [
            "database",
            "fact_id",
            "content_item_id",
            "source_path",
            "source_hash",
        ] {
            provenance[k] = proof[k].clone();
        }
        provenance["sources"] = json!([proof]);
        return Ok((
            Some(Edge {
                source: source.into(),
                relation: predicate.into(),
                target: target.into(),
                source_line: None,
                provenance: Some(provenance),
            }),
            None,
        ));
    }
    rejected(if matching {
        "missing relation provenance"
    } else {
        "undeclared relation fact"
    })
}
pub fn append_edge(emitted: &mut Vec<Edge>, edge: Edge, state: &mut SelectionState) -> bool {
    let Some(existing) = emitted.iter_mut().find(|e| {
        e.source == edge.source && e.relation == edge.relation && e.target == edge.target
    }) else {
        emitted.push(edge);
        return true;
    };
    if let Some(proof) = edge
        .provenance
        .as_ref()
        .and_then(|p| p["sources"][0].as_object())
        && let Some(p) = existing
            .provenance
            .as_mut()
            .filter(|p| p.as_object().is_some_and(|p| !p.is_empty()))
    {
        if p.get("sources").is_none() {
            p["sources"] = json!([]);
        }
        if let Some(sources) = p["sources"].as_array_mut() {
            if sources.len() < MAX_PROVENANCE_PER_EDGE {
                sources.push(json!(proof));
            } else {
                p["sources_omitted"] = json!(p["sources_omitted"].as_u64().unwrap_or(0) + 1);
                state.proofs_omitted += 1;
            }
        }
    }
    false
}
pub fn proof_notices(state: &SelectionState) -> Vec<String> {
    if state.proofs_omitted == 0 {
        vec![]
    } else {
        vec![format!(
            "truncated: per-edge source proof limit reached; {} proof(s) omitted",
            state.proofs_omitted
        )]
    }
}
pub fn memory_source() -> Value {
    json!({"memory_db":DB,"mode":"immutable_read_only"})
}
pub fn search_hint(anchors: &[String], purposes: &[String], reason: &str) -> Value {
    json!({"route":"search","anchors":anchors,"requested_purposes":purposes,"reason":reason,
        "scope":SCOPE,"edges":[],"notices":[],"truncated":false})
}
pub fn traverse_memory_rows(
    conn: &Connection,
    o: &Options<'_>,
    protections: &[String],
    resolved: &[String],
    purpose: &str,
    state: &mut SelectionState,
) -> Result<(Vec<Edge>, Vec<String>)> {
    let depth = o.depth.as_u64().unwrap_or(3) as usize;
    let max_edges = o.max_edges.as_u64().unwrap_or(16) as usize;
    let mut emitted = vec![];
    let mut skipped = BTreeMap::new();
    let mut notices = vec![];
    let mut frontier: BTreeSet<_> = resolved.iter().cloned().collect();
    let mut seen = frontier.clone();
    let mut seen_facts = BTreeSet::new();
    for level in 0..depth {
        let remaining = MAX_DB_ROWS.saturating_sub(state.selected_fact_ids.len());
        let mut cached = if state.selected_fact_ids.is_empty() {
            vec![]
        } else {
            relation_rows(
                conn,
                o.root,
                &frontier,
                purpose,
                Some(&state.selected_fact_ids),
                None,
                MAX_DB_ROWS as i64,
            )?
        };
        let mut fresh = relation_rows(
            conn,
            o.root,
            &frontier,
            purpose,
            None,
            Some(&state.selected_fact_ids),
            (remaining + 1).max(1) as i64,
        )?;
        let overflow = fresh.len() > remaining;
        state.incomplete |= overflow;
        fresh.truncate(remaining);
        state
            .selected_fact_ids
            .extend(fresh.iter().filter_map(|r| r[0].as_i64()));
        cached.extend(fresh);
        cached.sort_by_key(|r| r[0].as_i64());
        let mut next = BTreeSet::new();
        for row in cached {
            if !seen_facts.insert(row[0].as_i64().unwrap_or(0)) {
                continue;
            }
            let (Some(source), Some(target)) = (entity_value(&row[1]), entity_value(&row[3]))
            else {
                *skipped
                    .entry("invalid relation endpoint".into())
                    .or_default() += 1;
                continue;
            };
            let predicate = row[2].as_str().unwrap_or("");
            if emitted.len() >= max_edges
                && !emitted.iter().any(|e: &Edge| {
                    e.source == source && e.relation == predicate && e.target == target
                })
            {
                notices.push("truncated: max-edges reached; frontier remains unexplored".into());
                return Ok((emitted, r::notices(&skipped, notices)));
            }
            let (edge, reason) = validate_memory_row(conn, o.root, protections, &row, state)?;
            if let Some(reason) = reason {
                *skipped.entry(reason).or_default() += 1;
                continue;
            }
            if let Some(edge) = edge {
                let neighbour = if frontier.contains(&edge.source)
                    && r::allowed(purpose, &edge.relation, false)
                {
                    edge.target.clone()
                } else {
                    edge.source.clone()
                };
                if append_edge(&mut emitted, edge, state) && seen.insert(neighbour.clone()) {
                    next.insert(neighbour);
                }
            }
        }
        if overflow {
            notices.push(
                "truncated: memory fact row limit reached; frontier remains unexplored".into(),
            );
            break;
        }
        frontier = next;
        if frontier.is_empty() {
            break;
        }
        if level + 1 == depth
            && !relation_rows(conn, o.root, &frontier, purpose, None, None, 1)?.is_empty()
        {
            notices.push("truncated: depth reached; frontier remains unexplored".into());
            break;
        }
    }
    Ok((emitted, r::notices(&skipped, notices)))
}
fn graph_result(
    anchor: &str,
    purpose: &str,
    o: &Options<'_>,
    protections: &[String],
    edges: &[Edge],
    nodes: &[String],
) -> Result<Value> {
    let mut result = r::query_loaded(
        &json!(anchor),
        purpose,
        o,
        (edges, "memory", DB, protections),
        nodes,
    )?;
    result["scope"] = json!(SCOPE);
    result["source"] = memory_source();
    Ok(result)
}
fn with_memory<T>(root: &Path, operation: impl FnOnce(&Connection) -> Result<T>) -> Result<T> {
    let path = memory_db_path(root)?;
    // Keep semantic relation errors intact while the store checks the snapshot on both sides.
    store::immutable_snapshot_guard(&path, || {
        let connection = store::connect_read_only(&path)?;
        Ok(operation(&connection.conn))
    })
    .map_err(db_error)?
}
pub fn query_memory_relations(anchor: &Value, purpose: &str, o: &Options<'_>) -> Result<Value> {
    query_with_budget(anchor, purpose, o, MAX_TOTAL_SOURCE_BYTES)
}
pub fn query_with_budget(
    anchor: &Value,
    purpose: &str,
    o: &Options<'_>,
    budget: usize,
) -> Result<Value> {
    if !r::PURPOSES.contains(&purpose) {
        return Err(error(
            "purpose must be implementation, impact, verification, or dependencies",
        ));
    }
    let anchor = r::anchor_safe(anchor)?;
    let (depth, max_edges) = r::limits(o, purpose)?;
    let root = r::resolve_root(&json!(o.root))?;
    let protections = r::profile_protections(&root)?;
    let o = Options {
        root: &root,
        depth: json!(depth),
        ..o.clone()
    };
    let mut state = SelectionState {
        source_budget: Some(budget),
        ..Default::default()
    };
    let (resolved, edges, mut notices) = with_memory(&root, |conn| {
        let mut resolved = resolve_query_anchor(conn, &root, &protections, anchor)?;
        let mut notices = vec![];
        if resolved.len() > max_edges {
            notices.push(
                "truncated: anchor expansion limit reached; additional locators remain unexamined"
                    .into(),
            );
            resolved.truncate(max_edges);
        }
        let (edges, extra) =
            traverse_memory_rows(conn, &o, &protections, &resolved, purpose, &mut state)?;
        notices.extend(extra);
        Ok((resolved, edges, notices))
    })?;
    if state.incomplete {
        return Err(error(
            "memory relation view is incomplete; use ordinary search",
        ));
    }
    let mut result = graph_result(anchor, purpose, &o, &protections, &edges, &resolved)?;
    notices.extend(proof_notices(&state));
    notices.extend(
        result["notices"]
            .as_array()
            .into_iter()
            .flatten()
            .filter_map(|v| v.as_str().map(str::to_owned)),
    );
    result["truncated"] =
        json!(result["truncated"] == true || notices.iter().any(|s| s.starts_with("truncated:")));
    result["notices"] = json!(notices);
    Ok(result)
}
pub fn bundle_memory_relations(
    anchors: &Value,
    purposes: &Value,
    o: &Options<'_>,
) -> Result<Value> {
    let strings = |v: &Value| {
        v.as_array().and_then(|a| {
            a.iter()
                .map(|v| v.as_str().map(str::to_owned))
                .collect::<Option<Vec<_>>>()
        })
    };
    let (Some(anchors), Some(purposes)) = (strings(anchors), strings(purposes)) else {
        return Err(error("anchors and purposes must be lists"));
    };
    r::limits(o, "implementation")?;
    for anchor in &anchors {
        r::anchor_safe(&json!(anchor))?;
    }
    let anchors = r::unique(anchors);
    let purposes = r::unique(purposes);
    let search = |reason| search_hint(&anchors, &purposes, reason);
    if anchors.len() != 1 {
        return Ok(search("requires exactly one distinct anchor"));
    }
    if purposes.len() < 2 {
        return Ok(search("requires at least two distinct purposes"));
    }
    if purposes.iter().any(|p| !r::PURPOSES.contains(&p.as_str())) {
        return Ok(search("unknown purpose"));
    }
    let root = r::resolve_root(&json!(o.root))?;
    let protections = r::profile_protections(&root)?;
    let o = Options {
        root: &root,
        ..o.clone()
    };
    let work = with_memory(&root, |conn| {
        bundle_connected(conn, &anchors, &purposes, &o, &protections)
    });
    match work {
        Err(e) if e.0.contains("unavailable") || e.0.contains("cannot be read") => {
            let mut result = search("memory unavailable");
            result["notices"] = json!([e.0]);
            Ok(result)
        }
        other => other,
    }
}
fn bundle_connected(
    conn: &Connection,
    anchors: &[String],
    purposes: &[String],
    o: &Options<'_>,
    protections: &[String],
) -> Result<Value> {
    let search = |reason| search_hint(anchors, purposes, reason);
    let anchor = &anchors[0];
    let mut state = SelectionState::default();
    let mut owner_notices = BTreeMap::new();
    let mut resolution = Value::Null;
    let resolved = if r::endpoint_path(anchor, false).is_some() {
        if let Some(issue) = r::validate_endpoint(anchor, o.root, true, protections) {
            if issue == "unavailable endpoint" {
                return Ok(search("unknown anchor"));
            }
            return Err(error(&format!("anchor {issue}")));
        }
        let rows = implemented_in_rows(conn, o.root, anchor)?;
        if rows.len() > MAX_DB_ROWS {
            let mut result = search("memory relation view is incomplete");
            result["notices"] = json!([concat!(
                "truncated: memory fact row limit reached; ",
                "implementation owner frontier remains unexplored"
            )]);
            result["truncated"] = json!(true);
            return Ok(result);
        }
        let mut owners = vec![];
        for row in rows {
            state.selected_fact_ids.insert(row[0].as_i64().unwrap_or(0));
            let (edge, reason) = validate_memory_row(conn, o.root, protections, &row, &mut state)?;
            if let Some(reason) = reason {
                *owner_notices.entry(reason).or_default() += 1;
            }
            if let Some(edge) = edge {
                append_edge(&mut owners, edge, &mut state);
            }
        }
        let ids = r::unique(owners.iter().map(|e| e.source.clone()).collect());
        if state.incomplete || ids.len() != 1 {
            let mut result = search(if state.incomplete {
                "memory relation view is incomplete"
            } else if owners.is_empty() {
                "unknown anchor"
            } else {
                "ambiguous implementation owner"
            });
            result["notices"] = json!(r::notices(&owner_notices, vec![]));
            result["truncated"] = json!(state.incomplete);
            return Ok(result);
        }
        resolution = owners[0].as_dict();
        ids[0].clone()
    } else {
        let exact = eligible_nodes(conn, o.root, anchor)?;
        if exact.is_empty() {
            return Ok(search("unknown anchor"));
        }
        exact[0].clone()
    };
    let nodes = vec![resolved.clone()];
    let mut items = vec![];
    let mut notices = r::notices(&owner_notices, vec![]);
    for p in purposes {
        let (depth, _) = r::limits(o, p)?;
        let facet_o = Options {
            depth: json!(depth),
            ..o.clone()
        };
        let (edges, ns) = traverse_memory_rows(conn, &facet_o, protections, &nodes, p, &mut state)?;
        items.push((p, edges, ns));
    }
    if state.incomplete {
        let mut result = search("memory relation view is incomplete");
        notices.extend(items.iter().flat_map(|(_, _, ns)| ns.iter().cloned()));
        notices.extend(proof_notices(&state));
        result["notices"] = json!(notices);
        result["truncated"] = json!(true);
        return Ok(result);
    }
    let mut merged: Vec<Value> = vec![];
    let mut facets = vec![];
    let mut omitted = false;
    for (p, edges, mut ns) in items {
        let item = graph_result(&resolved, p, o, protections, &edges, &nodes)?;
        ns.extend(
            item["notices"]
                .as_array()
                .into_iter()
                .flatten()
                .filter_map(|v| v.as_str().map(str::to_owned)),
        );
        let available = item["edges"].as_array().map_or(0, Vec::len);
        let mut contributed = 0;
        for edge in item["edges"].as_array().into_iter().flatten() {
            if let Some(existing) = merged.iter_mut().find(|e| {
                ["source", "relation", "target"]
                    .iter()
                    .all(|k| e[*k] == edge[*k])
            }) {
                if let Some(ps) = existing["purposes"].as_array_mut() {
                    ps.push(json!(p));
                }
            } else if merged.len() < o.max_edges.as_u64().unwrap_or(16) as usize {
                let mut e = edge.clone();
                e["purposes"] = json!([p]);
                merged.push(e);
                contributed += 1;
            } else {
                omitted = true;
            }
        }
        facets.push(
            json!({"purpose":p,"available_count":available,"edge_count":contributed,
            "coverage":if omitted || ns.iter().any(|n| n.starts_with("truncated:")) {"truncated"}
                else if available == 0 {"empty"} else {"bounded"},"notices":ns}),
        );
        notices.extend(ns);
    }
    if facets.iter().any(|f| f["available_count"] == 0) {
        let mut result = search("one or more requested facets have no declared evidence");
        notices.extend(proof_notices(&state));
        notices = r::unique(notices);
        result["truncated"] = json!(notices.iter().any(|n| n.starts_with("truncated:")));
        result["notices"] = json!(notices);
        return Ok(result);
    }
    if omitted {
        notices.push("truncated: global max-edges reached; facet coverage incomplete".into());
    }
    notices.extend(proof_notices(&state));
    notices = r::unique(notices);
    let mut result = json!({"route":"memory","anchor":anchor,"resolved_anchor":resolved,
        "resolution":resolution,"requested_purposes":purposes,"facets":facets,"scope":SCOPE,
        "source":memory_source(),"edges":merged,"notices":notices,
        "truncated":notices.iter().any(|n| n.starts_with("truncated:"))});
    r::refresh_bundle_facets(&mut result);
    Ok(result)
}
