"""Direct execution retains live mutation transport and has only named declines."""
import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def launcher(tmp_path, monkeypatch):
    namespace = runpy.run_path(str(ROOT / 'tools/mir_executor/entrypoint.py'))
    scope = namespace['main'].__globals__
    monkeypatch.setitem(scope, '_HOME_ROOT', tmp_path)
    monkeypatch.setitem(scope, '_status_codec_decline', lambda: False)
    monkeypatch.setitem(scope, '_python_local_hooks_disabled', lambda: False)
    return scope


@pytest.mark.parametrize('selector', ['MIR_EXECUTOR_IMPL', 'MIR_EXECUTOR_EXECUTE_IMPL',
                                     'MIR_NATIVE_HOOKS'])
def test_direct_requires_native_with_selectors(launcher, monkeypatch, selector):
    monkeypatch.setenv(selector, '0' if selector == 'MIR_NATIVE_HOOKS' else 'python')
    calls = []
    monkeypatch.setitem(launcher, '_native_command',
                        lambda argv, **kwargs: calls.append((argv, kwargs)) or 23)
    assert launcher['main'](['execute', '--unknown']) == 23
    assert calls == [(['execute', '--unknown'], {'required': True})]


def test_direct_unavailable_never_imports_python(launcher, monkeypatch, capsys):
    monkeypatch.setitem(launcher, '_native_command', lambda *args, **kwargs: None)
    assert launcher['main'](['execute']) == 2
    assert capsys.readouterr().err == (
        '[mir_executor] pinned native execute unavailable or incompatible; '
        'Python execute is retired\n')


def test_dispatch_keeps_existing_route(launcher, monkeypatch):
    calls = []
    monkeypatch.setitem(launcher, '_native_query', lambda argv: None)
    monkeypatch.setitem(launcher, '_native_command',
                        lambda argv, **kwargs: calls.append(kwargs) or 19)
    assert launcher['main'](['execute', '--dispatch']) == 19
    assert calls == [{}]


def test_dispatch_after_option_terminator_is_owned_direct(launcher, monkeypatch):
    calls = []
    monkeypatch.setitem(launcher, '_native_command',
                        lambda argv, **kwargs: calls.append(kwargs) or 2)
    assert launcher['main'](['execute', '--', '--dispatch']) == 2
    assert calls == [{'required': True}]


def test_direct_deep_pin_is_owned_unavailable_error(launcher, capsys):
    pin = launcher['_HOME_ROOT'] / '.mir/bin/executor-query.json'
    pin.parent.mkdir(parents=True)
    pin.write_text('[' * 20000 + '0' + ']' * 20000, encoding='ascii')
    assert launcher['main'](['execute']) == 2
    assert capsys.readouterr().err == (
        '[mir_executor] pinned native execute unavailable or incompatible; '
        'Python execute is retired\n')


def test_global_terminator_preserves_optional_dispatch(launcher, monkeypatch):
    calls = []
    monkeypatch.setitem(launcher, '_native_query', lambda argv: None)
    monkeypatch.setitem(launcher, '_native_command',
                        lambda argv, **kwargs: calls.append(kwargs) or 19)
    assert launcher['main'](['--', 'execute', '--dispatch']) == 19
    assert calls == [{}]
