"""Pinned owner hooks compose with native admission through initial/resume CLI."""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import runpy
import shlex
import sqlite3
import sys
from pathlib import Path

import pytest

HUB = runpy.run_path(str(Path(__file__).with_name('test_executor_hub_native_parity.py')))
P1, DISPATCH, SUPPORT = HUB['P1'], HUB['DISPATCH'], HUB['SUPPORT']
binary = HUB['binary']
GOLDEN = json.loads((Path(__file__).parent / 'fixtures/executor_quiet_resume.json').read_text())


def seed(root, bridge):
    launcher, environment, args = DISPATCH['seed'](root, 'success', SUPPORT)
    config_path = root / 'config/mir-executor.local.json'
    config = json.loads(config_path.read_text())
    config['verifiers']['alias-last'] = config['verifiers']['offline']
    if bridge:
        (root / 'tools/mir_executor/local.py').write_text(GOLDEN['oracle_source'])
    else:
        (root / 'tools/mir_executor/local.py').unlink()
        config['native_policy'] = {
            'version': 1, 'brief_profile': {'name': 'base_v1'},
            'brief_controls': {'mode': 'resume_fill'},
            'verifier_aliases': {'configuration_root': 'initial'},
        }
    config_path.write_text(json.dumps(config))
    (root / 'brief.json').write_text(json.dumps(HUB['GENERATOR']['brief_payload']()))
    return launcher, environment, args


def test_oracle_pins():
    assert GOLDEN['sha256'] == {
        'local': 'b161a03637289a6a3a4c1e3b0e6bf15795551f572673b18c2c34aab52525ab54',
        'contracts': '4261212c8df5177646513775d92c286abb6dd1afb3000a1b1254cd1cac4e22fa',
        'loader': '8171f3ea0f41a84adcde60858d80a1c156a1ecb23ac58602275e0eff7edc80af',
    }


@pytest.mark.parametrize('case', GOLDEN['cases'], ids=lambda case: case['name'])
def test_captured_owner(tmp_path, monkeypatch, case):
    monkeypatch.setitem(sys.modules, 'mir.core.conductor.dispatch_brief', None)
    namespace = {}
    exec(GOLDEN['oracle_source'], namespace)
    namespace['DispatchBrief'].model_rebuild(_types_namespace=namespace)
    (tmp_path / 'config').mkdir()
    (tmp_path / 'config/mir-executor.local.json').write_text(
        json.dumps({'verifiers': GOLDEN['verifiers']}))
    if not case['missing']:
        (tmp_path / 'brief.json').write_text(case['raw'])
    root = json.dumps(str(tmp_path))[1:-1]  # JSON string content; Windows paths carry backslashes.
    args = argparse.Namespace(**json.loads(json.dumps(case['args']).replace('<root>', root)))
    stderr = io.StringIO()
    error = {}
    with contextlib.redirect_stderr(stderr):
        try:
            namespace['pre_execute'](args, tmp_path)
        except (Exception, SystemExit) as caught:
            error = dict(kind=type(caught).__name__, message=str(caught))
    assert error == {key: case[key] for key in ('kind', 'message') if key in case}
    repr_root = str(tmp_path).replace('\\', '\\\\')  # Python repr doubles backslashes.
    assert stderr.getvalue().replace(repr_root, '<root>').replace(
        str(tmp_path), '<root>') == case['stderr']
    assert json.loads(json.dumps(vars(args)).replace(root, '<root>')) == case['patch']
    assert namespace['_REQUESTED_BACKEND'].get() == case['requested_backend']


CLI_CASES = [case for case in GOLDEN['cases'] if case['name'].endswith('absent-resume')]
CLI_CASES += [case for case in GOLDEN['cases'] if case['name'].startswith('concrete-')]


@pytest.mark.parametrize('case', CLI_CASES, ids=lambda case: case['name'])
def test_resume_cli_matches_owner(binary, tmp_path, case):
    values = []
    for bridge in (True, False):
        root = tmp_path / ('bridge' if bridge else 'native')
        launcher, environment, args = seed(root, bridge)
        (root / 'brief.json').write_text(case['raw'])
        if case['name'].endswith('resume'):
            args = DISPATCH['resume'](root, 'current')
            with sqlite3.connect(root / 'tasks/jobs.db') as connection:
                options = json.loads(connection.execute(
                    'SELECT dispatch_options_json FROM jobs').fetchone()[0])
                for key in ('allow_paths', 'verify_cmds'):
                    if key in case['args']:
                        options[key] = case['args'][key]
                    else:
                        options.pop(key, None)
                connection.execute('UPDATE jobs SET dispatch_options_json=?',
                                   (json.dumps(options),))
        else:
            for flag, key in (('--allow-path', 'allow_paths'), ('--verify-cmd', 'verify_cmds')):
                index = args.index(flag)
                del args[index:index + 2]
                for value in case['args'].get(key, []):
                    args += [flag, value]
        if case['missing']:
            (root / 'brief.json').unlink()
        result = P1['invoke'](binary, root, environment, args)
        values.append(HUB['snapshot'](root, launcher, result, True))
    assert values[0] == values[1], values


@pytest.mark.parametrize('hook', ['validate_brief', 'pre_execute'])
def test_duplicate_exports_fail_closed(binary, tmp_path, hook):
    root = tmp_path / 'native'
    _, environment, args = seed(root, False)
    (root / 'tools/mir_executor/local.py').write_text(
        'from pathlib import Path\n'
        '(Path(__file__).resolve().parents[2] / "unexpected-import").touch()\n'
        f'def {hook}(*args): pass\n')
    result = P1['invoke'](binary, root, environment, args)
    assert result.returncode == 1
    assert hook.encode() in result.stderr
    for path in ('unexpected-import', 'provider-methods', 'tasks/jobs.db'):
        assert not (root / path).exists()


def test_undeclared_retains_python_pre_execute(binary, tmp_path):
    root = tmp_path / 'python'
    _, environment, args = seed(root, True)
    with (root / 'tools/mir_executor/local.py').open('a') as source:
        source.write('\ndef pre_execute(args, root):\n    raise ValueError("python-owned")\n')
    result = P1['invoke'](binary, root, environment, args)
    assert result.returncode == 1
    assert b'python-owned' in result.stderr
    assert not (root / 'provider-methods').exists()


@pytest.mark.parametrize('mode', ['explicit', 'restored'])
def test_requested_backend_composes_with_native_route(binary, tmp_path, mode):
    agent = runpy.run_path(str(Path(__file__).with_name('test_executor_agent_native_parity.py')))
    values = []
    for bridge in (True, False):
        root = tmp_path / ('bridge' if bridge else 'native')
        environment, args = agent['seed_agent'](root, 'claude')
        config_path = root / 'config/mir-executor.local.json'
        config = json.loads(config_path.read_text())
        route = dict(source='codex', criteria='declared', backend='policy',
                     sandbox='read_only', invalid_lock='empty', requested_backend=True)
        local = root / 'tools/mir_executor/local.py'
        if bridge:
            local.write_text(GOLDEN['oracle_source'])
        else:
            local.unlink()
            config['native_policy'] = dict(version=1, brief_profile={'name': 'base_v1'},
                brief_controls={'mode': 'resume_fill'},
                verifier_aliases={'configuration_root': 'initial'}, agent_route=route)
        config_path.write_text(json.dumps(config))
        (root / 'brief.json').write_text(json.dumps(HUB['GENERATOR']['brief_payload']()))
        generated = root / '.codex/agents/offline-agent.toml'
        generated.parent.mkdir(parents=True, exist_ok=True)
        generated.write_text('developer_instructions = "Offline route instructions."\n'
                             'sandbox_mode = "workspace-write"\n')
        (root / 'offline-policy.json').write_text(json.dumps(
            {'mode': 'user_command_priority', 'default_backend': 'codex'}))
        if mode == 'explicit':
            args += ['--execution-backend', 'claude']
        else:
            args = DISPATCH['resume'](root, 'current')
            with sqlite3.connect(root / 'tasks/jobs.db') as connection:
                saved = json.loads(connection.execute(
                    'SELECT dispatch_options_json FROM jobs').fetchone()[0])
                saved.update(execution_backend='claude', allow_paths=[], verify_cmds=[])
                connection.execute('UPDATE jobs SET execution_backend=?, dispatch_options_json=?',
                                   ('claude', json.dumps(saved)))
        result = P1['invoke'](binary, root, environment, args)
        assert result.returncode == 0, (result.stdout, result.stderr)
        assert (root / 'provider-arguments').exists()
        values.append(HUB['snapshot'](root, Path(environment['CODEX_BIN']), result, True))
    assert values[0] == values[1], values


@pytest.mark.parametrize('controls', ['absent', 'empty', 'supplied'])
def test_resume_fills_and_maps_commands_before_success(binary, tmp_path, controls):
    values = []
    for bridge in (True, False):
        root = tmp_path / ('bridge' if bridge else 'native')
        launcher, environment, _ = seed(root, bridge)
        payload = HUB['GENERATOR']['brief_payload']()
        payload['owned_scope'] = ['code.txt', 'code.txt']
        payload['verification_commands'] = [shlex.join([sys.executable, '-c', 'pass'])]
        (root / 'brief.json').write_text(json.dumps(payload))
        args = DISPATCH['resume'](root, 'current')
        with sqlite3.connect(root / 'tasks/jobs.db') as connection:
            saved = json.loads(connection.execute(
                'SELECT dispatch_options_json FROM jobs').fetchone()[0])
            for key in ('allow_paths', 'verify_cmds'):
                if controls == 'absent':
                    saved.pop(key, None)
                elif controls == 'empty':
                    saved[key] = []
            connection.execute('UPDATE jobs SET dispatch_options_json=?', (json.dumps(saved),))
        result = P1['invoke'](binary, root, environment, args)
        assert result.returncode == 0, (result.stdout, result.stderr)
        # The original resume row retains its saved controls. Compare all old
        # and new job records and require a successful provider/merge instead.
        assert (root / 'provider-methods').exists()
        assert (root / 'code.txt').read_text() != 'initial\n'
        values.append(HUB['snapshot'](root, launcher, result, True))
    assert values[0] == values[1], values
