from __future__ import annotations

import json
from pathlib import Path

import pytest

from mir.core.relations import (
    RelationError,
    bundle_relations,
    query_relations,
    render_human,
    render_json,
)


def _graph(root: Path, text: str) -> None:
    (root / "spec").mkdir(exist_ok=True)
    (root / "spec/graph.yaml").write_text(text, encoding="utf-8")


def test_implementation_route_and_adr57_optional_memory_invariant(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src/module.py").write_text("", encoding="utf-8")
    _graph(
        tmp_path,
        "edges:\n  - [FEAT-X, has_req, FR-X]\n  - [FR-X, realized_by, MOD-X]\n"
        "  - [MOD-X, implemented_in, src/module.py]\n",
    )
    result = query_relations("FEAT-X", "implementation", root=tmp_path)
    assert [(e["source"], e["relation"], e["target"]) for e in result["edges"]] == [
        ("FEAT-X", "has_req", "FR-X"),
        ("FR-X", "realized_by", "MOD-X"),
        ("MOD-X", "implemented_in", "src/module.py"),
    ]
    assert not (tmp_path / ".mir/memory.db").exists()


def test_verification_reaches_test_from_file_reverse_then_forward(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src/m.py").write_text("")
    (tmp_path / "tests/t.py").write_text("")
    _graph(
        tmp_path,
        "edges:\n  - [FR-X, realized_by, MOD-X]\n  - [MOD-X, implemented_in, src/m.py]\n"
        "  - [FR-X, verified_by, tests/t.py::test_x]\n",
    )
    assert [
        edge["relation"]
        for edge in query_relations("src/m.py", "verification", root=tmp_path)["edges"]
    ] == ["implemented_in", "realized_by", "verified_by"]


def test_impact_follows_reverse_dependencies_and_cycles_are_bounded(tmp_path: Path) -> None:
    _graph(
        tmp_path,
        "edges:\n  - [MOD-A, depends_on, MOD-B]\n  - [MOD-B, depends_on, MOD-A]\n"
        "  - [FR-X, realized_by, MOD-A]\n",
    )
    result = query_relations("MOD-B", "impact", root=tmp_path, depth=4)
    assert [(e["source"], e["relation"]) for e in result["edges"]] == [
        ("MOD-A", "depends_on"),
        ("MOD-B", "depends_on"),
        ("FR-X", "realized_by"),
    ]


def test_current_graph_is_reloaded_and_source_digest_changes(tmp_path: Path) -> None:
    _graph(tmp_path, "edges:\n  - [A, has_req, B]\n")
    first = query_relations("A", "implementation", root=tmp_path)
    (tmp_path / "spec/graph.yaml").write_text("edges:\n  - [A, has_req, C]\n", encoding="utf-8")
    second = query_relations("A", "implementation", root=tmp_path)
    assert (
        first["source"]["sha256"] != second["source"]["sha256"]
        and second["edges"][0]["target"] == "C"
    )


@pytest.mark.parametrize("anchor", ["../bad", "/bad", "secrets/key.txt", ".env"])
def test_unsafe_or_unknown_anchors_fail(tmp_path: Path, anchor: str) -> None:
    _graph(tmp_path, "edges:\n  - [A, has_req, B]\n")
    with pytest.raises(RelationError):
        query_relations(anchor, "implementation", root=tmp_path)


def test_malformed_graph_and_output_unicode_are_bounded(tmp_path: Path) -> None:
    _graph(tmp_path, "edges:\n  - [A, has_req]\n")
    with pytest.raises(RelationError):
        query_relations("A", "implementation", root=tmp_path)
    _graph(tmp_path, "edges:\n  - [A, has_req, B]\n")
    result = query_relations("A", "implementation", root=tmp_path)
    result["notices"].append("\ud55c\uae00")
    output = render_json(result, 1024)
    assert len(output.encode()) <= 1024 and json.loads(output)["anchor"] == "A"


def test_file_anchor_resolves_declared_test_endpoints(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/x.py").write_text("")
    _graph(tmp_path, "edges:\n  - [FR-X, verified_by, tests/x.py::test_one]\n")
    result = query_relations("tests/x.py", "verification", root=tmp_path)
    assert result["resolved_anchors"] == [
        "tests/x.py::test_one"
    ] and "resolved_anchors=tests/x.py::test_one" in render_human(result, 1024)


def test_exact_file_test_locator_does_not_expand_or_invent_symbols(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/x.py").write_text("")
    _graph(
        tmp_path,
        "edges:\n  - [FR-X, verified_by, tests/x.py::one]\n"
        "  - [FR-Y, verified_by, tests/x.py::two]\n",
    )
    assert query_relations("./tests/x.py::one", "verification", root=tmp_path)[
        "resolved_anchors"
    ] == ["tests/x.py::one"]
    with pytest.raises(RelationError, match="unknown anchor"):
        query_relations("tests/x.py::three", "verification", root=tmp_path)


def test_file_anchor_expansion_is_bounded_and_visible(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/x.py").write_text("")
    _graph(
        tmp_path,
        "edges:\n" + "".join(f"  - [R{i}, verified_by, tests/x.py::t{i}]\n" for i in range(4)),
    )
    result = query_relations("tests/x.py", "verification", root=tmp_path, max_edges=2)
    assert result["resolved_anchors"] == ["tests/x.py::t0", "tests/x.py::t1"] and any(
        "anchor expansion omitted 2" in notice for notice in result["notices"]
    )


def test_recursive_yaml_is_a_relation_error(tmp_path: Path) -> None:
    _graph(tmp_path, "edges: " + "[" * 2000 + "x" + "]" * 2000)
    with pytest.raises(RelationError, match="malformed graph"):
        query_relations("A", "implementation", root=tmp_path)


def test_protected_and_missing_file_endpoints_are_skipped_without_reading(tmp_path: Path) -> None:
    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets/value.py").write_text("secret")
    _graph(
        tmp_path, "edges:\n  - [A, has_req, ./secrets/value.py]\n  - [A, has_req, src/missing.py]\n"
    )
    result = query_relations("A", "implementation", root=tmp_path)
    assert (
        result["edges"] == []
        and any("protected endpoint" in notice for notice in result["notices"])
        and any("unavailable endpoint" in notice for notice in result["notices"])
    )


def test_relation_file_targets_cover_extensionless_files_without_misclassifying_ids(
    tmp_path: Path,
) -> None:
    (tmp_path / "Makefile").write_text("")
    _graph(
        tmp_path, "edges:\n  - [MOD-X, implemented_in, Makefile]\n  - [policy.v1, has_req, FR-X]\n"
    )
    assert (
        query_relations("MOD-X", "implementation", root=tmp_path)["edges"][0]["target"]
        == "Makefile"
    )
    assert (
        query_relations("policy.v1", "implementation", root=tmp_path)["edges"][0]["target"]
        == "FR-X"
    )
    (tmp_path / "Makefile").unlink()
    missing = query_relations("MOD-X", "implementation", root=tmp_path)
    assert missing["edges"] == [] and any(
        "unavailable endpoint" in notice for notice in missing["notices"]
    )


def test_symlink_escape_and_depth_terminal_do_not_overclaim(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.py"
    outside.write_text("")
    (tmp_path / "link.py").symlink_to(outside)
    _graph(tmp_path, "edges:\n  - [A, has_req, ./link.py]\n  - [B, has_req, C]\n")
    assert any(
        "symlink escapes" in notice
        for notice in query_relations("A", "implementation", root=tmp_path)["notices"]
    )
    assert not query_relations("B", "implementation", root=tmp_path, depth=1)["truncated"]


def test_output_limits_are_finite_for_long_unicode_records(tmp_path: Path) -> None:
    _graph(tmp_path, "edges:\n  - [A, has_req, B]\n")
    result = query_relations("A", "implementation", root=tmp_path)
    result["edges"][0]["target"] = "\ud55c" * 3000
    result["notices"] = ["\uc548\uc804" * 3000]
    with pytest.raises(RelationError):
        render_human(result, 1024)
    with pytest.raises(RelationError):
        render_json(result, 1024)


def test_duplicate_edges_and_non_string_yaml_values_fail(tmp_path: Path) -> None:
    _graph(tmp_path, "edges:\n  - [A, has_req, B]\nedges:\n  - [A, has_req, C]\n")
    with pytest.raises(RelationError):
        query_relations("A", "implementation", root=tmp_path)
    _graph(tmp_path, "edges:\n  - [A, has_req, 3]\n")
    with pytest.raises(RelationError):
        query_relations("A", "implementation", root=tmp_path)


def test_graph_read_error_and_direct_api_limits_are_safe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _graph(tmp_path, "edges:\n  - [A, has_req, B]\n")
    graph = tmp_path / "spec/graph.yaml"
    original_open = Path.open

    def denied(self: Path, *args, **kwargs):
        if self == graph:
            raise PermissionError("denied")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", denied)
    with pytest.raises(RelationError, match="cannot be read"):
        query_relations("A", "implementation", root=tmp_path)
    with pytest.raises(RelationError):
        query_relations("A" * 5000, "implementation", root=tmp_path)
    with pytest.raises(RelationError):
        query_relations("A", "implementation", root=tmp_path, depth=True)


def test_bundle_combines_facets_and_resolves_unique_file_owner(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src/m.py").write_text("")
    (tmp_path / "tests/m.py").write_text("")
    _graph(
        tmp_path,
        "edges:\n  - [MOD-X, implemented_in, src/m.py]\n  - [FR-X, realized_by, MOD-X]\n"
        "  - [FR-X, verified_by, tests/m.py]\n",
    )
    result = bundle_relations(["src/m.py"], ["implementation", "verification"], root=tmp_path)
    assert (
        result["route"] == "graph"
        and result["resolved_anchor"] == "MOD-X"
        and result["resolution"]["source_line"] == 2
    )


def test_bundle_skips_multi_anchor_without_graph_and_ambiguous_owner(tmp_path: Path) -> None:
    assert (
        bundle_relations(["A", "B"], ["implementation", "verification"], root=tmp_path)["route"]
        == "search"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src/m.py").write_text("")
    _graph(
        tmp_path, "edges:\n  - [M1, implemented_in, src/m.py]\n  - [M2, implemented_in, src/m.py]\n"
    )
    result = bundle_relations(["src/m.py"], ["implementation", "verification"], root=tmp_path)
    assert result["route"] == "search" and "ambiguous" in result["reason"]
