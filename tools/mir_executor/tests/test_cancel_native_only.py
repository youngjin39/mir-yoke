"""Cancel owns launcher outcomes apart from explicit compatibility declines."""
from __future__ import annotations

import ast
import inspect
import types

import pytest

from tools.mir_executor import entrypoint


@pytest.fixture(autouse=True)
def synthetic_home(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setattr(entrypoint, '_HOME_ROOT', tmp_path)


@pytest.mark.parametrize('selector', [
    'MIR_EXECUTOR_IMPL', 'MIR_EXECUTOR_QUERY_IMPL',
    'MIR_EXECUTOR_CANCEL_IMPL', 'MIR_NATIVE_HOOKS',
])
@pytest.mark.parametrize('argv', [
    ['cancel'], ['cancel', '--help'],
    ['--jobs-db', 'fixture.db', 'cancel', '--job-id', 'running'],
    ['--jobs-d=fixture.db', 'cancel', '--unknown'],
    ['--j=first.db', '--jobs-db', 'second.db', 'cancel', '--job-id', 'unknown'],
    ['--unknown', 'cancel', '--job-id', 'running'],
    ['--repo-root', '.', 'cancel', '--job-id', 'running'],
    ['--', 'cancel', '--job-id', 'running'],
])
def test_cancel_ignores_selectors_and_owns_64(monkeypatch, tmp_path, capsys, selector, argv):
    pin = tmp_path / 'pin.json'
    pin.write_text('{}', encoding='utf-8')
    monkeypatch.setenv(selector, '0' if selector == 'MIR_NATIVE_HOOKS' else 'python')
    monkeypatch.setattr(entrypoint, '_safe_path', lambda *_: pin)
    monkeypatch.setattr(entrypoint, '_pinned_query', lambda *_: tmp_path / 'executor-query')
    calls = []

    def launch(command, **kwargs):
        calls.append(command)
        return types.SimpleNamespace(returncode=64, stdout=b'', stderr=b'')

    monkeypatch.setattr(entrypoint.subprocess, 'run', launch)
    monkeypatch.setitem(__import__('sys').modules, 'tools.mir_executor.cli', None)
    assert entrypoint.main(argv) == 2
    assert len(calls) == 1
    assert capsys.readouterr().err == (
        '[mir_executor] pinned native cancel unavailable or incompatible; '
        'Python cancel is retired\n')


@pytest.mark.parametrize('pin_text', [None, '{', '{}', '[]', '[' * 20000 + ']' * 20000])
def test_cancel_unavailable_pin_is_owned(monkeypatch, tmp_path, capsys, pin_text):
    pin = tmp_path / 'pin.json'
    if pin_text is not None:
        pin.write_text(pin_text, encoding='utf-8')
    monkeypatch.setattr(entrypoint, '_safe_path', lambda *_: pin)
    monkeypatch.setitem(__import__('sys').modules, 'tools.mir_executor.cli', None)
    assert entrypoint.main(['cancel', '--job-id', 'running']) == 2
    assert 'pinned native cancel unavailable' in capsys.readouterr().err


def test_cancel_native_launch_has_no_python_forward_source():
    tree = ast.parse(inspect.getsource(entrypoint.main))
    cancel_branch = next(node for node in ast.walk(tree) if isinstance(node, ast.If)
                            and '_status_requested' in ast.unparse(node.test))
    assert isinstance(cancel_branch.body[-1], ast.Return)
    source = ast.unparse(cancel_branch)
    assert '_native_status' in source
    assert "_status_requested(argv, 'cancel')" in source
    native = inspect.getsource(entrypoint._native_status)
    assert 'return None' not in native
    assert 'return 64' not in native


def test_cancel_passes_actual_stream_codecs(monkeypatch, tmp_path):
    pin = tmp_path / 'pin.json'
    pin.write_text('{}', encoding='utf-8')
    monkeypatch.setattr(entrypoint, '_safe_path', lambda *_: pin)
    monkeypatch.setattr(entrypoint, '_pinned_query', lambda *_: tmp_path / 'executor-query')
    monkeypatch.setattr(entrypoint.sys, 'stdout', types.SimpleNamespace(
        encoding='latin1', errors='strict', write=lambda _: None))
    monkeypatch.setattr(entrypoint.sys, 'stderr', types.SimpleNamespace(
        encoding='ascii', errors='backslashreplace', write=lambda _: None))
    calls = []
    monkeypatch.setattr(entrypoint, '_write_output', lambda *_: None)
    monkeypatch.setattr(entrypoint.subprocess, 'run', lambda command, **kwargs:
                        calls.append(kwargs['env']) or types.SimpleNamespace(
                            returncode=0, stdout=b'', stderr=b''))
    assert entrypoint.main(['cancel', '--job-id', 'running']) == 0
    assert calls[0]['MIR_EXECUTOR_STDOUT_ENCODING'] == 'iso8859-1'
    assert calls[0]['MIR_EXECUTOR_STDOUT_ERRORS'] == 'strict'
    assert calls[0]['MIR_EXECUTOR_STDERR_ENCODING'] == 'ascii'
    assert calls[0]['MIR_EXECUTOR_STDERR_ERRORS'] == 'backslashreplace'


@pytest.mark.parametrize('guard', ['codec', 'handler', 'local-hook', 'disabled-local-hook'])
def test_cancel_only_explicit_compatibility_declines(monkeypatch, tmp_path, guard):
    import sys

    calls = []
    monkeypatch.setitem(sys.modules, 'tools.mir_executor.cli', types.SimpleNamespace(
        main=lambda argv: calls.append(argv) or 7))
    monkeypatch.setattr(entrypoint, '_native_status', lambda argv: 9)
    monkeypatch.setattr(entrypoint, '_status_codec_decline', lambda: guard in {'codec', 'handler'})
    if 'local-hook' in guard:
        local = tmp_path / 'tools/mir_executor/local.py'
        local.parent.mkdir(parents=True)
        local.write_text('raise AssertionError("must not import during admission")\n')
    if guard == 'disabled-local-hook':
        config = tmp_path / 'config/mir-executor.local.json'
        config.parent.mkdir()
        config.write_text('{"python_local_hooks": false}')
    argv = ['cancel', '--unknown']
    native = guard == 'disabled-local-hook'
    assert entrypoint.main(argv) == (9 if native else 7)
    assert calls == ([] if native else [argv])


@pytest.mark.parametrize('fault', [
    'digest', 'path', 'extra-key', 'linked-pin', 'linked-binary',
    'missing-binary', 'nonexecutable', 'spawn-error',
])
def test_cancel_pin_and_spawn_failures_never_forward(monkeypatch, tmp_path, capsys, fault):
    import hashlib
    import json
    import sys

    directory = tmp_path / '.mir/bin'
    directory.mkdir(parents=True)
    executable = directory / 'executor-query'
    executable.write_bytes(b'#!/bin/sh\nexit 64\n')
    executable.chmod(0o755)
    pin = {'path': '.mir/bin/executor-query',
           'sha256': hashlib.sha256(executable.read_bytes()).hexdigest()}
    if fault == 'digest':
        pin['sha256'] = '0' * 64
    elif fault == 'path':
        pin['path'] = '../executor-query'
    elif fault == 'extra-key':
        pin['unexpected'] = True
    elif fault == 'linked-binary':
        executable.rename(directory / 'real-query')
        executable.symlink_to('real-query')
    elif fault == 'missing-binary':
        executable.rename(directory / 'unused-query')
    elif fault == 'nonexecutable':
        executable.chmod(0o644)
    (directory / 'executor-query.json').write_text(json.dumps(pin), encoding='ascii')
    if fault == 'linked-pin':
        (directory / 'executor-query.json').rename(directory / 'real-pin.json')
        (directory / 'executor-query.json').symlink_to('real-pin.json')
    if fault == 'spawn-error':
        def fail(*args, **kwargs):
            raise OSError('synthetic spawn error')
        monkeypatch.setattr(entrypoint.subprocess, 'run', fail)
    monkeypatch.setitem(sys.modules, 'tools.mir_executor.cli', None)
    assert entrypoint.main(['cancel', '--job-id=fixture']) == 2
    assert capsys.readouterr().err == (
        '[mir_executor] pinned native cancel unavailable or incompatible; '
        'Python cancel is retired\n')
