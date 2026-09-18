"""Regression checks for anchor-first memory relation selection."""

from __future__ import annotations

from pathlib import Path

import pytest

from mir.core import memory_relations
from mir.core.engine.memory import distill, store
from mir.core.memory_relations import bundle_memory_relations, query_memory_relations


def _ingest(root: Path, name: str, declarations: list[tuple[str, str, str]]) -> Path:
    path = root / "docs" / "decisions" / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\nstatus: accepted\nmemory_relations:\n"
        + "".join(
            f"  - [{source}, {predicate}, {target}]\n" for source, predicate, target in declarations
        )
        + "---\n",
        encoding="utf-8",
    )
    return path


def _seed(root: Path, *documents: tuple[str, list[tuple[str, str, str]]]) -> list[Path]:
    (root / ".mir").mkdir(exist_ok=True)
    paths = [_ingest(root, name, declarations) for name, declarations in documents]
    connection = store.connect(root / ".mir" / "memory.db", load_vec=False)
    try:
        store.apply_migrations(connection.conn)
        for path in paths:
            distill.ingest_markdown_file(path, conn=connection.conn, project_root=root)
    finally:
        connection.conn.close()
    return paths


def test_sql_neighborhood_ignores_disconnected_sources_beyond_legacy_row_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".mir").mkdir()
    target = _ingest(tmp_path, "target", [("MOD-TARGET", "depends_on", "MOD-REQUIRED")])
    connection = store.connect(tmp_path / ".mir" / "memory.db", load_vec=False)
    try:
        store.apply_migrations(connection.conn)
        distill.ingest_markdown_file(target, conn=connection.conn, project_root=tmp_path)
        for group in range(32):
            source = _ingest(
                tmp_path,
                f"noise-{group}",
                [
                    (f"NOISE-{group}-{item}", "depends_on", f"OTHER-{group}-{item}")
                    for item in range(64)
                ],
            )
            distill.ingest_markdown_file(source, conn=connection.conn, project_root=tmp_path)
    finally:
        connection.conn.close()

    original_open = Path.open
    opened: list[Path] = []

    def record_open(path: Path, mode: str = "r", *args: object, **kwargs: object):
        if mode == "rb":
            opened.append(path)
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", record_open)
    result = query_memory_relations("MOD-TARGET", "dependencies", root=tmp_path)

    assert [(edge["source"], edge["relation"], edge["target"]) for edge in result["edges"]] == [
        ("MOD-TARGET", "depends_on", "MOD-REQUIRED")
    ]
    assert opened == [target]


def test_unknown_anchor_does_not_open_any_relation_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".mir").mkdir()
    source = _ingest(tmp_path, "known", [("KNOWN", "depends_on", "OTHER")])
    connection = store.connect(tmp_path / ".mir" / "memory.db", load_vec=False)
    try:
        store.apply_migrations(connection.conn)
        distill.ingest_markdown_file(source, conn=connection.conn, project_root=tmp_path)
    finally:
        connection.conn.close()

    original_open = Path.open

    def forbid_source_open(path: Path, mode: str = "r", *args: object, **kwargs: object):
        if path == source and mode == "rb":
            raise AssertionError("unknown anchors must not read relation sources")
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", forbid_source_open)
    with pytest.raises(ValueError, match="unknown anchor"):
        query_memory_relations("UNKNOWN", "dependencies", root=tmp_path)


def test_exact_candidate_cap_with_no_new_frontier_candidate_completes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(tmp_path, ("only", [("A", "depends_on", "B")]))
    monkeypatch.setattr(memory_relations, "_MAX_DB_ROWS", 1)
    assert query_memory_relations("A", "dependencies", root=tmp_path, depth=3)["edges"]


def test_candidate_cap_plus_one_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(
        tmp_path,
        ("first", [("A", "depends_on", "B")]),
        ("second", [("A", "depends_on", "C")]),
    )
    monkeypatch.setattr(memory_relations, "_MAX_DB_ROWS", 1)
    with pytest.raises(ValueError, match="memory relation view is incomplete"):
        query_memory_relations("A", "dependencies", root=tmp_path)


def test_bundle_reuses_validated_fact_without_duplicate_proof(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "check.py").write_text("", encoding="utf-8")
    _seed(tmp_path, ("proof", [("REQ", "verified_by", "tests/check.py")]))
    calls = 0
    original = memory_relations._source_text

    def counted(*args: object, **kwargs: object):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(memory_relations, "_source_text", counted)
    result = bundle_memory_relations(["REQ"], ["impact", "verification"], root=tmp_path)
    assert result["route"] == "memory" and calls == 1
    assert len(result["edges"][0]["provenance"]["sources"]) == 1


def test_stale_bridge_does_not_open_downstream_or_expand(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bridge, downstream = _seed(
        tmp_path,
        ("bridge", [("A", "depends_on", "B")]),
        ("downstream", [("B", "depends_on", "C")]),
    )
    bridge.write_text("stale", encoding="utf-8")
    original_open = Path.open

    def forbid_downstream(path: Path, mode: str = "r", *args: object, **kwargs: object):
        if path == downstream and mode == "rb":
            raise AssertionError("invalid bridge expanded into downstream source")
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", forbid_downstream)
    result = query_memory_relations("A", "dependencies", root=tmp_path, depth=3)
    assert result["edges"] == []


def test_depth_probe_does_not_open_beyond_depth_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _bridge, downstream = _seed(
        tmp_path,
        ("bridge", [("A", "depends_on", "B")]),
        ("downstream", [("B", "depends_on", "C")]),
    )
    original_open = Path.open

    def forbid_downstream(path: Path, mode: str = "r", *args: object, **kwargs: object):
        if path == downstream and mode == "rb":
            raise AssertionError("depth metadata probe read an unselected source")
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", forbid_downstream)
    result = query_memory_relations("A", "dependencies", root=tmp_path, depth=1)
    assert result["truncated"] is True


def test_canonical_file_anchor_matches_stored_locator_spelling_but_not_case(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "a.py").write_text("", encoding="utf-8")
    (tmp_path / "tests" / "check.py").write_text("", encoding="utf-8")
    _seed(
        tmp_path,
        (
            "locators",
            [
                ("././src/a.py::run", "verified_by", "tests/check.py"),
                ("MOD", "implemented_in", "src//a.py::run"),
                ("REQ", "realized_by", "MOD"),
                ("SRC/A.PY::run", "verified_by", "tests/check.py"),
            ],
        ),
    )
    direct = query_memory_relations("src/a.py", "verification", root=tmp_path)
    direct_sources = {edge["source"] for edge in direct["edges"]}
    assert "././src/a.py::run" in direct_sources
    assert "SRC/A.PY::run" not in direct_sources
    bundle = bundle_memory_relations(
        ["src/a.py"], ["implementation", "verification"], root=tmp_path
    )
    assert bundle["route"] == "memory" and bundle["resolved_anchor"] == "MOD"


def test_candidate_overflow_is_incomplete_even_when_max_edges_stops_processing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(
        tmp_path,
        ("neighbors", [("A", "depends_on", value) for value in ("B", "C", "D", "E")]),
    )
    monkeypatch.setattr(memory_relations, "_MAX_DB_ROWS", 3)
    with pytest.raises(ValueError, match="memory relation view is incomplete"):
        query_memory_relations("A", "dependencies", root=tmp_path, max_edges=1)


def test_bundle_candidate_accounting_keeps_unprocessed_fresh_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(
        tmp_path,
        (
            "facets",
            [
                ("A", "realized_by", "B"),
                ("A", "realized_by", "C"),
                ("A", "realized_by", "D"),
                ("A", "depends_on", "E"),
            ],
        ),
    )
    monkeypatch.setattr(memory_relations, "_MAX_DB_ROWS", 3)
    result = bundle_memory_relations(
        ["A"], ["implementation", "dependencies"], root=tmp_path, max_edges=1
    )
    assert result["route"] == "search" and result["truncated"] is True
    assert result["reason"] == "memory relation view is incomplete"


def test_owner_source_race_is_incomplete_with_diagnostic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("", encoding="utf-8")
    source = _seed(tmp_path, ("owner", [("MOD", "implemented_in", "src/a.py")]))[0]
    original_open = Path.open

    def mutate_owner(path: Path, mode: str = "r", *args: object, **kwargs: object):
        opened = original_open(path, mode, *args, **kwargs)
        if path == source and mode == "rb":
            with original_open(path, "ab") as writer:
                writer.write(b"race\n")
        return opened

    monkeypatch.setattr(Path, "open", mutate_owner)
    result = bundle_memory_relations(
        ["src/a.py"], ["implementation", "verification"], root=tmp_path
    )
    assert result["reason"] == "memory relation view is incomplete"
    assert result["truncated"] is True
    assert any("source changed while reading" in notice for notice in result["notices"])


@pytest.mark.parametrize(
    ("stored", "anchor"),
    [
        ("././src/a.py::run", "src/a.py"),
        ("src/./a.py::run", "src/a.py"),
        ("src///a.py::run", "src/a.py"),
        ("src/foo./a.py::run", "src/foo./a.py"),
    ],
)
def test_locator_variants_resolve_bare_and_exact_symbols(
    tmp_path: Path, stored: str, anchor: str
) -> None:
    file_path = tmp_path / anchor
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text("", encoding="utf-8")
    (tmp_path / "tests").mkdir(exist_ok=True)
    (tmp_path / "tests" / "check.py").write_text("", encoding="utf-8")
    _seed(tmp_path, ("locator", [(stored, "verified_by", "tests/check.py")]))
    for locator in (anchor, f"{anchor}::run"):
        result = query_memory_relations(locator, "verification", root=tmp_path)
        assert any(edge["source"] == stored for edge in result["edges"])


def test_uppercase_only_implementation_owner_does_not_match_lowercase_anchor(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("", encoding="utf-8")
    _seed(tmp_path, ("owner", [("MOD", "implemented_in", "SRC/A.PY::run")]))
    result = bundle_memory_relations(
        ["src/a.py"], ["implementation", "verification"], root=tmp_path
    )
    assert result["route"] == "search" and result["reason"] == "unknown anchor"


def test_empty_bundle_facet_preserves_stale_source_diagnostic(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/check.py").write_text("", encoding="utf-8")
    stale, _ = _seed(
        tmp_path,
        ("implementation", [("A", "realized_by", "B")]),
        ("verification", [("A", "verified_by", "tests/check.py")]),
    )
    stale.write_text("stale", encoding="utf-8")
    result = bundle_memory_relations(["A"], ["implementation", "verification"], root=tmp_path)
    assert result["route"] == "search" and result["truncated"] is False
    assert any("stale relation source" in notice for notice in result["notices"])


def test_alias_selection_sentinel_does_not_claim_exact_omitted_count(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/x.py").write_text("", encoding="utf-8")
    _seed(
        tmp_path,
        *[
            (
                f"aliases-{group}",
                [
                    (f"tests/x.py::symbol_{group}_{item}", "depends_on", "MODULE")
                    for item in range(64)
                ],
            )
            for group in range(2)
        ],
    )
    result = query_memory_relations("tests/x.py", "dependencies", root=tmp_path, max_edges=64)
    assert result["truncated"] is True
    assert any("additional locators remain unexamined" in notice for notice in result["notices"])
    assert not any("omitted 1 locator" in notice for notice in result["notices"])
