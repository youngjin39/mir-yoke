"""Independent contract checks for selective compound retrieval."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from mir.core.relations import bundle_relations, render_bundle_human, render_json


def _fixture(root: Path) -> None:
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "src/a.py").write_text("", encoding="utf-8")
    (root / "tests/a.py").write_text("", encoding="utf-8")
    (root / "spec").mkdir()
    (root / "spec/graph.yaml").write_text(
        "edges:\n"
        "  - [MOD-A, implemented_in, src/a.py]\n"
        "  - [FR-A, realized_by, MOD-A]\n"
        "  - [FR-A, verified_by, tests/a.py]\n"
        "  - [MOD-B, depends_on, MOD-A]\n",
        encoding="utf-8",
    )


def test_bundle_resolves_unique_file_owner_and_keeps_one_total_budget(tmp_path: Path) -> None:
    _fixture(tmp_path)
    result = bundle_relations(
        ["src/a.py"], ["implementation", "verification"], root=tmp_path, max_edges=2
    )
    assert result["route"] == "graph"
    assert result["resolved_anchor"] == "MOD-A"
    assert len(result["edges"]) <= 2
    assert any(facet["coverage"] == "truncated" for facet in result["facets"])


def test_bundle_uses_search_for_missing_graph_and_rendering_is_immutable(tmp_path: Path) -> None:
    assert (
        bundle_relations(["A", "B"], ["implementation", "verification"], root=tmp_path)["route"]
        == "search"
    )
    _fixture(tmp_path)
    result = bundle_relations(["src/a.py"], ["implementation", "verification"], root=tmp_path)
    original = deepcopy(result)
    rendered = render_json(result, 1024)
    assert len(rendered.encode()) <= 1024
    assert json.loads(rendered)["source"]["graph"] == "spec/graph.yaml"
    assert "resolution=implemented_in graph.yaml:2" in render_bundle_human(result, 1024)
    assert result == original


def _legacy_fixture(root: Path, extra: str = "") -> None:
    (root / "spec").mkdir()
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "src/a.py").write_text("")
    (root / "tests/a.py").write_text("")
    (root / "spec/graph.yaml").write_text(
        "edges:\n"
        "  - [MOD-A, implemented_in, src/a.py]\n"
        "  - [FR-A, realized_by, MOD-A]\n"
        "  - [FR-A, verified_by, tests/a.py]\n"
        "  - [MOD-B, depends_on, MOD-A]\n" + extra
    )


def test_should_share_evidence_without_empty_facets_and_load_once(
    tmp_path: Path, monkeypatch
) -> None:
    _legacy_fixture(tmp_path)
    from mir.core import relations

    load = relations._load_graph
    calls = []

    def counted(*args, **kwargs):
        calls.append(args[0])
        return load(*args, **kwargs)

    monkeypatch.setattr(relations, "_load_graph", counted)
    result = relations.bundle_relations(["src/a.py"], ["impact", "verification"], root=tmp_path)
    assert len(calls) == 1
    assert result["route"] == "graph"
    assert all(facet["edge_count"] > 0 for facet in result["facets"])
    keys = [(edge["source"], edge["relation"], edge["target"]) for edge in result["edges"]]
    assert len(keys) == len(set(keys))


@pytest.mark.parametrize(
    ("anchors", "purposes"),
    [(["A", "B"], ["implementation", "verification"]), (["A"], ["verification", "verification"])],
)
def test_should_skip_unrelated_and_single_need_without_loading_graph(
    tmp_path: Path, monkeypatch, anchors: list[str], purposes: list[str]
) -> None:
    from mir.core import relations

    def forbidden(*args, **kwargs):
        raise AssertionError("ordinary route must not load graph")

    monkeypatch.setattr(relations, "_load_graph", forbidden)
    assert relations.bundle_relations(anchors, purposes, root=tmp_path)["route"] == "search"


def test_should_not_call_unsafe_or_malformed_input_an_ordinary_skip(tmp_path: Path) -> None:
    from mir.core import relations

    with pytest.raises(relations.RelationError):
        relations.bundle_relations(["../escape", "other"], ["verification"], root=tmp_path)
    with pytest.raises(relations.RelationError):
        relations.bundle_relations(["A"], ["verification"], root=tmp_path, max_edges=65)
    with pytest.raises(relations.RelationError):
        relations.bundle_relations(["A"], [[]], root=tmp_path)
    _legacy_fixture(tmp_path)
    (tmp_path / "spec/graph.yaml").write_text("edges: [[A]]")
    with pytest.raises(relations.RelationError):
        relations.bundle_relations(["A"], ["implementation", "verification"], root=tmp_path)


def test_should_skip_missing_unknown_and_ambiguous_evidence(tmp_path: Path) -> None:
    purposes = ["implementation", "verification"]
    assert bundle_relations(["A"], purposes, root=tmp_path)["route"] == "search"
    _legacy_fixture(tmp_path)
    assert bundle_relations(["a_function_name"], purposes, root=tmp_path)["route"] == "search"
    with (tmp_path / "spec/graph.yaml").open("a") as handle:
        handle.write("  - [MOD-C, implemented_in, src/a.py]\n")
    result = bundle_relations(["src/a.py"], purposes, root=tmp_path)
    assert result["route"] == "search" and "ambiguous" in result["reason"]


def test_should_report_edge_and_byte_omissions_in_facet_coverage(tmp_path: Path) -> None:
    _legacy_fixture(
        tmp_path,
        "".join(
            f"  - [FR-A, verified_by, tests/a.py::test_{index}_{'x' * 90}]\n" for index in range(12)
        ),
    )
    limited = bundle_relations(
        ["src/a.py"], ["implementation", "verification"], root=tmp_path, max_edges=1
    )
    assert limited["route"] == "graph" and limited["truncated"]
    assert any(facet["coverage"] == "truncated" for facet in limited["facets"])
    full = bundle_relations(
        ["src/a.py"], ["implementation", "verification"], root=tmp_path, max_edges=32
    )
    original = deepcopy(full)
    rendered = render_json(full, 1600)
    bounded = json.loads(rendered)
    assert len(rendered.encode()) <= 1600
    assert bounded["truncated"] and len(bounded["edges"]) < len(full["edges"])
    assert all(facet["edge_count"] <= len(bounded["edges"]) for facet in bounded["facets"])
    assert any(facet["coverage"] == "truncated" for facet in bounded["facets"])
    human = render_bundle_human(full, 1024)
    assert len(human.encode()) <= 1024
    assert "facet=verification" in human and "coverage=truncated" in human
    assert "resolution=implemented_in graph.yaml:2" in human
    assert full == original


def test_should_render_successful_bundle_with_source_and_coverage(tmp_path: Path, capsys) -> None:
    _legacy_fixture(tmp_path)
    from mir.cli.relations import main

    assert (
        main(
            [
                "bundle",
                "src/a.py",
                "--purpose",
                "implementation",
                "--purpose",
                "verification",
                "--root",
                str(tmp_path),
            ]
        )
        == 0
    )
    text = capsys.readouterr().out
    assert "route=graph" in text and "resolved_anchor=MOD-A" in text
    assert "sha256=" in text and "verification" in text and "bounded" in text


def test_should_reject_graph_parent_symlink_into_protected_source(tmp_path: Path) -> None:
    from mir.core import relations

    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets/graph.yaml").write_text("edges: [[A, has_req, B]]")
    (tmp_path / "spec").symlink_to(tmp_path / "secrets", target_is_directory=True)
    with pytest.raises(relations.RelationError):
        relations.bundle_relations(["A"], ["implementation", "verification"], root=tmp_path)
