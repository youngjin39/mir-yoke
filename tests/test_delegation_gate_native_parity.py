"""Byte parity against Yoke's Bash reference, with jq present and native absent."""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CRATE = ROOT / 'native/handoff-packet'
CASES = json.loads((CRATE / 'tests/fixtures/delegation-gate.json').read_text())
BASH_NUL_WARNING = re.compile(
    rb'^[^\n]*: line \d+: warning: command substitution: ignored null byte in input\n', re.M)


@pytest.fixture(scope='module')
def gate():
    subprocess.run(['cargo', 'build', '--offline', '--locked', '--bin', 'delegation-gate'],
                   cwd=CRATE, check=True)
    target = Path(os.environ.get('CARGO_TARGET_DIR', CRATE / 'target'))
    if not target.is_absolute():
        target = CRATE / target
    return target / 'debug' / ('delegation-gate.exe' if os.name == 'nt' else 'delegation-gate')


@pytest.mark.skipif(shutil.which('bash') is None or shutil.which('jq') is None
                    or os.name == 'nt', reason='Bash reference requires jq')
@pytest.mark.parametrize('case', CASES, ids=lambda case: case['name'])
def test_gate_parity(gate, tmp_path, case):
    config = tmp_path / 'config'
    config.mkdir()
    if case['mode'] is not None and not case.get('no_policy'):
        mode = case['mode']
        source = case.get('source', 'lock')
        path, data = (('model-routing.lock.json', {'policy': {'delegation': {'mode': mode}}})
                      if source == 'lock' else ('sub-agent-policy.json',
                          {'mode': mode} if source == 'flat' else {'delegation': {'mode': mode}}))
        (config / path).write_text(json.dumps(data))
    if 'local_mode' in case:
        (config / 'sub-agent-policy.json').write_text(json.dumps({'mode': case['local_mode']}))
    lock = config / 'model-routing.lock.json'
    if case.get('raw_policy') is not None:
        lock.write_text(case['raw_policy'])
    if case.get('broken_policy'):
        lock.unlink()
        lock.symlink_to(tmp_path / 'absent')
    if case.get('directory_lock'):
        lock.unlink()
        lock.mkdir()
    env = {**os.environ, 'CLAUDE_PROJECT_DIR': str(tmp_path),
           'MIR_CODEX_MAIN': '1' if case.get('main') else '0',
           'MIR_R3_FALLBACK': case.get('r3', '0')}
    env.pop('MIR_SUB_AGENT_POLICY', None)
    if any(k in case for k in ('overlay', 'raw_overlay', 'missing_overlay')):
        overlay = tmp_path / 'overlay.json'
        env['MIR_SUB_AGENT_POLICY'] = str(overlay)
        if 'overlay' in case:
            overlay.write_text(json.dumps(case['overlay']))
        elif 'raw_overlay' in case:
            overlay.write_text(case['raw_overlay'])
    payload = case.get('raw', json.dumps(case['payload']))
    assert not (tmp_path / '.mir/bin').exists()  # Force the unchanged reference body.
    commands = ([str(gate)], ['bash', str(ROOT / '.claude/hooks/sub-agent-policy-gate.sh')])
    native, reference = [subprocess.run(command, input=payload.encode(), capture_output=True,
                                       env=env) for command in commands]
    assert reference.returncode == case['code']
    # Bash 4.4+ warns about NUL bytes it drops: interpreter noise, not gate output.
    reference_stderr = BASH_NUL_WARNING.sub(b'', reference.stderr)
    assert (native.returncode, native.stdout, native.stderr) == (
        reference.returncode, reference.stdout, reference_stderr)


@pytest.mark.skipif(os.name == 'nt', reason='POSIX wrapper')
@pytest.mark.parametrize('kind', ['executable', 'exe', 'symlink', 'nonexecutable', 'directory'])
def test_wrapper_dispatch(gate, tmp_path, kind):
    binary = tmp_path / '.mir/bin/delegation-gate'
    binary.parent.mkdir(parents=True)
    marker = b'#!/bin/sh\ncat >&2\nexit 7\n'
    if kind == 'directory':
        binary.mkdir()
    elif kind == 'symlink':
        target = tmp_path / 'marker'
        target.write_bytes(marker)
        target.chmod(0o755)
        binary.symlink_to(target)
    else:
        if kind == 'exe':
            binary = binary.with_suffix('.exe')
        binary.write_bytes(marker)
        binary.chmod(0o644 if kind == 'nonexecutable' else 0o755)
    payload = b'{"tool_name":"Read"}'
    result = subprocess.run(['bash', str(ROOT / '.claude/hooks/sub-agent-policy-gate.sh')],
                            input=payload, capture_output=True,
                            env={**os.environ, 'CLAUDE_PROJECT_DIR': str(tmp_path)})
    if kind in ('executable', 'exe'):
        assert (result.returncode, result.stderr) == (7, payload)
    else:
        assert (result.returncode, result.stderr) == (0, b'')


@pytest.mark.skipif(os.name == 'nt', reason='Bash reference dependency')
def test_native_needs_no_jq_but_reference_blocks_without_it(gate, tmp_path):
    bindir = tmp_path / 'path'
    bindir.mkdir()
    for name in ('dirname', 'cat'):
        (bindir / name).symlink_to(shutil.which(name))
    env = {**os.environ, 'PATH': str(bindir), 'CLAUDE_PROJECT_DIR': str(tmp_path),
           'MIR_R3_FALLBACK': '0'}
    payload = b'{"tool_name":"Read"}'
    native = subprocess.run([str(gate)], input=payload, capture_output=True, env=env)
    reference = subprocess.run([shutil.which('bash'),
                                str(ROOT / '.claude/hooks/sub-agent-policy-gate.sh')],
                               input=payload, capture_output=True, env=env)
    assert (native.returncode, native.stderr) == (0, b'')
    assert (reference.returncode, reference.stderr) == (
        2, b'[PreToolUse BLOCK] jq is required for PreToolUse parsing\n')
