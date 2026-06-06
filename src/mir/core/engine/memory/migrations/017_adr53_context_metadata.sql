-- Migration 017 — ADR-53 context-assembly current-only retrieval (Phase 1).
-- decisions/adr-53-context-assembly-current-only-retrieval-2026-06-05.md D4, D5, D9.
--
-- Additive only: ALTER TABLE adds nullable / DEFAULT columns; no existing
-- columns or constraints are modified. Safe to apply on any 016-state DB.
--
-- 1. D4 status-discipline column on external_documents (doc-level; chunks
--    inherit status implicitly via document_id FK).
-- 2. D5 ontology-prep columns: source_slug (pre-apply, populated at ingest in
--    Phase 2), doc_category, layer (free-form TEXT; working|episodic|semantic|
--    procedural is a documented convention — no CHECK constraint per ADR-53 D5).
-- 3. fact_documents: fact to document provenance join table (Phase 2 population).
-- 4. external_store_meta: sentinel KV store for forced re-scan backfill tracking
--    (scan()-side comparison logic is Phase 2 — storage only here).
-- 5. Index on status for efficient active-only filtering (IN #4 prerequisite).


-- D4: doc-level status column. NOT NULL with DEFAULT 'active' so existing rows
-- get the correct value automatically (SQLite ALTER TABLE DEFAULT semantics).
ALTER TABLE external_documents ADD COLUMN status TEXT NOT NULL DEFAULT 'active';

-- D5: ontology-prep columns. Nullable — populated at ingest in Phase 2.
ALTER TABLE external_documents ADD COLUMN source_slug TEXT;
ALTER TABLE external_documents ADD COLUMN doc_category TEXT;

-- D5: layer column. Free-form TEXT; working|episodic|semantic|procedural is the
-- documented convention. No CHECK constraint per ADR-53 D5 decision rationale.
ALTER TABLE external_documents ADD COLUMN layer TEXT;

-- fact_documents: provenance join table linking facts to the external documents
-- they were derived from. Cascade deletes keep referential integrity automatic.
CREATE TABLE fact_documents (
  fact_id     INTEGER NOT NULL REFERENCES facts(id) ON DELETE CASCADE,
  document_id INTEGER NOT NULL REFERENCES external_documents(id) ON DELETE CASCADE,
  PRIMARY KEY (fact_id, document_id)
);

-- Sentinel KV store for schema metadata version tracking. Used by scan() in
-- Phase 2 to detect when a forced re-scan backfill is required.
CREATE TABLE IF NOT EXISTS external_store_meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

-- Seed the schema_metadata_version sentinel (value '1' marks Phase 1 baseline).
-- scan() comparison logic (Phase 2) will bump this to trigger backfills.
INSERT OR IGNORE INTO external_store_meta(key, value) VALUES ('schema_metadata_version', '1');

-- Index for efficient active-only status filtering (ADR-53 IN #4 prerequisite).
CREATE INDEX IF NOT EXISTS idx_external_documents_status ON external_documents(status);
