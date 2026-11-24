"""Raw stdio oracles for native YAML relations using the retained Python server."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from test_mir_mcp_native_core import SCRIPT, request, wire
from test_mir_mcp_native_core import native as native

FIXTURES = Path(__file__).with_name('fixtures') / 'mcp_native_relations'
REFERENCE = [sys.executable, '-I', '-B', str(SCRIPT)]
GRAPH_LIMIT = 1024 * 1024


def setup_target(target):
    files = {
        'spec/graph.yaml': (FIXTURES / 'graph.yaml').read_bytes(),
        'spec/empty.yaml': b'edges: []\n',
        'spec/malformed.yaml': b'edges:\n  - [A, has_req, 2026-11-24]\n',
        'spec/implicit-scalar.yaml': 'edges:\n  - [A, has_req, .ınf]\n'.encode(),
        'spec/invalid-utf8.yaml': b'edges:\n  - [A, has_req, "\xff"]\n',
        'spec/duplicate.yaml': b'edges: []\nedges: []\n',
        'spec/max-rows.yaml': b'edges:\n' + b'  - [A, has_req, B]\n' * 10_000,
        'spec/too-many-rows.yaml': b'edges:\n' + b'  - [A, has_req, B]\n' * 10_001,
        'spec/max-field.yaml': b'edges:\n  - [A, has_req, "' + b'X' * 4096 + b'"]\n',
        'spec/oversize-field.yaml': b'edges:\n  - [A, has_req, "' + b'X' * 4097 + b'"]\n',
        'src/m.py': b'',
        'tests/check.py': b'',
        '.mir/repo-profile.toml': b'protected_paths = ["spec/private.yaml"]\n',
    }
    minimal = b'edges:\n  - [A, has_req, B]\n#'
    for name, size in [('max-graph', GRAPH_LIMIT), ('oversize-graph', GRAPH_LIMIT + 1)]:
        files[f'spec/{name}.yaml'] = minimal + b'x' * (size - len(minimal))
    for relative, contents in files.items():
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
    return target


@pytest.fixture
def target(tmp_path):
    return setup_target(tmp_path / 'work tree')


@pytest.fixture
def independent(native, tmp_path):
    unavailable = tmp_path / 'unavailable-python'
    assert not unavailable.exists()
    return [native[0], '--reference-python', str(unavailable), '--reference-script', str(SCRIPT)]


def query(target, case, **options):
    arguments = {'target_root': str(target), 'anchor': 'FEAT', 'purpose': 'implementation'}
    return wire(request('tools/call', {
        'name': 'relations_query', 'arguments': {**arguments, **options},
    }, id=case))


def capture(command, stdin):
    result = subprocess.run(command, input=stdin, capture_output=True, timeout=30)
    return result.stdout, result.stderr, result.returncode


def structured(stdout):
    return json.loads(stdout)['result']['structuredContent']


def golden_cases():
    # Each row names the reference outcome as well as its concrete request.
    return {
        'implementation': ({}, None),
        'verification': ({'anchor': 'src/m.py::run', 'purpose': 'verification'}, None),
        'impact': ({'anchor': 'MOD', 'purpose': 'impact'}, None),
        'dependencies': ({'anchor': 'MOD', 'purpose': 'dependencies'}, None),
        'dependency-cycle': ({'anchor': 'MOD', 'purpose': 'dependencies', 'depth': 4}, None),
        'locators': ({'anchor': 'src/m.py', 'graph': 'spec/./graph.yaml'}, None),
        'normalized-locator': ({'anchor': 'src/./m.py::run'}, None),
        'truncated-locators': ({'anchor': 'src/m.py', 'max_edges': 1}, None),
        'truncated-edges': ({'max_edges': 1}, None),
        'empty-result': ({'anchor': 'ISOLATED'}, None),
        'empty-graph': ({'graph': 'spec/empty.yaml'}, 'E_SCHEMA'),
        'missing-graph': ({'graph': 'spec/missing.yaml'}, 'E_IO'),
        'malformed-graph': ({'graph': 'spec/malformed.yaml'}, 'E_FORMAT'),
        'implicit-scalar-case': ({'graph': 'spec/implicit-scalar.yaml'}, 'E_FORMAT'),
        'invalid-utf8': ({'graph': 'spec/invalid-utf8.yaml'}, 'E_FORMAT'),
        'duplicate-header': ({'graph': 'spec/duplicate.yaml'}, 'E_FORMAT'),
        'protected-graph': ({'graph': 'spec/private.yaml'}, 'E_PROTECTED'),
        'unsafe-graph': ({'graph': '../graph.yaml'}, 'E_PATH'),
        'unknown-anchor': ({'anchor': 'ABSENT'}, 'E_SCHEMA'),
        'anchor-case': ({'anchor': 'feat'}, 'E_SCHEMA'),
        'locator-case': ({'anchor': 'src/m.py::RUN'}, 'E_SCHEMA'),
        'missing-file-anchor': ({'anchor': 'missing/file.py::symbol'}, 'E_PATH'),
        'max-graph': ({'anchor': 'A', 'graph': 'spec/max-graph.yaml'}, None),
        'oversize-graph': ({'anchor': 'A', 'graph': 'spec/oversize-graph.yaml'}, 'E_LIMIT'),
        'max-rows': ({'anchor': 'A', 'graph': 'spec/max-rows.yaml'}, None),
        'too-many-rows': ({'anchor': 'A', 'graph': 'spec/too-many-rows.yaml'}, 'E_LIMIT'),
        'max-field': ({'anchor': 'A', 'graph': 'spec/max-field.yaml'}, None),
        'oversize-field': ({'anchor': 'A', 'graph': 'spec/oversize-field.yaml'}, 'E_LIMIT'),
        'control-anchor': ({'anchor': 'FEAT\u2028'}, 'E_SCHEMA'),
        'invalid-adapter': ({'adapter': 'json'}, 'E_SCHEMA'),
        'invalid-purpose': ({'purpose': 'Implementation'}, 'E_SCHEMA'),
        'invalid-depth': ({'depth': 5}, 'E_SCHEMA'),
        'boolean-depth': ({'depth': True}, 'E_SCHEMA'),
        'invalid-max-edges': ({'max_edges': 0}, 'E_SCHEMA'),
        'invalid-page-size': ({'page_size': 65}, 'E_SCHEMA'),
        'unknown-argument': ({'extra': True}, 'E_SCHEMA'),
        'invalid-cursor': ({'cursor': 'invalid'}, 'E_CURSOR'),
    }


def golden_input(target):
    cases = golden_cases()
    assert len({json.dumps(options, sort_keys=True) for options, _ in cases.values()}) == len(cases)
    return b''.join(query(target, case, **options) for case, (options, _) in cases.items())


def test_native_relations_without_reference(independent, target):
    stdin = query(target, 'native-route')
    expected = capture(REFERENCE, stdin)
    assert structured(expected[0])['ok'] is True
    assert capture(independent, stdin) == expected


def test_relations_golden_transcript(native, independent, target):
    stdin = golden_input(target)
    golden = ((FIXTURES / 'oracle.stdout.jsonl').read_bytes(), b'', 0)
    expected = capture(REFERENCE, stdin)
    assert expected == golden
    replies = {json.loads(line)['id']: structured(line) for line in expected[0].splitlines()}
    assert list(replies) == list(golden_cases())
    for case, (_, error) in golden_cases().items():
        assert replies[case]['error'] == (None if error is None else {'code': error}), case
    implementation = replies['implementation']['data']
    assert [edge['source_line'] for edge in implementation['edges']] == [3, 4, 5, 6]
    assert implementation['notices'] == [
        'skipped unavailable endpoint: 1 edge(s)', 'skipped unsafe path endpoint: 1 edge(s)',
        'truncated: depth reached; frontier remains unexplored',
    ]
    assert replies['locators']['data']['resolved_anchors'] == ['src/m.py::run', 'src/./m.py::other']
    assert replies['empty-result']['data']['edges'] == []
    assert capture(native, stdin) == expected
    assert capture(independent, stdin) == expected


def test_file_anchor_case_is_independent_of_filesystem(independent, target):
    # Both spellings exist on every filesystem before querying the declared locator.
    exact, alternate = target / 'src/m.py', target / 'src/M.py'
    case_sensitive = not alternate.exists()
    if case_sensitive:
        alternate.write_bytes(exact.read_bytes())
    assert exact.is_file() and alternate.is_file()
    assert exact.samefile(alternate) is not case_sensitive
    stdin = query(target, 'exact', anchor='src/m.py')
    stdin += query(target, 'alternate', anchor='src/M.py')
    expected = capture(REFERENCE, stdin)
    exact_reply, alternate_reply = map(structured, expected[0].splitlines())
    assert exact_reply['ok'] is True
    assert alternate_reply['error'] == {'code': 'E_SCHEMA'}
    assert capture(independent, stdin) == expected


@pytest.mark.parametrize('max_edges,error', [(64, None), (65, 'E_SCHEMA')],
                         ids=['max', 'above-max'])
def test_relations_max_edges_boundary(independent, target, max_edges, error):
    stdin = query(target, 'max-edges-boundary', max_edges=max_edges)
    expected = capture(REFERENCE, stdin)
    assert structured(expected[0])['error'] == (None if error is None else {'code': error})
    assert capture(independent, stdin) == expected


def test_relations_cursor_continuation_and_binding(native, independent, target, tmp_path):
    def page(case, **options):
        stdin = query(target, case, page_size=1, **options)
        expected = capture(REFERENCE, stdin)
        # This token binds real fixture paths and endpoint metadata. Capture both
        # sides against the same tree in this run and keep raw evidence in scratch.
        (tmp_path / f'{case}.stdin.jsonl').write_bytes(stdin)
        (tmp_path / f'{case}.stdout.jsonl').write_bytes(expected[0])
        assert expected[1:] == (b'', 0)
        assert capture(native, stdin) == expected
        assert capture(independent, stdin) == expected
        return structured(expected[0])

    first = page('first', anchor='src/m.py')
    cursor = first['next_cursor']
    assert cursor
    assert first['data']['resolved_anchors'] == ['src/m.py::run']
    assert [edge['target'] for edge in first['data']['edges']] == ['API, π']
    second = page('second', anchor='src/m.py', cursor=cursor)
    assert second['data']['resolved_anchors'] == ['src/./m.py::other']
    assert [edge['target'] for edge in second['data']['edges']] == ["it's a target"]
    assert second['next_cursor'] is None
    assert page('different-args', cursor=cursor)['error'] == {'code': 'E_CURSOR'}

    graph = target / 'spec/graph.yaml'
    graph.write_bytes(graph.read_bytes() + b'# changed after first page\n')
    assert page('stale-graph', anchor='src/m.py', cursor=cursor)['error'] == {'code': 'E_CURSOR'}

    fresh = page('fresh', anchor='src/m.py')['next_cursor']
    assert fresh and fresh != cursor
    replacement = target / 'replacement.py'
    replacement.write_bytes(b'')
    replacement.replace(target / 'src/m.py')
    stale = page('stale-endpoint', anchor='src/m.py', cursor=fresh)
    assert stale['error'] == {'code': 'E_CURSOR'}


@pytest.mark.parametrize('graph', ['1:graph.yaml', 'é:graph.yaml', '::graph.yaml',
                                  'safe-graph.yaml'])
def test_windows_drive_graph_byte_oracle(independent, target, graph):
    # Invalid Windows names cannot be created there; guard refusal precedes I/O.
    if sys.platform != 'win32' or graph == 'safe-graph.yaml':
        (target / graph).write_bytes(b'edges:\n  - [A, has_req, B]\n')
    stdin = query(target, graph, anchor='A', graph=graph)
    expected = capture(REFERENCE, stdin)
    assert structured(expected[0])['error'] == (
        None if graph == 'safe-graph.yaml' else {'code': 'E_PATH'})
    assert capture(independent, stdin) == expected


@pytest.mark.parametrize('endpoint', ['1:foo', 'safe.py'])
def test_windows_drive_endpoint_byte_oracle(independent, target, endpoint):
    if sys.platform != 'win32' or endpoint == 'safe.py':
        (target / endpoint).write_bytes(b'')
    (target / 'spec/graph.yaml').write_bytes(
        f'edges:\n  - [A, implemented_in, {endpoint}]\n'.encode())
    stdin = query(target, endpoint, anchor='A')
    expected = capture(REFERENCE, stdin)
    data = structured(expected[0])['data']
    assert data['notices'] == (
        [] if endpoint == 'safe.py' else ['skipped unsafe path endpoint: 1 edge(s)'])
    assert len(data['edges']) == (1 if endpoint == 'safe.py' else 0)
    assert capture(independent, stdin) == expected
