"""Schema migration runner — idempotent + FTS5 trigger + predicate backfill."""
from __future__ import annotations

from pathlib import Path

import pytest

from mir.core.engine.memory import store


def _fresh(tmp_path: Path):
    conn = store.connect(tmp_path / "memory.db")
    return conn


def test_apply_migrations_is_idempotent(tmp_path: Path):
    c = _fresh(tmp_path)
    try:
        first = store.apply_migrations(c.conn)
        second = store.apply_migrations(c.conn)
        assert sorted(first) == ["001", "002", "003", "004", "014", "015", "016", "017"]
        assert second == []
        assert store.schema_version(c.conn) == "017"
    finally:
        c.conn.close()


def test_core_tables_present(tmp_path: Path):
    c = _fresh(tmp_path)
    try:
        store.apply_migrations(c.conn)
        names = {
            row[0]
            for row in c.conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table','view','virtual')"
            ).fetchall()
        }
        # Core shards across 001-004.
        for t in ("content_items", "facts", "fact_stats", "audit_log",
                  "schema_meta", "sessions", "conductor_mode"):
            assert t in names, f"missing table: {t}"
        assert "facts_fts" in names, "FTS5 virtual table must exist"
    finally:
        c.conn.close()


def test_fts_trigger_indexes_inserts(tmp_path: Path):
    c = _fresh(tmp_path)
    try:
        store.apply_migrations(c.conn)
        c.conn.execute(
            "INSERT INTO entities(type, canonical_name, slug) VALUES (?,?,?)",
            ("agent", "mir", "mir"),
        )
        eid = c.conn.execute("SELECT id FROM entities WHERE slug='mir'").fetchone()[0]
        c.conn.execute(
            "INSERT INTO facts (subject_entity_id, predicate, object_literal, "
            "polarity, status) VALUES (?, 'use', 'sqlite-vec embedding', 'asserted', 'active')",
            (eid,),
        )
        c.conn.commit()
        rows = c.conn.execute(
            "SELECT rowid FROM facts_fts WHERE facts_fts MATCH 'sqlite'"
        ).fetchall()
        assert rows, "FTS trigger must populate facts_fts"
    finally:
        c.conn.close()


def test_failing_migration_rolls_back(tmp_path: Path, monkeypatch):
    """A migration that fails mid-body must leave the DB in the pre-migration
    state (no partial DDL committed, no ``schema_migrations`` row written)."""
    from mir.core.engine.memory import store as _store

    real_iter = _store._iter_migrations
    bad_version = "999"
    bad_name = "999_deliberately_bad.sql"
    # Valid CREATE TABLE followed by a syntactically broken statement. The
    # first statement is what would leak if the rollback is broken.
    bad_body = (
        "CREATE TABLE leaked_if_broken(id INTEGER);\n"
        "THIS IS NOT VALID SQL AT ALL;\n"
    )

    def fake_iter():
        yield from real_iter()
        yield _store.MigrationEntry(bad_version, bad_name, bad_body)

    monkeypatch.setattr(_store, "_iter_migrations", fake_iter)

    import sqlite3 as _sqlite3
    c = _fresh(tmp_path)
    try:
        with pytest.raises(_sqlite3.OperationalError):
            _store.apply_migrations(c.conn)
        # leaked_if_broken must NOT exist — the partial DDL should have rolled back.
        row = c.conn.execute(
            "SELECT name FROM sqlite_master WHERE name='leaked_if_broken'"
        ).fetchone()
        assert row is None, "rollback failed: DDL from failed migration leaked"
        # schema_migrations must not record the failed version.
        versions = {
            r[0] for r in c.conn.execute(
                "SELECT version FROM schema_migrations"
            ).fetchall()
        }
        assert bad_version not in versions
    finally:
        c.conn.close()


def test_migration_014_backfills_predicates(tmp_path: Path):
    """014 must rewrite legacy predicates to canonical form."""
    # Apply 001-004 only, insert stale rows, then force 014 via second pass.
    # The runner is all-or-nothing per its design, so we emulate by using a
    # pristine db then checking that 014 applied (predicate already canonical
    # on fresh insert, so instead we test that the UPDATE idempotently runs
    # on legacy-shaped data).
    c = _fresh(tmp_path)
    try:
        store.apply_migrations(c.conn)  # everything including 014
        eid = c.conn.execute(
            "INSERT INTO entities(type, canonical_name, slug) VALUES (?,?,?) "
            "RETURNING id", ("x", "x", "x")
        ).fetchone()[0]
        # Simulate legacy row bypassing distill.canonicalize().
        c.conn.execute(
            "INSERT INTO facts(subject_entity_id, predicate, object_literal, "
            "polarity, status) VALUES (?, 'USING', 'pytest', 'asserted', 'active')",
            (eid,),
        )
        c.conn.commit()
        # Re-run the 014 statements manually (simulating a re-apply).
        from importlib.resources import files
        sql = files("mir.core.engine.memory.migrations").joinpath(
            "014_canonicalize_predicates.sql").read_text()
        c.conn.executescript(sql)
        c.conn.commit()
        row = c.conn.execute(
            "SELECT predicate FROM facts WHERE object_literal='pytest'"
        ).fetchone()
        assert row[0] == "use"
    finally:
        c.conn.close()
