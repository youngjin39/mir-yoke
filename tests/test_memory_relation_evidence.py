"""Compact authored evidence on explicit Markdown relation declarations."""

from __future__ import annotations

from pathlib import Path

import pytest

from mir.core.engine.memory import distill, store
from mir.core.engine.memory.relation_facts import (
    MAX_RELATION_NOTE_CHARS,
    RelationDeclarationError,
    has_relation_declaration,
    parse_relation_document,
)


def _db(tmp_path: Path):
    connection = store.connect(tmp_path / "memory.db", load_vec=False)
    store.apply_migrations(connection.conn)
    return connection.conn


def test_mapping_declaration_preserves_authored_evidence_and_physical_line(tmp_path: Path):
    path = tmp_path / "docs" / "decisions" / "evidence.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        "\ufeff---\r\n"
        "title: Compact evidence\r\n"
        "memory_relations:\r\n"
        "  - subject: REQ-1\r\n"
        "    predicate: implemented_in\r\n"
        "    object: src/app.py\r\n"
        "    summary: Handles signed payloads\r\n"
        "    reason: The handler is the required boundary\r\n"
        "---\r\n"
        "body confidential and never relation evidence\r\n",
        encoding="utf-8",
    )
    target = tmp_path / "src" / "app.py"
    target.parent.mkdir(parents=True)
    target.write_text("# fixture\n", encoding="utf-8")

    conn = _db(tmp_path)
    result = distill.ingest_markdown_file(path, conn=conn, project_root=tmp_path)

    assert result.facts_inserted >= 1
    declaration = parse_relation_document(path.read_text(encoding="utf-8-sig")).declarations[0]
    assert declaration.summary == "Handles signed payloads"
    assert declaration.reason == "The handler is the required boundary"
    assert declaration.source_line == 4
    assert "body confidential" not in declaration.quote
    quote = conn.execute("SELECT quote FROM provenance WHERE strength = 'stated'").fetchone()[0]
    assert "summary: Handles signed payloads" in quote
    assert "body confidential" not in quote


def test_triple_declarations_remain_compatible_and_receive_a_source_line():
    raw = "---\nstatus: accepted\nmemory_relations:\n  - [REQ-1, realized_by, CAP-1]\n---\nbody\n"

    declaration = parse_relation_document(raw).declarations[0]

    assert (declaration.subject, declaration.predicate, declaration.object) == (
        "REQ-1",
        "realized_by",
        "CAP-1",
    )
    assert declaration.summary is None
    assert declaration.reason is None
    assert declaration.source_line == 4


@pytest.mark.parametrize(
    ("mapping", "message"),
    [
        (
            "subject: REQ-1\n    predicate: realized_by\n    object: CAP-1\n    extra: no",
            "unknown",
        ),
        (
            "subject: REQ-1\n    subject: REQ-2\n    predicate: realized_by\n    object: CAP-1",
            "duplicate",
        ),
        (
            "subject: REQ-1\n    predicate: realized_by\n    object: CAP-1\n    summary: 12",
            "summary must be a string",
        ),
        (
            "subject: REQ-1\n    predicate: realized_by\n    object: CAP-1\n    reason: ''",
            "reason is unsafe",
        ),
        (
            "1: REQ-1\n    predicate: realized_by\n    object: CAP-1",
            "mapping key must be a string",
        ),
        (
            "subject: REQ-1\n    predicate: realized_by\n    object: CAP-1\n"
            '    summary: "one\\ntwo"',
            "summary is unsafe",
        ),
        (
            "subject: REQ-1\n    predicate: realized_by\n    object: CAP-1\n    summary: "
            + "x" * (MAX_RELATION_NOTE_CHARS + 1),
            "summary is unsafe",
        ),
    ],
)
def test_invalid_mapping_evidence_is_rejected_atomically(
    tmp_path: Path, mapping: str, message: str
):
    path = tmp_path / "docs" / "decisions" / "invalid.md"
    path.parent.mkdir(parents=True)
    path.write_text(f"---\nmemory_relations:\n  - {mapping}\n---\nbody\n", encoding="utf-8")
    conn = _db(tmp_path)

    with pytest.raises(RelationDeclarationError, match=message):
        distill.ingest_markdown_file(path, conn=conn, project_root=tmp_path)

    assert conn.execute("SELECT COUNT(*) FROM content_items").fetchone()[0] == 0


@pytest.mark.parametrize(
    "key",
    [
        "memory_relations",
        '"memory_relations"',
        "!!str memory_relations",
        '"memory_\\x72elations"',
    ],
)
def test_reserved_key_spellings_are_declared_relations_not_literal_metadata(
    tmp_path: Path, key: str
):
    raw = f"---\n{key}: [[REQ-1, realized_by, CAP-1]]\n---\nbody\n"
    assert has_relation_declaration(raw)
    assert parse_relation_document(raw).declarations[0].object == "CAP-1"

    path = tmp_path / "docs" / "decisions" / "reserved.md"
    path.parent.mkdir(parents=True)
    path.write_text(raw, encoding="utf-8")
    conn = _db(tmp_path)
    distill.ingest_markdown_file(path, conn=conn, project_root=tmp_path)

    assert conn.execute(
        "SELECT COUNT(*) FROM facts WHERE object_entity_id IS NOT NULL"
    ).fetchone()[0] == 1
    literal_fact_count = conn.execute(
        "SELECT COUNT(*) FROM facts WHERE object_literal IS NOT NULL"
    ).fetchone()[0]
    assert literal_fact_count == 0


def test_duplicate_reserved_key_spellings_are_rejected_consistently():
    raw = (
        "---\nmemory_relations: [[REQ-1, realized_by, CAP-1]]\n"
        '"memory_relations": [[REQ-2, realized_by, CAP-2]]\n---\n'
    )

    with pytest.raises(RelationDeclarationError, match="duplicate declaration"):
        parse_relation_document(raw)


def test_malformed_reserved_key_and_oversized_flow_key_are_rejected(tmp_path: Path):
    malformed = tmp_path / "docs" / "decisions" / "malformed.md"
    malformed.parent.mkdir(parents=True)
    malformed.write_text(
        "---\n\"memory_relations\": [[REQ-1, realized_by, CAP-1]]\ntitle: [\n---\nbody\n",
        encoding="utf-8",
    )
    conn = _db(tmp_path)
    with pytest.raises(RelationDeclarationError, match="malformed YAML"):
        distill.ingest_markdown_file(malformed, conn=conn, project_root=tmp_path)
    assert conn.execute("SELECT COUNT(*) FROM content_items").fetchone()[0] == 0

    oversized = malformed.with_name("oversized.md")
    oversized.write_text(
        "---\n{memory_relations: [[REQ-1, realized_by, CAP-1]]}\n---\n"
        + "x" * (1024 * 1024),
        encoding="utf-8",
    )
    with pytest.raises(RelationDeclarationError, match="source exceeds 1 MiB"):
        distill.ingest_markdown_file(oversized, conn=conn, project_root=tmp_path)
