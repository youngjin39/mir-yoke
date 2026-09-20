"""Contract coverage for purpose-aware relation traversal defaults."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mir.cli.relations import main
from mir.core.engine.memory import distill, store
from mir.core.memory_relations import bundle_memory_relations, query_memory_relations
from mir.core.relations import RelationError, bundle_relations, query_relations


def _write_graph(root: Path, edges: list[tuple[str, str, str]]) -> None:
    (root / "spec").mkdir()
    (root / "spec" / "graph.yaml").write_text(
        "edges:\n"
        + "".join(
            f"  - [{source}, {relation}, {target}]\n" for source, relation, target in edges
        ),
        encoding="utf-8",
    )


def _seed_memory(root: Path, edges: list[tuple[str, str, str]]) -> None:
    source = root / "docs" / "decisions" / "adr-purpose-defaults.md"
    source.parent.mkdir(parents=True)
    source.write_text(
        "---\nstatus: accepted\nmemory_relations:\n"
        + "".join(
            f"  - [{subject}, {predicate}, {target}]\n" for subject, predicate, target in edges
        )
        + "---\n",
        encoding="utf-8",
    )
    (root / ".mir").mkdir()
    connection = store.connect(root / ".mir" / "memory.db", load_vec=False)
    try:
        store.apply_migrations(connection.conn)
        distill.ingest_markdown_file(source, conn=connection.conn, project_root=root)
        assert connection.conn.execute(
            "SELECT COUNT(*) FROM facts WHERE object_entity_id IS NOT NULL "
            "AND predicate IN ('realized_by', 'implemented_in', 'verified_by', 'depends_on')"
        ).fetchone()[0] == len(edges)
    finally:
        connection.conn.close()


def _edge_keys(result: dict[str, object]) -> set[tuple[str, str, str]]:
    return {
        (edge["source"], edge["relation"], edge["target"])
        for edge in result["edges"]
    }


def _facet(result: dict[str, object], purpose: str) -> dict[str, object]:
    return next(item for item in result["facets"] if item["purpose"] == purpose)


_DEPENDENCY_CHAIN = [("A", "depends_on", "B"), ("B", "depends_on", "C")]
_IMPLEMENTATION_CHAIN = [
    ("A", "realized_by", "B"),
    ("B", "realized_by", "C"),
    ("C", "realized_by", "D"),
]
_VERIFICATION_CHAIN = [
    ("B", "realized_by", "A"),
    ("C", "realized_by", "B"),
    ("C", "verified_by", "tests/check.py"),
]
_IMPACT_CHAIN = [
    ("B", "depends_on", "A"),
    ("C", "depends_on", "B"),
    ("D", "depends_on", "C"),
]


def test_default_dependencies_are_direct_for_yaml_memory_and_cli(
    tmp_path: Path, capsys
) -> None:
    yaml_root, memory_root = tmp_path / "yaml", tmp_path / "memory"
    yaml_root.mkdir()
    memory_root.mkdir()
    _write_graph(yaml_root, _DEPENDENCY_CHAIN)
    _seed_memory(memory_root, _DEPENDENCY_CHAIN)

    assert _edge_keys(query_relations("A", "dependencies", root=yaml_root)) == {
        ("A", "depends_on", "B")
    }
    assert _edge_keys(query_memory_relations("A", "dependencies", root=memory_root)) == {
        ("A", "depends_on", "B")
    }
    assert (
        main(["query", "A", "--purpose", "dependencies", "--root", str(yaml_root), "--json"])
        == 0
    )
    assert {
        (edge["source"], edge["relation"], edge["target"])
        for edge in json.loads(capsys.readouterr().out)["edges"]
    } == {("A", "depends_on", "B")}
    assert (
        main(
            [
                "query",
                "A",
                "--purpose",
                "dependencies",
                "--root",
                str(memory_root),
                "--memory",
                "--json",
            ]
        )
        == 0
    )
    assert len(json.loads(capsys.readouterr().out)["edges"]) == 1


def test_explicit_depth_applies_to_dependency_chains_for_yaml_memory_and_cli(
    tmp_path: Path, capsys
) -> None:
    yaml_root, memory_root = tmp_path / "yaml", tmp_path / "memory"
    yaml_root.mkdir()
    memory_root.mkdir()
    _write_graph(yaml_root, _DEPENDENCY_CHAIN)
    _seed_memory(memory_root, _DEPENDENCY_CHAIN)

    assert _edge_keys(query_relations("A", "dependencies", root=yaml_root, depth=2)) == set(
        _DEPENDENCY_CHAIN
    )
    assert _edge_keys(
        query_memory_relations("A", "dependencies", root=memory_root, depth=2)
    ) == set(_DEPENDENCY_CHAIN)
    assert main(
        [
            "query",
            "A",
            "--purpose",
            "dependencies",
            "--root",
            str(yaml_root),
            "--depth",
            "2",
            "--json",
        ]
    ) == 0
    assert len(json.loads(capsys.readouterr().out)["edges"]) == 2


def test_non_dependency_default_remains_three_hops_for_yaml_and_memory(tmp_path: Path) -> None:
    yaml_root, memory_root = tmp_path / "yaml", tmp_path / "memory"
    yaml_root.mkdir()
    memory_root.mkdir()
    _write_graph(yaml_root, _IMPLEMENTATION_CHAIN)
    _seed_memory(memory_root, _IMPLEMENTATION_CHAIN)

    assert _edge_keys(query_relations("A", "implementation", root=yaml_root)) == set(
        _IMPLEMENTATION_CHAIN
    )
    assert _edge_keys(query_memory_relations("A", "implementation", root=memory_root)) == set(
        _IMPLEMENTATION_CHAIN
    )


def test_verification_default_remains_three_hops_for_yaml_and_memory(tmp_path: Path) -> None:
    yaml_root, memory_root = tmp_path / "yaml", tmp_path / "memory"
    yaml_root.mkdir()
    memory_root.mkdir()
    for root in (yaml_root, memory_root):
        (root / "tests").mkdir()
        (root / "tests" / "check.py").write_text("", encoding="utf-8")
    _write_graph(yaml_root, _VERIFICATION_CHAIN)
    _seed_memory(memory_root, _VERIFICATION_CHAIN)

    assert _edge_keys(query_relations("A", "verification", root=yaml_root)) == set(
        _VERIFICATION_CHAIN
    )
    assert _edge_keys(query_memory_relations("A", "verification", root=memory_root)) == set(
        _VERIFICATION_CHAIN
    )


def test_impact_default_remains_three_hops_for_yaml_and_memory(tmp_path: Path) -> None:
    yaml_root, memory_root = tmp_path / "yaml", tmp_path / "memory"
    yaml_root.mkdir()
    memory_root.mkdir()
    _write_graph(yaml_root, _IMPACT_CHAIN)
    _seed_memory(memory_root, _IMPACT_CHAIN)

    assert _edge_keys(query_relations("A", "impact", root=yaml_root)) == set(_IMPACT_CHAIN)
    assert _edge_keys(query_memory_relations("A", "impact", root=memory_root)) == set(
        _IMPACT_CHAIN
    )


def test_mixed_bundles_resolve_default_depth_per_facet_for_yaml_and_memory(
    tmp_path: Path,
) -> None:
    edges = [*_DEPENDENCY_CHAIN, *_IMPLEMENTATION_CHAIN]
    yaml_root, memory_root = tmp_path / "yaml", tmp_path / "memory"
    yaml_root.mkdir()
    memory_root.mkdir()
    _write_graph(yaml_root, edges)
    _seed_memory(memory_root, edges)

    for bundle in (
        bundle_relations(["A"], ["dependencies", "implementation"], root=yaml_root),
        bundle_memory_relations(["A"], ["dependencies", "implementation"], root=memory_root),
    ):
        assert bundle["route"] != "search"
        assert _facet(bundle, "dependencies")["available_count"] == 1
        assert _facet(bundle, "implementation")["available_count"] == 3


def test_explicit_bundle_depth_applies_to_every_facet_for_yaml_and_memory(
    tmp_path: Path,
) -> None:
    edges = [*_DEPENDENCY_CHAIN, *_IMPLEMENTATION_CHAIN]
    yaml_root, memory_root = tmp_path / "yaml", tmp_path / "memory"
    yaml_root.mkdir()
    memory_root.mkdir()
    _write_graph(yaml_root, edges)
    _seed_memory(memory_root, edges)

    for bundle in (
        bundle_relations(["A"], ["dependencies", "implementation"], root=yaml_root, depth=2),
        bundle_memory_relations(
            ["A"], ["dependencies", "implementation"], root=memory_root, depth=2
        ),
    ):
        assert _facet(bundle, "dependencies")["available_count"] == 2
        assert _facet(bundle, "implementation")["available_count"] == 2


@pytest.mark.parametrize("depth", [True, 0, 5])
def test_invalid_explicit_depths_preserve_limit_errors(tmp_path: Path, capsys, depth: int) -> None:
    _write_graph(tmp_path, _DEPENDENCY_CHAIN)
    with pytest.raises(RelationError, match="depth must be between 1 and 4"):
        query_relations("A", "dependencies", root=tmp_path, depth=depth)
    with pytest.raises(RelationError, match="depth must be between 1 and 4"):
        bundle_relations(["A"], ["dependencies", "implementation"], root=tmp_path, depth=depth)
    with pytest.raises(RelationError, match="depth must be between 1 and 4"):
        query_memory_relations("A", "dependencies", root=tmp_path, depth=depth)
    with pytest.raises(RelationError, match="depth must be between 1 and 4"):
        bundle_memory_relations(
            ["A"], ["dependencies", "implementation"], root=tmp_path, depth=depth
        )
    if not isinstance(depth, bool):
        assert (
            main(
                [
                    "query",
                    "A",
                    "--purpose",
                    "dependencies",
                    "--root",
                    str(tmp_path),
                    "--depth",
                    str(depth),
                ]
            )
            == 2
        )
        assert "depth must be between 1 and 4" in capsys.readouterr().err
