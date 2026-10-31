"""Execute shipped hook commands through POSIX and Windows session shells."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.test_handoff_packet_native_parity import binary as binary
from tests.test_handoff_packet_native_parity import stop_payload
from tests.test_handoff_packet_native_parity import stop_repository as stop_repository
from tests.test_mechanical_handoff import HANDLER_PYTHON, PROMPT, packet

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'plugins/mir-lifecycle-hooks'
pytestmark = [
    pytest.mark.skipif(shutil.which('cargo') is None, reason='cargo unavailable'),
]


@pytest.mark.skipif(os.name == 'nt', reason='POSIX hook shell contract')
@pytest.mark.parametrize('event', ['SessionStart', 'UserPromptSubmit', 'PreToolUse', 'Stop'])
@pytest.mark.parametrize('mode', ['absent', 'present', 'non-executable', 'exe'])
@pytest.mark.parametrize('deny', [False, True], ids=['allow', 'deny'])
def test_real_hook_command(binary, stop_repository, event, mode, deny):
    repo, _ = stop_repository
    plugin = repo / 'plugin with spaces'
    shutil.copytree(PLUGIN, plugin)
    name = 'runtime-continuity' if event == 'SessionStart' else 'handoff-packet'
    script = (plugin / 'hooks/runtime_continuity.py' if event == 'SessionStart' else
              plugin / 'skills/runtime-continuity/scripts/handoff_packet.py')
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(plugin), MIR_HANDOFF_PYTHON=HANDLER_PYTHON,
               PYTHONUTF8='1')
    # Resolve the same interpreter as the reference even when python3 differs on PATH.
    shim = repo / 'shim'
    shim.mkdir()
    (shim / 'python3').symlink_to(HANDLER_PYTHON)
    env['PATH'] = str(shim) + os.pathsep + env['PATH']
    prompt = PROMPT + '\nNo commands.' if deny else 'Inspect the repository. \u00e9 \ud55c'
    payload = json.dumps({'hook_event_name': event, 'cwd': str(repo), 'prompt': prompt,
                          'tool_name': 'Bash', 'tool_input': {'command': 'pwd'}}).encode()
    if event == 'Stop':
        body = packet() + '\nHEAD: abcdef123' if deny else 'Done.'
        payload = stop_payload(repo, prompt, body)
    reference = subprocess.run([HANDLER_PYTHON, str(script)], input=payload,
                               capture_output=True, env=env, timeout=15)
    if event == 'PreToolUse':
        assert reference.returncode == (2 if deny else 0)
    if event == 'Stop' and deny:
        assert json.loads(reference.stdout)['decision'] == 'block'
    if mode != 'absent':
        destination = plugin / 'bin' / (name + ('.exe' if mode == 'exe' else ''))
        destination.parent.mkdir()
        shutil.copyfile(binary.with_name(name), destination)
        destination.chmod(0o644 if mode == 'non-executable' else 0o755)
    if mode in {'present', 'exe'}:
        # A selected native deny must never fall through to the Python reference.
        script.write_text('raise SystemExit("Python reference unexpectedly executed")\n')
    command = json.loads((plugin / 'hooks/hooks.json').read_text())['hooks'][event][0]['hooks'][0]
    assert command['timeout'] == (2 if event == 'SessionStart' else 8)
    for shell in ['sh', 'bash']:
        result = subprocess.run([shell, '-c', command['command']], input=payload,
                                capture_output=True, env=env, timeout=15)
        assert (result.stdout, result.stderr, result.returncode) == (
            reference.stdout, reference.stderr, reference.returncode)


@pytest.mark.skipif(os.name != 'nt', reason='Codex Windows session-shell contract')
@pytest.mark.parametrize('event', ['SessionStart', 'UserPromptSubmit', 'PreToolUse', 'Stop'])
@pytest.mark.parametrize('mode', ['absent', 'present'])
@pytest.mark.parametrize('deny', [False, True], ids=['allow', 'deny'])
@pytest.mark.parametrize('shell', ['pwsh', 'powershell'])
def test_codex_windows_hook_command(binary, stop_repository, event, mode, deny, shell):
    repo, _ = stop_repository
    plugin = repo / 'plugin with spaces'
    shutil.copytree(PLUGIN, plugin)
    name = 'runtime-continuity' if event == 'SessionStart' else 'handoff-packet'
    script = (plugin / 'hooks/runtime_continuity.py' if event == 'SessionStart' else
              plugin / 'skills/runtime-continuity/scripts/handoff_packet.py')
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(plugin), MIR_HANDOFF_PYTHON=HANDLER_PYTHON,
               PYTHONUTF8='1')
    # Resolve the same interpreter as the reference even when python3 differs on PATH.
    shim = repo / 'shim'
    shim.mkdir()
    python_home = Path(sys.base_prefix)
    shutil.copyfile(python_home / 'python.exe', shim / 'python3.exe')
    for dll in python_home.glob('python*.dll'):
        shutil.copyfile(dll, shim / dll.name)
    env['PYTHONHOME'] = str(python_home)
    env['PATH'] = str(shim) + os.pathsep + env['PATH']
    prompt = PROMPT + '\nNo commands.' if deny else 'Inspect the repository. \u00e9 \ud55c'
    payload = json.dumps({'hook_event_name': event, 'cwd': str(repo), 'prompt': prompt,
                          'tool_name': 'Bash', 'tool_input': {'command': 'pwd'}}).encode()
    if event == 'Stop':
        body = packet() + '\nHEAD: abcdef123' if deny else 'Done.'
        payload = stop_payload(repo, prompt, body)
    reference = subprocess.run([HANDLER_PYTHON, str(script)], input=payload,
                               capture_output=True, env=env, timeout=15)
    if event == 'PreToolUse':
        assert reference.returncode == (2 if deny else 0)
    if event == 'Stop' and deny:
        assert json.loads(reference.stdout)['decision'] == 'block'
    if mode != 'absent':
        destination = plugin / 'bin' / (name + '.exe')
        destination.parent.mkdir()
        shutil.copyfile(binary.with_name(name + '.exe'), destination)
        destination.chmod(0o644 if mode == 'non-executable' else 0o755)
    if mode in {'present', 'exe'}:
        # A selected native deny must never fall through to the Python reference.
        script.write_text('raise SystemExit("Python reference unexpectedly executed")\n')
    command = json.loads((plugin / 'hooks/hooks.json').read_text())['hooks'][event][0]['hooks'][0]
    assert command['timeout'] == (2 if event == 'SessionStart' else 8)
    result = subprocess.run(
        [shell, '-NoProfile', '-Command', command['commandWindows']],
        input=payload, capture_output=True, env=env, timeout=15,
    )
    assert (result.stdout, result.stderr, result.returncode) == (
        reference.stdout, reference.stderr, reference.returncode)


@pytest.mark.skipif(os.name != 'nt', reason='Windows PowerShell required')
@pytest.mark.parametrize('shell', ['pwsh', 'powershell'])
def test_windows_missing_python_fails_closed(tmp_path, shell):
    plugin = tmp_path / 'plugin with spaces'
    plugin.mkdir()
    command = json.loads((PLUGIN / 'hooks/hooks.json').read_text())['hooks'][
        'SessionStart'][0]['hooks'][0]['commandWindows']
    # Hide external commands in this process, without changing the shipped selector.
    command = '$env:PATH = ""; ' + command
    result = subprocess.run(
        [shutil.which(shell), '-NoProfile', '-Command', command],
        input=b'{}', capture_output=True,
        env=dict(os.environ, CLAUDE_PLUGIN_ROOT=str(plugin)), timeout=15,
    )
    assert result.returncode == 1
    assert result.stdout == b''


@pytest.mark.skipif(os.name != 'nt', reason='Windows PowerShell required')
@pytest.mark.parametrize('shell', ['pwsh', 'powershell'])
def test_windows_python_fallback_preserves_utf8_stdin_and_exit(tmp_path, shell):
    plugin = tmp_path / 'plugin with spaces'
    (plugin / 'hooks').mkdir(parents=True)
    (plugin / 'hooks/runtime_continuity.py').write_text(
        'import sys\nsys.stdout.buffer.write(sys.stdin.buffer.read())\n'
        'raise SystemExit(2)\n', encoding='utf-8',
    )
    command = json.loads((PLUGIN / 'hooks/hooks.json').read_text())['hooks'][
        'SessionStart'][0]['hooks'][0]['commandWindows']
    payload = '\u00e9 \ud55c\n'.encode('utf-8')
    shim = tmp_path / 'shim'
    shim.mkdir()
    python_home = Path(sys.base_prefix)
    shutil.copyfile(python_home / 'python.exe', shim / 'python3.exe')
    for dll in python_home.glob('python*.dll'):
        shutil.copyfile(dll, shim / dll.name)
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(plugin), PYTHONHOME=str(python_home))
    env['PATH'] = str(shim) + os.pathsep + env['PATH']
    result = subprocess.run(
        [shell, '-NoProfile', '-Command', command], input=payload,
        capture_output=True, env=env, timeout=15,
    )
    assert (result.stdout, result.stderr, result.returncode) == (payload, b'', 2)
