"""ADR-53 Phase 1 — migration 017 schema tests.

Covers:
  - fresh DB: apply_migrations runs 017; all new columns/tables/index exist.
  - upgrade path: pre-017 external_documents rows survive with correct defaults.
  - fact_documents: PK uniqueness + FK insert semantics.
  - external_store_meta: seed row present with value '1'.
  - backward-compat smoke: ExternalStore import + store open work unchanged.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from mir.core.engine.memory import store

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _open_fresh(tmp_path: Path) -> store.Connection:
    return store.connect(tmp_path / "memory.db", load_vec=False)


def _table_columns(conn, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r[1] for r in rows}


def _index_exists(conn, index_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
        (index_name,),
    ).fetchone()
    return row is not None


def _table_exists(conn, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# Test 1 — fresh DB: 017 applied; new columns present on external_documents
# ---------------------------------------------------------------------------

def test_017_applies_and_columns_exist(tmp_path: Path):
    c = _open_fresh(tmp_path)
    try:
        applied = store.apply_migrations(c.conn)
        assert "017" in applied, f"017 not in applied: {applied}"
        assert store.schema_version(c.conn) == "017"

        cols = _table_columns(c.conn, "external_documents")
        assert "status" in cols, "status column missing from external_documents"
        assert "source_slug" in cols, "source_slug column missing"
        assert "doc_category" in cols, "doc_category column missing"
        assert "layer" in cols, "layer column missing"
    finally:
        c.conn.close()


# ---------------------------------------------------------------------------
# Test 2 — fresh DB: fact_documents and external_store_meta tables exist
# ---------------------------------------------------------------------------

def test_017_new_tables_exist(tmp_path: Path):
    c = _open_fresh(tmp_path)
    try:
        store.apply_migrations(c.conn)
        assert _table_exists(c.conn, "fact_documents"), "fact_documents table missing"
        assert _table_exists(c.conn, "external_store_meta"), "external_store_meta table missing"
    finally:
        c.conn.close()


# ---------------------------------------------------------------------------
# Test 3 — fresh DB: status index exists
# ---------------------------------------------------------------------------

def test_017_status_index_exists(tmp_path: Path):
    c = _open_fresh(tmp_path)
    try:
        store.apply_migrations(c.conn)
        assert _index_exists(c.conn, "idx_external_documents_status"), (
            "idx_external_documents_status index missing"
        )
    finally:
        c.conn.close()


# ---------------------------------------------------------------------------
# Test 4 — upgrade path: pre-017 rows get status='active', other cols NULL
# ---------------------------------------------------------------------------

def test_017_upgrade_path_existing_rows(tmp_path: Path, monkeypatch):
    """Simulate a DB with external_documents rows from before 017, then apply
    017 and assert status='active', other new cols NULL, zero row loss."""
    from mir.core.engine.memory import store as _store

    real_iter = _store._iter_migrations

    # We need to apply up-to-016 first (without 017), then insert a row, then
    # apply 017. We do this by monkeypatching _iter_migrations to exclude 017
    # for the first pass.
    def iter_without_017():
        for mig in real_iter():
            if mig.version == "017":
                continue
            yield mig

    monkeypatch.setattr(_store, "_iter_migrations", iter_without_017)

    c = _open_fresh(tmp_path)
    try:
        _store.apply_migrations(c.conn)

        # Insert a pre-017 external_archives row and external_documents row.
        c.conn.execute(
            "INSERT INTO external_archives(slug, root_path, mode, chunk_size, "
            "chunk_overlap, owner, created_at) "
            "VALUES ('test-archive', '/tmp/test', 'indexed', 800, 100, 'family:mir', '2026-06-05')"
        )
        archive_id = c.conn.execute(
            "SELECT id FROM external_archives WHERE slug='test-archive'"
        ).fetchone()[0]
        c.conn.execute(
            "INSERT INTO external_documents(archive_id, relative_path, file_hash) "
            "VALUES (?, 'foo/bar.md', 'abc123')",
            (archive_id,),
        )
        c.conn.commit()
        pre_count = c.conn.execute(
            "SELECT COUNT(*) FROM external_documents"
        ).fetchone()[0]
        assert pre_count == 1

        # Now restore real iter and apply 017.
        monkeypatch.setattr(_store, "_iter_migrations", real_iter)
        newly = _store.apply_migrations(c.conn)
        assert "017" in newly

        # Check row count preserved.
        post_count = c.conn.execute(
            "SELECT COUNT(*) FROM external_documents"
        ).fetchone()[0]
        assert post_count == pre_count, "Row lost during 017 migration"

        # Check defaults on pre-existing row.
        row = c.conn.execute(
            "SELECT status, source_slug, doc_category, layer "
            "FROM external_documents WHERE relative_path='foo/bar.md'"
        ).fetchone()
        assert row[0] == "active", f"status default wrong: {row[0]!r}"
        assert row[1] is None, f"source_slug should be NULL: {row[1]!r}"
        assert row[2] is None, f"doc_category should be NULL: {row[2]!r}"
        assert row[3] is None, f"layer should be NULL: {row[3]!r}"
    finally:
        c.conn.close()


# ---------------------------------------------------------------------------
# Test 5 — fact_documents: valid insert + PK rejects duplicates
# ---------------------------------------------------------------------------

def test_017_fact_documents_pk_semantics(tmp_path: Path):
    import sqlite3 as _sqlite3

    c = _open_fresh(tmp_path)
    try:
        store.apply_migrations(c.conn)

        # Need a fact row and a document row to satisfy FKs.
        # Insert entity + fact.
        c.conn.execute(
            "INSERT INTO entities(type, canonical_name, slug) VALUES (?,?,?)",
            ("agent", "mir-test", "mir-test"),
        )
        eid = c.conn.execute(
            "SELECT id FROM entities WHERE slug='mir-test'"
        ).fetchone()[0]
        c.conn.execute(
            "INSERT INTO facts(subject_entity_id, predicate, object_literal, "
            "polarity, status) VALUES (?, 'use', 'pytest', 'asserted', 'active')",
            (eid,),
        )
        fact_id = c.conn.execute(
            "SELECT id FROM facts WHERE object_literal='pytest'"
        ).fetchone()[0]

        # Insert archive + document.
        c.conn.execute(
            "INSERT INTO external_archives(slug, root_path, mode, chunk_size, "
            "chunk_overlap, owner, created_at) "
            "VALUES ('arc1', '/tmp/x', 'indexed', 800, 100, 'family:mir', '2026-06-05')"
        )
        arc_id = c.conn.execute(
            "SELECT id FROM external_archives WHERE slug='arc1'"
        ).fetchone()[0]
        c.conn.execute(
            "INSERT INTO external_documents(archive_id, relative_path, file_hash) "
            "VALUES (?, 'a.md', 'h1')",
            (arc_id,),
        )
        doc_id = c.conn.execute(
            "SELECT id FROM external_documents WHERE relative_path='a.md'"
        ).fetchone()[0]
        c.conn.commit()

        # Valid insert into fact_documents.
        c.conn.execute(
            "INSERT INTO fact_documents(fact_id, document_id) VALUES (?, ?)",
            (fact_id, doc_id),
        )
        c.conn.commit()

        count = c.conn.execute(
            "SELECT COUNT(*) FROM fact_documents"
        ).fetchone()[0]
        assert count == 1

        # Duplicate PK must fail.
        with pytest.raises(_sqlite3.IntegrityError):
            c.conn.execute(
                "INSERT INTO fact_documents(fact_id, document_id) VALUES (?, ?)",
                (fact_id, doc_id),
            )
            c.conn.commit()
    finally:
        c.conn.close()


# ---------------------------------------------------------------------------
# Test 6 — external_store_meta seed row
# ---------------------------------------------------------------------------

def test_017_external_store_meta_seed(tmp_path: Path):
    c = _open_fresh(tmp_path)
    try:
        store.apply_migrations(c.conn)
        row = c.conn.execute(
            "SELECT value FROM external_store_meta WHERE key='schema_metadata_version'"
        ).fetchone()
        assert row is not None, "seed row missing from external_store_meta"
        assert row[0] == "1", f"seed value wrong: {row[0]!r}"
    finally:
        c.conn.close()


# ---------------------------------------------------------------------------
# Test 7 — backward-compat smoke: ExternalStore import + store open
# ---------------------------------------------------------------------------

def test_017_external_store_import_smoke(tmp_path: Path):
    """Migration 017 is purely additive; existing ExternalStore code paths
    must still import cleanly and open a migrated DB without error."""
    from mir.core.engine.memory import external_store  # noqa: F401 — import smoke

    c = _open_fresh(tmp_path)
    try:
        store.apply_migrations(c.conn)
        # Basic query against the pre-existing external_archives table still works.
        rows = c.conn.execute("SELECT COUNT(*) FROM external_archives").fetchone()
        assert rows[0] == 0
    finally:
        c.conn.close()
