"""B30 validators oracle captured from unmodified Python, never from the port."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from mir.cli import bootstrap_adoption as M

FIXTURE = (Path(__file__).parents[1] /
           'native/handoff-packet/tests/fixtures/w2/b30-adoption-validators.json')
CASES = {}
def observe(case, tmp):
    try:
        value = json.loads(json.dumps(case(tmp)))
        text = json.dumps(value, sort_keys=True)
        return {'value': value if len(text) <= 512 else
                {'len': len(text), 'sha256': hashlib.sha256(text.encode()).hexdigest()}}
    except (Exception, SystemExit) as exc:
        return {'error': [type(exc).__name__, str(exc).replace(str(tmp), '<tmp>')]}
def put(tmp, name, body):
    path = tmp / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body if isinstance(body, bytes) else body.encode())
    return path
def matrix(tmp, values, call):
    return [observe(lambda tmp, v=value: call(v), tmp) for value in values]
def fake(tmp, call, code=0):
    calls = []
    def run(argv, **kw):
        calls.append([ [str(a).replace(str(tmp), '<tmp>') for a in argv],
                       str(kw.get('cwd', '')).replace(str(tmp), '<tmp>'),
                       kw.get('env', {}).get('GIT_OPTIONAL_LOCKS')])
        return SimpleNamespace(returncode=code, stdout='', stderr='')
    with mock.patch.object(M.subprocess, 'run', side_effect=run):
        value = call()
    return [value, calls]
def parse(tmp):
    def run(args):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(M.Path, 'cwd', return_value=tmp), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            value = observe(lambda tmp: {k: str(v).replace(str(tmp), '<tmp>')
                            if isinstance(v, Path) else v for k,
                                v in vars(M._parse(args)).items()}, tmp)
        return [value, out.getvalue(), err.getvalue()]
    return matrix(tmp, [[], ['--help'], ['--bad'], ['--project-root'],
                       ['--apply', '--json', '--project-root', 'p', '--native-evaluator',
                           'n']], run)
def load(tmp, body):
    path = tmp / 'data.json'
    if body is not None:
        put(tmp, 'data.json', body)
    try:
        raw, data = M._load_json_bytes(path)
        return [raw, data.hex()]
    except M.AdoptionError as exc:
        raise M.AdoptionError(str(exc).replace(str(tmp), '<tmp>')) from exc
def paths(tmp):
    (tmp / 'escape').symlink_to(tmp.parent)
    return matrix(tmp, [None, '', ' ', 1, '/abs', '../x', 'a/../x', 'escape/x', '.',
                        'a//b', './a', ' spaced ', 'a\\b'],
                  lambda p: [str(x).replace(str(tmp), '<tmp>') for x in
                             M._tracked_path(tmp, p, label='path')])
def profile(tmp, body=None, **changes):
    repo = dict(slug='sample', repository_type='code_app', overlay_archetype='code_app',
                purpose='Build tools', technology_stack=['Rust'])
    repo.update(changes)
    if body is None:
        body = '[repo]\n' + '\n'.join(f'{k} = {json.dumps(v)}' for k, v in repo.items())
    if body != 'MISSING':
        put(tmp, '.mir/repo-profile.toml', body)
    result = M._validate_profile(tmp, dict(project_slug='sample', repository_archetype='code_app',
                                         profile='code_app'))
    return json.loads(json.dumps(result).replace(str(tmp), '<tmp>'))
def surface(tmp, change=None, mode='ok'):
    put(tmp, 'proof', 'evidence')
    surfaces = {k: dict(disposition='applied', evidence_paths=['proof']) for k in M._SURFACE_KEYS}
    if change is not None:
        surfaces['project_profile'] = change
    if mode == 'empty':
        put(tmp, 'proof', ' ')
    if mode == 'missing':
        (tmp / 'proof').unlink()
    if mode == 'symlink':
        put(tmp, 'target', 'evidence')
        (tmp / 'proof').unlink()
        (tmp / 'proof').symlink_to(tmp / 'target')
    if mode == 'extra':
        surfaces['extra'] = {}
        del surfaces['identity_finalize']
    if mode == 'na':
        surfaces['content_onboarding'] = dict(disposition='not_applicable', evidence_paths=[],
            reason='No content')
    with (mock.patch.object(Path, 'read_bytes', side_effect=OSError('denied'))
          if mode == 'unreadable' else contextlib.nullcontext()):
        return fake(tmp, lambda: M._validate_surface_contract(tmp, {'surfaces': surfaces}),
                    int(mode == 'untracked'))

GATE = {'.claude/hooks/_lib/bootstrap-gate.sh':
        'mir_bootstrap_gate_state mir_bootstrap_gate_enforce',
        '.claude/hooks/session-start.sh': 'bootstrap-gate.sh mir_bootstrap_gate_state',
        '.claude/hooks/pre-tool-use.sh': 'bootstrap-gate.sh mir_bootstrap_gate_enforce',
        '.claude/settings.json': '{"command":"session-start.sh pre-tool-use.sh"}',
        '.codex/hooks.json': '{"command":"session-start.sh pre-tool-use.sh"}'}
LAUNCHER = '.claude/hooks/_lib/run-python.sh'
def files(tmp, validator, bodies, change):
    for name, body in {**bodies, **change}.items():
        if body is not None:
            put(tmp, name, body)
    result = validator(tmp)
    return json.loads(json.dumps(result).replace(str(tmp), '<tmp>'))
def canonical(tmp, mode):
    source = tmp / 'source'
    source.mkdir()
    relative = '.claude/hooks/_lib/run-python.sh' if mode == 'packaged' else 'helper'
    if mode not in ('unknown', 'packaged'):
        put(source, relative, 'canonical')
    if mode != 'missing':
        put(tmp, relative, 'different' if mode == 'different' else 'canonical')
    with mock.patch.object(M, '_SOURCE_ROOT', source), \
            mock.patch.object(M.importlib.resources, 'files', return_value=source), \
            (mock.patch.object(Path, 'read_bytes', side_effect=OSError('denied'))
             if mode == 'unreadable' else contextlib.nullcontext()):
        if mode == 'packaged':
            put(source, M._PACKAGED_CANONICAL[relative], 'canonical')
        result = M._validate_canonical_applied_helper(tmp, relative, label='helper')
    return json.loads(json.dumps(result).replace(str(tmp), '<tmp>'))

CASES.update(parse=parse, paths=paths,
             adoption_error=lambda tmp: [issubclass(M.AdoptionError, ValueError),
                 str(M.AdoptionError('bad'))],
             git_tracked=lambda tmp: [fake(tmp, lambda: M._is_git_tracked(tmp, 'a'),
                 c) for c in [0, 1]],
             text=lambda tmp: matrix(tmp, [None, 1, '', ' ', ' ready ', 'TODO', 'describe',
                 'placeholder', 'replace-me', 'replace me', 'replaceme', 'unknown', 'tbd', 'todos'],
                 lambda v: M._non_placeholder_text(v, label='text')),
             placeholders=lambda tmp: [M._contains_unresolved_placeholder(v) for v in
                 ['', 'ready', 'TODO', 'tbd: 0', '"todo":0,', 'TODO = 01', 'tbd: 0 TODO',
                  'tbd: 1', 'todo: 0\nunknown', 'todos', 'TBD=0, ready']],
             hook_commands=lambda tmp: M._hook_commands({'command': 'a', 'nested': [
                 {'command': 'b'}, {'command': {'command': 'c'}}, 1, {'command': 2}]}),
             raw_python=lambda tmp: [M._has_raw_python(s) for s in ['', '# python x',
                 '  # python3 x', 'python x', '/usr/bin/python3 x', 'exec python x',
                 'a; python3 x', 'a && python x', 'a | python x', 'python3',
                 'python3.12 x', '/bin/python3 x', 'uv run python x', 'run-python.sh x']],
             runtime=lambda tmp: {k: [M._validate_required_runtime_evidence(
                 {'evidence_paths': v}, surface_name=k) for v in [[], list(paths), ['extra']]]
                 for k, paths in M._REQUIRED_RUNTIME_EVIDENCE.items()})
for key, body in [('missing', None), ('invalid', '{'), ('array', '[]'), ('null', 'null'),
                  ('valid', '{"x":1}'), ('unicode', b'"\xff"')]:
    CASES[f'load.{key}'] = lambda tmp, b=body: load(tmp, b)
for key, changes in [('valid', {}), ('bad', dict(slug='BAD', overlay_archetype='',
        repository_type='other', purpose='TODO', technology_stack=[])),
        ('mismatch', dict(slug='other', overlay_archetype='infra_runtime',
            repository_type='infra_runtime')),
        ('stack', dict(technology_stack=['', 'unknown', 1])),
        ('fallback', dict(repository_type='other')), ('stack_type',
            dict(technology_stack='Rust', purpose=''))]:
    CASES[f'profile.{key}'] = lambda tmp, c=changes: profile(tmp, **c)
for key, body in [('missing', 'MISSING'), ('invalid', '['), ('no_repo', 'x=1')]:
    CASES[f'profile.{key}'] = lambda tmp, b=body: profile(tmp, b)
for key, change in [('object', 1), ('disposition', {}), ('paths_type',
    dict(disposition='applied', evidence_paths=[1])),
        ('owned', dict(disposition='repository_owned', evidence_paths=['proof'])),
        ('duplicate', dict(disposition='applied', evidence_paths=['proof', 'proof'], extra=1)),
        ('no_paths', dict(disposition='repository_owned', evidence_paths=[])),
        ('escape', dict(disposition='applied', evidence_paths=['../proof'])),
        ('exception', dict(disposition='exception', evidence_paths=['proof'], reason='Delayed',
            blockers=['Review'])),
        ('bad_exception', dict(disposition='exception', evidence_paths=[], reason='TODO',
            blockers=['', 'unknown'])),
        ('no_blockers', dict(disposition='exception', evidence_paths=['proof'], reason='',
            blockers=[])),
        ('not_applicable', dict(disposition='not_applicable', evidence_paths=[],
            reason='No content'))]:
    CASES[f'surface.{key}'] = lambda tmp, c=change: surface(tmp, c)
CASES['surface.absent'] = lambda tmp: M._validate_surface_contract(tmp, {})
for mode in ['ok', 'empty', 'missing', 'extra', 'na', 'unreadable', 'untracked', 'symlink']:
    CASES[f'surface.{mode}'] = lambda tmp, m=mode: surface(tmp, mode=m)
for key, change in [('valid', {}), ('missing', dict.fromkeys(GATE)),
        ('unwired', dict.fromkeys(GATE, '')), ('invalid',
            {p: '{' for p in GATE if p.endswith('.json')}),
        ('wiring_unicode', {p: b'\xff' for p in GATE if p.endswith('.json')}),
        ('unreadable', {p: b'\xff' for p in GATE if not p.endswith('.json')}),
        ('session_partial', {'.claude/hooks/session-start.sh': 'bootstrap-gate.sh'}),
        ('mutation_unwired', {p: '{"command":"session-start.sh"}' for p in GATE
                              if p.endswith('.json')})]:
    CASES[f'gate.{key}'] = lambda tmp, c=change: files(tmp, M._validate_bootstrap_gate, GATE, c)
for mode in ['same', 'different', 'missing', 'unknown', 'packaged', 'unreadable']:
    CASES[f'canonical.{mode}'] = lambda tmp, m=mode: canonical(tmp, m)
BASE = {LAUNCHER: '.venv/bin/python .venv/Scripts/python.exe\nuv run --project p python x',
        '.claude/hooks/session-start.sh': 'run-python.sh',
            '.claude/hooks/pre-tool-use.sh': 'run-python.sh'}
for key, change in [('valid', {}), ('missing', {LAUNCHER: None}), ('invalid', {LAUNCHER: b'\xff'}),
        ('routes', {LAUNCHER: ''}), ('external',
            {LAUNCHER: ('.venv/bin/python .venv/Scripts/python.exe '
            'bootstrap-receipt.json run-python --project-root')}),
        ('raw', {LAUNCHER: BASE[LAUNCHER] + '\npython3 x'}),
        ('hooks_missing', {p: None for p in BASE if p != LAUNCHER}),
        ('hooks_invalid', {p: b'\xff' for p in BASE if p != LAUNCHER}),
        ('hooks_raw', {p: 'python3 x' for p in BASE if p != LAUNCHER}),
        ('uv_exec', {LAUNCHER: BASE[LAUNCHER] + '\nexec uv run --project python3 x'})]:
    CASES[f'launcher.{key}'] = lambda tmp, c=change: files(tmp, M._validate_python_launcher,
        BASE, c)
def profile_maps(tmp):
    result = []
    for mapping, field in [(M._DIRECT_PROFILE_MAP, 'repository_type'),
                           (M._ARCHETYPE_PROFILE_MAP, 'overlay_archetype')]:
        for key in mapping:
            root = tmp / f'{field}-{key}'
            root.mkdir()
            changes = {field: key}
            if field == 'overlay_archetype':
                changes['repository_type'] = 'unmapped'
            result.append([key, profile(root, **changes)])
    return result

CASES['profile.maps'] = profile_maps
RECORDS = json.loads(FIXTURE.read_text()) if FIXTURE.exists() else {}
def test_every_case_has_a_frozen_record():
    assert sorted(RECORDS) == sorted(CASES)

@pytest.mark.parametrize('name', sorted(CASES))
def test_reference_matches_frozen_record(name, tmp_path):
    assert observe(CASES[name], tmp_path) == RECORDS[name]
