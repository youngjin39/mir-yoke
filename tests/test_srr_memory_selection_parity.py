"""The memory selector must preserve existing small-graph traversal semantics."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mir.core.engine.memory import distill, store
from mir.core.memory_relations import bundle_memory_relations, query_memory_relations
from mir.core.relations import RelationError, bundle_relations, query_relations

EDGES = [
    ['REQ-A', 'realized_by', 'MOD-A'],
    ['MOD-A', 'implemented_in', 'src/a.py::run'],
    ['REQ-A', 'verified_by', 'tests/test_a.py'],
    ['MOD-A', 'depends_on', 'MOD-B'],
    ['MOD-B', 'depends_on', 'MOD-C'],
    ['MOD-C', 'depends_on', 'MOD-A'],
    ['CLIENT', 'depends_on', 'MOD-A'],
    ['REQ-B', 'realized_by', 'MOD-B'],
    ['MOD-B', 'implemented_in', 'src/b.py'],
    ['REQ-B', 'verified_by', 'tests/test_b.py'],
    ['MOD-WILD', 'implemented_in', 'src/a_%.py::run'],
    ['MOD-OTHER', 'implemented_in', 'src/aXX.py::run'],
]


@pytest.fixture
def graph_root(tmp_path: Path) -> Path:
    for name in ['src/a.py', 'src/b.py', 'src/a_%.py', 'src/aXX.py',
                 'tests/test_a.py', 'tests/test_b.py']:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('# source fixture\n')
    (tmp_path / 'spec').mkdir()
    (tmp_path / 'spec/graph.yaml').write_text(yaml.safe_dump({'edges': EDGES}))
    source = tmp_path / 'docs/decisions/adr-selection.md'
    source.parent.mkdir(parents=True)
    source.write_text('---\n' + yaml.safe_dump({
        'status': 'accepted', 'memory_relations': EDGES,
    }) + '---\n')
    (tmp_path / '.mir').mkdir()
    connection = store.connect(tmp_path / '.mir/memory.db', load_vec=False).conn
    try:
        store.apply_migrations(connection)
        distill.ingest_markdown_file(source, conn=connection, project_root=tmp_path)
    finally:
        connection.close()
    return tmp_path


def triples(result: dict) -> list[tuple[str, str, str]]:
    return [(e['source'], e['relation'], e['target']) for e in result['edges']]


@pytest.mark.parametrize('anchor', ['REQ-A', 'MOD-A', 'src/a.py', './src/a.py::run', 'src/a_%.py'])
@pytest.mark.parametrize('purpose', ['implementation', 'verification', 'impact', 'dependencies'])
@pytest.mark.parametrize('depth', [1, 3])
def test_should_preserve_selected_edges_when_memory_replaces_yaml_loading(
    graph_root: Path, anchor: str, purpose: str, depth: int,
) -> None:
    expected = query_relations(anchor, purpose, root=graph_root, depth=depth)
    actual = query_memory_relations(anchor, purpose, root=graph_root, depth=depth)
    assert triples(actual) == triples(expected)
    assert actual['resolved_anchors'] == expected['resolved_anchors']
    # The SQL selector may conservatively report an unvalidated boundary; it
    # must never drop a truncation that the validated complete graph reports.
    if expected['truncated']:
        assert actual['truncated']


@pytest.mark.parametrize('anchor', ['REQ-A', 'MOD-A', 'src/a.py', './src/a.py', 'src/a_%.py'])
@pytest.mark.parametrize('purposes', [
    ['implementation', 'verification'], ['dependencies', 'impact'],
])
def test_should_preserve_bundle_facets_when_memory_selects_one_anchor(
    graph_root: Path, anchor: str, purposes: list[str],
) -> None:
    expected = bundle_relations([anchor], purposes, root=graph_root)
    actual = bundle_memory_relations([anchor], purposes, root=graph_root)
    assert (actual['route'] == 'search') == (expected['route'] == 'search')
    assert triples(actual) == triples(expected)
    if expected['route'] == 'search':
        assert actual['reason'] == expected['reason']
    else:
        assert actual['resolved_anchor'] == expected['resolved_anchor']
        assert actual['facets'] == expected['facets']


def test_should_reject_unknown_anchor_without_inventing_a_relation(graph_root: Path) -> None:
    with pytest.raises(RelationError, match='unknown anchor'):
        query_memory_relations('NOT-PRESENT', 'dependencies', root=graph_root)
