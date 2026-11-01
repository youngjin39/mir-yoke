"""Production bootstrap caller parity, admission, and exact-byte protocol checks."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import test_bootstrap_native as evaluator
from test_bootstrap_native import CASES, HELPER, _fixture, _hash, _signature

VERSION = b'bootstrap-gate 0.1.0\n'


@pytest.fixture
def native() -> Path:
    return evaluator.native.__wrapped__()


def _run(project: Path, *, rollback: bool = False, enforce: str | None = None,
         prelude: str = '') -> subprocess.CompletedProcess[bytes]:
    env = os.environ.copy()
    env['MIR_NATIVE_HOOKS'] = '0' if rollback else '1'
    command = ('mir_bootstrap_gate_state "$2"' if enforce is None else
               'mir_bootstrap_gate_enforce "$3" "$2"')
    return subprocess.run(
        ['bash', '-c', f'source "$1"; {prelude}\n{command}', 'b1b-caller',
         str(HELPER), str(project), enforce or ''],
        env=env, capture_output=True, check=False,
    )


def _pin(project: Path, executable: Path) -> None:
    receipt = project / '.mir/bootstrap-receipt.json'
    try:
        contents = receipt.read_text()
        data = json.loads(contents)
    except (FileNotFoundError, ValueError):
        return
    pin = {
        'path': '.mir/bin/bootstrap-gate', 'sha256': _hash(executable),
    }
    if 'native_evaluator' in data:
        data['native_evaluator'] = pin
        contents = json.dumps(data)
    else:
        # Keep duplicate JSON keys in the original differential fixture intact.
        contents = contents.replace('{', '{"native_evaluator": ' + json.dumps(pin) + ',', 1)
    receipt.write_text(contents.rstrip() + '\n')


def _executable(project: Path, *, stdout: bytes = b'invalid\n', code: int = 1,
                stderr: bytes = b'', version: bytes = VERSION, version_code: int = 0,
                version_stderr: bytes = b'') -> Path:
    executable = project / '.mir/bin/bootstrap-gate'
    # A shell executable emits arbitrary bytes without requiring a Python runtime.
    def emit(value: bytes) -> str:
        return "printf '" + ''.join(f'\\{byte:03o}' for byte in value) + "'"

    executable.write_text(
        '#!/bin/sh\n'
        'printf "called\\n" >> "$0.calls"\n'
        'if [ "$1" = --version ]; then\n'
        f'  {emit(version)}\n  {emit(version_stderr)} >&2\n'
        f'  exit {version_code}\nfi\n'
        f'{emit(stdout)}\n{emit(stderr)} >&2\nexit {code}\n'
    )
    executable.chmod(0o755)
    _pin(project, executable)
    return executable


def test_production_caller_uses_pinned_adoption_verdict(tmp_path: Path) -> None:
    _fixture(tmp_path, 'ready')
    _executable(tmp_path)
    assert _signature(_run(tmp_path, rollback=True)) == (0, b'ready\n', b'')
    assert _signature(_run(tmp_path)) == (1, b'invalid\n', b'')


@pytest.mark.parametrize('case', CASES)
@pytest.mark.parametrize('enforce', (None, 'application', 'evidence'))
def test_real_native_production_helper_parity(
    tmp_path: Path, native: Path, case: str, enforce: str | None,
) -> None:
    _fixture(tmp_path, case)
    executable = tmp_path / '.mir/bin/bootstrap-gate'
    shutil.copy2(native, executable)
    _pin(tmp_path, executable)
    payload = None if enforce is None else json.dumps({
        'tool_name': 'Write', 'tool_input': {
            'file_path': 'src/application.py' if enforce == 'application'
            else 'spec/evidence-0.yaml',
        },
    })
    assert _signature(_run(tmp_path, enforce=payload)) == _signature(
        _run(tmp_path, rollback=True, enforce=payload))


@pytest.mark.parametrize(('stdout', 'code', 'stderr'), (
    (b'ready\n', 0, b''), (b'invalid\n', 1, b''),
    # The receipt hash pins the evaluator bytes, so its stderr is discarded
    # and its version is implied; only stdout and exit status form a verdict.
    (b'ready\n', 0, b'warning\n'), (b'invalid\n', 1, b'\x00'),
))
def test_production_caller_accepts_exact_verdicts(
    tmp_path: Path, stdout: bytes, code: int, stderr: bytes,
) -> None:
    _fixture(tmp_path, 'hash_drift' if stdout == b'ready\n' else 'ready')
    _executable(tmp_path, stdout=stdout, code=code, stderr=stderr, version=b'any\n')
    assert _signature(_run(tmp_path)) == (code, stdout, b'')


PROTOCOL_FALLBACKS = (
    {'stdout': b'', 'code': 64},
    {'stdout': b'invalid\n', 'code': 64},
    {'stdout': b'invalid\n', 'code': 0},
    {'stdout': b'ready\n', 'code': 1},
    {'stdout': b'ready', 'code': 0},
    {'stdout': b'ready\n\n', 'code': 0},
    {'stdout': b'invalid\n', 'code': 2},
    {'stdout': b'invalid'},
    {'stdout': b'invalid\n\n'},
    {'stdout': b'invalid\r\n'},
    {'stdout': b'', 'stderr': b'invalid\n'},
    {'stdout': b'other\n'},
)


@pytest.mark.parametrize('mutation', PROTOCOL_FALLBACKS)
def test_production_caller_falls_back_for_every_protocol_deviation(
    tmp_path: Path, mutation: dict[str, object],
) -> None:
    _fixture(tmp_path, 'hash_drift' if mutation.get('stdout', b'').startswith(b'ready')
             else 'ready')
    _executable(tmp_path, **mutation)
    assert _signature(_run(tmp_path)) == _signature(_run(tmp_path, rollback=True))


@pytest.mark.parametrize('guard', (
    'rollback', 'missing_pin', 'wrong_path', 'malformed_hash', 'wrong_hash',
    'missing_file', 'replaced_file', 'symlink', 'bin_symlink', 'mir_symlink',
    'directory', 'fifo', 'nonexecutable',
    'execution_failure',
))
def test_production_caller_falls_back_for_every_integrity_guard(
    tmp_path: Path, guard: str,
) -> None:
    _fixture(tmp_path, 'ready')
    executable = _executable(tmp_path)
    receipt_path = tmp_path / '.mir/bootstrap-receipt.json'
    data = json.loads(receipt_path.read_text())
    if guard == 'missing_pin':
        del data['native_evaluator']
    elif guard == 'wrong_path':
        data['native_evaluator']['path'] = '.mir/bin/../bin/bootstrap-gate'
    elif guard in {'malformed_hash', 'wrong_hash'}:
        data['native_evaluator']['sha256'] = 'bad' if guard == 'malformed_hash' else '0' * 64
    receipt_path.write_text(json.dumps(data) + '\n')
    if guard in {'missing_file', 'directory', 'fifo'}:
        executable.unlink()
        if guard == 'directory':
            executable.mkdir()
        elif guard == 'fifo':
            os.mkfifo(executable)
    elif guard == 'replaced_file':
        executable.write_text(executable.read_text() + '# replaced\n')
    elif guard == 'symlink':
        target = executable.with_suffix('.real')
        executable.rename(target)
        executable.symlink_to(target)
    elif guard in {'bin_symlink', 'mir_symlink'}:
        directory = executable.parent if guard == 'bin_symlink' else executable.parent.parent
        target = directory.with_name(directory.name + '-real')
        directory.rename(target)
        directory.symlink_to(target, target_is_directory=True)
    elif guard == 'nonexecutable':
        executable.chmod(0o644)
    elif guard == 'execution_failure':
        executable.write_text('#!/nonexistent/interpreter\n')
        _pin(tmp_path, executable)
    assert _signature(_run(tmp_path, rollback=guard == 'rollback')) == (0, b'ready\n', b'')
    assert not executable.with_suffix('.calls').exists()


@pytest.mark.parametrize('signal', ('TERM', 'SEGV'))
def test_production_caller_falls_back_after_signal_without_stderr_leaks(
    tmp_path: Path, signal: str,
) -> None:
    _fixture(tmp_path, 'ready')
    executable = _executable(tmp_path)
    script = executable.read_text()
    script = script.removesuffix('exit 1\n') + f'kill -{signal} $$\n'
    executable.write_text(script)
    _pin(tmp_path, executable)
    assert _signature(_run(tmp_path, prelude='ulimit -c 0')) == (0, b'ready\n', b'')


@pytest.mark.parametrize('state', ('greenfield', 'restart_required', 'invalid', 'maintainer'))
def test_production_caller_never_admits_other_state_paths(tmp_path: Path, state: str) -> None:
    _fixture(tmp_path, 'ready')
    executable = _executable(tmp_path)
    receipt_path = tmp_path / '.mir/bootstrap-receipt.json'
    data = json.loads(receipt_path.read_text())
    if state == 'greenfield':
        data['mode'] = 'greenfield'
        (tmp_path / 'config/bootstrap-adoption.json').unlink()
    elif state in {'restart_required', 'invalid'}:
        data['status'] = state
    else:
        (tmp_path / '.mir/repo-profile.toml').write_text(
            '[repo]\nslug = "mir-yoke"\nrepository_type = "public_harness_template"\n')
    receipt_path.write_text(json.dumps(data) + '\n')
    prelude = '_mir_bootstrap_has_official_origin() { return 0; }' if state == 'maintainer' else ''
    assert _signature(_run(tmp_path, prelude=prelude)) == _signature(
        _run(tmp_path, rollback=True, prelude=prelude))
    assert not executable.with_suffix('.calls').exists()
