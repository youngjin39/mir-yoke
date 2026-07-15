"""ADR-53 Phase 2 — external-store metadata population tests.

These tests pin the ingest/population behavior that follows migration 017.
They intentionally cover only schema columns that exist in the current
external store schema: ``source_slug``, ``doc_category``, ``layer``, and the
``fact_documents`` join table. ``title`` / ``frontmatter_json`` are not tested
in this Phase 2 slice.
"""
from __future__ import annotations

from pathlib import Path

from mir.core.engine.memory import distill, external_store, store


def _fresh_db(tmp_path: Path) -> store.Connection:
    c = store.connect(tmp_path / "memory.db", load_vec=False)
    store.apply_migrations(c.conn)
    return c


def _write(root: Path, rel: str, body: str = "body\n") -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def _write_adr(
    root: Path,
    slug: str,
    frontmatter: str,
    body: str = "body\n",
) -> Path:
    return _write(
        root,
        f"docs/decisions/{slug}.md",
        f"---\n{frontmatter}\n---\n{body}",
    )


def _register_project_archive(
    c: store.Connection,
    root: Path,
) -> tuple[external_store.ExternalStore, int]:
    es = external_store.ExternalStore(c)
    archive_id = es.register(
        slug="source-repo",
        root_path=str(root),
        mode="indexed",
        glob_include=("**/*.md",),
        owner="family:your-harness",
    )
    return es, archive_id


def _metadata_rows(conn) -> dict[str, tuple[str | None, str | None, str | None]]:
    rows = conn.execute(
        "SELECT relative_path, source_slug, doc_category, layer "
        "FROM external_documents"
    ).fetchall()
    return {
        rel: (source_slug, doc_category, layer)
        for rel, source_slug, doc_category, layer in rows
    }


def _schema_metadata_version(conn) -> str | None:
    row = conn.execute(
        "SELECT value FROM external_store_meta WHERE key='schema_metadata_version'"
    ).fetchone()
    return row[0] if row else None


def test_scan_populates_source_slug_doc_category_and_layer_by_path(tmp_path: Path):
    c = _fresh_db(tmp_path)
    try:
        es, archive_id = _register_project_archive(c, tmp_path)
        expected = {
            "docs/decisions/adr-99-test.md": ("your-harness", "decision", "semantic"),
            "docs/_archive/decisions/old.md": ("your-harness", "archive", "episodic"),
            "docs/patterns/current.md": ("your-harness", "doc", "semantic"),
            "tasks/plan.md": ("your-harness", "task", "working"),
            ".ai-harness/bluebricks.md": (
                "your-harness",
                "harness-rule",
                "procedural",
            ),
            "misc/note.md": ("your-harness", None, None),
        }
        for rel in expected:
            _write(tmp_path, rel, f"{rel}\n")

        result = es.scan(archive_id, embed_fn=None)

        assert result.inserted == len(expected)
        assert _metadata_rows(c.conn) == expected
    finally:
        c.conn.close()


def test_stored_metadata_version_1_forces_unchanged_file_reindex(
    tmp_path: Path,
):
    assert getattr(external_store, "CURRENT_METADATA_VERSION", None) == "4"

    c = _fresh_db(tmp_path)
    try:
        es, archive_id = _register_project_archive(c, tmp_path)
        _write(tmp_path, "docs/decisions/adr-99-test.md", "stable body\n")
        first = es.scan(archive_id, embed_fn=None)
        assert first.inserted == 1

        c.conn.execute(
            "UPDATE external_documents "
            "SET source_slug = NULL, doc_category = NULL, layer = NULL "
            "WHERE relative_path = 'docs/decisions/adr-99-test.md'"
        )
        c.conn.execute(
            "UPDATE external_store_meta SET value = '1' "
            "WHERE key = 'schema_metadata_version'"
        )
        c.conn.execute(
            "DELETE FROM external_store_meta WHERE key = ?",
            (f"schema_metadata_version:archive:{archive_id}",),
        )
        c.conn.commit()

        second = es.scan(archive_id, embed_fn=None)

        assert second.inserted == 0
        assert second.reindexed == 1
        assert second.unchanged == 0
        assert _schema_metadata_version(c.conn) == "4"
        assert _metadata_rows(c.conn) == {
            "docs/decisions/adr-99-test.md": (
                "your-harness",
                "decision",
                "semantic",
            )
        }
    finally:
        c.conn.close()


def test_stored_current_metadata_version_does_not_reindex_unchanged_file(
    tmp_path: Path,
):
    assert getattr(external_store, "CURRENT_METADATA_VERSION", None) == "4"

    c = _fresh_db(tmp_path)
    try:
        es, archive_id = _register_project_archive(c, tmp_path)
        _write(tmp_path, "docs/decisions/adr-99-test.md", "stable body\n")
        first = es.scan(archive_id, embed_fn=None)
        assert first.inserted == 1
        c.conn.execute(
            "UPDATE external_store_meta SET value = '4' "
            "WHERE key = 'schema_metadata_version'"
        )
        c.conn.commit()

        second = es.scan(archive_id, embed_fn=None)

        assert second.inserted == 0
        assert second.reindexed == 0
        assert second.unchanged == 1
        assert _schema_metadata_version(c.conn) == "4"
    finally:
        c.conn.close()


def test_forced_rescan_failure_does_not_advance_sentinel(tmp_path: Path):
    import unittest.mock as mock

    c = _fresh_db(tmp_path)
    try:
        es, archive_id = _register_project_archive(c, tmp_path)
        _write(tmp_path, "docs/decisions/adr-99-test.md", "stable body\n")
        first = es.scan(archive_id, embed_fn=None)
        assert first.inserted == 1
        c.conn.execute(
            "UPDATE external_store_meta SET value = '1' "
            "WHERE key = 'schema_metadata_version'"
        )
        c.conn.execute(
            "DELETE FROM external_store_meta WHERE key = ?",
            (f"schema_metadata_version:archive:{archive_id}",),
        )
        c.conn.commit()
        # Monkeypatch _reindex_if_changed to raise so forced rescan has a failure
        def failing_reindex(*args, **kwargs):
            raise RuntimeError("injected failure")

        with mock.patch.object(es, "_reindex_if_changed", side_effect=failing_reindex):
            second = es.scan(archive_id, embed_fn=None)
        assert len(second.failed) > 0
        assert _schema_metadata_version(c.conn) == "1", (
            "sentinel must not advance when forced rescan had failures"
        )
        # Now a successful scan should backfill and advance sentinel
        _write(tmp_path, "docs/decisions/adr-99-test.md", "changed body\n")
        es.scan(archive_id, embed_fn=None)
        assert _schema_metadata_version(c.conn) == "4", (
            "sentinel must advance after successful scan"
        )
    finally:
        c.conn.close()


def test_ingest_markdown_file_links_facts_to_matching_external_document(
    tmp_path: Path,
):
    c = _fresh_db(tmp_path)
    try:
        adr = _write_adr(
            tmp_path,
            "adr-99-linked",
            "title: Linked ADR\nstatus: accepted",
        )
        es, archive_id = _register_project_archive(c, tmp_path)
        scan = es.scan(archive_id, embed_fn=None)
        assert scan.inserted == 1
        doc_id = c.conn.execute(
            "SELECT id FROM external_documents "
            "WHERE relative_path = 'docs/decisions/adr-99-linked.md'"
        ).fetchone()[0]

        result = distill.ingest_markdown_file(
            adr,
            conn=c.conn,
            project_root=tmp_path,
        )

        assert result.no_op is False
        assert result.facts_inserted > 0
        content_id_row = c.conn.execute(
            "SELECT id FROM content_items WHERE text_hash = ? LIMIT 1",
            (result.file_hash,),
        ).fetchone()
        assert content_id_row is not None
        content_id = content_id_row[0]
        rows = c.conn.execute(
            """
            SELECT fd.fact_id, fd.document_id
              FROM fact_documents fd
              JOIN facts f ON f.id = fd.fact_id
             WHERE f.created_from = ?
             ORDER BY fd.fact_id
            """,
            (content_id,),
        ).fetchall()
        assert len(rows) == result.facts_inserted
        assert {document_id for _, document_id in rows} == {doc_id}
    finally:
        c.conn.close()


def test_ingest_markdown_file_without_external_document_match_skips_link(
    tmp_path: Path,
):
    c = _fresh_db(tmp_path)
    try:
        adr = _write_adr(
            tmp_path,
            "adr-99-unmatched",
            "title: Unmatched ADR\nstatus: accepted",
        )

        result = distill.ingest_markdown_file(
            adr,
            conn=c.conn,
            project_root=tmp_path,
        )

        assert result.no_op is False
        assert result.facts_inserted > 0
        assert c.conn.execute("SELECT COUNT(*) FROM fact_documents").fetchone()[0] == 0
    finally:
        c.conn.close()


def test_ingest_sets_entity_type_from_frontmatter_type_only(tmp_path: Path):
    c = _fresh_db(tmp_path)
    try:
        typed = _write_adr(
            tmp_path,
            "adr-99-typed",
            "title: Typed ADR\ntype: decision\nstatus: accepted",
        )
        untyped = _write_adr(
            tmp_path,
            "adr-98-untyped",
            "title: Untyped ADR\nstatus: accepted",
        )

        distill.ingest_markdown_file(typed, conn=c.conn, project_root=tmp_path)
        distill.ingest_markdown_file(untyped, conn=c.conn, project_root=tmp_path)

        rows = dict(
            c.conn.execute(
                "SELECT slug, type FROM entities "
                "WHERE slug IN ('adr-99-typed', 'adr-98-untyped')"
            ).fetchall()
        )
        assert rows == {
            "adr-99-typed": "decision",
            "adr-98-untyped": None,
        }
    finally:
        c.conn.close()


def test_layer_episodic_for_sessions_and_handoffs(tmp_path: Path):
    c = _fresh_db(tmp_path)
    try:
        es, archive_id = _register_project_archive(c, tmp_path)
        expected = {
            "tasks/sessions/2026-06-06.md": ("your-harness", "archive", "episodic"),
            "tasks/handoffs/handoff-abc.md": ("your-harness", "archive", "episodic"),
        }
        for rel in expected:
            _write(tmp_path, rel, f"{rel}\n")
        result = es.scan(archive_id, embed_fn=None)
        assert result.inserted == len(expected)
        assert _metadata_rows(c.conn) == expected
    finally:
        c.conn.close()


def test_index_file_writes_status_active(tmp_path: Path):
    c = _fresh_db(tmp_path)
    try:
        es, archive_id = _register_project_archive(c, tmp_path)
        _write(tmp_path, "docs/decisions/adr-01-test.md", "body\n")
        es.scan(archive_id, embed_fn=None)
        row = c.conn.execute(
            "SELECT status FROM external_documents WHERE relative_path = ?",
            ("docs/decisions/adr-01-test.md",),
        ).fetchone()
        assert row is not None
        assert row[0] == "active"
    finally:
        c.conn.close()


def test_title_and_frontmatter_json_population(tmp_path: Path):
    import json as json_mod

    c = _fresh_db(tmp_path)
    try:
        es, archive_id = _register_project_archive(c, tmp_path)
        # title from frontmatter
        _write(
            tmp_path,
            "docs/decisions/adr-01.md",
            "---\ntitle: My Title\nstatus: accepted\n---\nbody\n",
        )
        # title from first heading (no frontmatter title)
        _write(
            tmp_path,
            "docs/decisions/adr-02.md",
            "---\nstatus: accepted\n---\n# Heading Title\nbody\n",
        )
        # both NULL for plain text (no frontmatter, no heading)
        _write(tmp_path, "docs/misc/plain.md", "plain text body\n")
        es.scan(archive_id, embed_fn=None)
        rows = {
            rel: (title, fm_json)
            for rel, title, fm_json in c.conn.execute(
                "SELECT relative_path, title, frontmatter_json FROM external_documents"
            ).fetchall()
        }
        assert rows["docs/decisions/adr-01.md"][0] == "My Title"
        fm1 = json_mod.loads(rows["docs/decisions/adr-01.md"][1])
        assert fm1["title"] == "My Title"
        assert fm1["status"] == "accepted"
        assert rows["docs/decisions/adr-02.md"][0] == "Heading Title"
        # adr-02 has frontmatter without title key, so frontmatter_json should exist
        assert rows["docs/decisions/adr-02.md"][1] is not None
        assert rows["docs/misc/plain.md"][0] is None
        assert rows["docs/misc/plain.md"][1] is None
    finally:
        c.conn.close()


def test_ingest_entity_type_not_overwritten_by_second_ingest(tmp_path: Path):
    c = _fresh_db(tmp_path)
    try:
        typed_adr = _write_adr(
            tmp_path,
            "adr-77-typed",
            "title: First Ingest\ntype: decision\nstatus: accepted",
        )
        distill.ingest_markdown_file(typed_adr, conn=c.conn, project_root=tmp_path)
        row = c.conn.execute(
            "SELECT type FROM entities WHERE slug = 'adr-77-typed'"
        ).fetchone()
        assert row[0] == "decision"
        # Re-ingest with a different file hash (changed body) and different type
        typed_adr.write_text(
            "---\ntitle: Second Ingest\ntype: design\nstatus: accepted\n"
            "---\nchanged body\n",
            encoding="utf-8",
        )
        distill.ingest_markdown_file(typed_adr, conn=c.conn, project_root=tmp_path)
        row2 = c.conn.execute(
            "SELECT type FROM entities WHERE slug = 'adr-77-typed'"
        ).fetchone()
        assert row2[0] == "decision", "type must not be overwritten once set"
    finally:
        c.conn.close()
