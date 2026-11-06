"""B33 unmodified-core oracle; each synthetic record replays against both copies."""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import sys
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
COPIES = {'core': 'plugins/mir-core/skills/selective-relations/scripts/relations_query.py',
          'mcp': 'plugins/mir-mcp/shared/relations_query.py'}
FIXTURE = ROOT / 'native/handoff-packet/tests/fixtures/w2/b33-relations-query.json'


def load(copy):
    spec = importlib.util.spec_from_file_location('relations_query', ROOT / COPIES[copy])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


M = load('core')

def compact(value):
    if isinstance(value, str) and len(value) > 240:
        return {'length': len(value), 'sha256': hashlib.sha256(value.encode()).hexdigest(),
                'first': value[:120], 'last': value[-120:]}
    if isinstance(value, list):
        return [compact(item) for item in value]
    if isinstance(value, dict):
        return {key: compact(item) for key, item in value.items()}
    return value


def observe(case, tmp):
    try:
        return {'value': compact(case(tmp))}
    except Exception as exc:  # noqa: BLE001 - freeze public class and message
        return {'error': [type(exc).__name__, str(exc).replace(str(tmp), '<tmp>')]}


def matrix(tmp, values, call):
    return [observe(lambda tmp, value=value: call(value), tmp) for value in values]

def graph(rows):
    return ('edges:\n' + ''.join('  - ' + json.dumps(row) + '\n' for row in rows)).encode()


ROWS = [('A', 'has_req', 'R'), ('R', 'realized_by', 'M'),
        ('M', 'implemented_in', 'src/a.py::z'), ('M', 'implemented_in', 'src/a.py::a'),
        ('R', 'verified_by', 'tests/a.py'), ('A', 'depends_on', 'B'),
        ('B', 'depends_on', 'C'), ('C', 'depends_on', 'A'), ('A', 'depends_on', 'B'),
        ('A', 'affects', 'Z'), ('A', 'blocks', 'Q'), ('A', 'decided_by', 'D'),
        ('A', 'governed_by', 'G'), ('A', 'exposes', 'E'), ('A', 'refines', 'R'),
        ('A', 'constrains', 'M'), ('A', 'implemented_in', '.env'),
        ('A', 'verified_by', 'missing/file'), ('../bad', 'has_req', 'A')]


def setup(tmp, raw=None):
    for name in ['src/a.py', 'tests/a.py', 'spec/graph.yaml']:
        path = tmp / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(graph(ROWS) if name.endswith('.yaml') else b'pass\n')
    if raw is not None:
        (tmp / 'spec/graph.yaml').write_bytes(raw)


def query(tmp, anchor='A', purpose='implementation', **kwargs):
    setup(tmp)
    return M.query_relations(anchor, purpose, root=tmp, **kwargs)


def parser(tmp):
    values = ['[A, depends_on, B] # comment', '["a,b", r, \'it\'\'s\']',
              '[]', '[a,b]', '[a,b,c,d]', '[a, b, c]#bad', '[a,b,c]junk',
              '[a, null, c]', '[a, 2026-01-01, c]', '[a, &x, c]', '[a, : x, c]',
              '[a, "", c]', '[a, "\\u0085", c]', '[a, "\\ud800", c]',
              '[a, \'unfinished, c]', '[a, "bad\\q", c]', '[a, b, c',
              '[a, ' + 'x' * 4096 + ', c]', '[a, ' + 'x' * 4097 + ', c]']
    return matrix(tmp, values, M._row)


def parse_graph(tmp):
    values = [b'# c\n\nedges: # c\n - [a,r,b]\r\n', b'edges: [] # empty\n',
              b'', b'edges:\n', b'other: []', b'edges: []\n - [a,r,b]',
              b'edges:\n - [a,r,b]\n  - [b,r,c]', b'edges:\n\t- [a,r,b]',
              b'edges:\n - [a,r,b]\rx', b'\xff', b'edges:\n - [a,r,b]\n - [a,r,b]']
    return matrix(tmp, values, lambda raw: [edge.as_dict() for edge in M._parse_graph(raw)])


def limits(tmp):
    return matrix(tmp, [M.MAX_GRAPH_EDGES, M.MAX_GRAPH_EDGES + 1],
                  lambda count: len(M._parse_graph(b'edges:\n' + b' - [a,r,b]\n' * count)))


def paths(tmp):
    values = [None, '', '.', './src//a.py', 'src\\a.py', '../x', '/x', 'C:\\x',
              'C:x', '\\\\host\\share', 'a\x00', 'a\x7f', 'a\u009f', 'a\u2028',
              '\ud800', 'x' * 4096, 'x' * 4097]
    return matrix(tmp, values, lambda value: M._relative(value).as_posix())


def reader(tmp, profile=''):
    setup(tmp)
    (tmp / '.mir').mkdir(exist_ok=True)
    (tmp / '.mir/repo-profile.toml').write_text(profile, encoding='utf-8')
    (tmp / 'alias').symlink_to(tmp / '.env')
    (tmp / 'escape').symlink_to(tmp.parent)
    obj = M.LocalReader(tmp)
    values = ['src/a.py', 'missing', 'src', '.env', '.aws/key', 'x.pem', 'alias',
              'escape/outside', 'private/a', 'vault/a', 'remember/a', '../x']
    return {mode: matrix(tmp, values, lambda value, mode=mode: (
        M._validate_endpoint(value, obj, force_file=True) if mode == 'endpoint' else
        obj.exists(value) if mode == 'exists' else
        str(obj.path(value, allow_missing=True)).replace(str(tmp), '<tmp>')))
        for mode in ['endpoint', 'exists', 'path']}


def reader_io(tmp):
    setup(tmp)
    obj = M.LocalReader(tmp)
    result = matrix(tmp, ['src/a.py', 'absent', 'src'], lambda p: obj.read(p).decode())
    result += matrix(tmp, [None, tmp / 'absent', tmp / 'src/a.py'], M.LocalReader)
    for size in [M.MAX_GRAPH_BYTES, M.MAX_GRAPH_BYTES + 1]:
        (tmp / 'large').write_bytes(b'#' * size)
        result.append(observe(lambda tmp: obj.read('large').decode(), tmp))
    with mock.patch.object(Path, 'open', side_effect=OSError('blocked')):
        result.append(observe(lambda tmp: obj.read('src/a.py'), tmp))
    return result


def injected(tmp, refusal=None):
    class Reader:
        def path(self, value, allow_missing=False):
            calls.append(['path', value, allow_missing])
            if refusal == 'path':
                raise PermissionError('guard path refusal')
        def exists(self, value):
            calls.append(['exists', value])
            if refusal == 'exists':
                raise PermissionError('guard exists refusal')
            return refusal != 'missing'
        def read(self, value):
            calls.append(['read', value])
            if refusal == 'read':
                raise PermissionError('guard read refusal')
            return b'x' * (M.MAX_GRAPH_BYTES + 1) if refusal == 'large' else graph(ROWS)
    calls = []
    result = observe(lambda tmp: M.query_relations('src/a.py', 'impact', root=tmp,
                                                 io=Reader()), tmp)
    return {'result': result, 'calls': calls}


def cli(tmp, args):
    setup(tmp)
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.object(sys, 'argv', ['relations_query.py', *args, '--root', str(tmp)]), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = M.main()
        except SystemExit as exc:
            code = exc.code
    return {'exit': code, 'stdout': out.getvalue().replace(str(tmp), '<tmp>'),
            'stderr': err.getvalue().replace(str(tmp), '<tmp>')}


CASES = {'row': parser, 'parse_graph': parse_graph, 'graph_edges_limit': limits,
         'relative': paths, 'reader_default': reader, 'reader_io': reader_io,
         'reader_profile': lambda tmp: reader(tmp, '[paths]\nprotected_paths=["private"]\n'
                                             '[boundaries]\nsecrets=["vault/*"]\n'
                                             '[preserve]\nagent_memory_paths=["remember"]'),
         'helpers': lambda tmp: {'paths': [M._endpoint_path(x)
                                         for x in ['A', 'a.py', './x', 'a/b::f']],
                                'normalized': M._normalized_locator('./a//b::f'),
                                'controls': [M._has_control_characters(x)
                                             for x in ['a', '\t', '\u2029']],
                                'notices': M._notices({'z': 2, 'a': 1}, ['extra'])},
         'query_invalid': lambda tmp: matrix(tmp, [('', {}), ('src/a.py\x01', {}), ('\ud800', {}),
             ('x' * 4097, {}), ('\u00e9' * 2049, {}), ('unknown', {}), ('../a', {}),
             ('.env', {}), ('A', {'depth': True}), ('A', {'depth': 0}), ('A', {'depth': 5}),
             ('A', {'max_edges': 0}), ('A', {'max_edges': 65}), ('A', {'max_edges': 1.5})],
             lambda item: query(tmp, item[0], **item[1])),
         'purpose_invalid': lambda tmp: matrix(tmp, [None, '', 'other'],
                                               lambda p: query(tmp, purpose=p))}
for purpose in ['implementation', 'verification', 'impact', 'dependencies']:
    CASES['query_' + purpose] = lambda tmp, p=purpose: query(tmp, purpose=p)
    CASES['depth_' + purpose] = lambda tmp, p=purpose: matrix(
        tmp, [1, 2, 4], lambda depth: query(tmp, purpose=p, depth=depth))
for anchor in ['src/a.py', './src/a.py::a', 'src/a.py::z']:
    CASES['locator_' + anchor] = lambda tmp, a=anchor: query(tmp, a, 'impact', max_edges=1)
for cap in [1, 2, 64]:
    CASES[f'max_edges_{cap}'] = lambda tmp, cap=cap: query(tmp, max_edges=cap, depth=4)
for refusal in [None, 'path', 'exists', 'read', 'missing', 'large']:
    CASES[f'injected_{refusal}'] = lambda tmp, r=refusal: injected(tmp, r)
for index, profile in enumerate(['[paths]\nprotected_paths="x"', 'paths=[]', '[',
                                  '[paths]\nprotected_paths=["../x"]',
                                  '[paths]\nprotected_paths=' + json.dumps(['x'] * 257),
                                  '#' * 65537]):
    CASES[f'profile_invalid_{index}'] = lambda tmp, p=profile: reader(tmp, p)
CASES['main'] = lambda tmp: matrix(tmp, [
    ['A', 'implementation'], ['A', 'dependencies', '--depth', '4'],
    ['unknown', 'impact'], ['A', 'bad'], [], ['A', 'impact', '--depth', 'bad']],
    lambda args: cli(tmp, args))
# A carriage return inside a comment line is still a format error.
CASES['parse_graph_comment_cr'] = lambda tmp: matrix(
    tmp, [b'edges:\n - [a,r,b]\n# c\rx\n'],
    lambda raw: [edge.as_dict() for edge in M._parse_graph(raw)])


def reader_uppercase(tmp):
    """Protection matching lower-cases the path first."""
    setup(tmp)
    obj = M.LocalReader(tmp)
    return matrix(tmp, ['SECRETS/a', '.ENV', 'X.PEM', '.AWS/key'], obj.exists)


CASES['reader_uppercase'] = reader_uppercase
RECORDS = json.loads(FIXTURE.read_text(encoding='ascii')) if FIXTURE.exists() else {}


def test_every_case_has_a_frozen_record():
    assert sorted(RECORDS) == sorted(CASES)


@pytest.mark.parametrize('copy', sorted(COPIES))
@pytest.mark.parametrize('name', sorted(CASES))
def test_reference_matches_frozen_record(copy, name, tmp_path, monkeypatch):
    monkeypatch.setitem(globals(), 'M', load(copy))
    assert observe(CASES[name], tmp_path) == RECORDS[name]
