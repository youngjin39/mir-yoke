"""Closed brief controls and result artifacts match generic local-hook oracles."""
from __future__ import annotations

import json
import runpy
import sqlite3
from pathlib import Path

import pytest

P1 = runpy.run_path(str(Path(__file__).with_name('test_executor_target_policy_native_parity.py')))
SUPPORT = P1['SUPPORT']
DISPATCH = P1['PARITY']['DISPATCH']
binary = P1['binary']
ORACLE = (Path(__file__).parent / 'fixtures/executor_brief_policy_oracle.py').read_text()


def brief_payload():
    return {
        'version': 2, 'task_id': 'sample-task', 'slice_id': 'sample-slice',
        'target_agent': 'offline-agent', 'user_intent': 'Update the owned file.',
        'expanded_goal': 'Update code.txt with the delegated change.',
        'owned_scope': ['code.txt'], 'verification_ids': ['python-tests'],
        'stop_conditions': ['Stop if scope changes.'],
        'resume_state_ref': 'tasks/dispatch/sample-task/sample-slice.json',
        'source_refs': {'task_spec': 'tasks/spec.json', 'phase': 'tasks/phase.json'},
    }


def seed(root, bridge, *, limit=None):
    launcher, environment, args = DISPATCH['seed'](root, 'success', SUPPORT)
    for flag in ('--allow-path', '--verify-cmd'):
        index = args.index(flag)
        del args[index:index + 2]
    config_path = root / 'config/mir-executor.local.json'
    config = json.loads(config_path.read_text())
    config['verifiers']['python-tests'] = config['verifiers'].pop('offline')
    if bridge:
        (root / 'tools/mir_executor/local.py').write_text(ORACLE)
        if limit is not None:
            config['input_limit_bytes'] = limit
    else:
        (root / 'tools/mir_executor/local.py').unlink()
        config['native_policy'] = {
            'version': 1, 'brief_profile': {'name': 'closed_verifier_v2'},
            'brief_controls': {'mode': 'brief_owned'},
            'result_policy': {'provider_output': 'sanitize_persisted_text',
                              'attempt_artifact': 'result_json'},
        }
        if limit is not None:
            config['native_policy']['brief_profile']['input_limit_bytes'] = limit
    config_path.write_text(json.dumps(config))
    (root / 'brief.json').write_text(json.dumps(brief_payload()))
    return launcher, environment, args


def snapshot(root, launcher, result):
    value = DISPATCH['snapshot'](root, result)
    value.pop('git_status')
    for stream in ('stdout', 'stderr'):
        value[stream + '_bytes'] = P1['stream_bytes'](
            value[stream].encode(), root, launcher)
    value['artifact_modes'] = sorted(
        path.stat().st_mode & 0o777
        for path in (root / 'artifacts').rglob('result.json'))
    return value


CASES = ['v2', 'v1', 'prompt', 'prompt_file', 'allow', 'verify', 'missing', 'extra',
         'bad_verifier', 'no_verifiers', 'commands', 'bad_resume_ref', 'bad_plan',
         'resume_equal', 'resume_different', 'resume_empty',
         'resume_verify_different', 'resume_verify_empty']


@pytest.mark.parametrize('case', CASES)
def test_brief_profile_matches_bridge(binary, tmp_path, case):
    values = []
    for bridge in (True, False):
        root = tmp_path / ('bridge' if bridge else 'native')
        launcher, environment, args = seed(root, bridge)
        payload = brief_payload()
        if case == 'v1':
            payload.update(version=1, verification_ids=[], verification_commands=['check'])
        elif case == 'missing':
            payload.pop('user_intent')
        elif case == 'extra':
            payload['unexpected'] = True
        elif case == 'bad_verifier':
            payload['verification_ids'] = ['unregistered']
        elif case == 'no_verifiers':
            payload['verification_ids'] = []
        elif case == 'commands':
            payload['verification_commands'] = ['check']
        elif case == 'bad_resume_ref':
            payload['resume_state_ref'] = 'tasks/dispatch/other.json'
        elif case == 'bad_plan':
            payload['source_refs']['plan'] = 'tasks/other.md'
        (root / 'brief.json').write_text(json.dumps(payload))
        if case == 'prompt':
            args += ['--codex-args', 'exec explicit prompt']
        elif case == 'prompt_file':
            (root / 'prompt.json').write_text('["exec", "explicit prompt"]')
            args += ['--codex-args-file', str(root / 'prompt.json')]
        elif case == 'allow':
            args += ['--allow-path', 'code.txt']
        elif case == 'verify':
            args += ['--verify-cmd', 'python-tests']
        elif case.startswith('resume_'):
            args = DISPATCH['resume'](root, 'current')
            with sqlite3.connect(root / 'tasks/jobs.db') as connection:
                options = json.loads(connection.execute(
                    'SELECT dispatch_options_json FROM jobs').fetchone()[0])
                options['verify_cmds'] = ['python-tests']
                if case == 'resume_different':
                    options['allow_paths'] = ['other.txt']
                elif case == 'resume_empty':
                    options['allow_paths'] = []
                elif case == 'resume_verify_different':
                    options['verify_cmds'] = ['ruff']
                elif case == 'resume_verify_empty':
                    options['verify_cmds'] = []
                connection.execute('UPDATE jobs SET dispatch_options_json=?',
                                   (json.dumps(options),))
        result = P1['invoke'](binary, root, environment, args)
        values.append(snapshot(root, launcher, result))
        assert result.returncode == (0 if case in ('v2', 'resume_equal') else 1), values[-1]
    assert values[0] == values[1], values


def test_explicit_raw_brief_limit_stops_before_provider(binary, tmp_path):
    # The optional raw-file cap is declarative; the historical hook has no cap.
    root = tmp_path / 'native'
    _, environment, args = seed(root, False, limit=16)
    result = P1['invoke'](binary, root, environment, args)
    assert result.returncode == 1
    assert result.stderr
    assert not (root / 'provider-methods').exists()
    assert not (root / 'tasks/jobs.db').exists()


@pytest.mark.parametrize('hook', ['validate_brief', 'pre_execute',
                                 'after_provider_call', 'after_run'])
def test_native_owned_hooks_reject_local_exports_before_import(binary, tmp_path, hook):
    root = tmp_path / 'native'
    _, environment, args = seed(root, False)
    (root / 'tools/mir_executor/local.py').write_text(
        'from pathlib import Path\n'
        'Path(__file__).resolve().parents[2].joinpath("unexpected-import").touch()\n'
        'raise RuntimeError("unexpected import")\n'
        f'def {hook}(*args): pass\n')
    result = P1['invoke'](binary, root, environment, args)
    assert result.returncode == 1
    assert hook.encode() in result.stderr
    assert b'native local policy configuration error' in result.stderr
    assert b'unexpected import' not in result.stderr
    assert not (root / 'unexpected-import').exists()
    assert not (root / 'provider-methods').exists()
    assert not (root / 'tasks/jobs.db').exists()


@pytest.mark.parametrize('case', ['redaction', 'bounded'])
def test_result_policy_matches_bridge(binary, tmp_path, case):
    values = []
    for bridge in (True, False):
        root = tmp_path / ('bridge' if bridge else 'native')
        launcher, environment, args = seed(root, bridge)
        text = ('authorization: Bearer synthetic-token-value\napi_key=synthetic-secret-value'
                if case == 'redaction' else '\u00e9' * 17000)
        source = DISPATCH['SERVER'].replace(
            "text = 'offline dispatch complete'", f'text = {text!r}')
        launcher.write_text('#!/usr/bin/env python3\n' + source)
        result = P1['invoke'](binary, root, environment, args)
        value = snapshot(root, launcher, result)
        assert result.returncode == 0, value
        artifacts = list((root / 'artifacts').rglob('result.json'))
        assert len(artifacts) == 1, value
        payload = json.loads(artifacts[0].read_text())
        assert artifacts[0].stat().st_mode & 0o777 == 0o600
        if case == 'bounded':
            assert len(payload['stdout']) == 16384
            assert payload['stdout'].endswith('\n...[truncated]...\n')
        else:
            assert 'synthetic-token-value' not in payload['stdout']
        values.append(value)
    assert values[0] == values[1], values
