"""Status owns launcher outcomes apart from explicit compatibility declines."""
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
    'MIR_EXECUTOR_STATUS_IMPL', 'MIR_NATIVE_HOOKS',
])
@pytest.mark.parametrize('argv', [
    ['status'], ['status', '--help'],
    ['--jobs-db', 'fixture.db', 'status', '--job', 'missing'],
    ['--jobs-d=fixture.db', 'status', '--unknown'],
    ['--j=first.db', '--jobs-db', 'second.db', 'status', '--job-id', '-1'],
    ['--unknown', 'status', '--job-id', 'fixture'],
    ['--repo-root', '.', 'status', '--job-id', 'fixture'],
    ['--', 'status', '--job-id', 'fixture'],
])
def test_status_ignores_selectors_and_owns_64(monkeypatch, tmp_path, capsys, selector, argv):
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
        '[mir_executor] pinned native status unavailable or incompatible; '
        'Python status is retired\n')


@pytest.mark.parametrize('pin_text', [None, '{', '{}', '[]'])
def test_status_unavailable_pin_is_owned(monkeypatch, tmp_path, capsys, pin_text):
    pin = tmp_path / 'pin.json'
    if pin_text is not None:
        pin.write_text(pin_text, encoding='utf-8')
    monkeypatch.setattr(entrypoint, '_safe_path', lambda *_: pin)
    monkeypatch.setitem(__import__('sys').modules, 'tools.mir_executor.cli', None)
    assert entrypoint.main(['status', '--job-id', 'missing']) == 2
    assert 'pinned native status unavailable' in capsys.readouterr().err


def test_status_native_launch_has_no_python_forward_source():
    tree = ast.parse(inspect.getsource(entrypoint.main))
    status_branch = next(node for node in ast.walk(tree) if isinstance(node, ast.If)
                         and '_status_requested' in ast.unparse(node.test))
    assert isinstance(status_branch.body[-1], ast.Return)
    source = ast.unparse(status_branch)
    assert '_native_status' in source
    native = inspect.getsource(entrypoint._native_status)
    assert 'return None' not in native
    assert 'return 64' not in native


def test_status_passes_actual_stream_codecs(monkeypatch, tmp_path):
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
    assert entrypoint.main(['status', '--job-id', 'fixture']) == 0
    assert calls[0]['MIR_EXECUTOR_STDOUT_ENCODING'] == 'iso8859-1'
    assert calls[0]['MIR_EXECUTOR_STDOUT_ERRORS'] == 'strict'
    assert calls[0]['MIR_EXECUTOR_STDERR_ENCODING'] == 'ascii'
    assert calls[0]['MIR_EXECUTOR_STDERR_ERRORS'] == 'backslashreplace'


@pytest.mark.parametrize('codec', [
    'utf-8', 'utf-8-sig', 'ascii', 'latin1', 'cp1252',
    'utf-16', 'utf-16-le', 'utf-16-be', 'utf-32', 'utf-32-le', 'utf-32-be',
    'cp932', 'cp437', 'iso8859-15', 'koi8-r', 'utf-7',
    'unicode_escape', 'raw_unicode_escape',
])
@pytest.mark.parametrize('handler', [
    'strict', 'ignore', 'replace', 'backslashreplace', 'xmlcharrefreplace',
    'surrogateescape', 'surrogatepass', 'namereplace', 'custom',
])
def test_status_codec_decline_exact_family(monkeypatch, codec, handler):
    import codecs
    supported = codecs.lookup(codec).name in {
        'utf-8', 'utf-8-sig', 'ascii', 'iso8859-1', 'cp1252',
        'utf-16', 'utf-16-le', 'utf-16-be', 'utf-32', 'utf-32-le', 'utf-32-be',
    } and handler in {
        'strict', 'ignore', 'replace', 'backslashreplace', 'xmlcharrefreplace',
        'surrogateescape', 'surrogatepass',
    }
    for stream in ('stdout', 'stderr'):
        with monkeypatch.context() as patch:
            patch.setattr(entrypoint.sys, stream, types.SimpleNamespace(
                encoding=codec, errors=handler))
            assert entrypoint._status_codec_decline() is not supported


def test_status_compatibility_source_is_only_codec_or_legacy():
    source = ast.parse(inspect.getsource(entrypoint.main))
    branch = next(node for node in ast.walk(source) if isinstance(node, ast.If)
                  and '_status_requested' in ast.unparse(node.test))
    decline = next(node for node in branch.body if isinstance(node, ast.If))
    assert ast.unparse(decline.test) == (
        "_status_codec_decline() or ((_HOME_ROOT / 'tools/mir_executor/local.py').exists() "
        "and (not disabled))")
    assert ast.unparse(decline.body[-1]) == 'return python_main(argv)'
    assert ast.unparse(branch.body[-1]) == 'return _native_status(argv)'
    codec_source = ast.parse(inspect.getsource(entrypoint._status_codec_decline))
    predicate = ast.unparse(codec_source.body[0].body[-1].value)
    assert predicate == (
        "any((codecs.lookup(getattr(stream, 'encoding', None) or 'utf-8').name "
        "not in encodings or (getattr(stream, 'errors', None) or 'strict') "
        "not in handlers for stream in (sys.stdout, sys.stderr)))")
