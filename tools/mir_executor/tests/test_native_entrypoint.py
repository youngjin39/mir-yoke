"""Portable process cleanup checks for the lightweight native command caller."""
from __future__ import annotations

import signal
import subprocess
import sys
import types

import pytest

from tools.mir_executor import entrypoint


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
