"""Native lifecycle parity against immutable pre-retirement reference captures."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from tests import test_mechanical_handoff as mechanical
from tests.lifecycle_golden import (
    FROZEN_CASES,
    GOLDEN,
    expand,
    expected_result,
    install_snapshot,
    snapshot_context,
    unpack,
)
from tests.test_mechanical_handoff import HANDLER_PYTHON


def test_frozen_event_inventory():
    registered = json.loads((ROOT / 'plugins/mir-lifecycle-hooks/hooks/hooks.json').read_text())
    assert set(registered['hooks']) == {'SessionStart', 'UserPromptSubmit', 'PreToolUse', 'Stop'}
    counts = GOLDEN['provenance']['event_counts']
    assert all(counts[event] > 0 for event in registered['hooks'])


def test_windows_stream_endings_preserve_json_escapes(tmp_path, monkeypatch):
    monkeypatch.setattr(os, 'name', 'nt')
    assert expand({'text': '{"context":"one\\ntwo"}\n'}, tmp_path, stream=True) == (
        b'{"context":"one\\ntwo"}\r\n')


@pytest.mark.parametrize('name,index,record', FROZEN_CASES,
                         ids=[f'{name}#{index}' for name, index, _ in FROZEN_CASES])
def test_frozen_lifecycle(binary, tmp_path, name, index, record):
    install_snapshot(record['setup'], tmp_path)
    session = any(b'runtime_continuity.py' in unpack(arg) for arg in record['argv'])
    executable = binary.with_name('runtime-continuity' + binary.suffix) if session else binary
    env = {key: value for key, value in os.environ.items()
           if key in {'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'TMPDIR'}}
    env.update(HOME=str(tmp_path), PATH='', MIR_HANDOFF_PYTHON=HANDLER_PYTHON,
               PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', GIT_OPTIONAL_LOCKS='0')
    start = time.monotonic()
    result = subprocess.run([str(executable)],
                            input=expand(record['input'], tmp_path, context='json'),
                            capture_output=True, env=env, cwd=ROOT, timeout=15)
    if 'test_supply_timeout_tree' in name:
        assert time.monotonic() - start < 5.6
        time.sleep(1)
        assert not (tmp_path / 'descendant-survived').exists()
    expected = expected_result(record, tmp_path)
    assert (result.stdout, result.stderr, result.returncode) == (
        expected.stdout, expected.stderr, expected.returncode), (name, index)
    for path_name, value in record['after'].items():
        path = tmp_path / path_name
        if 'directory' in value:
            assert path.is_dir(), path_name
        elif 'symlink' in value:
            assert path.is_symlink(), path_name
            link, target = os.readlink(path), value['symlink'].replace('@TMP@', str(tmp_path))
            if os.name == 'nt':
                # Windows reports the stored target with a verbatim prefix and native separators.
                link = os.path.normpath(link.removeprefix('\\\\?\\'))
                target = os.path.normpath(target)
            assert link == target, path_name
        else:
            assert path.read_bytes() == expand(
                value, tmp_path, context=snapshot_context(path_name)), path_name
    actual = {p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob('*')}
    assert actual == set(record['after'])

ROOT = Path(__file__).resolve().parents[1]
CRATE = ROOT / 'native/handoff-packet'
pytestmark = pytest.mark.skipif(shutil.which('cargo') is None, reason='cargo unavailable')


@pytest.fixture(scope='module')
def binary():
    env = dict(os.environ)
    command = ['cargo', 'build', '--release', '--locked']
    if env.get('MIR_HANDOFF_CARGO_OFFLINE') == '1':
        command.append('--offline')
    subprocess.run(command, cwd=CRATE, env=env, check=True)
    target = Path(env.get('CARGO_TARGET_DIR', 'target'))
    if not target.is_absolute():
        target = CRATE / target
    executable = 'handoff-packet.exe' if os.name == 'nt' else 'handoff-packet'
    return target / 'release' / executable


def test_without_reference(binary):
    p = subprocess.run([str(binary)], input=b'{"hook_event_name":"PreToolUse"}',
                       capture_output=True, check=False)
    assert (p.stdout, p.stderr, p.returncode) == (b'', b'', 0)
    p = subprocess.run([str(binary)], input=b'{"hook_event_name":"Stop"}',
                       capture_output=True, check=False)
    assert p.returncode == 0
    newline = b'\r\n' if os.name == 'nt' else b'\n'
    assert json.loads(p.stdout)['systemMessage'].encode() + newline == p.stderr
    assert b'hook unavailable; allowing turn to continue.' in p.stderr

def test_build_environment(monkeypatch, tmp_path):
    target = tmp_path / 'custom target'
    home = tmp_path / 'cargo home'
    monkeypatch.setenv('CARGO_HOME', str(home))
    monkeypatch.setenv('CARGO_TARGET_DIR', str(target))
    monkeypatch.delenv('MIR_HANDOFF_CARGO_OFFLINE', raising=False)
    calls = []
    monkeypatch.setattr(subprocess, 'run',
                        lambda command, **kwargs: calls.append((command, kwargs)))
    path = binary.__wrapped__()
    command, options = calls.pop()
    assert options['env']['CARGO_HOME'] == str(home)
    assert options['env']['CARGO_TARGET_DIR'] == str(target)
    assert '--locked' in command
    assert '--offline' not in command
    assert path == target / 'release' / ('handoff-packet.exe' if os.name == 'nt'
                                        else 'handoff-packet')
    monkeypatch.setenv('MIR_HANDOFF_CARGO_OFFLINE', '1')
    binary.__wrapped__()
    assert '--offline' in calls.pop()[0]
    monkeypatch.setenv('CARGO_TARGET_DIR', 'relative target')
    assert binary.__wrapped__() == CRATE / 'relative target/release' / path.name
    monkeypatch.delenv('CARGO_TARGET_DIR')
    monkeypatch.delenv('CARGO_HOME')
    assert binary.__wrapped__() == CRATE / 'target/release' / path.name
    assert 'CARGO_HOME' not in calls.pop()[1]['env']

@pytest.mark.parametrize('event', ['Stop', 'PreToolUse', 'UserPromptSubmit', 'unknown'])
def test_no_reference_forwarding(binary, tmp_path, event):
    reference = tmp_path / 'reference with spaces.py'
    marker = tmp_path / 'forwarded'
    reference.write_text(
        f'from pathlib import Path\nPath({str(marker)!r}).touch()\n'
        'raise SystemExit(7)\n', encoding='utf-8')
    raw = json.dumps({'hook_event_name': event}).encode()
    env = dict(os.environ, MIR_HANDOFF_PYTHON=HANDLER_PYTHON, PATH=str(tmp_path))
    direct = subprocess.run([str(binary)], input=raw, capture_output=True, env=env, timeout=10)
    supplied = subprocess.run([str(binary), str(reference)], input=raw,
                              capture_output=True, env=env, timeout=10)
    assert not marker.exists(), 'native dispatch executed the reference argument'
    assert (supplied.stdout, supplied.stderr, supplied.returncode) == (
        direct.stdout, direct.stderr, direct.returncode)

@pytest.fixture
def stop_repository(tmp_path):
    (tmp_path / '.git').mkdir()
    (tmp_path / 'scripts').mkdir()
    # JSON-escape the path: Windows backslashes are not valid JSON escapes.
    pins = mechanical.PINS.replace('/example', json.dumps(str(tmp_path))[1:-1])
    (tmp_path / 'scripts/mir_ontology.py').write_text(
        f'print({pins!r})\n', encoding='utf-8')
    return tmp_path, pins

def stop_payload(repo, prompt, body, rows=(), shape='claude'):
    if shape == 'claude':
        user = {'type': 'user', 'message': {'content': prompt}}
        assistant = {'type': 'assistant', 'message': {'content': body}}
    else:
        user = {'type': 'response_item', 'payload': {'role': 'user', 'content': prompt}}
        assistant = {'type': 'response_item', 'payload': {'role': 'assistant', 'content': body}}
    transcript = repo / 'stop.jsonl'
    transcript.write_text(''.join(json.dumps(row) + '\n' for row in [user, *rows, assistant]),
                          encoding='utf-8')
    return json.dumps({'hook_event_name': 'Stop', 'cwd': str(repo),
                       'session_id': 'native-stop', 'transcript_path': str(transcript),
                       'stop_hook_active': False, 'last_assistant_message': body}).encode()
