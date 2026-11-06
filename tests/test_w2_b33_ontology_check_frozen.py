"""Unmodified B33 checker oracle, replayed against both distributed copies."""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import sys
from functools import reduce
from operator import getitem
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
COPIES = {k: f'plugins/{v}/ontology/scripts/ontology_check.py' for k, v in
          [('core', 'mir-core/skills'), ('mcp', 'mir-mcp')]}
FIXTURE = ROOT / 'native/handoff-packet/tests/fixtures/w2/b33-ontology-check.json'
def load(key):
    spec = importlib.util.spec_from_file_location('ontology_check', ROOT / COPIES[key])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
M = load('core')
def clean(value, tmp):
    if isinstance(value, str):
        value = value.replace(str(tmp), '<tmp>').replace(str(tmp.parent), '<parent>')
        if len(value) > 240:
            return {'length': len(value), 'sha256': hashlib.sha256(value.encode()).hexdigest(),
                    'first': value[:120], 'last': value[-120:]}
    if isinstance(value, (list, tuple)):
        return [clean(v, tmp) for v in value]
    if isinstance(value, dict):
        return {k: clean(v, tmp) for k, v in value.items()}
    return value
def observe(case, tmp):
    try:
        return {'value': clean(case(tmp), tmp)}
    except Exception as exc:  # noqa: BLE001 - freeze reference exception class and message
        return {'error': [type(exc).__name__, str(exc).replace(str(tmp), '<tmp>')]}
def matrix(tmp, values, call):
    return [observe(lambda tmp, v=v: call(v), tmp) for v in values]
def setup(tmp):
    (tmp / '.mir').mkdir(exist_ok=True)
    for name, text in [('a.py', 'def alpha():\n    pass\n'), ('a.md', '# Alpha\n'),
                       ('.mir/repo-profile.toml', 'slug = "sample"\n')]:
        (tmp / name).write_text(text, encoding='ascii')
    contract = dict(schema='mir-semantic-contract/v1', contract_id='sample', version='1.1.0',
                    rules=[{'id': 'r'}], concepts=[{'id': 'c'}],
                    relations=[dict(id='rel', **{'from': ['c'], 'to': ['*']})],
                    error_cases=[dict(id='e', rules=['r'])], axes={'state': {'values': {'ok': ''}}},
                    mapping=dict(required_keys=['namespace'],
                                 knowledge_supply_values=['connected']))
    mapping = dict(schema='mir-semantic-mapping/v1', namespace='sample',
                   contract=dict(id='sample', version='1.1.0', version_range='>=1.0.0 <2.0.0'),
                   canonical_index=['a.py'], concepts={'c': {'status': 'mapped', 'local':
                   [{'name': 'alpha', 'ref': 'a.py#alpha'}]}}, vocabularies=[dict(name='v',
                   ref='a.md', values={'ready': {'state': 'ok'}})],
                   relations=[dict(local='r', common='rel', **{'from': ['c'], 'to': '*'})],
                   domain=dict(concepts=[{'ref': 'a.py'}], relations=[{'ref': 'a.py'}],
                               invariants=[{'ref': 'a.py', 'check': 'a.py:2'}, {'ref': 'a.md'}]),
                   questions=[dict(id='q', question='alpha sample', evidence=['a.py', 'absent'])],
                   error_cases=[dict(id='e', status='covered', check='a.py#alpha')],
                   knowledge_supply=dict(memory_keeper='connected', binding='resident_stdio'),
                   entrypoints=[{'ref': 'a.py'}])
    for name, data in [('contract.json', contract), ('.mir/ontology-map.json', mapping)]:
        (tmp / name).write_text(json.dumps(data, ensure_ascii=True), encoding='ascii')
    return contract, mapping
def Reader(root):
    return SimpleNamespace(root=root, path=lambda v, **kw: root / v,
                           exists=lambda v: (root / v).exists(),
                           read=lambda v: (root / v).read_bytes())
def digest(value):
    text = json.dumps(value, sort_keys=True)
    return value if len(text) <= 512 else {'len': len(text),
                                           'sha256': hashlib.sha256(text.encode()).hexdigest()}


def check(tmp, mode):
    contract, mapping = setup(tmp)
    results = []
    def run(data, is_contract=False):
        checker = M.Checker(Reader(tmp) if mode else None)
        result = (checker.contract(data) if is_contract else
                  checker.mapping(data, contract, b'{}', tmp))
        if isinstance(result, (dict, list)):
            result = {'sha256': hashlib.sha256(json.dumps(
                result, sort_keys=True, default=str).encode()).hexdigest()}
        return [result, checker.errors, checker.warnings, sorted(checker.checked_refs),
                sorted(checker.line_refs)]
    def variants(data, path=()):
        yield path
        if isinstance(data, (dict, list)):
            items = data.items() if isinstance(data, dict) else enumerate(data)
            for key, value in items:
                yield from variants(value, (*path, key))
    for original, is_contract in [(contract, True), (mapping, False)]:
        results.append(run(original, is_contract))
        for path in variants(original):
            for value in [None, {}, [], '', 'unknown', False]:
                data = copy.deepcopy(original)
                if path:
                    reduce(getitem, path[:-1], data)[path[-1]] = value
                else:
                    data = value
                results.append([list(path), value, digest(observe(
                    lambda tmp, d=data, c=is_contract: run(d, c), tmp))])
    for version in ['1.0.0', '1.2.0', '2.0.0', 'bad']:
        for bounds in ['>=1.0.0 <2.0.0', '>=2.0.0 <3.0.0', '>=2.0.0 <1.0.0']:
            mapping['contract'].update(version=version, version_range=bounds, sha256='bad')
            results.append(run(mapping))
    for path, values in [(('contract', 'version'), ['1.0.0']),
            (('concepts', 'c'), [{'status': 'absent'},
                                {'status': 'not_applicable', 'reason': 'x'}]),
            (('relations',), [[{'local': 'r', 'local_only': 'x', 'ref': 'a.py'}],
                             [{'local': 'r', 'common': 'rel', 'from': ['bad'], 'to': []}]]),
            (('vocabularies', 0, 'values'), [{'x': {'local_only': 'x', 'state': 'ok'}},
                                          {'x': {'local_only': 'x'}}]),
            (('error_cases',), [[{'id': 'e', 'status': 'covered'}],
                               [{'id': 'e', 'status': 'planned', 'check': 'a.py'}]])]:
        for value in values:
            data = copy.deepcopy(mapping)
            data['contract'].update(version='1.1.0', version_range='>=1.0.0 <2.0.0')
            reduce(getitem, path[:-1], data)[path[-1]] = value
            results.append(run(data))
    contract['rules'].append({'id': 'r'})
    results.append(run(contract, True))
    mapping['contract'].update(version='1.0.0', version_range='>=1.0.0 <2.0.0')
    del mapping['knowledge_supply']['binding']
    results.append(run(mapping))
    mapping['domain']['relations'][0].update(common='rel', **{'from': ['bad'], 'to': []})
    mapping['contract']['version'] = '1.1.0'
    results.append(run(mapping))
    del mapping['namespace']
    for profile in [None, '', 'slug = "other"']:
        file = tmp / '.mir/repo-profile.toml'
        if profile is None:
            file.unlink()
        else:
            file.write_text(profile, encoding='ascii')
        results.append(run(mapping))
    return results
def refs(tmp, guarded):
    setup(tmp)
    (tmp / 'escape').symlink_to(tmp.parent)
    (tmp / 'loop').symlink_to('loop')
    checker = M.Checker(Reader(tmp) if guarded else None)
    values = [None, '', '/abs', 'C:\\abs', 'C:rel', 'a\\b', '../x', 'escape', 'absent',
              '.', 'a.py', 'a.py#alpha', 'a.py#missing', 'a.py:0', 'a.py:99', 'a.md:1']
    result = matrix(tmp, values, lambda ref: str(checker.covered_check(ref, '/r', tmp)))
    checker.refs([{'ref': 'a.py'}, 'a.md'], '/refs', tmp)
    return [result, checker.errors, checker.warnings, sorted(checker.checked_refs),
            M.impact({'canonical_index': ['loop']}, tmp, ['loop'])]
def symbols(tmp):
    rows = [(s, t, n) for s in ['.md', '.markdown', '.mdx', '.json', '.py', '.rs', '.js',
            '.ts', '.go', '.kt', '.kts', '.dart', '.toml', '.sh', '.bash', '.zsh', '.txt']
            for t in ['# Alpha\n# Alpha\n```\n# Hidden\n```\n<!-- # Secret -->',
                      'pub fn alpha() {}\nalpha = 1\n[alpha]\nfunction alpha() {',
                      '/* fun hidden() */\n// fun secret()\nfun alpha() {}',
                      '{"a/b": [{"~x": 0}], "alpha": {}}', '{bad', 'test("alpha", x)']
            for n in ['', 'alpha', 'pkg.alpha', 'alpha-1', 'hidden', 'secret', '/a~1b/0/~0x',
                      '/a~1b/00', '/bad~2']]
    return matrix(tmp, rows, lambda row: M.resolves_symbol(row[1], row[2], row[0])) + matrix(
        tmp, [None, lambda text: json.loads(text)],
        lambda validate: M.resolves_symbol('{bad', 'alpha', '.json', validate))
def fake_git(tmp, action, state='ok'):
    calls = []
    def run(argv, **kwargs):
        calls.append([argv, kwargs])
        if state == 'timeout':
            raise M.subprocess.TimeoutExpired('git', kwargs.get('timeout', 5))
        if state == 'oserror':
            raise OSError('blocked')
        out = (b'a.py\0old\0' if 'diff' in argv else
               b'abc\n' if 'rev-parse' in argv or 'log' in argv else b'')
        return SimpleNamespace(returncode=int(state == 'fail'), stdout=out, stderr=b'bad\xff\n')
    with mock.patch.object(M.subprocess, 'run', side_effect=run):
        value = observe(lambda tmp: action(), tmp)
    return [value, calls]
def pins(tmp, state, guarded=False):
    setup(tmp)
    report = dict.fromkeys(['mapping_path', 'mapping_version', 'mapping_sha256', 'contract_id',
                            'contract_version', 'contract_sha256'], None)
    with mock.patch.object(M, 'datetime') as clock:
        clock.now.return_value.isoformat.return_value = 'fixed'
        return fake_git(tmp, lambda: M.handoff_pins(tmp, ['a.py', 'absent'], report,
                        io=Reader(tmp) if guarded else None,
                        git_runner=(lambda label, *args: None if state == 'fail' else
                        False if label.endswith('modified_vs_head') else 'abc') if guarded
                        and state != 'missing_runner' else None), state)
def cli(tmp, args, state='ok', payload=None):
    setup(tmp)
    if payload is not None:
        path = tmp / '.mir/ontology-map.json'
        path.unlink() if payload == 'missing' else path.write_text(payload, encoding='ascii')
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
            mock.patch.object(sys, 'argv', ['ontology_check.py']), \
            mock.patch.object(M, 'datetime') as clock:
        clock.now.return_value.isoformat.return_value = 'fixed'
        def invoke():
            try:
                return M.main([*args, '--contract', str(tmp / 'contract.json')])
            except SystemExit as exc:
                return exc.code
        result = fake_git(tmp, invoke, state)
    return [result, out.getvalue(), err.getvalue()]
CASES = {'validation': lambda tmp: check(tmp, False),
         'validation_codes': lambda tmp: check(tmp, True),
         'refs': lambda tmp: refs(tmp, False), 'refs_codes': lambda tmp: refs(tmp, True),
         'symbols': symbols, 'version': lambda tmp: matrix(tmp,
         [None, 1, '', '01.0.0', '1.2.3', '1.2.3-01', '1.2.3-a.2+build', '1.2.3-0'], M.version_key),
         'helpers': lambda tmp: [M.pointer('/a', '~x/y'), M.ref_path('a.py:3#x'),
         M.touches('./a', ['a/b']), matrix(tmp, ['0', '-1', '1', 'bad', '1.5'], M.positive_int)]}
for guarded in [False, True]:
    def selections(tmp, guarded=guarded):
        _, mapping = setup(tmp)
        reader = Reader(tmp) if guarded else None
        return [list(M.map_entries(mapping)), list(M.entry_refs(mapping, '')),
                *[M.impact(mapping, tmp, paths, git_diff=diff, io=reader) for diff in [False, True]
                  for paths in [[], ['a.py'], ['.mir/ontology-map.json'], ['a.md']]],
                *[M.lookup(mapping, query, limit, io=reader) for query in ['', 'alpha', 'sample c']
                  for limit in [0, 1, 3, 99]]]
    CASES[f'selection_{guarded}'] = selections
def question_counts(tmp):
    contract, mapping = setup(tmp)
    rows = []
    for count in (1, 2, 3):
        data = copy.deepcopy(mapping)
        data['questions'] = [dict(id=f'q{i}', question='alpha sample', evidence=['a.py'])
                             for i in range(count)]
        checker = M.Checker(None)
        checker.mapping(data, contract, b'{}', tmp)
        rows.append([count, checker.warnings])
    return rows


def lookup_scores(tmp):
    _, mapping = setup(tmp)
    mapping['questions'] = [dict(id='one', question='alpha', evidence=[]),
                            dict(id='three', question='alpha beta gamma', evidence=[]),
                            dict(id='two', question='alpha beta', evidence=[])]
    return [[m['pointer'], m['score']] for m in
            M.lookup(mapping, 'alpha beta gamma', 99)['matches']]


CASES['question_counts'] = question_counts
CASES['lookup_scores'] = lookup_scores
CASES['git'] = lambda tmp: matrix(tmp, ['ok', 'fail', 'timeout', 'oserror'],
    lambda s: fake_git(tmp, lambda: M.changed_paths(
        SimpleNamespace(paths=None, git_diff='HEAD'), tmp), s))
CASES['pins'] = lambda t: matrix(t, ['ok', 'fail', 'timeout', 'oserror'], lambda s: pins(t, s))
CASES['guarded_pins'] = lambda t: matrix(t, ['ok', 'fail', 'missing_runner'],
                                        lambda s: pins(t, s, True))
CASES['paths'] = lambda tmp: matrix(tmp, [(['a', './a', 'z'], None), (['../a'], None),
    ([str(tmp / 'a')], None), (['/outside'], None), (None, '-bad')],
    lambda v: M.changed_paths(SimpleNamespace(paths=v[0], git_diff=v[1]), tmp))
CASES['main'] = lambda tmp: matrix(tmp, [['contract'], ['mapping', '--handoff', 'a.py'],
    ['mapping', '--json'], ['impact', '--paths', 'a.py', '--strict'],
    ['impact', '--git-diff', '--json'], ['lookup', 'alpha'], ['lookup', 'alpha', '--json'],
    ['lookup', 'alpha', '--limit', '0'], [], ['unknown']],
    lambda args: cli(tmp, args if args in (['contract'], []) else [*args, '--repo', str(tmp)]))
CASES['main_errors'] = lambda tmp: matrix(tmp,
    [(cmd, data) for cmd in ['mapping', 'impact', 'lookup'] for data in ['missing', '{', '[]',
     ' ' * 32769 + '{}']], lambda v: cli(tmp, [v[0], *(['alpha'] if v[0] == 'lookup' else
     ['--paths', 'a.py', '--strict'] if v[0] == 'impact' else []), '--repo', str(tmp)],
     payload=v[1]))
# --limit goes through Python int(): whitespace, underscores, Unicode digits, any size.
CASES['main_limit'] = lambda tmp: matrix(tmp, ['abc', '1_0', ' 2 ', '\x1c3', '\u0663',
    '-99999999999999999999999', '99999999999999999999', "a'b", '+1', '1__0', '-0'],
    lambda v: cli(tmp, ['lookup', 'alpha', '--limit', v, '--repo', str(tmp)]))
# lookup case-folds the query and the entry text before comparing words.
CASES['lookup_casefold'] = lambda tmp: matrix(tmp, ['ALPHA', 'aLpHa_x'],
    lambda q: cli(tmp, ['lookup', q, '--json', '--repo', str(tmp)]))
RECORDS = json.loads(FIXTURE.read_text(encoding='ascii')) if FIXTURE.exists() else {}
def test_every_case_has_a_frozen_record():
    assert sorted(RECORDS) == sorted(CASES)
@pytest.mark.parametrize('copy,name', [(c, n) for c in sorted(COPIES) for n in sorted(CASES)])
def test_reference_matches_frozen_record(copy, name, tmp_path, monkeypatch):
    monkeypatch.setitem(globals(), 'M', load(copy))
    assert observe(CASES[name], tmp_path) == RECORDS[name]
