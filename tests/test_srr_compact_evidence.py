from __future__ import annotations

from pathlib import Path

import pytest

from mir.core.engine.memory import distill, store
from mir.core.memory_relations import bundle_memory_relations, query_memory_relations
from mir.core.relations import RelationError, render_bundle_human, render_human, render_json


def _seed_large_sources(root: Path, count: int = 5) -> None:
    (root / ".mir").mkdir()
    (root / "docs" / "decisions").mkdir(parents=True)
    connection = store.connect(root / ".mir/memory.db", load_vec=False)
    try:
        store.apply_migrations(connection.conn)
        for index in range(count):
            source = root / "docs" / "decisions" / f"source-{index}.md"
            text = (
                "---\nstatus: accepted\nmemory_relations:\n"
                f"  - [MOD-A, depends_on, MOD-{index}]\n---\n"
            )
            source.write_bytes(
                text.encode("utf-8") + b"x" * (1024 * 1024 - len(text.encode("utf-8")))
            )
            distill.ingest_markdown_file(source, conn=connection.conn, project_root=root)
    finally:
        connection.conn.close()


def test_source_budget_refuses_partial_memory_view_and_keeps_fallback_diagnostics(
    tmp_path: Path,
) -> None:
    _seed_large_sources(tmp_path)

    with pytest.raises(RelationError, match="memory relation view is incomplete"):
        query_memory_relations("MOD-A", "dependencies", root=tmp_path)

    result = bundle_memory_relations(
        ["MOD-A"], ["dependencies", "implementation"], root=tmp_path
    )
    assert result["route"] == "search"
    assert result["scope"] == "declared_memory_relations_only"
    assert result["truncated"] is True
    assert any("source validation byte limit" in notice for notice in result["notices"])
    assert "scope=declared_memory_relations_only" in render_bundle_human(result, 1024)


def test_compact_evidence_keeps_authored_notes_and_source_location(tmp_path: Path) -> None:
    (tmp_path / ".mir").mkdir()
    source = tmp_path / "docs" / "decisions" / "relation.md"
    source.parent.mkdir(parents=True)
    source.write_text(
        "---\nstatus: accepted\nmemory_relations:\n"
        "  - subject: REQ-1\n"
        "    predicate: realized_by\n"
        "    object: MOD-1\n"
        "    summary: The requirement has a concrete module.\n"
        "    reason: The decision assigns this work to the module.\n"
        "---\nRAW_DECLARATION_OR_BODY_MUST_NOT_LEAK\n",
        encoding="utf-8",
    )
    connection = store.connect(tmp_path / ".mir" / "memory.db", load_vec=False)
    try:
        store.apply_migrations(connection.conn)
        distill.ingest_markdown_file(source, conn=connection.conn, project_root=tmp_path)
    finally:
        connection.conn.close()

    result = query_memory_relations("REQ-1", "implementation", root=tmp_path)
    edge = result["edges"][0]
    aggregate = edge["provenance"]
    proof = aggregate["sources"][0]
    for field in ("source_line", "summary", "summary_basis", "reason", "reason_basis"):
        assert field not in edge and field not in aggregate
    assert proof["source_line"] == 4
    assert proof["summary"] == "The requirement has a concrete module."
    assert proof["reason"] == "The decision assigns this work to the module."
    assert proof["summary_basis"] == proof["reason_basis"] == "authored"
    for rendered in (render_json(result, 1024), render_human(result, 1024)):
        assert "RAW_DECLARATION_OR_BODY_MUST_NOT_LEAK" not in rendered
        assert len(rendered.encode("utf-8")) <= 1024


def test_independent_source_reasons_remain_on_their_own_proofs(tmp_path: Path) -> None:
    (tmp_path / ".mir").mkdir()
    source_dir = tmp_path / "docs" / "decisions"
    source_dir.mkdir(parents=True)
    connection = store.connect(tmp_path / ".mir" / "memory.db", load_vec=False)
    try:
        store.apply_migrations(connection.conn)
        for name, reason in (
            ("first", "First source rationale."),
            ("second", "Second source rationale."),
        ):
            source = source_dir / f"{name}.md"
            source.write_text(
                "---\nstatus: accepted\nmemory_relations:\n"
                "  - subject: REQ-1\n"
                "    predicate: realized_by\n"
                "    object: MOD-1\n"
                f"    reason: {reason}\n---\n",
                encoding="utf-8",
            )
            distill.ingest_markdown_file(source, conn=connection.conn, project_root=tmp_path)
    finally:
        connection.conn.close()

    edge = query_memory_relations("REQ-1", "implementation", root=tmp_path)["edges"][0]
    proofs = edge["provenance"]["sources"]
    assert {(proof["source_path"], proof["reason"]) for proof in proofs} == {
        ("docs/decisions/first.md", "First source rationale."),
        ("docs/decisions/second.md", "Second source rationale."),
    }


def test_source_proof_cap_is_visible_and_marks_the_result_truncated(tmp_path: Path) -> None:
    (tmp_path / ".mir").mkdir()
    sources = tmp_path / "docs" / "decisions"
    sources.mkdir(parents=True)
    connection = store.connect(tmp_path / ".mir" / "memory.db", load_vec=False)
    try:
        store.apply_migrations(connection.conn)
        for index in range(9):
            source = sources / f"source-{index}.md"
            source.write_text(
                "---\nstatus: accepted\nmemory_relations:\n"
                "  - [REQ-1, realized_by, MOD-1]\n---\n",
                encoding="utf-8",
            )
            distill.ingest_markdown_file(source, conn=connection.conn, project_root=tmp_path)
    finally:
        connection.conn.close()

    result = query_memory_relations("REQ-1", "implementation", root=tmp_path)
    provenance = result["edges"][0]["provenance"]
    assert len(provenance["sources"]) == 8
    assert provenance["sources_omitted"] == 1
    assert result["truncated"] is True
    assert any("source proof limit" in notice for notice in result["notices"])


@pytest.mark.parametrize("mutation", ["append", "replace"])
def test_source_change_after_open_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    (tmp_path / ".mir").mkdir()
    source = tmp_path / "docs" / "decisions" / "race.md"
    source.parent.mkdir(parents=True)
    source.write_text(
        "---\nstatus: accepted\nmemory_relations:\n"
        "  - [REQ-1, realized_by, MOD-1]\n---\n",
        encoding="utf-8",
    )
    connection = store.connect(tmp_path / ".mir" / "memory.db", load_vec=False)
    try:
        store.apply_migrations(connection.conn)
        distill.ingest_markdown_file(source, conn=connection.conn, project_root=tmp_path)
    finally:
        connection.conn.close()

    original_open = Path.open
    changes = 0

    def mutate_after_open(path: Path, mode: str = "r", *args, **kwargs):
        nonlocal changes
        opened = original_open(path, mode, *args, **kwargs)
        if path == source and mode == "rb":
            changes += 1
            with original_open(path, "ab" if mutation == "append" else "wb") as writer:
                writer.write(b"changed while relation reader was open\n")
        return opened

    monkeypatch.setattr(Path, "open", mutate_after_open)
    with pytest.raises(RelationError, match="memory relation view is incomplete"):
        query_memory_relations("REQ-1", "implementation", root=tmp_path)
    fallback = bundle_memory_relations(
        ["REQ-1"], ["implementation", "verification"], root=tmp_path
    )
    assert changes == 2 and fallback["route"] == "search" and fallback["truncated"] is True
    assert fallback["scope"] == "declared_memory_relations_only"
    assert any("source changed while reading" in notice for notice in fallback["notices"])
