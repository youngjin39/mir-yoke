//! Library-only archive helpers and vector/FTS indexer; Python remains the live reference.
#![forbid(unsafe_code)]
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
impl From<rusqlite::Error> for HelperError {
    fn from(e: rusqlite::Error) -> Self {
        let kind = if matches!(&e, rusqlite::Error::SqliteFailure(code, _)
            if code.code == rusqlite::ErrorCode::ConstraintViolation)
        {
            "IntegrityError"
        } else {
            "OperationalError"
        };
        Self {
            kind,
            message: e.to_string(),
        }
    }
}
#[derive(Clone, Debug)]
pub struct Registration {
    pub slug: String,
    pub root_path: String,
    pub mode: String,
    pub owner: String,
    pub glob_include: Vec<String>,
    pub glob_exclude: Vec<String>,
    pub historical_glob: Vec<String>,
    pub chunk_size: i64,
    pub chunk_overlap: i64,
}
#[derive(Debug)]
pub struct ArchiveRow {
    pub id: i64,
    pub registration: Registration,
}
#[derive(Debug, Default)]
pub struct ScanResult {
    pub inserted: usize,
    pub deleted: usize,
    pub reindexed: usize,
    pub unchanged: usize,
    pub failed: Vec<(String, String)>,
}
impl Serialize for ScanResult {
    fn serialize<S: serde::Serializer>(
        &self,
        serializer: S,
    ) -> std::result::Result<S::Ok, S::Error> {
        serde_json::json!({"inserted":self.inserted,"deleted":self.deleted,
            "reindexed":self.reindexed,"unchanged":self.unchanged,"failed":self.failed})
        .serialize(serializer)
    }
}
pub type EmbedFn<'a> = dyn FnMut(&[String]) -> Result<Vec<Vec<f64>>> + 'a;
#[derive(Debug, Default)]
pub struct VectorReindexResult {
    pub indexed: i64,
    pub eligible: i64,
    pub reindexed: usize,
    pub unchanged: usize,
    pub failed: Vec<(String, String)>,
}
impl Serialize for VectorReindexResult {
    fn serialize<S: serde::Serializer>(
        &self,
        serializer: S,
    ) -> std::result::Result<S::Ok, S::Error> {
        serde_json::json!({"indexed":self.indexed,"eligible":self.eligible,
            "reindexed":self.reindexed,"unchanged":self.unchanged,"failed":self.failed})
        .serialize(serializer)
    }
}
pub fn ensure_external_vec_table(conn: &rusqlite::Connection, dim: usize) -> Result<()> {
    super::vector_index::ensure_vec_table(conn, dim, "external_chunks_vec").map_err(vector_error)
}
fn vector_error(e: super::vector_index::Error) -> HelperError {
    HelperError {
        kind: e.python_class(),
        message: e.to_string(),
    }
}
pub struct ExternalStore<'a> {
    pub connection: &'a super::store::Connection,
    clock: &'a dyn Fn() -> String,
}
fn store_error(message: impl Into<String>) -> HelperError {
    HelperError {
        kind: "ExternalStoreError",
        message: message.into(),
    }
}
impl<'a> ExternalStore<'a> {
    pub fn new(
        connection: &'a super::store::Connection,
        clock: &'a dyn Fn() -> String,
    ) -> Result<Self> {
        if connection.vec_available {
            ensure_external_vec_table(&connection.conn, DEFAULT_EMBED_DIM)?;
        }
        Ok(Self { connection, clock })
    }
    pub fn register(&self, a: &Registration) -> Result<i64> {
        use rusqlite::{OptionalExtension, params};
        if !["indexed", "immutable"].contains(&a.mode.as_str()) {
            return Err(HelperError {
                kind: "ValueError",
                message: format!("invalid mode {}", crate::executor_execute::repr(&a.mode)),
            });
        }
        let c = &self.connection.conn;
        let joined = |v: &[String]| (!v.is_empty()).then(|| v.join(","));
        let (inc, exc, hist) = (
            joined(&a.glob_include),
            joined(&a.glob_exclude),
            joined(&a.historical_glob),
        );
        let prior = c.query_row(
            "SELECT root_path,glob_include,glob_exclude,historical_glob,chunk_size,chunk_overlap
             FROM external_archives WHERE slug=?", [&a.slug], |r| Ok((
                r.get::<_, String>(0)?, r.get::<_, Option<String>>(1)?,
                r.get::<_, Option<String>>(2)?, r.get::<_, Option<String>>(3)?,
                r.get::<_, i64>(4)?, r.get::<_, i64>(5)?))).optional()?;
        let tx = c.unchecked_transaction()?;
        let id: i64 = tx.query_row(
            "INSERT INTO external_archives
             (slug,root_path,mode,glob_include,glob_exclude,historical_glob,
              chunk_size,chunk_overlap,owner,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)
             ON CONFLICT(slug) DO UPDATE SET root_path=excluded.root_path,mode=excluded.mode,
             glob_include=excluded.glob_include,glob_exclude=excluded.glob_exclude,
             historical_glob=excluded.historical_glob,chunk_size=excluded.chunk_size,
             chunk_overlap=excluded.chunk_overlap,owner=excluded.owner RETURNING id",
            params![
                a.slug,
                a.root_path,
                a.mode,
                inc,
                exc,
                hist,
                a.chunk_size,
                a.chunk_overlap,
                a.owner,
                (self.clock)()
            ],
            |r| r.get(0),
        )?;
        if let Some(p) = prior {
            let content_changed = (p.0, p.1, p.2, p.4, p.5)
                != (a.root_path.clone(), inc, exc, a.chunk_size, a.chunk_overlap);
            if content_changed {
                tx.execute(
                    "INSERT OR REPLACE INTO external_store_meta(key,value) VALUES (?,'1')",
                    [format!("{ARCHIVE_CONTENT_REINDEX_PREFIX}{id}")],
                )?;
            }
            if content_changed || p.3 != hist {
                tx.execute(
                    "DELETE FROM external_store_meta WHERE key=?",
                    [format!("{ARCHIVE_METADATA_VERSION_PREFIX}{id}")],
                )?;
            }
        }
        tx.commit()?;
        Ok(id)
    }
    pub fn fetch_archive(&self, id: i64) -> Result<ArchiveRow> {
        use rusqlite::OptionalExtension;
        self.connection
            .conn
            .query_row(
                "SELECT slug,root_path,mode,glob_include,glob_exclude,historical_glob,
             chunk_size,chunk_overlap,owner FROM external_archives WHERE id=?",
                [id],
                |r| {
                    Ok(ArchiveRow {
                        id,
                        registration: Registration {
                            slug: r.get(0)?,
                            root_path: r.get(1)?,
                            mode: r.get(2)?,
                            glob_include: compile_globs(r.get::<_, Option<String>>(3)?.as_deref()),
                            glob_exclude: compile_globs(r.get::<_, Option<String>>(4)?.as_deref()),
                            historical_glob: compile_globs(
                                r.get::<_, Option<String>>(5)?.as_deref(),
                            ),
                            chunk_size: r.get(6)?,
                            chunk_overlap: r.get(7)?,
                            owner: r.get(8)?,
                        },
                    })
                },
            )
            .optional()?
            .ok_or_else(|| store_error(format!("archive_id {id} not found")))
    }
    pub fn read_file(&self, archive: &ArchiveRow, rel: &str) -> Result<(String, String, usize)> {
        let authored = Path::new(&archive.registration.root_path);
        let root =
            crate::supply::resolve(&std::env::current_dir().map_err(regex_error)?.join(authored))
                .map_err(|e| store_error(format!("{e:?}")))?;
        let path = root.join(rel);
        if path.is_symlink() {
            return Err(store_error(format!(
                "{rel}: symbolic links are not indexed"
            )));
        }
        let resolved = crate::supply::resolve(&path).map_err(|e| store_error(format!("{e:?}")))?;
        if !resolved.starts_with(&root) {
            return Err(store_error(format!(
                "{rel}: resolved path escapes archive root"
            )));
        }
        let display_path = resolved
            .to_str()
            .ok_or_else(|| store_error("archive path is not UTF-8"))?
            .to_owned();
        let data = std::fs::read(&resolved).map_err(|e| HelperError {
            kind: if e.kind() == std::io::ErrorKind::NotFound {
                "FileNotFoundError"
            } else {
                "OSError"
            },
            message: if e.kind() == std::io::ErrorKind::NotFound {
                format!(
                    "[Errno 2] No such file or directory: {}",
                    crate::executor_execute::repr(&display_path)
                )
            } else {
                e.to_string()
            },
        })?;
        let text = std::str::from_utf8(&data).map_err(|e| {
            let i = e.valid_up_to();
            let reason = if e.error_len().is_none() {
                "unexpected end of data"
            } else if (0xc2..=0xf4).contains(&data[i]) {
                "invalid continuation byte"
            } else {
                "invalid start byte"
            };
            store_error(format!(
                "{rel}: not utf-8 ('utf-8' codec can't decode byte 0x{:02x} \
                in position {i}: {reason})",
                data[i]
            ))
        })?;
        Ok((text.into(), sha256(&data), data.len()))
    }
    fn document_metadata(&self, a: &ArchiveRow, rel: &str, text: &str) -> Result<Vec<Value>> {
        let logical = logical_metadata_path(&a.registration.root_path, rel);
        let category = derive_doc_category(&logical);
        let layer = derive_layer(&logical);
        let (title, fm) = extract_title_and_frontmatter(text);
        let front: Value = fm
            .as_deref()
            .and_then(|v| serde_json::from_str(v).ok())
            .unwrap_or(Value::Null);
        let field = |key: &str| front[key].as_str().unwrap_or("").trim().to_lowercase();
        let historical = category == Some("archive")
            || HISTORICAL_STATUSES.contains(&field("status").as_str())
            || field("source") == "mirrored-summary"
            || matches_regex_any(
                &logical,
                &compile_pattern_set(&a.registration.historical_glob)?,
            )?;
        Ok(vec![
            serde_json::json!("your-harness"),
            serde_json::json!(category),
            serde_json::json!(layer),
            serde_json::json!(if historical { "expired" } else { "active" }),
            serde_json::json!(title),
            serde_json::json!(fm),
        ])
    }
    fn metadata_params(values: &[Value]) -> Vec<Option<&str>> {
        values.iter().map(Value::as_str).collect()
    }
    pub fn index_file(&self, a: &ArchiveRow, rel: &str) -> Result<i64> {
        self.index_file_with_vectors(a, rel, None, None)
    }
    pub fn index_file_with_vectors(
        &self,
        a: &ArchiveRow,
        rel: &str,
        embed_fn: Option<&mut EmbedFn<'_>>,
        batch_size: Option<usize>,
    ) -> Result<i64> {
        use rusqlite::params;
        let (text, hash, len) = self.read_file(a, rel)?;
        let chunks = chunk_text(
            &text,
            a.registration.chunk_size,
            a.registration.chunk_overlap,
        )?;
        let tx = self.connection.conn.unchecked_transaction()?;
        let values = self.document_metadata(a, rel, &text)?;
        let m = Self::metadata_params(&values);
        tx.execute(
            "INSERT INTO external_documents
            (archive_id,relative_path,file_hash,byte_len,vec_indexed_at,source_slug,
             doc_category,layer,status,title,frontmatter_json) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            params![
                a.id,
                rel,
                hash,
                len as i64,
                (embed_fn.is_some() && self.connection.vec_available).then(|| (self.clock)()),
                m[0],
                m[1],
                m[2],
                m[3],
                m[4],
                m[5]
            ],
        )?;
        let id = tx.last_insert_rowid();
        self.insert_chunks(id, &chunks, embed_fn, batch_size)?;
        tx.commit()?;
        Ok(id)
    }
    fn insert_chunks(
        &self,
        doc: i64,
        chunks: &[Chunk],
        embed_fn: Option<&mut EmbedFn<'_>>,
        batch_size: Option<usize>,
    ) -> Result<()> {
        use rusqlite::params;
        let c = &self.connection.conn;
        if chunks.is_empty() {
            return Ok(());
        }
        let embeddings = if let Some(encode) = embed_fn.filter(|_| self.connection.vec_available) {
            let texts: Vec<_> = chunks.iter().map(|ch| ch.text.clone()).collect();
            let mut embeddings = Vec::new();
            for batch in texts.chunks(batch_size.filter(|n| *n > 0).unwrap_or(texts.len())) {
                embeddings.extend(encode(batch)?);
            }
            if embeddings.len() != chunks.len() {
                return Err(store_error(format!(
                    "embed_fn returned {} vectors for {} chunks",
                    embeddings.len(),
                    chunks.len()
                )));
            }
            Some(embeddings)
        } else {
            None
        };
        for (i, ch) in chunks.iter().enumerate() {
            c.execute(
                "INSERT INTO external_chunks
                (document_id,chunk_index,byte_start,byte_end,text_hash) VALUES (?,?,?,?,?)",
                params![
                    doc,
                    ch.chunk_index as i64,
                    ch.byte_start as i64,
                    ch.byte_end as i64,
                    ch.text_hash
                ],
            )?;
            let id = c.last_insert_rowid();
            c.execute(
                "INSERT INTO external_chunks_fts(rowid,content) VALUES (?,?)",
                params![id, ch.text],
            )?;
            if let Some(embeddings) = &embeddings {
                let vector = &embeddings[i];
                super::vector_index::validate_embedding(vector, DEFAULT_EMBED_DIM)
                    .map_err(vector_error)?;
                c.execute(
                    "INSERT INTO external_chunks_vec(rowid,embedding) VALUES (?,?)",
                    params![id, super::vector_index::pack_vector(vector)],
                )?;
            }
        }
        Ok(())
    }
    fn delete_chunk_rowid(&self, id: i64) -> Result<()> {
        self.connection
            .conn
            .execute("DELETE FROM external_chunks_fts WHERE rowid=?", [id])?;
        if self.connection.vec_available {
            self.connection
                .conn
                .execute("DELETE FROM external_chunks_vec WHERE rowid=?", [id])?;
        }
        Ok(())
    }
    fn delete_document_chunks(&self, doc: i64) -> Result<()> {
        let c = &self.connection.conn;
        let ids = c
            .prepare("SELECT id FROM external_chunks WHERE document_id=?")?
            .query_map([doc], |r| r.get::<_, i64>(0))?
            .collect::<std::result::Result<Vec<_>, _>>()?;
        for id in ids {
            self.delete_chunk_rowid(id)?;
        }
        Ok(())
    }
    pub fn cascade_delete_document(&self, archive: i64, rel: &str) -> Result<()> {
        use rusqlite::{OptionalExtension, params};
        let tx = self.connection.conn.unchecked_transaction()?;
        let doc = tx
            .query_row(
                "SELECT id FROM external_documents WHERE archive_id=? AND relative_path=?",
                params![archive, rel],
                |r| r.get::<_, i64>(0),
            )
            .optional()?;
        if let Some(doc) = doc {
            self.delete_document_chunks(doc)?;
            tx.execute("DELETE FROM external_documents WHERE id=?", [doc])?;
        }
        tx.commit()?;
        Ok(())
    }
    pub fn reindex_if_changed(
        &self,
        a: &ArchiveRow,
        rel: &str,
        forced: bool,
        force_content: bool,
    ) -> Result<bool> {
        self.reindex_with_vectors(a, rel, forced, force_content, None, None)
    }
    fn reindex_with_vectors(
        &self,
        a: &ArchiveRow,
        rel: &str,
        forced: bool,
        force_content: bool,
        embed_fn: Option<&mut EmbedFn<'_>>,
        batch_size: Option<usize>,
    ) -> Result<bool> {
        use rusqlite::{OptionalExtension, params};
        let (text, hash, len) = self.read_file(a, rel)?;
        let row = self.connection.conn.query_row(
            "SELECT id,file_hash FROM external_documents WHERE archive_id=? AND relative_path=?",
            params![a.id,rel],|r| Ok((r.get::<_,i64>(0)?,r.get::<_,String>(1)?))).optional()?;
        let Some((doc, old_hash)) = row else {
            self.index_file_with_vectors(a, rel, embed_fn, None)?;
            return Ok(true);
        };
        if old_hash == hash && !force_content && !forced {
            return Ok(false);
        }
        let values = self.document_metadata(a, rel, &text)?;
        let m = Self::metadata_params(&values);
        let metadata_only = old_hash == hash && !force_content;
        let chunks = if metadata_only {
            vec![]
        } else {
            chunk_text(
                &text,
                a.registration.chunk_size,
                a.registration.chunk_overlap,
            )?
        };
        let tx = self.connection.conn.unchecked_transaction()?;
        if metadata_only {
            tx.execute(
                "UPDATE external_documents SET source_slug=?,doc_category=?,layer=?,
                status=?,title=?,frontmatter_json=? WHERE id=?",
                params![m[0], m[1], m[2], m[3], m[4], m[5], doc],
            )?;
        } else {
            self.delete_document_chunks(doc)?;
            tx.execute("DELETE FROM external_chunks WHERE document_id=?", [doc])?;
            tx.execute(
                "UPDATE external_documents SET file_hash=?,byte_len=?,vec_indexed_at=?,
                source_slug=?,doc_category=?,layer=?,status=?,title=?,frontmatter_json=?
                WHERE id=?",
                params![
                    hash,
                    len as i64,
                    (embed_fn.is_some() && self.connection.vec_available).then(|| (self.clock)()),
                    m[0],
                    m[1],
                    m[2],
                    m[3],
                    m[4],
                    m[5],
                    doc
                ],
            )?;
            self.insert_chunks(doc, &chunks, embed_fn, batch_size)?;
        }
        tx.commit()?;
        Ok(true)
    }
    pub fn vector_coverage(&self, archive: i64) -> Result<(i64, i64)> {
        let eligible = self.connection.conn.query_row(
            "SELECT COUNT(*) FROM external_chunks c
            JOIN external_documents d ON d.id=c.document_id WHERE d.archive_id=?",
            [archive],
            |r| r.get(0),
        )?;
        let indexed = if self.connection.vec_available {
            self.connection.conn.query_row(
                "SELECT COUNT(*) FROM external_chunks_vec v
                JOIN external_chunks c ON c.id=v.rowid
                JOIN external_documents d ON d.id=c.document_id WHERE d.archive_id=?",
                [archive],
                |r| r.get(0),
            )?
        } else {
            0
        };
        Ok((indexed, eligible))
    }
    pub fn ensure_encoder_fingerprint(&self, fingerprint: Option<&str>) -> Result<()> {
        let requested = fingerprint.unwrap_or("").trim();
        if requested.is_empty() {
            return Err(store_error(
                "vector indexing requires an encoder fingerprint",
            ));
        }
        let stored = self.meta(EMBEDDING_FINGERPRINT_KEY)?;
        let count: i64 = self.connection.conn.query_row(
            "SELECT COUNT(*) FROM external_chunks_vec",
            [],
            |r| r.get(0),
        )?;
        if stored.as_deref() == Some(requested) {
            return Ok(());
        }
        if count > 0 {
            self.validate_encoder_fingerprint(Some(requested))?;
        }
        self.connection.conn.execute(
            "INSERT OR REPLACE INTO external_store_meta(key,value) VALUES (?,?)",
            [EMBEDDING_FINGERPRINT_KEY, requested],
        )?;
        Ok(())
    }
    pub fn validate_encoder_fingerprint(&self, fingerprint: Option<&str>) -> Result<()> {
        let count: i64 = self.connection.conn.query_row(
            "SELECT COUNT(*) FROM external_chunks_vec",
            [],
            |r| r.get(0),
        )?;
        if count == 0 {
            return Ok(());
        }
        let requested = fingerprint.unwrap_or("").trim();
        if requested.is_empty() {
            return Err(store_error(
                "vector retrieval requires an encoder fingerprint",
            ));
        }
        let stored = self.meta(EMBEDDING_FINGERPRINT_KEY)?;
        if stored.is_none() {
            return Err(store_error(
                "existing vectors have no recorded encoder fingerprint; \
                build a fresh or versioned index",
            ));
        }
        if stored.as_deref() != Some(requested) {
            return Err(store_error(
                "encoder fingerprint differs from the active vector index; \
                build a fresh or versioned index",
            ));
        }
        Ok(())
    }
    pub fn replace_document_vectors(
        &self,
        archive: &ArchiveRow,
        doc: i64,
        rel: &str,
        expected_hash: &str,
        embed_fn: &mut EmbedFn<'_>,
    ) -> Result<()> {
        let (text, hash, _) = self.read_file(archive, rel)?;
        if hash != expected_hash {
            return Err(store_error(
                "source changed; run 'mir context sync' before vector backfill",
            ));
        }
        let chunks = chunk_text(
            &text,
            archive.registration.chunk_size,
            archive.registration.chunk_overlap,
        )?;
        let tx = self.connection.conn.unchecked_transaction()?;
        self.delete_document_chunks(doc)?;
        tx.execute("DELETE FROM external_chunks WHERE document_id=?", [doc])?;
        self.insert_chunks(doc, &chunks, Some(embed_fn), None)?;
        tx.execute(
            "UPDATE external_documents SET vec_indexed_at=? WHERE id=?",
            rusqlite::params![(self.clock)(), doc],
        )?;
        tx.commit()?;
        Ok(())
    }
    pub fn reindex_missing_vectors(
        &self,
        archive_id: i64,
        embed_fn: Option<&mut EmbedFn<'_>>,
        fingerprint: &str,
    ) -> Result<VectorReindexResult> {
        let encode = embed_fn
            .ok_or_else(|| store_error("missing-vector reindex requires an embedding function"))?;
        if !self.connection.vec_available {
            return Err(store_error("missing-vector reindex requires sqlite-vec"));
        }
        let archive = self.fetch_archive(archive_id)?;
        self.ensure_encoder_fingerprint(Some(fingerprint))?;
        let rows = self.connection.conn.prepare(
            "SELECT d.id,d.relative_path,d.file_hash,d.vec_indexed_at,COUNT(c.id),COUNT(v.rowid)
             FROM external_documents d LEFT JOIN external_chunks c ON c.document_id=d.id
             LEFT JOIN external_chunks_vec v ON v.rowid=c.id WHERE d.archive_id=?
             GROUP BY d.id ORDER BY d.relative_path")?.query_map([archive_id], |r| Ok((
                r.get::<_,i64>(0)?,r.get::<_,String>(1)?,r.get::<_,String>(2)?,
                r.get::<_,Option<String>>(3)?,r.get::<_,i64>(4)?,r.get::<_,i64>(5)?)))?
            .collect::<std::result::Result<Vec<_>,_>>()?;
        let mut result = VectorReindexResult::default();
        for (doc, rel, hash, stamp, chunks, vectors) in rows {
            if chunks == 0 || (chunks == vectors && stamp.is_some()) {
                result.unchanged += 1;
                continue;
            }
            match self.replace_document_vectors(&archive, doc, &rel, &hash, encode) {
                Ok(()) => result.reindexed += 1,
                Err(e) => result.failed.push((rel, e.message)),
            }
        }
        (result.indexed, result.eligible) = self.vector_coverage(archive_id)?;
        Ok(result)
    }
    pub fn scan(&self, id: i64, embed_fn: Option<&mut EmbedFn<'_>>) -> Result<ScanResult> {
        self.scan_with_vectors(id, embed_fn, None, None)
    }
    pub fn scan_with_vectors(
        &self,
        id: i64,
        mut embed_fn: Option<&mut EmbedFn<'_>>,
        fingerprint: Option<&str>,
        batch_size: Option<usize>,
    ) -> Result<ScanResult> {
        use std::collections::BTreeSet;
        let archive = self.fetch_archive(id)?;
        if embed_fn.is_some() && self.connection.vec_available {
            self.ensure_encoder_fingerprint(fingerprint)?;
        }
        let a = &archive.registration;
        let fs: BTreeSet<_> =
            walk_archive(Path::new(&a.root_path), &a.glob_include, &a.glob_exclude)?
                .into_iter()
                .collect();
        let c = &self.connection.conn;
        let stored: BTreeSet<String> = c
            .prepare("SELECT relative_path FROM external_documents WHERE archive_id=?")?
            .query_map([id], |r| r.get(0))?
            .collect::<std::result::Result<_, _>>()?;
        let meta = format!("{ARCHIVE_METADATA_VERSION_PREFIX}{id}");
        let content = format!("{ARCHIVE_CONTENT_REINDEX_PREFIX}{id}");
        let version = self.meta("schema_metadata_version")?;
        let forced = !stored.is_empty()
            && self.meta(&meta)?.is_none_or(|v| {
                int_ver(&Value::String(v))
                    < int_ver(&Value::String(CURRENT_METADATA_VERSION.into()))
            });
        let force_content = self.meta(&content)?.is_some();
        let mut result = ScanResult::default();
        for rel in stored.difference(&fs) {
            match self.cascade_delete_document(id, rel) {
                Ok(()) => result.deleted += 1,
                Err(e) => result.failed.push((rel.clone(), format!("delete: {e}"))),
            }
        }
        for rel in fs.difference(&stored) {
            match self.index_file_with_vectors(
                &archive,
                rel,
                embed_fn.as_mut().map(|f| &mut **f as &mut EmbedFn<'_>),
                batch_size,
            ) {
                Ok(_) => result.inserted += 1,
                Err(e) => result.failed.push((rel.clone(), format!("insert: {e}"))),
            }
        }
        for rel in fs.intersection(&stored) {
            match self.reindex_with_vectors(
                &archive,
                rel,
                forced,
                force_content,
                embed_fn.as_mut().map(|f| &mut **f as &mut EmbedFn<'_>),
                batch_size,
            ) {
                Ok(true) => result.reindexed += 1,
                Ok(false) => result.unchanged += 1,
                Err(e) => result.failed.push((rel.clone(), format!("reindex: {e}"))),
            }
        }
        let tx = c.unchecked_transaction()?;
        if result.failed.is_empty() {
            tx.execute(
                "INSERT OR REPLACE INTO external_store_meta(key,value) VALUES (?,?)",
                [&meta, CURRENT_METADATA_VERSION],
            )?;
            tx.execute("DELETE FROM external_store_meta WHERE key=?", [&content])?;
        } else {
            tx.execute("DELETE FROM external_store_meta WHERE key=?", [&meta])?;
        }
        let versions = tx
            .prepare(
                "SELECT m.value FROM external_archives a
            LEFT JOIN external_store_meta m ON m.key=? || CAST(a.id AS TEXT)",
            )?
            .query_map([ARCHIVE_METADATA_VERSION_PREFIX], |r| {
                r.get::<_, Option<String>>(0)
            })?
            .collect::<std::result::Result<Vec<_>, _>>()?;
        let current = int_ver(&Value::String(CURRENT_METADATA_VERSION.into()));
        let all_current = !versions.is_empty()
            && versions.iter().all(|v| {
                v.as_ref()
                    .is_some_and(|v| int_ver(&Value::String(v.clone())) >= current)
            });
        let global = if all_current {
            CURRENT_METADATA_VERSION.into()
        } else {
            int_ver(&Value::String(version.unwrap_or_default()))
                .min((current - 1).max(0))
                .to_string()
        };
        tx.execute(
            "INSERT OR REPLACE INTO external_store_meta(key,value)
            VALUES ('schema_metadata_version',?)",
            [global],
        )?;
        tx.execute(
            "UPDATE external_archives SET last_scanned_at=? WHERE id=?",
            rusqlite::params![(self.clock)(), id],
        )?;
        tx.commit()?;
        Ok(result)
    }
    fn meta(&self, key: &str) -> Result<Option<String>> {
        use rusqlite::OptionalExtension;
        Ok(self
            .connection
            .conn
            .query_row(
                "SELECT value FROM external_store_meta WHERE key=?",
                [key],
                |r| r.get(0),
            )
            .optional()?)
    }
}
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

/// Metadata-only FTS search leaf of ExternalStore.search, with no vector backend.
#[derive(Debug)]
pub struct SearchHit {
    pub archive_slug: String,
    pub relative_path: String,
    pub byte_start: usize,
    pub byte_end: usize,
    pub score: f64,
    pub status: String,
    pub root: String,
    pub file_hash: String,
}
pub fn search_fts(
    conn: &rusqlite::Connection,
    query: &str,
    k: i64,
    scopes: &[String],
    history: bool,
) -> std::result::Result<Vec<SearchHit>, Box<dyn std::error::Error>> {
    if k <= 0 {
        return Ok(Vec::new());
    }
    let query = super::distill::sanitize_fts_query(query)
        .map_err(|e| std::io::Error::other(format!("{e:?}")))?;
    let mut stmt = conn.prepare(
        "SELECT c.id, a.slug, a.root_path, d.relative_path, c.byte_start, c.byte_end,
         d.status, d.file_hash, d.frontmatter_json, s.rank
         FROM external_chunks_fts s JOIN external_chunks c ON c.id=s.rowid
         JOIN external_documents d ON d.id=c.document_id
         JOIN external_archives a ON a.id=d.archive_id
         WHERE external_chunks_fts MATCH ? ORDER BY s.rank, c.id ASC",
    )?;
    let rows = stmt.query_map([query], |r| {
        Ok((
            r.get::<_, i64>(0)?,
            SearchHit {
                archive_slug: r.get(1)?,
                root: r.get(2)?,
                relative_path: r.get(3)?,
                byte_start: r.get::<_, i64>(4)? as usize,
                byte_end: r.get::<_, i64>(5)? as usize,
                status: r.get(6)?,
                file_hash: r.get(7)?,
                score: 0.0,
            },
            r.get::<_, Option<String>>(8)?,
            r.get::<_, f64>(9)?,
        ))
    })?;
    let mut candidates = Vec::new();
    let (mut previous, mut tie) = (None, 0);
    for row in rows {
        let (id, mut hit, frontmatter, rank) = row?;
        let logical = logical_metadata_path(&hit.root, &hit.relative_path);
        if !history && (hit.status != "active" || is_history_path(&logical)) {
            continue;
        }
        if !scopes.is_empty() {
            let mut allowed = false;
            for scope in scopes {
                allowed |= is_within_path_scope(&logical, scope)?;
            }
            if !allowed {
                continue;
            }
        }
        let position = candidates.len();
        if previous != Some(rank) {
            tie = position;
            previous = Some(rank);
        }
        hit.score = 1.0 / (60.0 + tie as f64);
        candidates.push((id, hit, doc_created_ordinal(frontmatter.as_deref())));
        if candidates.len() as i64 >= k.saturating_mul(3) {
            break;
        }
    }
    candidates.sort_by(|a, b| {
        b.1.score
            .total_cmp(&a.1.score)
            .then(b.2.cmp(&a.2))
            .then(a.0.cmp(&b.0))
    });
    candidates.truncate(k as usize);
    Ok(candidates.into_iter().map(|(_, hit, _)| hit).collect())
}
