"""Deterministic, source-owned Markdown relation ingestion."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from mir.cli import memory as memory_cli
from mir.core.engine.memory import distill, store
from mir.core.engine.memory.relation_facts import RelationDeclarationError


def _db(tmp_path: Path):
    connection = store.connect(tmp_path / "memory.db", load_vec=False)
    store.apply_migrations(connection.conn)
    return connection.conn


def _write(root: Path, name: str, frontmatter: str, *, files: tuple[str, ...] = ()) -> Path:
    for file_name in files:
        target = root / file_name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# fixture\n", encoding="utf-8")
    path = root / "docs" / "decisions" / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{frontmatter}\n---\nbody\n", encoding="utf-8")
    return path


def _ingest(conn, root: Path, path: Path):
    return distill.ingest_markdown_file(path, conn=conn, project_root=root)


def _active_edges(conn):
    return conn.execute(
        """
        SELECT subject.slug, f.predicate, object.slug, f.object_literal
          FROM facts f
          JOIN entities subject ON subject.id = f.subject_entity_id
          JOIN entities object ON object.id = f.object_entity_id
         WHERE f.status = 'active' AND f.object_entity_id IS NOT NULL
         ORDER BY subject.slug, f.predicate, object.slug, f.id
        """
    ).fetchall()


def test_relation_declarations_persist_entity_edges_and_stated_provenance(tmp_path: Path):
    conn = _db(tmp_path)
    path = _write(
        tmp_path,
        "adr-relation",
        "status: accepted\nmemory_relations:\n"
        "  - [REQ-1, implemented_in, src/app.py]\n  - [REQ-1, realized_by, CAP-1]",
        files=("src/app.py",),
    )

    result = _ingest(conn, tmp_path, path)

    assert result.facts_inserted >= 2
    assert _active_edges(conn) == [
        ("REQ-1", "implemented_in", "src/app.py", None),
        ("REQ-1", "realized_by", "CAP-1", None),
    ]
    metadata_json, quote, strength = conn.execute(
        """
        SELECT ci.metadata_json, p.quote, p.strength
          FROM facts f
          JOIN content_items ci ON ci.id = f.created_from
          JOIN provenance p ON p.fact_id = f.id AND p.content_item_id = ci.id
         WHERE f.object_entity_id IS NOT NULL AND f.predicate = 'implemented_in'
        """
    ).fetchone()
    metadata = json.loads(metadata_json)
    assert metadata["relation_schema"] == "mir-memory-relations/v1"
    assert metadata["relation_document_status"] == "accepted"
    assert "[REQ-1, implemented_in, src/app.py]" in quote
    assert strength == "stated"
    assert _ingest(conn, tmp_path, path).no_op_reason == "unchanged"
    assert len(_active_edges(conn)) == 2


def test_relation_source_reversions_and_independent_support_are_preserved(tmp_path: Path):
    conn = _db(tmp_path)
    source_a = _write(tmp_path, "adr-a", "memory_relations: [[REQ-1, realized_by, CAP-A]]")
    source_b = _write(tmp_path, "adr-b", "memory_relations: [[REQ-1, realized_by, CAP-A]]")
    _ingest(conn, tmp_path, source_a)
    _ingest(conn, tmp_path, source_b)
    assert len(_active_edges(conn)) == 2

    _write(tmp_path, "adr-a", "memory_relations: [[REQ-1, realized_by, CAP-B]]")
    _ingest(conn, tmp_path, source_a)
    _write(tmp_path, "adr-a", "memory_relations: [[REQ-1, realized_by, CAP-A]]")
    _ingest(conn, tmp_path, source_a)

    assert _active_edges(conn).count(("REQ-1", "realized_by", "CAP-A", None)) == 2
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM facts WHERE predicate='realized_by' AND status='superseded'"
        ).fetchone()[0]
        >= 2
    )


def test_relation_reconciliation_removes_only_owned_siblings_and_not_literal_facts(tmp_path: Path):
    conn = _db(tmp_path)
    path = _write(
        tmp_path,
        "adr-siblings",
        "memory_relations: [[REQ-1, depends_on, DEP-A], [REQ-1, depends_on, DEP-B]]",
    )
    _ingest(conn, tmp_path, path)
    subject = distill._upsert_entity(conn, "REQ-1")
    conn.execute(
        """INSERT INTO facts(subject_entity_id, predicate, object_literal, polarity, valid_from,
           status, confidence, scope) VALUES (?, 'depends_on', 'literal stays', 'asserted',
           '2026-01-01', 'active', 1.0, 'global')""",
        (subject,),
    )
    conn.commit()

    _write(tmp_path, "adr-siblings", "memory_relations: [[REQ-1, depends_on, DEP-A]]")
    _ingest(conn, tmp_path, path)

    assert _active_edges(conn) == [("REQ-1", "depends_on", "DEP-A", None)]
    assert conn.execute(
        "SELECT status FROM facts WHERE subject_entity_id=? AND object_literal='literal stays'",
        (subject,),
    ).fetchone() == ("active",)


def test_relation_invalid_declaration_rolls_back_and_cli_reports_cleanly(
    tmp_path: Path, capsys, monkeypatch
):
    conn = _db(tmp_path)
    path = _write(
        tmp_path, "adr-invalid", "title: before\nmemory_relations: [[REQ-1, realized_by, CAP-A]]"
    )
    _ingest(conn, tmp_path, path)
    before = conn.execute("SELECT COUNT(*) FROM content_items").fetchone()[0]
    _write(tmp_path, "adr-invalid", "title: after\nmemory_relations: [[REQ-1, illegal, CAP-A]]")

    with pytest.raises(RelationDeclarationError):
        _ingest(conn, tmp_path, path)
    assert conn.execute("SELECT COUNT(*) FROM content_items").fetchone()[0] == before
    assert conn.execute(
        "SELECT object_literal FROM facts WHERE predicate='title' AND status='active'"
    ).fetchone() == ("before",)

    db_path = tmp_path / "memory.db"
    monkeypatch.chdir(tmp_path)
    assert memory_cli.main(["ingest-md", str(path), "--db", str(db_path)]) == 2
    assert "invalid memory_relations" in capsys.readouterr().err


def test_relation_removed_frontmatter_deleted_source_and_inactive_verification(tmp_path: Path):
    conn = _db(tmp_path)
    path = _write(
        tmp_path,
        "adr-source",
        "status: accepted\nmemory_relations: [[REQ-1, verified_by, tests/test_check.py]]",
        files=("tests/test_check.py",),
    )
    _ingest(conn, tmp_path, path)
    assert _active_edges(conn) == [("REQ-1", "verified_by", "tests/test_check.py", None)]

    _write(
        tmp_path,
        "adr-source",
        "status: proposed\nmemory_relations: [[REQ-1, verified_by, tests/test_check.py]]",
    )
    _ingest(conn, tmp_path, path)
    assert _active_edges(conn) == []

    _write(tmp_path, "adr-source", "title: relation block removed")
    _ingest(conn, tmp_path, path)
    assert _active_edges(conn) == []

    path.unlink()
    assert distill.reconcile_missing_source(conn, project_root=tmp_path) >= 1


def test_relation_frontmatter_tombstone_allows_restoring_the_original_declaration(tmp_path: Path):
    conn = _db(tmp_path)
    path = _write(tmp_path, "adr-tombstone", "memory_relations: [[REQ-1, realized_by, CAP-A]]")
    _ingest(conn, tmp_path, path)
    path.write_text("body without frontmatter\n", encoding="utf-8")
    removed = _ingest(conn, tmp_path, path)
    assert not removed.no_op
    assert removed.facts_superseded == 1
    assert _active_edges(conn) == []
    _write(tmp_path, "adr-tombstone", "memory_relations: [[REQ-1, realized_by, CAP-A]]")
    restored = _ingest(conn, tmp_path, path)
    assert not restored.no_op
    assert _active_edges(conn) == [("REQ-1", "realized_by", "CAP-A", None)]


def test_relation_revision_replaces_all_owned_edges_with_current_provenance(tmp_path: Path):
    conn = _db(tmp_path)
    path = _write(
        tmp_path,
        "adr-revision",
        "title: first\nstatus: accepted\n"
        "memory_relations: [[REQ-1, implemented_in, src/app.py], [REQ-1, depends_on, DEP-A]]",
        files=("src/app.py",),
    )
    _ingest(conn, tmp_path, path)
    _write(
        tmp_path,
        "adr-revision",
        "title: second\nstatus: accepted\n"
        "memory_relations: [[REQ-1, implemented_in, src/app.py], [REQ-1, depends_on, DEP-B]]",
    )
    _ingest(conn, tmp_path, path)
    latest_content = conn.execute(
        "SELECT id FROM content_items WHERE json_extract(metadata_json, '$.path') = ? "
        "ORDER BY id DESC LIMIT 1",
        ("docs/decisions/adr-revision.md",),
    ).fetchone()[0]
    assert _active_edges(conn) == [
        ("REQ-1", "depends_on", "DEP-B", None),
        ("REQ-1", "implemented_in", "src/app.py", None),
    ]
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM facts WHERE object_entity_id IS NOT NULL "
            "AND status='active' AND created_from=?",
            (latest_content,),
        ).fetchone()[0]
        == 2
    )


@pytest.mark.parametrize(
    "predicate, target",
    [
        ("realized_by", "CAP-A"),
        ("implemented_in", "src/app.py"),
        ("verified_by", "tests/test_check.py"),
        ("depends_on", "DEP-A"),
    ],
)
def test_unsettled_document_never_creates_an_active_relation(
    tmp_path: Path, predicate: str, target: str
):
    conn = _db(tmp_path)
    files = tuple(
        file_name for file_name in ("src/app.py", "tests/test_check.py") if file_name == target
    )
    path = _write(
        tmp_path,
        "adr-unsettled",
        f"status: draft\nmemory_relations: [[REQ-1, {predicate}, {target}]]",
        files=files,
    )
    _ingest(conn, tmp_path, path)
    assert _active_edges(conn) == []


@pytest.mark.parametrize(
    "relation",
    [
        "[REQ-1, implemented_in, ../outside.py]",
        "[REQ-1, implemented_in, .env]",
        "[REQ-1, implemented_in, src/missing.py]",
        "[REQ-1, unknown_relation, CAP-A]",
        "[REQ-1, realized_by]",
    ],
)
def test_relation_rejects_unsafe_or_malformed_declarations_before_writing(
    tmp_path: Path, relation: str
):
    conn = _db(tmp_path)
    (tmp_path / ".env").write_text("secret", encoding="utf-8")
    path = _write(tmp_path, "adr-unsafe", f"memory_relations: [{relation}]")

    with pytest.raises(RelationDeclarationError):
        _ingest(conn, tmp_path, path)
    assert conn.execute("SELECT COUNT(*) FROM content_items").fetchone()[0] == 0


@pytest.mark.parametrize(
    "declaration",
    ["[[.env, realized_by, CAP-A]]", "[[REQ-1, realized_by, CAP-A], [REQ-1, realized_by, CAP-A]]"],
)
def test_relation_rejects_protected_subjects_and_duplicate_declarations(
    tmp_path: Path, declaration: str
):
    conn = _db(tmp_path)
    (tmp_path / ".env").write_text("secret", encoding="utf-8")
    path = _write(tmp_path, "adr-invalid-edge", f"memory_relations: {declaration}")
    with pytest.raises(RelationDeclarationError):
        _ingest(conn, tmp_path, path)
    assert conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0] == 0


def test_relation_revisions_have_atomic_audit_history(tmp_path: Path):
    conn = _db(tmp_path)
    path = _write(tmp_path, "adr-audit", "memory_relations: [[REQ-1, realized_by, CAP-A]]")
    _ingest(conn, tmp_path, path)
    _write(tmp_path, "adr-audit", "memory_relations: [[REQ-1, realized_by, CAP-B]]")
    _ingest(conn, tmp_path, path)
    events = {row[0] for row in conn.execute("SELECT event FROM audit_log")}
    assert {"memory_relation.ingested", "memory_relation.superseded"} <= events


@pytest.mark.parametrize("status", ["[draft]", "true", "1", "null", "{state: draft}"])
def test_relation_rejects_non_string_or_duplicate_status_before_writing(
    tmp_path: Path, status: str
):
    conn = _db(tmp_path)
    path = _write(
        tmp_path,
        "adr-status-type",
        f"status: {status}\nmemory_relations: [[REQ-1, realized_by, CAP-A]]",
    )
    with pytest.raises(RelationDeclarationError, match="status must be a string"):
        _ingest(conn, tmp_path, path)
    assert conn.execute("SELECT COUNT(*) FROM content_items").fetchone()[0] == 0

    _write(
        tmp_path,
        "adr-status-type",
        "status: accepted\nstatus: draft\nmemory_relations: [[REQ-1, realized_by, CAP-A]]",
    )
    with pytest.raises(RelationDeclarationError, match="duplicate status"):
        _ingest(conn, tmp_path, path)


def test_relation_error_inside_outer_transaction_keeps_prior_state(tmp_path: Path):
    conn = _db(tmp_path)
    path = _write(tmp_path, "adr-outer", "memory_relations: [[REQ-1, malformed, CAP-A]]")
    conn.execute("BEGIN")
    with pytest.raises(RelationDeclarationError):
        _ingest(conn, tmp_path, path)
    assert conn.in_transaction
    assert conn.execute("SELECT COUNT(*) FROM content_items").fetchone()[0] == 0
    conn.rollback()


def test_relation_database_error_rolls_back_only_its_outer_transaction_savepoint(tmp_path: Path):
    conn = _db(tmp_path)
    path = _write(tmp_path, "adr-trigger", "memory_relations: [[REQ-1, realized_by, CAP-A]]")
    conn.execute(
        """
        CREATE TRIGGER reject_relation_insert BEFORE INSERT ON facts
        WHEN NEW.object_entity_id IS NOT NULL
        BEGIN SELECT RAISE(ABORT, 'relation insert rejected'); END
        """
    )
    conn.execute("BEGIN")
    with pytest.raises(sqlite3.IntegrityError, match="relation insert rejected"):
        _ingest(conn, tmp_path, path)
    assert conn.in_transaction
    assert conn.execute("SELECT COUNT(*) FROM content_items").fetchone()[0] == 0
    conn.rollback()


def test_relation_rejects_source_change_after_acquiring_the_write_guard(
    tmp_path: Path, monkeypatch
):
    conn = _db(tmp_path)
    path = _write(tmp_path, "adr-race", "memory_relations: [[REQ-1, realized_by, CAP-A]]")
    original_read_text = Path.read_text
    reads = 0

    def changing_read_text(self: Path, *args, **kwargs):
        nonlocal reads
        if self == path:
            reads += 1
            if reads == 2:
                return "---\nmemory_relations: [[REQ-1, realized_by, CAP-B]]\n---\nbody\n"
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", changing_read_text)
    with pytest.raises(RelationDeclarationError, match="source changed during ingestion"):
        _ingest(conn, tmp_path, path)
    assert conn.execute("SELECT COUNT(*) FROM content_items").fetchone()[0] == 0


def test_relation_physical_byte_limit_and_ordinary_body_mention(tmp_path: Path):
    conn = _db(tmp_path)
    relation = tmp_path / "docs" / "decisions" / "adr-large.md"
    relation.parent.mkdir(parents=True)
    relation.write_text(
        "\ufeff---\r\nmemory_relations: [[REQ-1, realized_by, CAP-A]]\r\n---\r\n"
        + "\ud55c" * 350_000,
        encoding="utf-8",
    )
    assert relation.stat().st_size > 1024 * 1024
    with pytest.raises(RelationDeclarationError, match="source exceeds 1 MiB"):
        _ingest(conn, tmp_path, relation)
    ordinary = relation.with_name("adr-ordinary.md")
    ordinary.write_text(
        "---\ntitle: ordinary\n---\n" + "memory_relations body mention\n" * 40_000, encoding="utf-8"
    )
    assert ordinary.stat().st_size > 1024 * 1024
    assert not _ingest(conn, tmp_path, ordinary).no_op


def test_missing_relation_reconcile_preserves_outer_transaction(tmp_path: Path):
    conn = _db(tmp_path)
    path = _write(tmp_path, "adr-expire", "memory_relations: [[REQ-1, realized_by, CAP-A]]")
    _ingest(conn, tmp_path, path)
    fact_id = conn.execute(
        "SELECT id FROM facts WHERE object_entity_id IS NOT NULL AND status='active'"
    ).fetchone()[0]
    path.unlink()
    conn.execute(
        """CREATE TRIGGER reject_expiry BEFORE INSERT ON audit_log
        WHEN NEW.event = 'memory_relation.expired'
        BEGIN SELECT RAISE(ABORT, 'audit fail'); END"""
    )
    conn.execute(
        "INSERT INTO entities(type, canonical_name, slug) VALUES (NULL, 'marker', 'marker')"
    )
    with pytest.raises(sqlite3.IntegrityError, match="audit fail"):
        distill.reconcile_missing_source(conn, project_root=tmp_path)
    assert conn.in_transaction and conn.execute(
        "SELECT status FROM facts WHERE id=?", (fact_id,)
    ).fetchone() == ("active",)
    assert conn.execute("SELECT COUNT(*) FROM entities WHERE slug='marker'").fetchone()[0] == 1
    conn.rollback()


def test_missing_relation_reconcile_success_leaves_outer_transaction_open(tmp_path: Path):
    conn = _db(tmp_path)
    path = _write(tmp_path, "adr-expire-ok", "memory_relations: [[REQ-1, realized_by, CAP-A]]")
    _ingest(conn, tmp_path, path)
    path.unlink()
    conn.execute("INSERT INTO entities(type, canonical_name, slug) VALUES (NULL, 'outer', 'outer')")
    assert distill.reconcile_missing_source(conn, project_root=tmp_path) >= 1
    assert conn.in_transaction
    conn.rollback()
    assert conn.execute("SELECT COUNT(*) FROM entities WHERE slug='outer'").fetchone()[0] == 0
