from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from mir.core.engine.memory import store
from mir.core.memory_relations import bundle_memory_relations, query_memory_relations
from mir.core.relations import RelationError, render_bundle_human, render_human, render_json


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_text(encoding="utf-8-sig").encode("utf-8")).hexdigest()


def _seed(
    root: Path,
    *,
    source_path: str = "docs/relations.md",
    document_status: str = "accepted",
    predicate: str = "realized_by",
    subject: str = "FR-1",
    target: str = "MOD-1",
    endpoint_status: str | None = None,
    additional_declarations: tuple[tuple[str, str, str], ...] = (),
) -> tuple[Path, int]:
    document = root / source_path
    document.parent.mkdir(parents=True, exist_ok=True)
    document.write_text(
        f"---\nstatus: {document_status}\nmemory_relations:\n"
        f"  - [{subject}, {predicate}, {target}]\n"
        + "".join(
            f"  - [{left}, {relation}, {right}]\n"
            for left, relation, right in additional_declarations
        )
        + "---\n",
        encoding="utf-8",
    )
    db_path = root / ".mir/memory.db"
    db_path.parent.mkdir(exist_ok=True)
    connection = store.connect(db_path, load_vec=False)
    try:
        store.apply_migrations(connection.conn)
        conn = connection.conn
        conn.execute(
            "INSERT OR IGNORE INTO entities(canonical_name, slug) VALUES (?, ?)",
            (subject, subject),
        )
        subject_id = int(
            conn.execute("SELECT id FROM entities WHERE slug = ?", (subject,)).fetchone()[0]
        )
        conn.execute(
            "INSERT OR IGNORE INTO entities(canonical_name, slug) VALUES (?, ?)",
            (target, target),
        )
        target_id = int(
            conn.execute("SELECT id FROM entities WHERE slug = ?", (target,)).fetchone()[0]
        )
        metadata = json.dumps(
            {
                "path": source_path,
                "relation_schema": "mir-memory-relations/v1",
                "relation_project_path": str(root.resolve()),
                "relation_document_status": document_status,
            }
        )
        conn.execute(
            "INSERT INTO content_items(source, text_hash, metadata_json) VALUES (?, ?, ?)",
            ("self_ingest_md", _hash(document), metadata),
        )
        content_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        conn.execute(
            """
            INSERT INTO facts(subject_entity_id, predicate, object_entity_id, object_literal,
                              polarity, status, valid_to, scope, project_path, created_from)
            VALUES (?, ?, ?, NULL, 'asserted', 'active', NULL, 'project', ?, ?)
            """,
            (subject_id, predicate, target_id, str(root.resolve()), content_id),
        )
        fact_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        conn.execute(
            "INSERT INTO provenance(fact_id, content_item_id, quote, strength) "
            "VALUES (?, ?, ?, 'stated')",
            (fact_id, content_id, f"  - [{subject}, {predicate}, {target}]"),
        )
        if endpoint_status is not None:
            conn.execute(
                """
                INSERT INTO facts(subject_entity_id, predicate, object_literal, polarity, status)
                VALUES (?, 'status', ?, 'asserted', 'active')
                """,
                (target_id, endpoint_status),
            )
        conn.commit()
    finally:
        connection.conn.close()
    return db_path, fact_id


def test_should_query_declared_memory_fact_read_only_with_provenance(tmp_path: Path) -> None:
    db_path, fact_id = _seed(tmp_path)
    before = db_path.read_bytes()
    result = query_memory_relations("FR-1", "implementation", root=tmp_path)
    assert [(edge["source"], edge["relation"], edge["target"]) for edge in result["edges"]] == [
        ("FR-1", "realized_by", "MOD-1")
    ]
    provenance = result["edges"][0]["provenance"]
    assert provenance["fact_id"] == fact_id
    assert provenance["source_path"] == "docs/relations.md"
    assert provenance["source_hash"] == _hash(tmp_path / "docs/relations.md")
    assert result["source"]["memory_db"] == ".mir/memory.db"
    assert db_path.read_bytes() == before
    assert not Path(f"{db_path}-wal").exists() and not Path(f"{db_path}-shm").exists()
    assert "fact_id=" in render_human(result, 4096)
    assert json.loads(render_json(result, 4096))["edges"][0]["provenance"]["fact_id"] == fact_id


def test_should_render_each_deduplicated_memory_source_within_budget(tmp_path: Path) -> None:
    _, first_fact = _seed(tmp_path, source_path="docs/first.md")
    _, second_fact = _seed(tmp_path, source_path="docs/second.md")
    result = query_memory_relations("FR-1", "implementation", root=tmp_path)
    assert len(result["edges"]) == 1
    human = render_human(result, 4096)
    for source_path, fact_id in (("docs/first.md", first_fact), ("docs/second.md", second_fact)):
        assert json.dumps(source_path) in human
        assert f"fact_id={fact_id}" in human
        assert _hash(tmp_path / source_path) in human
    assert len(human.encode("utf-8")) <= 4096
    bounded = render_human(result, 1024)
    assert len(bounded.encode("utf-8")) <= 1024


@pytest.mark.parametrize(
    "change", ["changed", "deleted", "draft", "endpoint_inactive", "subject_candidate"]
)
def test_should_exclude_stale_or_noncurrent_memory_evidence(tmp_path: Path, change: str) -> None:
    kwargs = {"document_status": "draft"} if change == "draft" else {}
    if change == "endpoint_inactive":
        kwargs["endpoint_status"] = "historical"
    db_path, _ = _seed(tmp_path, **kwargs)
    if change == "subject_candidate":
        conn = sqlite3.connect(db_path)
        try:
            subject_id = conn.execute("SELECT id FROM entities WHERE slug = 'FR-1'").fetchone()[0]
            conn.execute(
                "INSERT INTO facts(subject_entity_id, predicate, object_literal, polarity, status) "
                "VALUES (?, 'status', 'candidate', 'asserted', 'active')",
                (subject_id,),
            )
            conn.commit()
        finally:
            conn.close()
    source = tmp_path / "docs/relations.md"
    if change == "changed":
        source.write_text("changed", encoding="utf-8")
    elif change == "deleted":
        source.unlink()
    if change in {"endpoint_inactive", "subject_candidate"}:
        with pytest.raises(RelationError, match="unknown anchor"):
            query_memory_relations("FR-1", "implementation", root=tmp_path)
    else:
        result = query_memory_relations("FR-1", "implementation", root=tmp_path)
        assert result["edges"] == []
        assert result["notices"]


def test_should_not_reuse_source_cache_for_wrong_row_metadata(tmp_path: Path) -> None:
    db_path, _ = _seed(tmp_path)
    conn = sqlite3.connect(db_path)
    try:
        source_id = conn.execute("SELECT id FROM entities WHERE slug = 'FR-1'").fetchone()[0]
        conn.execute("INSERT INTO entities(canonical_name, slug) VALUES ('MOD-2', 'MOD-2')")
        target_id = conn.execute("SELECT id FROM entities WHERE slug = 'MOD-2'").fetchone()[0]
        text_hash = _hash(tmp_path / "docs/relations.md")
        metadata = json.dumps(
            {
                "path": "docs/relations.md",
                "relation_schema": "mir-memory-relations/v1",
                "relation_project_path": "/wrong/root",
                "relation_document_status": "accepted",
            }
        )
        conn.execute(
            "INSERT INTO content_items(source, text_hash, metadata_json) "
            "VALUES ('self_ingest_md', ?, ?)",
            (text_hash, metadata),
        )
        content_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            """
            INSERT INTO facts(subject_entity_id, predicate, object_entity_id, object_literal,
                              polarity, status, valid_to, scope, project_path, created_from)
            VALUES (?, 'realized_by', ?, NULL, 'asserted', 'active', NULL, 'project', ?, ?)
            """,
            (source_id, target_id, str(tmp_path.resolve()), content_id),
        )
        fact_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO provenance(fact_id, content_item_id, quote, strength) "
            "VALUES (?, ?, ?, 'stated')",
            (fact_id, content_id, "- [FR-1, realized_by, MOD-1]"),
        )
        conn.commit()
    finally:
        conn.close()
    targets = {
        edge["target"]
        for edge in query_memory_relations("FR-1", "implementation", root=tmp_path)["edges"]
    }
    assert targets == {"MOD-1"}


def test_should_bind_fact_provenance_quote_to_its_declared_triple(tmp_path: Path) -> None:
    db_path, _ = _seed(
        tmp_path,
        additional_declarations=(("FR-1", "depends_on", "MOD-OTHER"),),
    )
    conn = sqlite3.connect(db_path)
    try:
        fact_id = conn.execute("SELECT id FROM facts WHERE predicate = 'realized_by'").fetchone()[0]
        conn.execute(
            "UPDATE provenance SET quote = ? WHERE fact_id = ?",
            ("  - [FR-1, depends_on, MOD-OTHER]", fact_id),
        )
        conn.commit()
    finally:
        conn.close()
    result = query_memory_relations("FR-1", "implementation", root=tmp_path)
    assert result["edges"] == []
    assert any("missing relation provenance" in notice for notice in result["notices"])


def test_should_validate_query_before_memory_database_access(tmp_path: Path) -> None:
    with pytest.raises(RelationError, match="purpose must"):
        query_memory_relations("FR-1", "unknown", root=tmp_path)
    with pytest.raises(RelationError, match="anchor must be non-empty"):
        query_memory_relations("", "implementation", root=tmp_path)


def test_should_refuse_unsafe_memory_database_and_protected_source(tmp_path: Path) -> None:
    _seed(tmp_path)
    (tmp_path / ".mir/repo-profile.toml").write_text(
        "[paths]\nprotected_paths = ['docs/**']\n", encoding="utf-8"
    )
    assert query_memory_relations("FR-1", "implementation", root=tmp_path)["edges"] == []
    other = tmp_path.parent / "other-memory.db"
    other.write_bytes((tmp_path / ".mir/memory.db").read_bytes())
    (tmp_path / ".mir/memory.db").unlink()
    (tmp_path / ".mir/memory.db").symlink_to(other)
    with pytest.raises(RelationError, match="memory database"):
        query_memory_relations("FR-1", "implementation", root=tmp_path)


def test_should_bundle_memory_edges_with_budgets_and_honest_unavailable_search(
    tmp_path: Path,
) -> None:
    _seed(tmp_path, predicate="realized_by")
    _seed(
        tmp_path,
        source_path="docs/verification.md",
        predicate="verified_by",
        target="tests/test_relation.py",
    )
    (tmp_path / "tests/test_relation.py").parent.mkdir(exist_ok=True)
    (tmp_path / "tests/test_relation.py").write_text("", encoding="utf-8")
    result = bundle_memory_relations(
        ["FR-1"], ["implementation", "verification"], root=tmp_path, max_edges=1
    )
    assert result["route"] == "memory" and result["truncated"]
    assert len(result["edges"]) == 1
    assert "fact_id=" in render_bundle_human(result, 4096)
    missing_root = tmp_path / "missing"
    missing_root.mkdir()
    missing = bundle_memory_relations(
        ["FR-1"], ["implementation", "verification"], root=missing_root
    )
    assert missing["route"] == "search" and "memory unavailable" in missing["reason"]
