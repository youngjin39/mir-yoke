-- Migration 015 — external_store (ADR 1) + phase_gate_lock (ADR 3, single wave · Third Review TN3).
-- design v0.6 §4.1/§4.3 · decisions/adr-01-external-store.md · decisions/adr-03-phase-gate-policy.md
--
-- vec0 virtual table (external_chunks_vec) is created at runtime by
-- ensure_external_vec_table() in external_store.py — NOT here. sqlite-vec
-- is an optional extension and migration-time CREATE would hard-fail in
-- environments without the extension (design §9.9 graceful degradation
-- · Third Review TB1, follows the facts_vec pattern from store.py).


-- external_archives: registered external archive roots.
CREATE TABLE external_archives (
  id                INTEGER PRIMARY KEY,
  slug              TEXT NOT NULL UNIQUE,
  root_path         TEXT NOT NULL,
  mode              TEXT NOT NULL CHECK (mode IN ('indexed', 'immutable')),
  glob_include      TEXT,                     -- comma-separated globs
  glob_exclude      TEXT,
  chunk_size        INTEGER NOT NULL DEFAULT 800,
  chunk_overlap     INTEGER NOT NULL DEFAULT 100,
  owner             TEXT NOT NULL,            -- 'family:<slug>'
  created_at        TEXT NOT NULL,
  last_scanned_at   TEXT
);

-- external_documents: 1:1 with files inside an archive. Body is NOT stored.
CREATE TABLE external_documents (
  id                INTEGER PRIMARY KEY,
  archive_id        INTEGER NOT NULL REFERENCES external_archives(id) ON DELETE CASCADE,
  relative_path     TEXT NOT NULL,
  file_hash         TEXT NOT NULL,            -- sha256 of file body
  byte_len          INTEGER,
  title             TEXT,
  frontmatter_json  TEXT,
  vec_indexed_at    TEXT,
  UNIQUE (archive_id, relative_path)
);

CREATE INDEX idx_external_documents_archive ON external_documents (archive_id);

-- external_chunks: embedding-target chunks. body is NOT stored; only offsets.
CREATE TABLE external_chunks (
  id            INTEGER PRIMARY KEY,
  document_id   INTEGER NOT NULL REFERENCES external_documents(id) ON DELETE CASCADE,
  chunk_index   INTEGER NOT NULL,
  byte_start    INTEGER NOT NULL,
  byte_end      INTEGER NOT NULL,
  text_hash     TEXT NOT NULL,
  UNIQUE (document_id, chunk_index)
);

CREATE INDEX idx_external_chunks_document ON external_chunks (document_id);

-- FTS5 contentless + contentless_delete=1 (SQLite 3.43+): stores rowid +
-- tokenized content only, no body, but supports ``DELETE FROM`` by rowid
-- **and by ``MATCH`` queries** (wave 2 TM2). Standard contentless forbids
-- DELETE, but under the contentless_delete=1 option, both ``DELETE FROM
-- external_chunks_fts WHERE rowid = ?`` and ``DELETE FROM ... WHERE
-- external_chunks_fts MATCH '...'`` behave like ordinary DELETE. The scan()
-- reindexing path uses rowid-based deletes.
--
-- Rationale (Third Review TH1):
--   external_chunks holds path+offset, never body. A shadowed (content=)
--   pattern needs a text column to pull from, which external_chunks lacks.
--   Contentless keeps the file-owned invariant intact; contentless_delete
--   gives back the ordinary DELETE semantics scan() relies on, avoiding
--   the old ``INSERT INTO fts(fts, rowid, <col>) VALUES('delete', ...)``
--   dance that would otherwise force us to cache the original text.
--
-- Sync: no triggers. scan() in external_store.py issues explicit INSERT/DELETE
-- inside a single transaction (ADR 1 §2.6), keeping rowids aligned with
-- external_chunks.id.
CREATE VIRTUAL TABLE external_chunks_fts USING fts5(
  content,
  content='',
  contentless_delete = 1,
  tokenize = 'unicode61'
);


-- phase_gate_lock: single-row advisory lock for `mir phase advance`
-- concurrent-race guard (ADR 3 §2.4, self-review H6). BEGIN IMMEDIATE +
-- UPDATE gives us a SQLite-row-level busy; the holder column records the
-- host:pid:ts for diagnostics (IM1 stale-holder cleanup is done by
-- advance.py on success/failure exit paths).
CREATE TABLE phase_gate_lock (
  id            INTEGER PRIMARY KEY CHECK (id = 1),
  holder        TEXT,
  acquired_at   TEXT
);
INSERT OR IGNORE INTO phase_gate_lock (id) VALUES (1);
