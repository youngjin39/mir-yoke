"""Execution-layer contracts for the common v3 executor."""

import asyncio
import json
from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tools.mir_executor import executor as mod
from tools.mir_executor.dispatch import AgentRoute


def route(backend="codex", sandbox=None):
    return AgentRoute(
        "reviewer", backend, "test-model", "high", "agent.md", "hash", "review only", sandbox
    )


@pytest.fixture
def provider(monkeypatch):
    calls = []

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def call_codex(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                content_text="answer", model="test-model", token_usage={"total_tokens": 4}
            )

    monkeypatch.setenv("MIR_CODEX_MAIN", "1")
    monkeypatch.setattr(mod, "CodexMcpClient", Client)
    return calls


def local_hook(tmp_path, text):
    path = tmp_path / "tools/mir_executor/local.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_item2_agent_constructor_and_codex(tmp_path, provider):
    selected = route(sandbox="read-only")
    runner = mod.MirExecutor(tmp_path, target_agent="reviewer", agent_route=selected)
    assert runner.repo_root == tmp_path
    assert runner.resolve_agent_route() == selected
    asyncio.run(runner.run_agent_async(["exec", "review"], 30))
    assert provider[0]["sandbox"] == "read-only"
    assert provider[0]["base_instructions"] == "review only"
    assert provider[0]["model"] == "test-model"
    assert provider[0]["config"]["model_reasoning_effort"] == "high"
    with pytest.raises(ValueError, match="same agent"):
        mod.MirExecutor(tmp_path, target_agent="other", agent_route=selected)


def test_item2_agent_claude(tmp_path, monkeypatch):
    process = SimpleNamespace(
        returncode=0, communicate=AsyncMock(return_value=(b"answer", b"warning"))
    )
    spawn = AsyncMock(return_value=process)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    runner = mod.MirExecutor(tmp_path, agent_route=route("claude"))
    result = asyncio.run(runner.run_agent_async(["exec", "review"], 30))
    assert result.stdout == "answer" and result.stderr == "warning"
    assert spawn.call_args.args[1:] == ("--agent", "reviewer", "-p")
    assert process.communicate.call_args.args == (b"review",)


@pytest.mark.parametrize("async_call", [False, True])
def test_item3_executor_writer_lease(tmp_path, monkeypatch, provider, async_call):
    events = []

    @contextmanager
    def scope(root):
        events.append("enter")
        yield
        events.append("exit")

    monkeypatch.setattr(mod, "writer_scope", scope, raising=False)
    runner = mod.MirExecutor(tmp_path)
    if async_call:
        asyncio.run(runner.run_codex_async(["exec", "go"], 30))
    else:
        runner.run_codex(["exec", "go"], 30)
    assert events == ["enter", "exit"]


@pytest.mark.parametrize("async_call", [False, True])
@pytest.mark.parametrize("error", [False, True])
def test_item5_provider_hook(tmp_path, monkeypatch, provider, async_call, error):
    observed = []

    def hook(root, result, **metadata):
        observed.append((result, metadata))
        return replace(result, exit_code=2)

    monkeypatch.setattr(mod, "after_provider_call", hook, raising=False)
    if error:
        monkeypatch.setattr(
            mod.CodexMcpClient,
            "call_codex",
            lambda *a, **k: (_ for _ in ()).throw(mod.CodexMcpError("failed")),
        )
    runner = mod.MirExecutor(tmp_path)
    kwargs = {"model": "test-model", "reasoning_effort": "high"}
    result = (
        asyncio.run(runner.run_codex_async(["exec", "go"], 30, **kwargs))
        if async_call
        else runner.run_codex(["exec", "go"], 30, **kwargs)
    )
    assert result.exit_code == 2
    assert len(observed) == 1
    assert observed[0][1]["prompt"] == "go"
    assert observed[0][1]["attempt"] == 1
    assert (observed[0][1]["raw_result"] is None) == error


@pytest.mark.parametrize("async_call", [False, True])
@pytest.mark.parametrize("timeout", [1, 21])
def test_item6_executor_timeout_bounds(tmp_path, provider, async_call, timeout):
    (tmp_path / "config").mkdir()
    (tmp_path / "config/mir-executor.local.json").write_text(
        json.dumps({"timeout_seconds_range": [2, 20]})
    )
    runner = mod.MirExecutor(tmp_path)
    with pytest.raises(ValueError, match="timeout"):
        if async_call:
            asyncio.run(runner.run_codex_async(["exec", "go"], timeout))
        else:
            runner.run_codex(["exec", "go"], timeout)
    assert provider == []


def test_item3_read_only_agent_skips_writer(tmp_path, monkeypatch, provider):
    def reject(root):
        raise AssertionError("read-only provider must not acquire a writer lease")

    monkeypatch.setattr(mod, "writer_scope", reject)
    runner = mod.MirExecutor(tmp_path, agent_route=route(sandbox="read-only"))
    runner.run_codex(["exec", "review"], 30)
    asyncio.run(runner.run_agent_async(["exec", "review"], 30))


@pytest.mark.parametrize("timeout", [None, 2, 20])
def test_item6_executor_timeout_bounds_allowed(tmp_path, provider, timeout):
    (tmp_path / "config").mkdir()
    (tmp_path / "config/mir-executor.local.json").write_text(
        json.dumps({"timeout_seconds_range": [2, 20]})
    )
    assert mod.MirExecutor(tmp_path).run_codex(["exec", "go"], timeout).exit_code == 0


def test_item2_claude_cancellation_reaps_before_lease_release(tmp_path, monkeypatch):
    import threading

    started = threading.Event()
    events = []

    class Process:
        returncode = None

        async def communicate(self, prompt):
            started.set()
            await asyncio.sleep(60)

        def terminate(self):
            events.append("terminate")
            self.returncode = -15

        async def wait(self):
            events.append("reaped")
            return self.returncode

    @contextmanager
    def scope(root):
        events.append("enter")
        try:
            yield
        finally:
            events.append("exit")

    monkeypatch.setattr(mod, "writer_scope", scope)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=Process()))

    async def exercise():
        runner = mod.MirExecutor(tmp_path, agent_route=route("claude"))
        task = asyncio.create_task(runner.run_agent_async(["exec", "go"]))
        assert await asyncio.to_thread(started.wait, 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(exercise())
    assert events == ["enter", "terminate", "reaped", "exit"]


@pytest.mark.parametrize("async_call", [False, True])
def test_item3_execute_ledger_write_holds_lease(tmp_path, monkeypatch, async_call):
    ledger = tmp_path / "tasks/tdd.json"
    ledger.parent.mkdir()
    ledger.write_text(
        json.dumps({"changes": [{"id": "change", "categories": {"unit": {"status": "planned"}}}]})
    )
    active = []
    replace_file = mod.os.replace

    @contextmanager
    def scope(root):
        active.append(root)
        try:
            yield
        finally:
            active.pop()

    def guarded_replace(*args):
        assert active, "ledger mutation must hold the writer lease"
        replace_file(*args)

    monkeypatch.setattr(mod, "writer_scope", scope)
    monkeypatch.setattr(mod.os, "replace", guarded_replace)
    result = mod.SubprocessResult(0, "done", "", 0, ["test"])
    runner = mod.MirExecutor(tmp_path)
    monkeypatch.setattr(runner, "run_codex", lambda *args, **kwargs: result)
    monkeypatch.setattr(runner, "run_codex_async", AsyncMock(return_value=result))
    if async_call:
        asyncio.run(runner.execute_async("change", "unit", ["exec", "go"]))
    else:
        runner.execute("change", "unit", ["exec", "go"])
    assert not active
