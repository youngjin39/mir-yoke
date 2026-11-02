"""Portable process cleanup checks for the lightweight native command caller."""
from __future__ import annotations

import signal
import subprocess
import sys
import types
from pathlib import Path

import pytest

from tools.mir_executor import entrypoint


@pytest.mark.parametrize('arguments,selector', [
    (['execute', '--dispatch'], 'MIR_EXECUTOR_DISPATCH_IMPL'),
    (['resume', '--job-id', 'fixture'], 'MIR_EXECUTOR_RESUME_IMPL'),
    (['sweep'], 'MIR_EXECUTOR_SWEEP_IMPL'),
])
@pytest.mark.parametrize('override', [None, 'command', 'master', 'hooks'])
@pytest.mark.parametrize('owned,code', [(None, 64), (b'owned', 64),
                                       (b'owned\n', 64), (b'owned', 7)])
def test_native_mutation_routes_and_owned_decline(
        monkeypatch, tmp_path, arguments, selector, override, owned, code):
    for key in ('MIR_EXECUTOR_IMPL', 'MIR_EXECUTOR_EXECUTE_IMPL',
                'MIR_EXECUTOR_DISPATCH_IMPL', 'MIR_EXECUTOR_RESUME_IMPL',
                'MIR_EXECUTOR_SWEEP_IMPL', 'MIR_NATIVE_HOOKS'):
        monkeypatch.delenv(key, raising=False)
    if override:
        key = {'command': selector, 'master': 'MIR_EXECUTOR_IMPL',
               'hooks': 'MIR_NATIVE_HOOKS'}[override]
        monkeypatch.setenv(key, '0' if override == 'hooks' else 'python')
    pin = tmp_path / 'executor-query.json'
    pin.write_text('{}', encoding='utf-8')
    monkeypatch.setattr(entrypoint, '_safe_path', lambda *_: pin)
    monkeypatch.setattr(entrypoint, '_pinned_query', lambda *_: tmp_path / 'executor-query')
    calls = []

    def launch(command, **kwargs):
        calls.append(command)
        if owned:
            Path(kwargs['env']['MIR_EXECUTOR_OWNED_RECEIPT']).write_bytes(owned)
        return types.SimpleNamespace(wait=lambda: code)

    monkeypatch.setattr(entrypoint.subprocess, 'Popen', launch)
    result = entrypoint._native_command(arguments)
    assert len(calls) == (0 if override else 1)
    assert result == (None if override or (code == 64 and owned != b'owned') else code)


@pytest.mark.parametrize('number', [signal.SIGINT, signal.SIGTERM])
def test_windows_signal_failure_and_timeout_still_kill_and_reap(monkeypatch, number):
    # Use an actual portable child. Simulate a missing Windows console and a
    # process that outlives the first wait, including on a POSIX test host.
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
    wait = child.wait
    send_signal = child.send_signal
    waits = []

    def failed_signal(_number):
        raise OSError('no console')

    def delayed_wait(timeout=None):
        waits.append(timeout)
        if len(waits) == 1:
            monkeypatch.setattr(child, 'send_signal', send_signal)
            raise subprocess.TimeoutExpired(child.args, timeout)
        return wait(timeout=10)

    monkeypatch.setattr(entrypoint, 'os', types.SimpleNamespace(name='nt'))
    monkeypatch.setattr(entrypoint, 'signal', types.SimpleNamespace(
        SIGINT=signal.SIGINT, CTRL_BREAK_EVENT=1))
    monkeypatch.setattr(child, 'send_signal', failed_signal)
    monkeypatch.setattr(child, 'terminate', lambda: None)
    monkeypatch.setattr(child, 'wait', delayed_wait)
    try:
        entrypoint._stop_native(child, number)
        assert waits == [5, None]
        assert child.poll() is not None
    finally:
        if child.poll() is None:
            child.kill()
        wait(timeout=10)
