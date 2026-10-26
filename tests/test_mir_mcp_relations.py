"""Differential contract for the standalone, stdlib-only YAML adapter."""

import importlib.util
from pathlib import Path

import pytest

from mir.core.relations import query_relations as existing_query

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "plugins/mir-core/skills/selective-relations/scripts/relations_query.py"
)


def adapter():
    spec = importlib.util.spec_from_file_location("standalone_relations", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    # Compile from source so a test never writes __pycache__ into a plugin tree.
    exec(compile(SCRIPT.read_bytes(), str(SCRIPT), "exec"), module.__dict__)
    return module


def fixture(root):
    for path in ("src/m.py", "tests/check.py"):
        target = root / path
        target.parent.mkdir(exist_ok=True)
        target.write_text("")
    (root / "spec").mkdir()
    (root / "spec/graph.yaml").write_text(
        "# declared graph\nedges:\n"
        "  - [FEAT, has_req, REQ]\n"
        "  - [REQ, realized_by, MOD]\n"
        "  - [MOD, implemented_in, src/m.py::run]\n"
        "  - [REQ, verified_by, tests/check.py::test_run]\n"
        "  - [MOD, depends_on, DEP]\n"
        "  - [DEP, depends_on, OTHER]\n"
        "  - [MOD, implemented_in, ../outside.py]\n"
        "  - [MOD, implemented_in, missing/file.py]\n"
        "  - [MOD, implemented_in, .env]\n"
        "  - ['src/m.py::run', exposes, 'API'] # comment\n"
    )


@pytest.mark.parametrize("purpose", ["implementation", "verification", "impact", "dependencies"])
@pytest.mark.parametrize("anchor", ["FEAT", "MOD", "src/m.py", "src/m.py::run"])
@pytest.mark.parametrize("limits", [{}, {"depth": 1}, {"depth": 4, "max_edges": 1}])
def test_admitted_graph_matches_existing(tmp_path, purpose, anchor, limits):
    fixture(tmp_path)
    assert adapter().query_relations(anchor, purpose, root=tmp_path, **limits) == existing_query(
        anchor, purpose, root=tmp_path, **limits
    )


@pytest.mark.parametrize(
    "text",
    [
        "edges:\n  - [A, has_req, 1]\n",
        "edges:\n  - [A, has_req, true]\n",
        "edges:\n  - [A, has_req, null]\n",
        "edges:\n  - [A, has_req, *alias]\n",
        "edges: &anchor []\n",
        "edges:\n  - [!tag A, has_req, B]\n",
        "edges: []\nedges: []\n",
        "edges: []\n---\nedges: []\n",
        "edges:\n  - {source: A}\n",
        "edges:\n  - [A, has_req, B, C]\n",
        "edges:\n  - [A, has_req, [B]]\n",
        "edges:\n  - [A, has_req, 2026-10-26]\n",
    ],
)
def test_unsupported_yaml_is_format_error(tmp_path, text):
    (tmp_path / "spec").mkdir()
    (tmp_path / "spec/graph.yaml").write_text(text)
    module = adapter()
    with pytest.raises(module.RelationsError) as error:
        module.query_relations("A", "implementation", root=tmp_path)
    assert error.value.code == "E_FORMAT"


def test_injected_endpoint_refusal_propagates(tmp_path):
    fixture(tmp_path)

    class Refusal(Exception):
        pass

    class Guard:
        root = tmp_path

        def read(self, relative):
            return (self.root / relative).read_bytes()

        def path(self, relative, allow_missing=False):
            if relative == "src/m.py":
                raise Refusal("E_PROTECTED")
            return self.root / relative

        def exists(self, relative):
            self.path(relative, allow_missing=True)
            return (self.root / relative).exists()

    with pytest.raises(Refusal):
        adapter().query_relations("MOD", "implementation", root=tmp_path, io=Guard())


@pytest.mark.parametrize(
    "row",
    [
        '["A", "has_req", "quoted, target"]',
        "['A', 'has_req', 'it''s a target']",
        '[A, has_req, "true"]',
        '[A, has_req, "2026-10-26"]',
        "[A, has_req, target:locator]",
    ],
)
def test_quoted_subset_matches_existing(tmp_path, row):
    (tmp_path / "spec").mkdir()
    (tmp_path / "spec/graph.yaml").write_text("edges:\n  - " + row + "\n")
    assert adapter().query_relations("A", "implementation", root=tmp_path) == existing_query(
        "A", "implementation", root=tmp_path
    )


@pytest.mark.parametrize(
    "options",
    [{"depth": True}, {"depth": 0}, {"depth": 5}, {"max_edges": False}, {"max_edges": 65}],
)
def test_limits_are_closed(tmp_path, options):
    module = adapter()
    with pytest.raises(module.RelationsError) as error:
        module.query_relations("A", "implementation", root=tmp_path, **options)
    assert error.value.code == "E_SCHEMA"


def test_graph_and_row_size_bounds(tmp_path):
    module = adapter()
    with pytest.raises(module.RelationsError) as error:
        module._parse_graph(b"edges:\n" + b"  - [A, has_req, B]\n" * 10001)
    assert error.value.code == "E_LIMIT"
    with pytest.raises(module.RelationsError) as error:
        module._parse_graph(b"edges:\n  - [A, has_req, " + b"x" * 4097 + b"]\n")
    assert error.value.code == "E_LIMIT"


def test_dependency_default_is_one_and_cycles_deduplicate(tmp_path):
    (tmp_path / "spec").mkdir()
    (tmp_path / "spec/graph.yaml").write_text(
        "edges:\n  - [A, depends_on, B]\n  - [B, depends_on, C]\n"
        "  - [C, depends_on, A]\n  - [A, depends_on, B]\n"
    )
    for options in ({}, {"depth": 4}):
        assert adapter().query_relations("A", "dependencies", root=tmp_path, **options) == (
            existing_query("A", "dependencies", root=tmp_path, **options)
        )


def test_multiple_anchor_expansions_match_existing(tmp_path):
    fixture(tmp_path)
    with (tmp_path / "spec/graph.yaml").open("a") as handle:
        handle.write("  - [src/m.py::other, exposes, SECOND]\n")
    for options in ({}, {"max_edges": 1}):
        assert adapter().query_relations(
            "src/m.py", "implementation", root=tmp_path, **options
        ) == existing_query("src/m.py", "implementation", root=tmp_path, **options)


@pytest.mark.parametrize("value", ["foo:", "?foo", ":foo", '"\\ud800"', '"\\udfff"'])
def test_implicit_mapping_and_surrogate_values_are_rejected(tmp_path, value):
    (tmp_path / "spec").mkdir()
    (tmp_path / "spec/graph.yaml").write_text(f"edges:\n  - [A, has_req, {value}]\n")
    module = adapter()
    with pytest.raises(module.RelationsError) as error:
        module.query_relations("A", "implementation", root=tmp_path)
    assert error.value.code == "E_FORMAT"


@pytest.mark.parametrize("value", ['"foo:"', "'?foo'", '":foo"', "'it''s quoted'", '"a,b"'])
@pytest.mark.parametrize("comment", ["", " # trailing comment", "   # [ignored, tokens]"])
def test_quoted_variations_and_trailing_comments_match_existing(tmp_path, value, comment):
    (tmp_path / "spec").mkdir()
    (tmp_path / "spec/graph.yaml").write_text(
        f"edges: # header comment\n  - [A, has_req, {value}]{comment}\n"
    )
    assert adapter().query_relations("A", "implementation", root=tmp_path) == existing_query(
        "A", "implementation", root=tmp_path
    )
