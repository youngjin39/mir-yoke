from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from mir.core.relations import (
    RelationError,
    bundle_relations,
    query_relations,
    render_human,
    render_json,
)


def _graph(root: Path, relative: str, text: str) -> Path:
    graph = root / relative
    graph.parent.mkdir(parents=True, exist_ok=True)
    graph.write_text(text, encoding="utf-8")
    return graph


def test_custom_graph_provenance_and_declared_upstream_dependencies(tmp_path: Path) -> None:
    graph = _graph(
        tmp_path,
        "relations/declared graph.yaml",
        "edges:\n  - [APP, depends_on, LIB]\n  - [LIB, depends_on, BASE]\n",
    )
    result = query_relations(
        "APP", "dependencies", root=tmp_path, graph="relations/declared graph.yaml", depth=2
    )
    assert [(edge["source"], edge["target"]) for edge in result["edges"]] == [
        ("APP", "LIB"),
        ("LIB", "BASE"),
    ]
    assert result["source"]["graph"] == "relations/declared graph.yaml"
    assert result["source"]["sha256"]
    assert "source=relations/declared graph.yaml" in render_human(result, 1024)
    assert graph.exists()


def test_custom_graph_is_bounded_and_rendering_does_not_mutate_result(tmp_path: Path) -> None:
    _graph(tmp_path, "graphs/graph.yaml", "edges:\n  - [A, has_req, B]\n")
    result = query_relations("A", "implementation", root=tmp_path, graph="graphs/graph.yaml")
    original = deepcopy(result)
    assert len(render_json(result, 1024).encode()) <= 1024
    assert len(render_human(result, 1024).encode()) <= 1024
    assert result == original


@pytest.mark.parametrize(
    "graph", ["/tmp/graph.yaml", "../graph.yaml", "C:\\graph.yaml", ".mir/memory.db"]
)
def test_custom_graph_rejects_absolute_traversal_windows_and_protected_paths(
    tmp_path: Path, graph: str
) -> None:
    with pytest.raises(RelationError):
        query_relations("A", "implementation", root=tmp_path, graph=graph)


def test_custom_graph_rejects_symlink_escape_and_protected_resolved_target(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-graph.yaml"
    outside.write_text("edges: [[A, has_req, B]]\n", encoding="utf-8")
    (tmp_path / "links").mkdir()
    (tmp_path / "links/escape.yaml").symlink_to(outside)
    with pytest.raises(RelationError, match="escapes root"):
        query_relations("A", "implementation", root=tmp_path, graph="links/escape.yaml")
    _graph(tmp_path, "secrets/graph.yaml", "edges: [[A, has_req, B]]\n")
    (tmp_path / "links/protected.yaml").symlink_to(tmp_path / "secrets/graph.yaml")
    with pytest.raises(RelationError, match="protected"):
        query_relations("A", "implementation", root=tmp_path, graph="links/protected.yaml")


def test_missing_custom_source_is_query_error_and_bundle_search_fallback(tmp_path: Path) -> None:
    with pytest.raises(RelationError, match="unavailable"):
        query_relations("A", "implementation", root=tmp_path, graph="relations/missing.yaml")
    result = bundle_relations(
        ["A"], ["implementation", "verification"], root=tmp_path, graph="relations/missing.yaml"
    )
    assert result["route"] == "search"


def test_malformed_custom_source_is_an_error_not_a_search_fallback(tmp_path: Path) -> None:
    _graph(tmp_path, "relations/invalid.yaml", "edges: [[A, has_req]]\n")
    with pytest.raises(RelationError, match="three-item"):
        query_relations("A", "implementation", root=tmp_path, graph="relations/invalid.yaml")
    with pytest.raises(RelationError, match="three-item"):
        bundle_relations(
            ["A"], ["implementation", "verification"], root=tmp_path, graph="relations/invalid.yaml"
        )


def test_optional_profile_protects_target_specific_graph_location(tmp_path: Path) -> None:
    _graph(tmp_path, "private/graph.yaml", "edges: [[A, has_req, B]]\n")
    profile = tmp_path / ".mir/repo-profile.toml"
    profile.parent.mkdir()
    profile.write_text("[paths]\nprotected_paths = ['private/**']\n", encoding="utf-8")
    with pytest.raises(RelationError, match="protected"):
        query_relations("A", "implementation", root=tmp_path, graph="private/graph.yaml")


def test_optional_profile_protects_declared_file_endpoints_and_malformed_profile_fails_closed(
    tmp_path: Path,
) -> None:
    _graph(tmp_path, "spec/graph.yaml", "edges: [[MOD, implemented_in, private/module.py]]\n")
    private = tmp_path / "private"
    private.mkdir()
    (private / "module.py").write_text("", encoding="utf-8")
    profile = tmp_path / ".mir/repo-profile.toml"
    profile.parent.mkdir()
    profile.write_text("[paths]\nprotected_paths = ['PRIVATE/**']\n", encoding="utf-8")
    result = query_relations("MOD", "implementation", root=tmp_path)
    assert result["edges"] == []
    assert "protected endpoint" in result["notices"][0]
    profile.write_text("[paths\n", encoding="utf-8")
    with pytest.raises(RelationError, match="profile"):
        query_relations("MOD", "implementation", root=tmp_path)


def test_profile_symlink_to_protected_target_is_rejected_without_reading_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _graph(tmp_path, "spec/graph.yaml", "edges: [[A, has_req, B]]\n")
    protected = tmp_path / "secrets/profile.toml"
    protected.parent.mkdir()
    protected.write_text("[paths]\nprotected_paths = []\n", encoding="utf-8")
    profile = tmp_path / ".mir/repo-profile.toml"
    profile.parent.mkdir()
    profile.symlink_to(protected)
    original_open = Path.open
    reads: list[Path] = []

    def denied(self: Path, *args, **kwargs):
        if self == protected:
            reads.append(self)
            raise AssertionError("protected profile target must not be opened")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", denied)
    with pytest.raises(RelationError, match="profile"):
        query_relations("A", "implementation", root=tmp_path)
    assert reads == []


def test_dotted_logical_targets_remain_declared_nodes(tmp_path: Path) -> None:
    _graph(
        tmp_path,
        "spec/graph.yaml",
        "edges:\n  - [A, has_req, policy.v1]\n  - [A, depends_on, module.v2]\n",
    )
    implementation = query_relations("A", "implementation", root=tmp_path)
    dependencies = query_relations("A", "dependencies", root=tmp_path)
    assert implementation["edges"][0]["target"] == "policy.v1"
    assert dependencies["edges"][0]["target"] == "module.v2"


def test_profile_is_bounded_before_traversal(tmp_path: Path) -> None:
    _graph(tmp_path, "spec/graph.yaml", "edges: [[A, has_req, B]]\n")
    profile = tmp_path / ".mir/repo-profile.toml"
    profile.parent.mkdir()
    profile.write_text("#" * (64 * 1024 + 1), encoding="utf-8")
    with pytest.raises(RelationError, match="profile"):
        query_relations("A", "implementation", root=tmp_path)


def test_graph_rejects_control_values_and_non_string_top_level_keys(tmp_path: Path) -> None:
    _graph(tmp_path, "spec/graph.yaml", 'edges: [[A, has_req, "B\\nnotice: forged"]]\n')
    with pytest.raises(RelationError, match="control"):
        query_relations("A", "implementation", root=tmp_path)
    _graph(tmp_path, "spec/graph.yaml", "3: hidden\nedges: [[A, has_req, B]]\n")
    with pytest.raises(RelationError, match="keys must be strings"):
        query_relations("A", "implementation", root=tmp_path)
