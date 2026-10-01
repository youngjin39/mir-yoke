"""Regression evidence for the shared executor transport contract."""

import asyncio
import io
import json
import threading
import time
from types import SimpleNamespace

import pytest

from tools.mir_executor.codex_mcp_client import (
    CodexMcpClient,
    CodexMcpProtocolError,
    CodexMcpTimeoutError,
    _PendingRequest,
    _PendingTurn,
    _record_completed_item,
)
from tools.mir_executor.executor import MirExecutor, SubprocessResult
from tools.mir_executor.tests.test_executor import _install_fake_codex_mcp_client, _make_ledger


def test_should_reject_empty_agent_item_id():
    with pytest.raises(CodexMcpProtocolError):
        _record_completed_item(
            _PendingTurn(), {"type": "agentMessage", "id": "", "text": "x"}, "test"
        )


@pytest.mark.parametrize(
    "envelope",
    [
        {"id": 1, "result": {}, "error": {}},
        {"id": 1, "result": {}, "method": "unexpected"},
    ],
)
def test_should_reject_conflicting_response_envelope(envelope):
    client = CodexMcpClient()
    client._pending["1"] = _PendingRequest()
    with pytest.raises(CodexMcpProtocolError):
        client._handle_stdout_line(json.dumps(envelope))


@pytest.mark.parametrize(
    "turn", [None, [], {"id": "", "status": "completed"}, {"id": "t", "status": []}]
)
def test_should_reject_invalid_completion_turn(turn):
    client = CodexMcpClient()
    client._turns["thread"] = _PendingTurn()
    with pytest.raises(CodexMcpProtocolError):
        client._handle_stdout_line(
            json.dumps({"method": "turn/completed", "params": {"threadId": "thread", "turn": turn}})
        )


def test_should_terminate_after_reader_protocol_error(monkeypatch):
    client = CodexMcpClient()
    client._proc = SimpleNamespace(stdout=io.StringIO("{}\n"))
    monkeypatch.setattr(
        client, "_handle_stdout_line", lambda _: (_ for _ in ()).throw(CodexMcpProtocolError("bad"))
    )
    terminated = []
    monkeypatch.setattr(client, "_terminate_server", lambda: terminated.append(True))
    client._read_stdout()
    assert terminated == [True]


def test_should_bound_blocked_send_by_request_timeout(monkeypatch):
    client = CodexMcpClient()
    released = threading.Event()
    monkeypatch.setattr(client, "_send", lambda _: released.wait(0.4))
    monkeypatch.setattr(client, "_terminate_server", released.set)
    started = time.monotonic()
    with pytest.raises(CodexMcpTimeoutError):
        client._request("test", {}, timeout=0.03)
    assert time.monotonic() - started < 0.2


def test_should_preserve_extra_ledger_category_keys(tmp_path):
    ledger = _make_ledger(
        tmp_path, {"unit": {"status": "planned", "evidence": ["keep"], "owner": "project"}}
    )
    MirExecutor(tmp_path, ledger_path=ledger).update_ledger(
        "test-change-id", "unit", SubprocessResult(0, "", "", 0, ["codex"])
    )
    category = json.loads(ledger.read_text())["changes"][0]["categories"]["unit"]
    assert category["evidence"] == ["keep"]
    assert category["owner"] == "project"


@pytest.mark.parametrize("asynchronous", [False, True])
def test_should_default_executor_sandbox_to_workspace_write(tmp_path, monkeypatch, asynchronous):
    calls, _ = _install_fake_codex_mcp_client(monkeypatch)
    executor = MirExecutor(tmp_path)
    if asynchronous:
        asyncio.run(executor.run_codex_async(["exec", "hello"]))
    else:
        executor.run_codex(["exec", "hello"])
    assert calls[0]["sandbox"] == "workspace-write"


def test_should_wait_for_worker_before_propagating_cancellation(tmp_path, monkeypatch):
    entered = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def worker(*_):
        entered.set()
        release.wait(1)
        finished.set()

    executor = MirExecutor(tmp_path)
    monkeypatch.setattr(executor, "_run_codex_mcp_for_async", worker)

    async def scenario():
        task = asyncio.create_task(executor.run_codex_async(["exec", "x"]))
        while not entered.is_set():
            await asyncio.sleep(0.001)
        task.cancel()
        await asyncio.sleep(0.02)
        pending_before_release = not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert pending_before_release
        assert finished.is_set()

    asyncio.run(scenario())


def test_should_filter_credentials_from_dispatch_environment(tmp_path):
    from tools.mir_executor.worktree import dispatch_env

    env = dispatch_env(
        tmp_path,
        {
            "PATH": "/bin",
            "HOME": "/test-home",
            "OPENAI_API_KEY": "secret",
            "GITHUB_TOKEN": "secret",
        },
        filter_credentials=True,
    )
    assert env["PATH"] == "/bin"
    assert env["HOME"] == "/test-home"
    assert "OPENAI_API_KEY" not in env
    assert "GITHUB_TOKEN" not in env


def test_should_import_common_executor_without_mir_package():
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import builtins
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name == 'mir' or name.startswith('mir.'):
        raise ModuleNotFoundError(name)
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from tools.mir_executor.executor import MirExecutor
assert MirExecutor
""",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_should_secure_and_redact_initial_worktree_artifacts(tmp_path):
    from tools.mir_executor.tests.test_worktree import _make_repo
    from tools.mir_executor.worktree import cleanup_worktree, create_dispatch_worktree

    worktree = create_dispatch_worktree(
        _make_repo(tmp_path), "security-test", brief_text="API_KEY=private-value"
    )
    try:
        assert worktree.brief_path.stat().st_mode & 0o777 == 0o600
        assert worktree.status_path.stat().st_mode & 0o777 == 0o600
        assert "private-value" not in worktree.brief_path.read_text()
    finally:
        cleanup_worktree(worktree)


@pytest.mark.parametrize("asynchronous", [False, True])
def test_should_filter_executor_child_env_using_local_config(tmp_path, monkeypatch, asynchronous):
    config = tmp_path / "config" / "mir-executor.local.json"
    config.parent.mkdir()
    config.write_text(
        json.dumps({
            "child_env_filter": True,
            "child_env_extra_keys": ["PROJECT_ALLOWED_TOKEN"],
        })
    )
    monkeypatch.setenv("OPENAI_API_KEY", "private-value")
    monkeypatch.setenv("PROJECT_ALLOWED_TOKEN", "explicitly-retained")
    _, constructors = _install_fake_codex_mcp_client(monkeypatch)
    executor = MirExecutor(tmp_path)
    if asynchronous:
        asyncio.run(executor.run_codex_async(["exec", "hello"]))
    else:
        executor.run_codex(["exec", "hello"])
    child_env = constructors[0]["env"]
    assert "OPENAI_API_KEY" not in child_env
    assert child_env["PROJECT_ALLOWED_TOKEN"] == "explicitly-retained"
