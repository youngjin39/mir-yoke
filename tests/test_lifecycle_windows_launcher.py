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
    ('runtime-continuity', 'SessionStart'),
    ('handoff-packet', 'UserPromptSubmit'),
    ('handoff-packet', 'PreToolUse'),
    ('handoff-packet', 'Stop'),
]
EVENTS = ['SessionStart', 'UserPromptSubmit', 'PreToolUse', 'Stop']
PAYLOAD = '\u00e9 \ud55c\n'.encode('utf-8')


def unavailable(event):
    diagnostic = (f'mir-lifecycle-hooks: native handoff-packet unavailable for {event}\n'
                  .encode() if event in ('PreToolUse', 'Stop') else b'')
    return b'', diagnostic, 0


@pytest.fixture
def plugin(tmp_path, monkeypatch):
    root = tmp_path / 'plugin with spaces'
    shutil.copytree(PLUGIN, root)
    monkeypatch.delenv('MIR_NATIVE_HOOKS', raising=False)
    return root


def load_launcher(plugin):
    spec = importlib.util.spec_from_file_location('windows_hook', plugin / 'hooks/windows_hook.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('name,event', PAIRS)
@pytest.mark.parametrize('tail', [[], [';', 'exit', '$LASTEXITCODE']])
@pytest.mark.parametrize('mode', ['absent', 'file', 'directory', 'symlink', 'rollback', 'nonexec'])
def test_launcher_selects_only_regular_native_file(plugin, monkeypatch, capfdbinary, name, event,
                                                  mode, tail):
    launcher = load_launcher(plugin)
    binary = plugin / 'bin' / (name + '.exe')
    binary.parent.mkdir(exist_ok=True)
    if mode in ('file', 'rollback', 'nonexec'):
        binary.write_bytes(b'fixture')
        binary.chmod(0o644 if mode == 'nonexec' else 0o755)
    elif mode == 'directory':
        binary.mkdir()
    elif mode == 'symlink':
        target = plugin / 'target.exe'
        target.write_bytes(b'fixture')
        target.chmod(0o755)
        try:
            binary.symlink_to(target)
        except OSError:
            pytest.skip('symlink creation unavailable')
    if mode == 'rollback':
        monkeypatch.setenv('MIR_NATIVE_HOOKS', '0')
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        if argv[-1] == '--mir-warmup':
            assert kwargs == {'stdin': subprocess.DEVNULL, 'capture_output': True}
            return subprocess.CompletedProcess(argv, 0, b'', b'')
        assert kwargs == {'capture_output': True}
        return subprocess.CompletedProcess(argv, 37, PAYLOAD, b'fixture stderr\n')

    monkeypatch.setattr(launcher.subprocess, 'run', run)
    monkeypatch.setenv('CLAUDE_PLUGIN_ROOT', str(plugin / 'wrong root'))
    monkeypatch.setattr(sys, 'argv', ['windows_hook.py', name, event, *tail])
    code = launcher.main()
    streams = capfdbinary.readouterr()
    admitted = mode == 'file' or (mode == 'nonexec' and os.name == 'nt')
    expected = (PAYLOAD, b'fixture stderr\n', 37) if admitted else unavailable(event)
    assert (streams.out, streams.err, code) == expected
    assert calls == ([[str(binary), '--mir-warmup'], [str(binary)]] if admitted else [])


@pytest.mark.parametrize('args', [
    [], ['runtime-continuity'], ['unknown', PAIRS[0][1]],
    ['runtime-continuity', PAIRS[1][1]], ['handoff-packet', PAIRS[0][1]],
    ['runtime-continuity', 'hooks/runtime_continuity.py'],
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


@pytest.mark.parametrize('name,event', PAIRS)
@pytest.mark.parametrize('tail', [[], [';', 'exit', '$LASTEXITCODE']])
def test_launcher_absent_uses_event_class(plugin, name, event, tail):
    command = [sys.executable, str(plugin / 'hooks/windows_hook.py'), name, event, *tail]
    result = subprocess.run(command, input=PAYLOAD, capture_output=True, timeout=15)
    assert (result.stdout, result.stderr, result.returncode) == unavailable(event)


@pytest.mark.parametrize('name,event', PAIRS)
@pytest.mark.parametrize('status', [0, 2, 37, 64, 126, 127, 'launch-failure'])
@pytest.mark.parametrize('stage', ['probe', 'execution'])
def test_launcher_buffers_child_streams_until_status_is_known(plugin, monkeypatch, capfdbinary,
                                                            name, event, status, stage):
    launcher = load_launcher(plugin)
    binary = plugin / 'bin' / (name + '.exe')
    binary.parent.mkdir(exist_ok=True)
    binary.write_bytes(b'fixture')
    binary.chmod(0o755)
    stdout, stderr = b'partial\xff\r\n', b'error\xfe\r\n'

    def run(argv, **kwargs):
        if stage == 'execution' and argv[-1] == '--mir-warmup':
            return subprocess.CompletedProcess(argv, 0, b'', b'')
        if status == 'launch-failure':
            raise OSError('fixture launch failure')
        return subprocess.CompletedProcess(argv, status, stdout, stderr)

    monkeypatch.setattr(launcher.subprocess, 'run', run)
    monkeypatch.setattr(sys, 'argv', ['windows_hook.py', name, event])
    code = launcher.main()
    streams = capfdbinary.readouterr()
    admitted = status in (0, 2, 37) and (stage == 'execution' or status == 0)
    expected = (stdout, stderr, status) if admitted else unavailable(event)
    assert (streams.out, streams.err, code) == expected


@pytest.mark.skipif(os.name == 'nt', reason='POSIX executable fixture')
@pytest.mark.parametrize('name,event', PAIRS)
@pytest.mark.parametrize('status', [2, 37, 64, 126, 127])
def test_launcher_real_child_preserves_or_discards_bytes(plugin, name, event, status):
    binary = plugin / 'bin' / (name + '.exe')
    binary.parent.mkdir(exist_ok=True)
    binary.write_text('#!/usr/bin/env python3\nimport sys\n'
                      'if "--mir-warmup" in sys.argv: raise SystemExit(0)\n'
                      'sys.stdout.buffer.write(sys.stdin.buffer.read())\n'
                      'sys.stderr.buffer.write(b"fixture stderr\\n")\n'
                      f'raise SystemExit({status})\n')
    binary.chmod(0o755)
    result = subprocess.run([sys.executable, str(plugin / 'hooks/windows_hook.py'), name, event],
                            input=PAYLOAD, capture_output=True, timeout=15)
    expected = (PAYLOAD, b'fixture stderr\n', status) if status in (2, 37) else unavailable(event)
    assert (result.stdout, result.stderr, result.returncode) == expected


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
                      'if std::env::args().nth(1).as_deref() == Some("--mir-warmup") { return; } '
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
    name = 'runtime-continuity' if event == 'SessionStart' else 'handoff-packet'
    binary, exit_code = windows_echo_exe
    if native:
        (plugin / 'bin').mkdir(exist_ok=True)
        shutil.copyfile(binary, plugin / 'bin' / (name + '.exe'))
    hook = json.loads((plugin / 'hooks/hooks.json').read_text())['hooks'][event][0]['hooks'][0]
    command = hook['commandWindows'].replace('${CLAUDE_PLUGIN_ROOT}', str(plugin))
    result = subprocess.run(shell_argv(shell, command), input=PAYLOAD, capture_output=True,
                            env=windows_python_env, timeout=15)
    expected = (PAYLOAD, b'fixture stderr\n', exit_code) if native else unavailable(event)
    assert (result.stdout, result.stderr, result.returncode) == expected
