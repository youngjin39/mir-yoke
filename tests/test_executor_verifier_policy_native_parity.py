"""Compare exact verifier aliases with Python local hooks through the bridge."""
from __future__ import annotations

import json
import runpy
import shlex
import sys
from pathlib import Path

import pytest

P1 = runpy.run_path(str(Path(__file__).with_name('test_executor_target_policy_native_parity.py')))
SUPPORT = P1['SUPPORT']
binary = P1['binary']
ORACLE = r'''
import json, pathlib, shlex
def pre_execute(args, repo_root):
    if getattr(args, 'family', None) == 'refused':
        raise ValueError('Family refused')
    commands = getattr(args, 'verify_cmds', None)
    if not commands:
        return
    config = json.loads((pathlib.Path(repo_root) / 'config/mir-executor.local.json').read_text())
    verifiers = config.get('verifiers', {})
    by_argv = {tuple(argv): key for key, argv in verifiers.items()}
    mapped = []
    for command in commands:
        if command not in verifiers:
            try:
                command = by_argv.get(tuple(shlex.split(command)), command)
            except ValueError:
                pass
        mapped.append(command)
    args.verify_cmds = mapped
'''


@pytest.mark.parametrize('configuration_root', ['initial', 'target'])
@pytest.mark.parametrize('style', ['loop', 'comprehension', 'helper'])
@pytest.mark.parametrize('command', [None, 'stable', "check 'two words'", 'check two words',
                                     'check "unterminated', '', ' # literal',
                                     'check \u00e9', 'check ""', 'check', 'duplicate'])
@pytest.mark.parametrize('family', [None, 'sample', 'refused'])
def test_verifier_aliases_match_bridge(
        binary, tmp_path, command, family, style, configuration_root):
    snapshots = []
    for bridge in (True, False):
        root = tmp_path / ('bridge' if bridge else 'native')
        launcher = SUPPORT['seed'](root, 'success')
        config = {'verifiers': {'stable': ['check', 'two words'],
                                'z-first': ['check'], 'a-last': ['check'],
                                'duplicate': ['other']}}
        if not bridge:
            config['native_policy'] = {
                'version': 1,
                'target_admission': {'family': {
                    'mode': 'alias_map', 'aliases': {'sample': '.'},
                    'unknown': {'kind': 'ValueError', 'message': 'Family refused'}}},
                'verifier_aliases': {'configuration_root': configuration_root}}
        (root / 'config').mkdir(exist_ok=True)
        (root / 'config/mir-executor.local.json').write_text(json.dumps(config))
        local = root / 'tools/mir_executor/local.py'
        if bridge:
            oracle = ORACLE
            if style == 'comprehension':
                start = oracle.index('    mapped = []')
                oracle = oracle[:start] + """
    def argv(command):
        try:
            return tuple(shlex.split(command))
        except ValueError:
            return None
    args.verify_cmds = [c if c in verifiers else by_argv.get(argv(c), c) for c in commands]
"""
            elif style == 'helper':
                oracle = oracle.replace('def pre_execute(args, repo_root):',
                                        'def map_commands(args, repo_root):')
                oracle += '\ndef pre_execute(args, repo_root):\n    map_commands(args, repo_root)\n'
            local.write_text(oracle)
        else:
            local.unlink(missing_ok=True)
        args = SUPPORT['argv']('background_success')
        if command is not None:
            args += ['--verify-cmd', command]
        if family:
            args += ['--family', family]
        result = P1['invoke'](binary, root, SUPPORT['environment'](root, 'success', launcher), args)
        snapshot = SUPPORT['snapshot'](root, launcher, result)
        for stream in ('stdout', 'stderr'):
            snapshot[stream + '_bytes'] = P1['stream_bytes'](
                getattr(result, stream), root, launcher)
        snapshot['provider_started'] = (root / 'provider-started').exists()
        snapshots.append(snapshot)
    assert snapshots[0] == snapshots[1], snapshots


@pytest.mark.parametrize('section', [None, True, {}, {'configuration_root': 'unknown'},
                                    {'configuration_root': 'initial', 'extra': True}])
def test_strict_verifier_section(binary, tmp_path, section):
    root = tmp_path / 'invalid'
    launcher = SUPPORT['seed'](root, 'success')
    (root / 'config').mkdir(exist_ok=True)
    (root / 'config/mir-executor.local.json').write_text(json.dumps({'native_policy': {
        'version': 1, 'target_admission': {}, 'verifier_aliases': section}}))
    result = P1['invoke'](binary, root, SUPPORT['environment'](root, 'success', launcher),
                          SUPPORT['argv']('success'))
    assert result.returncode == 1
    assert b'native local policy configuration error' in result.stderr
    assert not (root / 'provider-started').exists()


def test_verifier_section_rejects_duplicate_hook_before_import(binary, tmp_path):
    root = tmp_path / 'duplicate'
    launcher = SUPPORT['seed'](root, 'success')
    (root / 'config').mkdir(exist_ok=True)
    (root / 'config/mir-executor.local.json').write_text(json.dumps({'native_policy': {
        'version': 1, 'target_admission': {},
        'verifier_aliases': {'configuration_root': 'initial'}}}))
    (root / 'tools/mir_executor/local.py').write_text(
        'raise RuntimeError("unexpected import")\ndef pre_execute(args, root): pass\n')
    result = P1['invoke'](binary, root, SUPPORT['environment'](root, 'success', launcher),
                          SUPPORT['argv']('success'))
    assert result.returncode == 1
    assert b'pre_execute' in result.stderr
    assert b'unexpected import' not in result.stderr
    assert not (root / 'provider-started').exists()


@pytest.mark.parametrize('command', ['alias', 'offline', 'unregistered', 'unterminated "'])
def test_mapping_reaches_dispatch_merge_gate(binary, tmp_path, command):
    dispatch = P1['PARITY']['DISPATCH']
    snapshots = []
    for bridge in (True, False):
        root = tmp_path / ('bridge' if bridge else 'native')
        launcher, environment, args = dispatch['seed'](root, 'success', SUPPORT)
        path = root / 'config/mir-executor.local.json'
        config = json.loads(path.read_text())
        if not bridge:
            config['native_policy'] = {'version': 1, 'target_admission': {},
                                       'verifier_aliases': {'configuration_root': 'initial'}}
        path.write_text(json.dumps(config))
        local = root / 'tools/mir_executor/local.py'
        if bridge:
            local.write_text(ORACLE)
        else:
            local.unlink()
        args[args.index('--verify-cmd') + 1] = (
            shlex.join([sys.executable, '-c', 'pass']) if command == 'alias' else command)
        result = P1['invoke'](binary, root, environment, args)
        snapshot = dispatch['snapshot'](root, result)
        snapshot.pop('git_status')
        # These streams contain worktree IDs/commits; apply the same identity
        # masks as dispatch snapshots, preserving all whitespace bytes.
        for stream in ('stdout', 'stderr'):
            snapshot[stream + '_bytes'] = snapshot[stream].encode()
        snapshots.append(snapshot)
        assert result.returncode == (0 if command in ('alias', 'offline') else 1), snapshot
    assert snapshots[0] == snapshots[1], snapshots
