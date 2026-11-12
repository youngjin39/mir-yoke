"""List-jobs owns launcher outcomes apart from explicit compatibility declines."""
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
    'MIR_EXECUTOR_RESULT_IMPL', 'MIR_EXECUTOR_LIST_JOBS_IMPL', 'MIR_NATIVE_HOOKS',
])
@pytest.mark.parametrize('argv', [
    ['list-jobs'], ['list-jobs', '--help'],
    ['--jobs-db', 'fixture.db', 'list-jobs', '--status', 'running'],
    ['--jobs-d=fixture.db', 'list-jobs', '--unknown'],
    ['--j=first.db', '--jobs-db', 'second.db', 'list-jobs', '--status', 'unknown'],
    ['--unknown', 'list-jobs', '--status', 'running'],
    ['--repo-root', '.', 'list-jobs', '--status', 'running'],
    ['--', 'list-jobs', '--status', 'running'],
])
def test_list_jobs_ignores_selectors_and_owns_64(monkeypatch, tmp_path, capsys, selector, argv):
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
        '[mir_executor] pinned native list-jobs unavailable or incompatible; '
        'Python list-jobs is retired\n')


@pytest.mark.parametrize('pin_text', [None, '{', '{}', '[]', '[' * 20000 + ']' * 20000])
def test_list_jobs_unavailable_pin_is_owned(monkeypatch, tmp_path, capsys, pin_text):
    pin = tmp_path / 'pin.json'
    if pin_text is not None:
        pin.write_text(pin_text, encoding='utf-8')
    monkeypatch.setattr(entrypoint, '_safe_path', lambda *_: pin)
    monkeypatch.setitem(__import__('sys').modules, 'tools.mir_executor.cli', None)
    assert entrypoint.main(['list-jobs', '--status', 'running']) == 2
    assert 'pinned native list-jobs unavailable' in capsys.readouterr().err


def test_list_jobs_native_launch_has_no_python_forward_source():
    tree = ast.parse(inspect.getsource(entrypoint.main))
    list_jobs_branch = next(node for node in ast.walk(tree) if isinstance(node, ast.If)
                            and '_status_requested' in ast.unparse(node.test))
    assert isinstance(list_jobs_branch.body[-1], ast.Return)
    source = ast.unparse(list_jobs_branch)
    assert '_native_status' in source
    assert "_status_requested(argv, 'list-jobs')" in source
    native = inspect.getsource(entrypoint._native_status)
    assert 'return None' not in native
    assert 'return 64' not in native


def test_list_jobs_passes_actual_stream_codecs(monkeypatch, tmp_path):
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
    assert entrypoint.main(['list-jobs', '--status', 'running']) == 0
    assert calls[0]['MIR_EXECUTOR_STDOUT_ENCODING'] == 'iso8859-1'
    assert calls[0]['MIR_EXECUTOR_STDOUT_ERRORS'] == 'strict'
    assert calls[0]['MIR_EXECUTOR_STDERR_ENCODING'] == 'ascii'
    assert calls[0]['MIR_EXECUTOR_STDERR_ERRORS'] == 'backslashreplace'


@pytest.mark.parametrize('guard', ['codec', 'handler', 'local-hook', 'disabled-local-hook'])
def test_list_jobs_only_explicit_compatibility_declines(monkeypatch, tmp_path, guard):
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
    argv = ['list-jobs', '--unknown']
    native = guard == 'disabled-local-hook'
    assert entrypoint.main(argv) == (9 if native else 7)
    assert calls == ([] if native else [argv])
