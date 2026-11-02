"""Capture local configuration behavior from the unchanged Python executor."""
from __future__ import annotations

import json
import os
import pathlib
import sys
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.mir_executor import dispatch, local_hooks, sweep  # noqa: E402

SCRATCH = pathlib.Path(os.environ['E2A_SCRATCH'])
DEFAULTS = {
    'input_limit_bytes': None, 'timeout_seconds_range': None, 'max_codex_attempts_cap': None,
    'codex_sandbox_default': 'workspace-write', 'child_env_filter': False,
    'child_env_extra_keys': [], 'require_review': False, 'verifiers': {},
    'verifier_env': 'inherit', 'artifact_retention_days': 30,
}

def capture(case):
    path = SCRATCH / 'config/mir-executor.local.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    if 'bytes' in case:
        path.write_bytes(bytes(case['bytes']))
    else:
        path.write_text(case['text'], encoding='utf-8')
    try:
        config = local_hooks.local_config(SCRATCH)
        op = case['operation']
        if op == 'defaults':
            result = {**DEFAULTS, **config}
        elif op == 'timeout':
            result = local_hooks.validate_timeout(SCRATCH, case.get('argument'))
        elif op == 'sandbox':
            dispatch.build_codex_mcp_runner(SCRATCH, 'fixture')
            result = config.get('codex_sandbox_default', 'workspace-write')
        elif op == 'verifier_env':
            with patch.object(dispatch, 'dispatch_env', return_value={}):
                with dispatch._verifier_env(SCRATCH):
                    result = config.get('verifier_env', 'inherit')
        elif op == 'retention':
            result = case.get('argument', config.get(
                'artifact_retention_days', sweep.ARTIFACT_RETENTION_DAYS,
            ))
            if isinstance(result, bool) or not isinstance(result, int) or result < 0:
                raise ValueError('artifact_retention_days must be a non-negative integer')
        elif op == 'verifiers':
            verifiers = config.get('verifiers', {})
            if set(['check']) - set(verifiers):
                raise ValueError('unknown-verifier:check')
            argv = verifiers['check']
            if (not isinstance(argv, list) or not argv
                    or any(not isinstance(v, str) or not v for v in argv)):
                raise ValueError('invalid-verifier:check')
            result = [argv]
        elif op == 'attempts':
            class ReachedWorktree(Exception):
                pass
            with patch.object(dispatch, 'create_dispatch_worktree', side_effect=ReachedWorktree):
                try:
                    dispatch.run_dispatch(
                        SCRATCH, 'fixture', codex_runner=None,
                        max_codex_attempts=case['argument'],
                    )
                except ReachedWorktree:
                    result = None
        elif op == 'input_size':
            from argparse import Namespace

            from tools.mir_executor import cli
            cli._resolve_execute_codex_args(Namespace(
                repo_root=SCRATCH, codex_args='[]' * case['argument'],
                codex_args_file=None, dispatch=False,
            ))
            result = None
        elif op == 'truthy':
            result = [bool(config.get('require_review', False)),
                      bool(config.get('child_env_filter', False))]
        return {'value': result}
    except (ValueError, TypeError, OverflowError) as error:
        result = {'error': type(error).__name__}
        if isinstance(error, json.JSONDecodeError):
            result['error'] = 'JSONDecodeError'
        result['message'] = str(error).replace(str(path), '<config>')
        return result

CASES = []
def add(name, operation, config, **kwargs):
    if 'argument' in kwargs:
        kwargs['argument_json'] = json.dumps(kwargs['argument'])
    CASES.append(dict(name=name, operation=operation, text=json.dumps(config), **kwargs))

add('empty-defaults', 'defaults', {})
add('unknown-fields-and-unvalidated-truthiness', 'defaults', {
    'extension': {'text': '\u03bb'}, 'child_env_filter': 'yes',
    'child_env_extra_keys': ['CUSTOM'], 'require_review': 1, 'max_codex_attempts_cap': 2,
})
for text in ('null', '[]', 'true', '1', '"text"', '{', '\ufeff{}'):
    CASES.append(dict(name='shape-'+repr(text), operation='defaults', text=text))
for text in ('', '[', '{"a":}', '{"a" 1}', '[1,]', '{"a":1,}', '1 2',
             '"abc', '"a\\x"', '"\\uXX00"', '"\\u123"', '"a\nb"', '{}\n x',
             '{"extension":"\u03bb", "a":}', '{"x":1e}', '{"x":1.}',
             '{"x":tru}', '{"x":-}', '{"x":[1 2]}', '{"x":"abc\\'):
    CASES.append(dict(name='syntax-'+repr(text), operation='defaults', text=text))
for data in (b'\xff', b'\xc3(', b'\xe1\x80A', b'\xc3', b'a\x80',
             b'\xf0\x80\x80\x80'):
    CASES.append(dict(name='unicode-'+data.hex(), operation='defaults', bytes=list(data)))
for bounds in (None, [1, 10], [2, 2], [10, 1], [0, 1], [True, 10], [1], 'bad', [1, '2']):
    for timeout in (None, True, 0, -1, 1, 2, 10, 11, '2'):
        add(f'timeout-{bounds!r}-{timeout!r}', 'timeout',
            {'timeout_seconds_range': bounds}, argument=timeout)
for sandbox in ('workspace-write', 'read-only', 'danger-full-access', 'invalid', None, False,
                [], {}):
    add(f'sandbox-{sandbox}', 'sandbox', {'codex_sandbox_default': sandbox})
for mode in ('inherit', 'invalid', None, False):
    add(f'verifier-env-{mode}', 'verifier_env', {'verifier_env': mode})
# isolated creates temporary storage, so capture its known successful mode using
# a scratch-local TemporaryDirectory destination.
with patch.dict('os.environ', {'TMPDIR': str(SCRATCH)}):
    import tempfile
    tempfile.tempdir = str(SCRATCH)
    add('verifier-env-isolated', 'verifier_env', {'verifier_env': 'isolated'})
for value in (0, 1, 30, -1, True, 1.5, None, '30'):
    add(f'retention-{value!r}', 'retention', {'artifact_retention_days': value})
add('retention-explicit-override', 'retention', {'artifact_retention_days': -1}, argument=7)
CASES.append(dict(name='retention-negative-zero', operation='retention',
                  text='{"artifact_retention_days":-0}'))
CASES.append(dict(name='default-negative-zero', operation='defaults',
                  text='{"extension":-0}'))
for argv in ([], ['true'], ['tool', 'two words'], [''], [True], 'true', None):
    add(f'verifier-{argv!r}', 'verifiers', {'verifiers': {'check': argv}})
add('unknown-verifier', 'verifiers', {})
for value in (None, 1, 1.5, True, [], ['other'], ['check'], 'check', [[]], [{}]):
    add('verifier-container-'+repr(value), 'verifiers', {'verifiers': value})
for token in ('NaN', 'Infinity', str(10**100)):
    CASES.append(dict(name='numeric-sandbox-'+token[:20], operation='sandbox',
                      text='{"codex_sandbox_default":'+token+'}'))
for token in ('NaN', 'Infinity', '-Infinity', '1e999', str(10**400)):
    CASES.append(dict(name='extended-timeout-'+token[:20], operation='timeout',
                      text='{"timeout_seconds_range":[1,'+token+']}'))
add('numeric-strings', 'defaults', {'extension': ['NaN', 'Infinity', '1e999', '\\"NaN']})
for text in ('{"unused":01e999}', '{"unused":1.e999}', '{"unused":-01}',
             '{"unused":NaNx}'):
    CASES.append(dict(name='invalid-numeric-'+text, operation='defaults', text=text))
for bounds, value in (([9007199254740992, 9007199254740992], 9007199254740993),
                      ([9007199254740993, 9007199254740994], 9007199254740992),
                      ([1, 18446744073709551616], 18446744073709551617)):
    add('precise-timeout-'+str(value), 'timeout',
        {'timeout_seconds_range': bounds}, argument=value)
for bounds, value in (([1e-7, 1e20], 1e21), ([1e-5, 1e16], 1e-7),
                      ([1.0, 2.0], 3), ([1e-4, 1e15], 1e16)):
    add('float-repr-'+repr(bounds), 'timeout',
        {'timeout_seconds_range': bounds}, argument=value)
for cap in (None, 1, 2, 0, -1, 1.5, True, False, 'bad', [], {}):
    for attempts in (0, 1, 2):
        add(f'attempts-{cap!r}-{attempts}', 'attempts',
            {'max_codex_attempts_cap': cap}, argument=attempts)
for limit in (None, 0, 1, 2, 4, True, False, -1, 1.5, 'bad'):
    add(f'input-limit-{limit!r}', 'input_size', {'input_limit_bytes': limit}, argument=1)
for value in (None, False, True, 0, 1, '', 'yes', [], [1], {}, {'a': 1}):
    add(f'truthy-{value!r}', 'truthy',
        {'require_review': value, 'child_env_filter': value})
for case in CASES:
    case['expected'] = capture(case)
pathlib.Path(__file__).with_name('executor_local.json').write_text(
    json.dumps(CASES, ensure_ascii=True, indent=2) + '\n',
)
print(f'captured {len(CASES)} Python local configuration cases')
