"""B30 main oracle captured from unmodified Python, never from a port.

Main cases script the already-frozen validators; no native process is executed.
"""
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
           'native/handoff-packet/tests/fixtures/w2/b30-adoption-main.json')
CASES = {}


def observe(case, tmp):
    try:
        with mock.patch.object(M.subprocess, 'run', side_effect=AssertionError('unexpected run')):
            value = json.loads(json.dumps(case(tmp), default=str).replace(str(tmp), '<tmp>'))
        text = json.dumps(value, sort_keys=True)
        return {'value': value if len(text) <= 512 else
                {'len': len(text), 'sha256': hashlib.sha256(text.encode()).hexdigest()}}
    except (Exception, SystemExit) as exc:
        return {'error': [type(exc).__name__, str(exc).replace(str(tmp), '<tmp>')]}


def put(tmp, name, body):
    path = tmp / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    return path


def digest(tmp, mode):
    path = put(tmp, 'proof', 'plain\n\u00e9')
    calls = []
    def run(argv, **kw):
        calls.append([argv, kw.get('cwd'), kw.get('input'), kw])
        if mode == 'oserror':
            raise OSError('jq unavailable')
        return SimpleNamespace(returncode=int(mode == 'failure'),
            stdout={'empty': b'', 'blank': b' \n', 'newlines': b'{"hooks":{}}\n\n',
                    'no_newline': b'{"hooks":{}}'}.get(mode, b'{"hooks":{"a":[]}}\n'))
    def call():
        if mode == 'missing':
            path.unlink()
        if mode.startswith('list'):
            surfaces = {'b': {'evidence_paths': ['proof', 'absent']},
                        'a': {'evidence_paths': ['proof', 'z']}, 'c': {}}
            put(tmp, 'z', 'last')
            if mode == 'list_settings_error':
                surfaces['a']['evidence_paths'].append('.claude/settings.json')
                with mock.patch.object(M, 'evidence_digest', side_effect=M.AdoptionError('bad')):
                    return M._evidence_digests(tmp, surfaces)
            return M._evidence_digests(tmp, surfaces)
        return M.evidence_digest('proof' if mode in ('plain', 'missing') else
                                 '.claude/settings.json', path)
    with mock.patch.object(M.subprocess, 'run', side_effect=run):
        try:
            result = {'value': call()}
        except (Exception, SystemExit) as exc:
            result = {'error': [type(exc).__name__, str(exc).replace(str(tmp), '<tmp>')]}
    return [result, calls]


def atomic(tmp, mode):
    path = put(tmp, 'nested/receipt.json', 'previous') if mode != 'new' else (
        tmp / 'nested/receipt.json')
    with (mock.patch.object(M.os, 'replace', side_effect=OSError('replace denied'))
          if mode == 'replace_failure' else contextlib.nullcontext()):
        result = observe(lambda tmp: M._atomic_write_json(path, {'z': '\u00e9', 'a': [1]}), tmp)
    return [result, path.read_bytes().hex() if path.exists() else None,
            sorted(p.name for p in path.parent.iterdir())]


def emit(tmp, as_json, written):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        M._emit(SimpleNamespace(json=as_json), dict(status='not_ready',
            errors=['one', 'two'], receipt_written=written, extra='\u00e9'))
    return out.getvalue()


VALIDATORS = ['_validate_profile', '_validate_surface_contract',
              '_validate_required_runtime_evidence', '_validate_bootstrap_gate',
              '_validate_canonical_applied_helper', '_validate_python_launcher',
              '_validate_content_onboarding', '_validate_memory', '_validate_phase2']


def main_case(tmp, mode, apply=False, as_json=True):
    surfaces = {key: dict(disposition='applied', evidence_paths=['proof'])
                for key in M._SURFACE_KEYS}
    if mode in ('exceptions', 'not_applicable', 'content_workspace'):
        for key in ('content_onboarding', 'memory_acceptance', 'phase2_spec'):
            surfaces[key].update(disposition='exception', reason='Deferred')
        if mode != 'exceptions':
            surfaces['content_onboarding']['disposition'] = 'not_applicable'
    if mode == 'repository_owned':
        for surface in surfaces.values():
            surface['disposition'] = 'repository_owned'
    manifest = dict(schema_version=1, project_slug='sample', repository_archetype='code_app',
                    profile='content_workspace' if mode == 'content_workspace' else 'code_app',
                    mir_yoke_source_commit='a' * 40, surfaces=surfaces)
    if mode == 'manifest_fields':
        manifest.update(schema_version=2, mir_yoke_source_commit='BAD', extra=1)
    if mode != 'missing':
        put(tmp, 'config/bootstrap-adoption.json', '{' if mode == 'invalid' else
            '[]' if mode == 'array' else json.dumps(manifest))
    put(tmp, 'proof', 'Verified')
    calls, installs = [], []
    def validator(name):
        def call(*args, **kw):
            calls.append([name, list(args), kw])
            errors = ['scripted ' + name] if mode == name else []
            if name == '_validate_required_runtime_evidence':
                return errors
            if name == '_validate_surface_contract':
                return errors, {} if mode == 'empty_surfaces' else surfaces, (
                    [{'surface': 'phase2_spec', 'reason': 'Deferred'}]
                    if mode == 'exceptions' else [])
            return errors, {'status': 'scripted'}
        return call
    def install(*args, **kw):
        installs.append([list(args), kw])
        return None if mode == 'install_none' else {'path': '.mir/bin/evaluator', 'sha256': 'pin'}
    out, err = io.StringIO(), io.StringIO()
    args = ['--project-root', str(tmp)] + (['--apply'] if apply else [])
    args += ['--json'] if as_json else []
    if mode == 'help':
        args = ['--help']
    elif mode == 'bad_arg':
        args = ['--bad']
    elif mode == 'missing_arg':
        args = ['--project-root']
    elif mode == 'native_arg':
        args += ['--native-evaluator', str(tmp / 'local-evaluator')]
    with contextlib.ExitStack() as stack:
        for name in VALIDATORS:
            stack.enter_context(mock.patch.object(M, name, side_effect=validator(name)))
        stack.enter_context(mock.patch.object(M, 'install_evaluator', side_effect=install))
        stack.enter_context(mock.patch.object(M, '_SOURCE_ROOT', tmp / 'source'))
        stack.enter_context(mock.patch.object(M.Path, 'cwd', return_value=tmp))
        stack.enter_context(mock.patch.dict(M.os.environ, {'HOME': str(tmp)}))
        if mode == 'digest_error':
            stack.enter_context(mock.patch.object(M, '_evidence_digests',
                                                  side_effect=M.AdoptionError('digest denied')))
        stack.enter_context(contextlib.redirect_stdout(out))
        stack.enter_context(contextlib.redirect_stderr(err))
        if mode == 'argv_none':
            stack.enter_context(mock.patch.object(M.sys, 'argv', ['mir', *args]))
        result = observe(lambda tmp: M.main(None if mode == 'argv_none' else args), tmp)
    receipts = {p.relative_to(tmp).as_posix(): p.read_text() for p in
                sorted(tmp.rglob('*')) if p.is_file() and 'receipt' in p.name}
    return dict(result=result, stdout=out.getvalue(), stderr=err.getvalue(), calls=calls,
                installs=installs, receipts=receipts)


for mode in ['plain', 'missing', 'success', 'failure', 'empty', 'blank', 'oserror',
             'newlines', 'no_newline', 'list', 'list_settings_error']:
    CASES[f'digest.{mode}'] = lambda tmp, m=mode: digest(tmp, m)
for mode in ['new', 'overwrite', 'replace_failure']:
    CASES[f'atomic.{mode}'] = lambda tmp, m=mode: atomic(tmp, m)
for as_json in [False, True]:
    for written in [False, True]:
        CASES[f'emit.json_{as_json}.written_{written}'] = (
            lambda tmp, j=as_json, w=written: emit(tmp, j, w))
for mode in ['pass', *VALIDATORS, 'missing', 'invalid', 'array', 'manifest_fields',
             'empty_surfaces', 'exceptions', 'not_applicable', 'content_workspace',
             'digest_error', 'install_none', 'native_arg', 'argv_none', 'help',
             'bad_arg', 'missing_arg', 'repository_owned']:
    for apply in [False, True]:
        CASES[f'main.scripted_validators.{mode}.apply_{apply}'] = (
            lambda tmp, m=mode, a=apply: main_case(tmp, m, a))
CASES['main.scripted_validators.pass.text'] = lambda tmp: main_case(tmp, 'pass', True, False)
CASES['main.scripted_validators.failure.text'] = (
    lambda tmp: main_case(tmp, '_validate_profile', True, False))
RECORDS = json.loads(FIXTURE.read_text()) if FIXTURE.exists() else {}


def test_every_case_has_a_frozen_record():
    assert sorted(RECORDS) == sorted(CASES)


@pytest.mark.parametrize('name', sorted(CASES))
def test_reference_matches_frozen_record(name, tmp_path):
    assert observe(CASES[name], tmp_path) == RECORDS[name]
