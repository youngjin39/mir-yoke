"""Execute shipped hook commands through POSIX and Windows session shells."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.lifecycle_golden import GOLDEN, expected_result
from tests.test_handoff_packet_native_parity import binary as binary
from tests.test_handoff_packet_native_parity import stop_payload
from tests.test_handoff_packet_native_parity import stop_repository as stop_repository
from tests.test_lifecycle_windows_launcher import shell_argv
from tests.test_mechanical_handoff import HANDLER_PYTHON, PROMPT, packet

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'plugins/mir-lifecycle-hooks'
pytestmark = [
    pytest.mark.skipif(shutil.which('cargo') is None, reason='cargo unavailable'),
]


def _cmd_command(command):
    # CMD parses /C itself; list2cmdline would C-runtime-escape the hook's quotes.
    comspec = os.environ.get('COMSPEC', 'cmd.exe')
    return f'"{comspec}" /C "{command}"'


@pytest.mark.skipif(os.name == 'nt', reason='POSIX hook shell contract')
@pytest.mark.parametrize('event', ['SessionStart', 'UserPromptSubmit', 'PreToolUse', 'Stop'])
@pytest.mark.parametrize('mode', ['absent', 'present', 'non-executable', 'exe'])
@pytest.mark.parametrize('deny', [False, True], ids=['allow', 'deny'])
def test_real_hook_command(binary, stop_repository, event, mode, deny, request):
    repo, _ = stop_repository
    plugin = repo / 'plugin with spaces'
    shutil.copytree(PLUGIN, plugin)
    name = 'runtime-continuity' if event == 'SessionStart' else 'handoff-packet'
    env = dict(os.environ, HOME=str(repo), CLAUDE_PLUGIN_ROOT=str(plugin),
               MIR_HANDOFF_PYTHON=HANDLER_PYTHON, PYTHONUTF8='1')
    # Resolve the same interpreter as the reference even when python3 differs on PATH.
    shim = repo / 'shim'
    shim.mkdir()
    (shim / 'python3').symlink_to(HANDLER_PYTHON)
    env['PATH'] = str(shim)
    prompt = PROMPT + '\nNo commands.' if deny else 'Inspect the repository. \u00e9 \ud55c'
    payload = json.dumps({'hook_event_name': event, 'cwd': str(repo), 'prompt': prompt,
                          'tool_name': 'Bash', 'tool_input': {'command': 'pwd'}}).encode()
    if event == 'Stop':
        body = packet() + '\nHEAD: abcdef123' if deny else 'Done.'
        payload = stop_payload(repo, prompt, body)
    case = f"tests/test_lifecycle_native_commands.py::{request.node.name}"
    reference = expected_result(GOLDEN["records"][case][0], repo)
    if mode != 'present':
        reference = unavailable_result(event)
    if mode != 'absent':
        destination = plugin / 'bin' / (name + ('.exe' if mode == 'exe' else ''))
        destination.parent.mkdir()
        shutil.copyfile(binary.with_name(name), destination)
        destination.chmod(0o644 if mode == 'non-executable' else 0o755)
    command = json.loads((plugin / 'hooks/hooks.json').read_text())['hooks'][event][0]['hooks'][0]
    assert command['timeout'] == (2 if event == 'SessionStart' else 8)
    for shell in ['/bin/sh', '/bin/bash']:
        result = subprocess.run([shell, '-c', command['command']], input=payload,
                                capture_output=True, env=env, timeout=15)
        assert (result.stdout, result.stderr, result.returncode) == (
            reference.stdout, reference.stderr, reference.returncode)


@pytest.mark.skipif(os.name != 'nt', reason='Codex Windows session-shell contract')
@pytest.mark.parametrize('shell', ['cmd.exe', 'powershell', 'pwsh', 'bash'])
@pytest.mark.parametrize('event', ['SessionStart', 'UserPromptSubmit', 'PreToolUse', 'Stop'])
@pytest.mark.parametrize('mode', ['absent', 'present'])
@pytest.mark.parametrize('deny', [False, True], ids=['allow', 'deny'])
def test_codex_windows_hook_command(binary, stop_repository, event, mode, deny, shell, request):
    repo, _ = stop_repository
    plugin = repo / 'plugin with spaces'
    shutil.copytree(PLUGIN, plugin)
    name = 'runtime-continuity' if event == 'SessionStart' else 'handoff-packet'
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
    case = ('tests/test_lifecycle_native_commands.py::test_real_hook_command['
            f'{"deny" if deny else "allow"}-{mode}-{event}]')
    reference = expected_result(GOLDEN["records"][case][0], repo)
    if mode != 'present':
        reference = unavailable_result(event)
    if mode != 'absent':
        destination = plugin / 'bin' / (name + '.exe')
        destination.parent.mkdir()
        shutil.copyfile(binary.with_name(name + '.exe'), destination)
        destination.chmod(0o644 if mode == 'non-executable' else 0o755)
    command = json.loads((plugin / 'hooks/hooks.json').read_text())['hooks'][event][0]['hooks'][0]
    assert command['timeout'] == (2 if event == 'SessionStart' else 8)
    substituted = command['commandWindows'].replace('${CLAUDE_PLUGIN_ROOT}', str(plugin))
    result = subprocess.run(
        shell_argv(shell, substituted),
        input=payload, capture_output=True, env=env, timeout=15,
    )
    assert (result.stdout, result.stderr, result.returncode) == (
        reference.stdout, reference.stderr, reference.returncode)


@pytest.mark.skipif(os.name != 'nt', reason='Windows cmd.exe required')
def test_windows_missing_python_fails_closed(tmp_path):
    plugin = tmp_path / 'plugin with spaces'
    plugin.mkdir()
    command = json.loads((PLUGIN / 'hooks/hooks.json').read_text())['hooks'][
        'SessionStart'][0]['hooks'][0]['commandWindows']
    command = command.replace('${CLAUDE_PLUGIN_ROOT}', str(plugin))
    # Hide external commands without changing the shipped selector.
    result = subprocess.run(
        _cmd_command(command),
        input=b'{}', capture_output=True,
        env=dict(os.environ, CLAUDE_PLUGIN_ROOT=str(plugin), PATH=''), timeout=15,
    )
    # cmd.exe reports a missing command as 9009 or 1 depending on host and locale.
    assert result.returncode != 0
    assert result.stdout == b''


@pytest.mark.skipif(os.name != 'nt', reason='Windows cmd.exe required')
def test_windows_missing_native_never_executes_retired_handler(tmp_path):
    plugin = tmp_path / 'plugin with spaces'
    (plugin / 'hooks').mkdir(parents=True)
    shutil.copyfile(PLUGIN / 'hooks/windows_hook.py', plugin / 'hooks/windows_hook.py')
    (plugin / 'hooks/runtime_continuity.py').write_text(
        'import sys\nsys.stdout.buffer.write(sys.stdin.buffer.read())\n'
        'raise SystemExit(2)\n', encoding='utf-8',
    )
    command = json.loads((PLUGIN / 'hooks/hooks.json').read_text())['hooks'][
        'SessionStart'][0]['hooks'][0]['commandWindows']
    command = command.replace('${CLAUDE_PLUGIN_ROOT}', str(plugin))
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
        _cmd_command(command), input=payload,
        capture_output=True, env=env, timeout=15,
    )
    assert (result.stdout, result.stderr, result.returncode) == (b'', b'', 0)


def unavailable_result(event):
    error = (f'mir-lifecycle-hooks: native handoff-packet unavailable for {event}\n'.encode()
             if event in {'PreToolUse', 'Stop'} else b'')
    return subprocess.CompletedProcess([], 0, b'', error)


@pytest.mark.skipif(os.name == 'nt', reason='POSIX hook shell contract')
@pytest.mark.parametrize('event', ['SessionStart', 'UserPromptSubmit', 'PreToolUse', 'Stop'])
@pytest.mark.parametrize('mode', ['absent', 'invalid', 'directory', 'symlink', 'rollback',
                                  'unsupported', 'launch-failure'])
def test_missing_native_event_contract(tmp_path, event, mode):
    plugin = tmp_path / 'plugin with spaces'
    shutil.copytree(PLUGIN, plugin)
    name = 'runtime-continuity' if event == 'SessionStart' else 'handoff-packet'
    destination = plugin / 'bin' / name
    destination.parent.mkdir()
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(plugin))
    if mode == 'directory':
        destination.mkdir()
    elif mode == 'symlink':
        destination.symlink_to(sys.executable)
    elif mode != 'absent':
        destination.write_text('not an executable' if mode == 'invalid' else
                               '#!/bin/sh\nprintf partial; printf partial >&2; exit 64\n'
                               if mode == 'unsupported' else '#!/missing/interpreter\n')
        destination.chmod(0o755)
    if mode == 'rollback':
        env['MIR_NATIVE_HOOKS'] = '0'
    hook = json.loads((plugin / 'hooks/hooks.json').read_text())['hooks'][event][0]['hooks'][0]
    expected = unavailable_result(event)
    for shell in ['/bin/sh', '/bin/bash']:
        result = subprocess.run([shell, '-c', hook['command']], input=b'{}',
                                capture_output=True, env=env, timeout=10)
        assert (result.stdout, result.stderr, result.returncode) == (
            expected.stdout, expected.stderr, expected.returncode)
