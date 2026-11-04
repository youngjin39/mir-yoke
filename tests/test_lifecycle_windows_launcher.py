"""Windows launcher selection and stream contracts, including shell boundaries."""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[1] / 'plugins/mir-lifecycle-hooks'
PAIRS = [
    ('runtime-continuity', 'hooks/runtime_continuity.py'),
    ('handoff-packet', 'skills/runtime-continuity/scripts/handoff_packet.py'),
]
EVENTS = ['SessionStart', 'UserPromptSubmit', 'PreToolUse', 'Stop']
PAYLOAD = '\u00e9 \ud55c\n'.encode('utf-8')
ECHO = ('import sys\nsys.stdout.buffer.write(sys.stdin.buffer.read())\n'
        'sys.stderr.buffer.write(b"fixture stderr\\n")\nraise SystemExit(2)\n')


@pytest.fixture
def plugin(tmp_path):
    root = tmp_path / 'plugin with spaces'
    shutil.copytree(PLUGIN, root)
    return root


def load_launcher(plugin):
    spec = importlib.util.spec_from_file_location('windows_hook', plugin / 'hooks/windows_hook.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('name,reference', PAIRS)
@pytest.mark.parametrize('tail', [[], [';', 'exit', '$LASTEXITCODE']])
@pytest.mark.parametrize('mode', ['absent', 'file', 'directory'])
def test_launcher_selects_only_regular_native_file(plugin, monkeypatch, name, reference,
                                                  mode, tail):
    launcher = load_launcher(plugin)
    binary = plugin / 'bin' / (name + '.exe')
    binary.parent.mkdir()
    if mode == 'file':
        binary.write_bytes(b'fixture')
    elif mode == 'directory':
        binary.mkdir()
    calls = []

    def run(argv):
        # No stream redirection: the child inherits all three handles.
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 2)

    monkeypatch.setattr(launcher.subprocess, 'run', run)
    monkeypatch.setenv('CLAUDE_PLUGIN_ROOT', str(plugin / 'wrong root'))
    monkeypatch.setattr(sys, 'argv', ['windows_hook.py', name, reference, *tail])
    assert launcher.main() == 2
    expected = [str(binary)] if mode == 'file' else [sys.executable, str(plugin / reference)]
    assert calls == [expected]


@pytest.mark.parametrize('args', [
    [], ['runtime-continuity'], ['unknown', PAIRS[0][1]],
    ['runtime-continuity', PAIRS[1][1]], ['handoff-packet', PAIRS[0][1]],
    ['runtime-continuity', '../outside.py'],
    ['runtime-continuity', 'hooks\\runtime_continuity.py'],
    ['runtime-continuity', PAIRS[0][1], 'extra'],
    ['runtime-continuity', PAIRS[0][1], ';', 'exit'],
    ['runtime-continuity', PAIRS[0][1], ';', 'exit', '$?'],
    ['runtime-continuity', PAIRS[0][1], ';', 'EXIT', '$LASTEXITCODE'],
    ['runtime-continuity', PAIRS[0][1], ';', 'exit', '$LASTEXITCODE', 'extra'],
    ['unknown', PAIRS[0][1], ';', 'exit', '$LASTEXITCODE'],
    ['runtime-continuity', PAIRS[1][1], ';', 'exit', '$LASTEXITCODE'],
])
def test_launcher_rejects_unadmitted_arguments_without_execution(plugin, monkeypatch, args):
    launcher = load_launcher(plugin)
    monkeypatch.setattr(sys, 'argv', ['windows_hook.py', *args])

    def forbidden(*args, **kwargs):
        pytest.fail('unadmitted invocation executed a child')

    monkeypatch.setattr(launcher.subprocess, 'run', forbidden)
    assert launcher.main() != 0


@pytest.mark.parametrize('name,reference', PAIRS)
@pytest.mark.parametrize('tail', [[], [';', 'exit', '$LASTEXITCODE']])
@pytest.mark.parametrize('exit_code', [2, 37])
def test_launcher_fallback_inherits_utf8_streams_and_exit(plugin, name, reference, tail, exit_code):
    (plugin / reference).write_text(ECHO.replace('SystemExit(2)', f'SystemExit({exit_code})'),
                                    encoding='utf-8')
    command = [sys.executable, str(plugin / 'hooks/windows_hook.py'), name, reference, *tail]
    result = subprocess.run(command, input=PAYLOAD, capture_output=True, timeout=15)
    assert (result.stdout, result.stderr, result.returncode) == (
        PAYLOAD, b'fixture stderr\n', exit_code)


@pytest.fixture
def windows_python_env(tmp_path):
    shim = tmp_path / 'shim'
    shim.mkdir()
    home = Path(sys.base_prefix)
    shutil.copyfile(home / 'python.exe', shim / 'python3.exe')
    for dll in home.glob('python*.dll'):
        shutil.copyfile(dll, shim / dll.name)
    return dict(os.environ, PYTHONHOME=str(home), PYTHONUTF8='1',
                PATH=str(shim) + os.pathsep + os.environ['PATH'])


def shell_argv(shell, command):
    if shell == 'cmd.exe':
        # Codex passes the command as one raw /C argument, without CRT escaping.
        return f'"{os.environ.get("COMSPEC", "cmd.exe")}" /C "{command}"'
    if shell == 'bash':
        # Select Git Bash explicitly; System32/bash.exe may launch WSL instead.
        git = shutil.which('git')
        executable = Path(git).parent.parent / 'bin/bash.exe' if git else None
        if executable is None or not executable.is_file():
            pytest.skip('Git Bash unavailable')
        return [str(executable), '-c', command]
    executable = shutil.which(shell)
    if executable is None:
        pytest.skip(f'{shell} unavailable')
    return [executable, '-NoProfile', '-Command', command]


@pytest.fixture(scope='module', params=[2, 37], ids=['deny', 'fixture-exit'])
def windows_echo_exe(tmp_path_factory, request):
    exit_code = request.param
    root = tmp_path_factory.mktemp('windows-echo')
    source = root / 'echo.rs'
    source.write_text('use std::io::{self, Read, Write}; fn main() { '
                      'let mut b = Vec::new(); io::stdin().read_to_end(&mut b).unwrap(); '
                      'io::stdout().write_all(&b).unwrap(); '
                      'io::stderr().write_all(b"fixture stderr\\n").unwrap(); '
                      f'std::process::exit({exit_code}); }}')
    binary = root / 'echo.exe'
    subprocess.run(['rustc', str(source), '-o', str(binary)], check=True, timeout=60)
    return binary, exit_code


@pytest.mark.skipif(os.name != 'nt', reason='Windows shell execution required')
@pytest.mark.parametrize('shell', ['cmd.exe', 'powershell', 'pwsh', 'bash'])
@pytest.mark.parametrize('event', EVENTS)
@pytest.mark.parametrize('native', [False, True])
def test_windows_command_streams_and_exact_exit(plugin, windows_python_env, windows_echo_exe,
                                             shell, event, native):
    name, reference = PAIRS[0 if event == 'SessionStart' else 1]
    binary, exit_code = windows_echo_exe
    (plugin / reference).write_text(ECHO.replace('SystemExit(2)', f'SystemExit({exit_code})'),
                                    encoding='utf-8')
    expected = subprocess.run([sys.executable, str(plugin / reference)], input=PAYLOAD,
                              capture_output=True, timeout=15)
    assert expected.returncode == exit_code
    if native:
        (plugin / 'bin').mkdir()
        shutil.copyfile(binary, plugin / 'bin' / (name + '.exe'))
        (plugin / reference).write_text('raise SystemExit("unexpected fallback")\n')
    hook = json.loads((plugin / 'hooks/hooks.json').read_text())['hooks'][event][0]['hooks'][0]
    command = hook['commandWindows'].replace('${CLAUDE_PLUGIN_ROOT}', str(plugin))
    result = subprocess.run(shell_argv(shell, command), input=PAYLOAD, capture_output=True,
                            env=windows_python_env, timeout=15)
    assert (result.stdout, result.stderr, result.returncode) == (
        expected.stdout, expected.stderr, expected.returncode)
