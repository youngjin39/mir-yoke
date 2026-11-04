"""Installed native selection stays before input and source tool imports."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

SERVER = Path(__file__).resolve().parents[1] / 'plugins/mir-mcp/mir_mcp.py'


def launcher():
    # Read only startup definitions, so missing tool modules cannot be hidden.
    source = SERVER.read_text().split('ONTOLOGY, RELATIONS = load_modules()')[0]
    spec = importlib.util.spec_from_file_location('launcher', SERVER)
    module = importlib.util.module_from_spec(spec)
    exec(compile(source, str(SERVER), 'exec'), module.__dict__)
    return module


def install(tmp_path, module):
    module.PACKAGE = tmp_path
    binary = tmp_path / ('bin/mir-mcp.exe' if module.sys.platform == 'win32' else 'bin/mir-mcp')
    binary.parent.mkdir()
    binary.write_bytes(b'fixture executable')
    binary.chmod(0o755)
    pin = {'target': module.native_target(), 'size': binary.stat().st_size,
           'sha256': hashlib.sha256(binary.read_bytes()).hexdigest()}
    (binary.parent / 'native-artifacts.json').write_text(json.dumps({'mir-mcp': pin}))
    return binary, pin


def test_verified_selection_and_reference_arguments(tmp_path, monkeypatch):
    module = launcher()
    binary, _ = install(tmp_path, module)
    calls = []
    monkeypatch.setattr(module.os, 'execv', lambda path, args: calls.append((path, args)))
    # Windows relays through a child instead of exec; record its arguments the same way.
    monkeypatch.setattr(module, 'relay_native', lambda args: calls.append((args[0], args)) or 0)
    assert module.select_native() == 0
    assert calls == [(str(binary), [str(binary), '--reference-python', module.sys.executable,
                                  '--reference-script', str(tmp_path / 'mir_mcp.py')])]


@pytest.mark.parametrize('mutation', ['absent', 'size', 'digest', 'target', 'link', 'malformed'])
def test_unverified_binary_stays_python(tmp_path, mutation, monkeypatch):
    module = launcher()
    binary, pin = install(tmp_path, module)
    monkeypatch.setattr(module.os, 'execv', lambda *args: pytest.fail('unverified execution'))
    monkeypatch.setattr(module, 'relay_native', lambda *args: pytest.fail('unverified execution'))
    record = binary.parent / 'native-artifacts.json'
    if mutation == 'absent':
        record.unlink()
    elif mutation == 'link':
        binary.rename(binary.with_suffix('.real'))
        binary.symlink_to(binary.with_suffix('.real'))
    elif mutation == 'malformed':
        record.write_text('[]')
    else:
        pin[{'size': 'size', 'digest': 'sha256', 'target': 'target'}[mutation]] = {
            'size': pin['size'] + 1, 'digest': '0' * 64, 'target': 'wrong-target',
        }[mutation]
        record.write_text(json.dumps({'mir-mcp': pin}))
    assert module.select_native() is None


def test_exec_failure_before_input_stays_python(tmp_path, monkeypatch):
    module = launcher()
    install(tmp_path, module)
    def fail(*args):
        raise OSError('not executable')
    monkeypatch.setattr(module.os, 'execv', fail)
    assert module.select_native() is None


@pytest.mark.parametrize('code', [0, 7])
def test_windows_relay_binary_eof_and_exit(monkeypatch, code):
    module = launcher()
    child = SimpleNamespace(stdin=io.BytesIO(), stdout=io.BytesIO(b'\xff\x00\n'),
                            wait=lambda **kwargs: code, kill=lambda: None)
    captured = []
    def spawn(args, **kwargs):
        captured.append(kwargs)
        return child
    monkeypatch.setattr(module.subprocess, 'Popen', spawn)
    monkeypatch.setattr(module.sys, 'stdin', SimpleNamespace(buffer=io.BytesIO(b'\x00\xff\n')))
    output = io.BytesIO()
    monkeypatch.setattr(module.sys, 'stdout', SimpleNamespace(buffer=output))
    assert module.relay_native(['fixture']) == code
    assert output.getvalue() == b'\xff\x00\n'
    assert child.stdin.closed
    assert captured[0]['creationflags'] == 0x08000000
    assert captured[0]['bufsize'] == 0


def test_selection_precedes_tool_imports():
    source = SERVER.read_text()
    assert source.index('native_exit = select_native()') < source.index(
        'ONTOLOGY, RELATIONS = load_modules()')


@pytest.mark.skipif(__import__('sys').platform == 'win32', reason='POSIX exec contract')
def test_exec_never_falls_back_after_native_input(tmp_path):
    import shutil
    import subprocess
    import sys

    plugin = tmp_path / 'plugin'
    shutil.copytree(SERVER.parent, plugin)
    module = launcher()
    binary, _ = install(plugin, module)
    # Consume input, then fail deliberately. Bundled tool modules are removed so
    # any import/fallback would change the exit code and expose the error.
    binary.write_text('#!/bin/sh\nread line\nprintf "native:%s\\n" "$line"\nexit 7\n')
    pin = {'target': module.native_target(), 'size': binary.stat().st_size,
           'sha256': hashlib.sha256(binary.read_bytes()).hexdigest()}
    (binary.parent / 'native-artifacts.json').write_text(json.dumps({'mir-mcp': pin}))
    shutil.rmtree(plugin / 'ontology')
    result = subprocess.run([sys.executable, '-I', '-B', '-u', str(plugin / 'mir_mcp.py')],
                            input=b'one\n', capture_output=True, timeout=5)
    assert (result.returncode, result.stdout, result.stderr) == (7, b'native:one\n', b'')


def test_windows_selection_uses_exe_and_does_not_retry(tmp_path, monkeypatch):
    module = launcher()
    monkeypatch.setattr(module, 'native_target', lambda: 'x86_64-pc-windows-msvc')
    binary, pin = install(tmp_path, module)
    binary.rename(binary.with_suffix('.exe'))
    monkeypatch.setattr(module.sys, 'platform', 'win32')
    calls = []
    def relay(args):
        calls.append(args)
        return 9
    monkeypatch.setattr(module, 'relay_native', relay)
    assert module.select_native() == 9
    assert calls[0][0].endswith('mir-mcp.exe')
    assert pin['target'] == 'x86_64-pc-windows-msvc'


def test_windows_spawn_failure_is_before_input(monkeypatch):
    module = launcher()
    def fail(*args, **kwargs):
        raise OSError('cannot start')
    monkeypatch.setattr(module.subprocess, 'Popen', fail)
    assert module.relay_native(['fixture']) is None


@pytest.mark.parametrize('code', [0, 7])
def test_windows_relay_child_exit_with_client_stdin_open(code):
    import subprocess
    import sys

    wrapper = '''
import os
import subprocess
import sys
from pathlib import Path

script = Path(sys.argv[1])
source = script.read_text().split('ONTOLOGY, RELATIONS = load_modules()')[0]
namespace = {'__name__': 'relay_probe', '__file__': str(script)}
exec(compile(source, str(script), 'exec'), namespace)
if os.name != 'nt':
    real_spawn = subprocess.Popen
    def spawn(args, **kwargs):
        kwargs.pop('creationflags', None)
        return real_spawn(args, **kwargs)
    subprocess.Popen = spawn
sys.exit(namespace['relay_native']([
    sys.executable, '-I', '-B', '-u', '-c', 'raise SystemExit(' + sys.argv[2] + ')',
]))
'''
    child = subprocess.Popen(
        [sys.executable, '-I', '-B', '-u', '-c', wrapper, str(SERVER), str(code)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        # communicate() would close client stdin and hide the shutdown race.
        assert child.wait(timeout=5) == code
        assert child.stdout.read() == b''
        assert child.stderr.read() == b''
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()
        child.stdin.close()
        child.stdout.close()
        child.stderr.close()


def test_windows_eof_deadline_kills_child(monkeypatch):
    module = launcher()
    killed = []
    def wait(**kwargs):
        if killed:
            return 1
        raise module.subprocess.TimeoutExpired('fixture', 10)
    child = SimpleNamespace(stdin=io.BytesIO(), stdout=io.BytesIO(),
                            wait=wait, kill=lambda: killed.append(True))
    monkeypatch.setattr(module.subprocess, 'Popen', lambda *args, **kwargs: child)
    monkeypatch.setattr(module.sys, 'stdin', SimpleNamespace(buffer=io.BytesIO()))
    monkeypatch.setattr(module.sys, 'stdout', SimpleNamespace(buffer=io.BytesIO()))
    assert module.relay_native(['fixture']) == 1
    assert killed


def test_windows_broken_output_kills_and_reaps(monkeypatch):
    module = launcher()
    events = []
    class Broken(io.BytesIO):
        def write(self, value):
            raise BrokenPipeError()
    child = SimpleNamespace(stdin=io.BytesIO(), stdout=io.BytesIO(b'response'),
                            wait=lambda **kwargs: events.append('wait') or 0,
                            kill=lambda: events.append('kill'))
    monkeypatch.setattr(module.subprocess, 'Popen', lambda *args, **kwargs: child)
    monkeypatch.setattr(module.sys, 'stdin', SimpleNamespace(buffer=io.BytesIO()))
    monkeypatch.setattr(module.sys, 'stdout', SimpleNamespace(buffer=Broken()))
    assert module.relay_native(['fixture']) == 0
    assert 'kill' in events
    assert events[-1] == 'wait'


def test_real_installed_binary_before_module_imports(tmp_path):
    import os
    import shutil
    import subprocess
    import sys

    native = os.environ.get('MIR_MCP_NATIVE_BINARY')
    if not native:
        pytest.skip('MIR_MCP_NATIVE_BINARY not configured')
    plugin = tmp_path / 'plugin'
    shutil.copytree(SERVER.parent, plugin)
    directory = plugin / 'bin'
    directory.mkdir()
    binary = directory / ('mir-mcp.exe' if sys.platform == 'win32' else 'mir-mcp')
    shutil.copyfile(native, binary)
    binary.chmod(0o755)
    module = launcher()
    (directory / 'native-artifacts.json').write_text(json.dumps({'mir-mcp': {
        'target': module.native_target(), 'size': binary.stat().st_size,
        'sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
    }}))
    shutil.rmtree(plugin / 'ontology')
    request = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list', 'params': {'_meta': {
        'io.modelcontextprotocol/protocolVersion': '2026-07-28',
        'io.modelcontextprotocol/clientCapabilities': {},
    }}}
    result = subprocess.run([sys.executable, '-I', '-B', '-u', str(plugin / 'mir_mcp.py')],
                            input=json.dumps(request).encode() + b'\n',
                            capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert result.stderr == b''
    assert len(json.loads(result.stdout)['result']['tools']) == 5


@pytest.mark.parametrize('kind', ['fifo', 'oversized'])
def test_native_metadata_guard_returns_to_python_without_reading(tmp_path, kind):
    import os
    import subprocess
    import sys

    if kind == 'fifo' and not hasattr(os, 'mkfifo'):
        pytest.skip('named FIFO fixture requires POSIX')
    module = launcher()
    binary, _ = install(tmp_path, module)
    metadata = binary.parent / 'native-artifacts.json'
    if kind == 'fifo':
        metadata.unlink()
        os.mkfifo(metadata)
    else:
        metadata.write_bytes(metadata.read_bytes() + b' ' * 4096)
    wrapper = '''
from pathlib import Path
import sys

script = Path(sys.argv[1])
namespace = {'__name__': 'metadata_probe', '__file__': str(script)}
source = script.read_text().split('ONTOLOGY, RELATIONS = load_modules()')[0]
exec(compile(source, str(script), 'exec'), namespace)
namespace['PACKAGE'] = Path(sys.argv[2])
def forbidden_exec(*args):
    raise AssertionError('invalid metadata selected native')
namespace['os'].execv = forbidden_exec
namespace['relay_native'] = forbidden_exec
assert namespace['select_native']() is None
'''
    result = subprocess.run(
        [sys.executable, '-I', '-B', '-c', wrapper, str(SERVER), str(tmp_path)],
        capture_output=True, timeout=5,
    )
    assert (result.returncode, result.stdout, result.stderr) == (0, b'', b'')


def test_installed_native_forwarding_stays_in_python_reference(tmp_path):
    # The installed launcher execs native; its forwarded child must never select native again.
    import os
    import shutil
    import subprocess
    import sys

    native = os.environ.get('MIR_MCP_NATIVE_BINARY')
    if not native:
        pytest.skip('MIR_MCP_NATIVE_BINARY not configured')
    plain = tmp_path / 'plain'
    shutil.copytree(SERVER.parent, plain)
    plugin = tmp_path / 'plugin'
    shutil.copytree(SERVER.parent, plugin)
    directory = plugin / 'bin'
    directory.mkdir()
    binary = directory / ('mir-mcp.exe' if sys.platform == 'win32' else 'mir-mcp')
    shutil.copyfile(native, binary)
    binary.chmod(0o755)
    (directory / 'native-artifacts.json').write_text(json.dumps({'mir-mcp': {
        'target': launcher().native_target(), 'size': binary.stat().st_size,
        'sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
    }}))
    target = tmp_path / 'target'
    target.mkdir()
    request = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {
        '_meta': {'io.modelcontextprotocol/protocolVersion': '2026-07-28',
                  'io.modelcontextprotocol/clientCapabilities': {}},
        'name': 'ontology_lookup',
        'arguments': {'target_root': str(target), 'query': 'evidence'}}}
    payload = json.dumps(request).encode() + b'\n'
    results = [subprocess.run([sys.executable, '-I', '-B', '-u', str(root / 'mir_mcp.py')],
                              input=payload, capture_output=True, timeout=15)
               for root in (plugin, plain)]
    assert results[0].returncode == results[1].returncode == 0
    assert results[0].stdout == results[1].stdout
    assert b'"error"' not in results[0].stdout.split(b'"result"')[0]
