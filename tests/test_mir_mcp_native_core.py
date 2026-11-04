"""Byte transcript oracle for the native core; no installed runtime is used."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'plugins/mir-mcp/mir_mcp.py'
META = {'io.modelcontextprotocol/protocolVersion': '2026-07-28',
        'io.modelcontextprotocol/clientCapabilities': {}}


def request(method='tools/list', params=None, **extra):
    return {'jsonrpc': '2.0', 'id': 1, 'method': method,
            'params': {'_meta': META, **(params or {})}, **extra}


def wire(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode() + b'\n'


@pytest.fixture(scope='session')
def native(tmp_path_factory):
    configured = os.environ.get('MIR_MCP_NATIVE_BINARY')
    if configured:
        binary = Path(configured)
    else:
        if shutil.which('cargo') is None:
            pytest.skip('cargo unavailable')
        target = tmp_path_factory.mktemp('mcp-target')
        env = {**os.environ, 'CARGO_TARGET_DIR': str(target)}
        subprocess.run(['cargo', 'build', '--offline', '--locked'],
                       cwd=ROOT / 'native/mir-mcp', env=env, check=True, timeout=120)
        binary = target / 'debug' / ('mir-mcp.exe' if os.name == 'nt' else 'mir-mcp')
    assert binary.is_file(), 'Build the native server before running this oracle'
    return [str(binary), '--reference-python', sys.executable, '--reference-script', str(SCRIPT)]


def run(command, payload):
    result = subprocess.run(command, input=payload, capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert result.stderr == b''
    return result.stdout


@pytest.mark.parametrize('payload', [
    wire(request()), wire(request('server/discover')),
    b'', b'\xff\n', b'{\n', b'{"a":1,"a":2}\n', b'NaN\n',
    b'[' * 33 + b']' * 33 + b'\n', wire('x' * 4097),
    b'x' * 65537 + b'\n' + wire(request()),
    *[wire(request(method)) for method in ['ping', 'shutdown', 'exit', 'resources/list',
                                          'prompts/list', 'notifications/cancelled']],
    *[wire(request(params={'_meta': meta})) for meta in [None, {},
       {**META, 'io.modelcontextprotocol/protocolVersion': 'future'},
       {**META, 'io.modelcontextprotocol/clientCapabilities': None},
       {**META, 'io.modelcontextprotocol/clientInfo': {}}]],
    wire({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
        'protocolVersion': 'old', 'clientInfo': {'name': 'test', 'version': '1'},
        'capabilities': {}}}) + wire(request()) +
    wire({'jsonrpc': '2.0', 'method': 'notifications/initialized'}) +
    wire({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'}) + wire(request('initialize')),
])
def test_transcript(native, payload):
    payload += wire(request('tools/list'))  # Recovery after every failure.
    assert run(native, payload) == run([sys.executable, '-I', '-B', str(SCRIPT)], payload)


@pytest.mark.parametrize('name,arguments', [
    ('ontology_validate', {}), ('ontology_lookup', {'query': 'evidence'}),
    ('ontology_impact', {'paths': ['README.md']}), ('handoff_pins', {'paths': []}),
    ('relations_query', {'anchor': 'README.md'}), ('unknown', {}),
])
def test_forward(native, tmp_path, name, arguments):
    payload = wire(request('tools/call', {'name': name,
        'arguments': {'target_root': str(tmp_path), **arguments}}))
    assert run(native, payload) == run([sys.executable, '-I', '-B', str(SCRIPT)], payload)


def test_reference_mode(native):
    payload = wire(request())
    reference = [sys.executable, '-I', '-B', str(SCRIPT), '--internal-reference']
    assert run(reference, payload) == run(native, payload)
    result = subprocess.run([*reference, 'extra'], input=payload, capture_output=True, timeout=5)
    assert result.returncode == 2
    assert result.stdout == b''


@pytest.fixture
def fixed_reference(tmp_path):
    """Freeze the reference clock before execution, never normalize result bytes."""
    wrapper = tmp_path / 'reference.py'
    wrapper.write_text(f'''import importlib.util, sys
from datetime import datetime, timezone
spec = importlib.util.spec_from_file_location("reference", {str(SCRIPT)!r})
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
class Fixed(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 1, 1, tzinfo=timezone.utc)
m.ONTOLOGY.datetime = Fixed
m.main(reference="--internal-reference" in sys.argv)
''')
    return wrapper


def test_all_tools_fixture(native, fixed_reference, tmp_path):
    from datetime import datetime, timezone

    target = tmp_path / 'target'
    (target / '.mir').mkdir(parents=True)
    (target / '.mir/repo-profile.toml').write_text('slug = "test"\n')
    (target / 'source.py').write_text('def sample(): pass\n')
    (target / '.mir/ontology-map.json').write_text(json.dumps({
        'contract': {'id': 'mir.common-semantics', 'version': '1.1.0'},
        'domain': {'concepts': [{'name': 'sample', 'ref': 'source.py'}]},
    }))
    (target / 'spec').mkdir()
    (target / 'spec/graph.yaml').write_text('edges:\n  - [REQ, implemented_in, source.py]\n')
    frames = []
    for name, extra in [('ontology_validate', {}), ('ontology_lookup', {'query': 'sample'}),
                        ('ontology_impact', {'paths': ['source.py']}),
                        ('handoff_pins', {'paths': ['source.py']}),
                        ('relations_query', {'anchor': 'REQ', 'purpose': 'implementation'})]:
        frames.append(request('tools/call', {'name': name,
                      'arguments': {'target_root': str(target), **extra}}))
    command = [*native[:-1], str(fixed_reference)]
    payload = b''.join(map(wire, frames))
    expected = run([sys.executable, '-I', '-B', str(fixed_reference)], payload)
    before = datetime.now(timezone.utc)  # noqa: UP017 - Python 3.9
    actual = run(command, payload)
    after = datetime.now(timezone.utc)  # noqa: UP017 - Python 3.9
    actual_lines, expected_lines = actual.splitlines(), expected.splitlines()
    assert len(actual_lines) == len(expected_lines) == 5
    for index in (0, 1, 2, 4):
        assert actual_lines[index] == expected_lines[index]
    observed = json.loads(actual_lines[3])['result']['structuredContent']['data']['observed_at']
    frozen = json.loads(expected_lines[3])['result']['structuredContent']['data']['observed_at']
    assert observed.endswith('Z')
    assert before <= datetime.fromisoformat(observed.replace('Z', '+00:00')) <= after
    assert actual_lines[3].replace(observed.encode(), frozen.encode()) == expected_lines[3]
    # No Git repository: handoff reports partial evidence; other tools succeed.
    values = [json.loads(line) for line in expected.splitlines()]
    assert all(not values[i]['result']['isError'] for i in (0, 1, 2, 4))


@pytest.mark.parametrize('payload', [
    b'{"jsonrpc":"2.0","id":true,"method":"tools/list"}\n',
    b'{"x":{"k":1,"k":2}}\n', b'"\\ud800"\n',
    wire(request(identity='id')), wire(request(identity=9007199254740991)),
    wire(request(identity=9007199254740992)), wire(request(identity=1.0)),
    wire(request(params={'_meta': {**META, 'io.modelcontextprotocol/clientInfo':
                                 {'name': 'test', 'version': '1'}}})),
    wire(request('tools/call', {'name': 'unknown', 'arguments': {}})).rstrip(b'\n'),
    b'{"jsonrpc":"2.0","method":"notifications/cancelled","params":{"requestId":1}}\n',
    b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n',
    wire('é' * 2048), wire('é' * 2049), b'[]' + b' ' * 65533 + b'\n',
])
def test_boundaries(native, payload):
    assert run(native, payload) == run([sys.executable, '-I', '-B', str(SCRIPT)], payload)


def test_cancel_during_call(native, tmp_path):
    wrapper = tmp_path / 'slow.py'
    wrapper.write_text(f'''import importlib.util, sys, time
spec = importlib.util.spec_from_file_location("reference", {str(SCRIPT)!r})
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
original = m.execute
def slow(*args):
    time.sleep(0.3)
    return original(*args)
m.execute = slow
m.main(reference="--internal-reference" in sys.argv)
''')
    payload = wire(request('tools/call', {'name': 'unknown', 'arguments': {}}))
    cancel = wire({'jsonrpc': '2.0', 'method': 'notifications/cancelled',
                   'params': {'requestId': 1}})
    def transcript(command):
        import time
        child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)
        child.stdin.write(payload)
        child.stdin.flush()
        time.sleep(0.1)
        output, error = child.communicate(cancel + wire(request()), timeout=5)
        assert child.returncode == 0 and not error
        return output
    assert transcript([*native[:-1], str(wrapper)]) == transcript(
        [sys.executable, '-I', '-B', str(wrapper)])


@pytest.mark.parametrize('mode,code', [('flood', 'E_LIMIT'), ('fail', 'E_IO'),
                                      ('invalid', 'E_FORMAT'), ('hang', 'E_TIMEOUT')])
def test_forward_failure_recovery(native, tmp_path, mode, code):
    import time
    wrapper = tmp_path / 'child.py'
    wrapper.write_text({
        'flood': 'import sys\nsys.stdout.write("x" * 20000)\n',
        'fail': 'raise SystemExit(1)\n', 'invalid': 'print("invalid")\n',
        'hang': 'import time\ntime.sleep(60)\n',
    }[mode])
    attempts = tmp_path / 'attempts'
    wrapper.write_text(f'from pathlib import Path\n'
                       f'with Path({str(attempts)!r}).open("a") as log: log.write("attempt\\n")\n'
                       + wrapper.read_text())
    start = time.monotonic()
    payload = wire(request('tools/call', {'name': 'unknown', 'arguments': {}}))
    values = [json.loads(line) for line in run(
        [*native[:-1], str(wrapper)], payload + wire(request())).splitlines()]
    assert values[0]['result']['structuredContent']['error'] == {'code': code}
    assert values[1]['result']['tools']
    assert time.monotonic() - start < 12
    assert attempts.read_text() == 'attempt\n'


def test_broken_pipe(native):
    for command in (native, [sys.executable, '-I', '-B', '-u', str(SCRIPT)]):
        child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)
        child.stdout.close()
        child.stdin.write(wire(request()))
        child.stdin.close()
        assert child.wait(timeout=5) == 0
        assert child.stderr.read() == b''


@pytest.mark.parametrize('payload', [b'\xef\xbb\xbf' + wire(request()),
    b'{"jsonrpc":"2.0","id":-0,"method":"ping"}\n',
    b'1e400\n', b'1234567890123456789012345678901234567890\n'])
def test_number_and_bom(native, payload):
    assert run(native, payload) == run([sys.executable, '-I', '-B', str(SCRIPT)], payload)


def test_forward_preserves_child_bytes(native, tmp_path):
    expected = b'{ "jsonrpc": "2.0", "id": 1, "result": {"opaque": 1e400} }\n'
    wrapper = tmp_path / 'literal.py'
    wrapper.write_text(f'import sys\nsys.stdout.buffer.write({expected!r})\n')
    payload = wire(request('tools/call', {'name': 'unknown', 'arguments': {}}))
    assert run([*native[:-1], str(wrapper)], payload) == expected


def test_legacy_forward(native, fixed_reference, tmp_path):
    init = {'jsonrpc': '2.0', 'id': 0, 'method': 'initialize', 'params': {
        'protocolVersion': 'anything', 'clientInfo': {'name': 'test', 'version': '1'},
        'capabilities': {}}}
    payload = wire(init) + wire({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
    payload += wire({'jsonrpc': '2.0', 'id': 'legacy', 'method': 'tools/call', 'params': {
        'name': 'ontology_validate', 'arguments': {'target_root': str(tmp_path),
                                                'scope': 'contract'}}})
    assert run([*native[:-1], str(fixed_reference)], payload) == run(
        [sys.executable, '-I', '-B', str(fixed_reference)], payload)


def test_numeric_and_structure_oracle(native):
    frames = []
    for literal in ('0', '-0', '0.0', '-0.0', '1e400', '-1e400', '1e-400',
                    '1234567890123456789012345678901234567890', '00', '-01',
                    '.1', '1.', '1e+', 'NaN', 'Infinity', '-Infinity'):
        frames.append(('{"jsonrpc":"2.0","id":' + literal +
                       ',"method":"tools/list"}\n').encode())
    for depth in (31, 32, 33):
        frames.append(b'[' * depth + b'0' + b']' * depth + b'\n')
    for size in (4096, 4097):
        frames.append(wire({'x' * size: {}}))
    frames.append(b'x' * 65537)  # Drain oversized EOF, without a final newline.
    payload = b''.join(frames)
    assert run(native, payload) == run([sys.executable, '-I', '-B', str(SCRIPT)], payload)


@pytest.mark.parametrize('name', [
    'test_modern_discovery_and_direct_calls', 'test_legacy_initialization_list_and_call',
    'test_legacy_request_metadata_without_version_is_ordinary',
    'test_versioned_metadata_after_legacy_initialization_stays_modern',
    'test_unversioned_metadata_before_initialization_is_refused',
    'test_direct_modern_calls_require_version_and_capabilities',
    'test_malformed_oversized_frames_preserve_stdout_protocol',
    'test_modern_client_info_is_optional',
])
def test_existing_protocol_oracle(native, tmp_path, monkeypatch, name):
    import test_mir_mcp_protocol as oracle

    def native_run(interpreter, frames, *, cwd, package=None):
        payload = b''.join(wire(frame) if isinstance(frame, dict) else frame + b'\n'
                           for frame in frames)
        return [json.loads(line) for line in run(native, payload).splitlines()]

    monkeypatch.setattr(oracle, '_run', native_run)
    function = getattr(oracle, name)
    parametrizations = [mark for mark in getattr(function, 'pytestmark', [])
                        if mark.name == 'parametrize']
    if not parametrizations:
        function(sys.executable, tmp_path)
    else:
        mark = parametrizations[0]
        keys = mark.args[0].split(',')
        for value in mark.args[1]:
            values = (value,) if len(keys) == 1 else value
            function(sys.executable, tmp_path, **dict(zip(keys, values, strict=True)))


def test_existing_limits_command_oracle(native, tmp_path, monkeypatch):
    from types import SimpleNamespace

    import test_mir_mcp_limits as oracle

    def native_run(command, **kwargs):
        assert command[-1] == str(SCRIPT)
        return subprocess.run(native, **kwargs)

    monkeypatch.setattr(oracle, 'subprocess', SimpleNamespace(run=native_run))
    oracle.test_output_cap_and_stateless_cursor_bindings(sys.executable, tmp_path)
