"""Tests for async methods in tools.mir_executor.executor and async CLI path."""

from __future__ import annotations

import asyncio
import json
import pathlib

import pytest

from tools.mir_executor.codex_mcp_client import CodexMcpResult, CodexMcpTimeoutError
from tools.mir_executor.dispatch import _MCP_DISPATCH_BASE_INSTRUCTIONS
from tools.mir_executor.executor import LedgerUpdate, MirExecutor, SubprocessResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ledger(tmp_path: pathlib.Path, categories: dict) -> pathlib.Path:
    """Write a minimal tdd.json with one entry to tmp_path/tasks/tdd.json."""
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = tasks_dir / "tdd.json"
    ledger = {
        "version": 1,
        "changes": [
            {
                "id": "test-change-id",
                "scope": "synthetic async test entry",
                "targets": ["tasks/tdd.json"],
                "categories": categories,
            }
        ],
    }
    ledger_path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    return ledger_path


def _install_fake_codex_mcp_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    result: CodexMcpResult | None = None,
    side_effect: BaseException | None = None,
    enter_side_effect: BaseException | None = None,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Monkeypatch executor.CodexMcpClient and return (calls, init_kwargs)."""
    calls: list[dict[str, object]] = []
    init_kwargs: list[dict[str, object]] = []
    mcp_result = result or CodexMcpResult(
        content_text="",
        thread_id="thread-test",
        raw_result={},
    )

    class FakeCodexMcpClient:
        def __init__(self, **kwargs: object) -> None:
            init_kwargs.append(kwargs)

        def __enter__(self) -> FakeCodexMcpClient:
            if enter_side_effect is not None:
                raise enter_side_effect
            return self

        def __exit__(self, *_exc_info: object) -> None:
            return None

        def call_codex(self, **kwargs: object) -> CodexMcpResult:
            calls.append(kwargs)
            if side_effect is not None:
                raise side_effect
            return mcp_result

    monkeypatch.setattr(
        "tools.mir_executor.executor.CodexMcpClient",
        FakeCodexMcpClient,
    )
    return calls, init_kwargs


# ---------------------------------------------------------------------------
# 1. run_codex_async returns SubprocessResult on success
# ---------------------------------------------------------------------------

def test_run_codex_async_returns_subprocess_result(tmp_path, monkeypatch):
    _install_fake_codex_mcp_client(
        monkeypatch,
        result=CodexMcpResult(
            content_text="ok",
            thread_id="thread-test",
            raw_result={},
        ),
    )
    executor = MirExecutor(repo_root=tmp_path, ledger_path=tmp_path / "tasks" / "tdd.json")
    result = asyncio.run(executor.run_codex_async(["exec", "--help"]))
    assert isinstance(result, SubprocessResult)
    assert result.exit_code == 0
    assert result.stdout == "ok"


# ---------------------------------------------------------------------------
# 2. run_codex_async maps content to stdout and keeps stderr empty
# ---------------------------------------------------------------------------

def test_run_codex_async_maps_content_to_stdout(tmp_path, monkeypatch):
    _install_fake_codex_mcp_client(
        monkeypatch,
        result=CodexMcpResult(
            content_text="stdout text",
            thread_id="thread-test",
            raw_result={},
        ),
    )
    executor = MirExecutor(repo_root=tmp_path, ledger_path=tmp_path / "tasks" / "tdd.json")
    result = asyncio.run(executor.run_codex_async(["arg"]))
    assert result.stdout == "stdout text"
    assert result.stderr == ""


def test_run_codex_async_default_timeout_waits_for_completion(tmp_path, monkeypatch):
    calls, init_kwargs = _install_fake_codex_mcp_client(monkeypatch)
    executor = MirExecutor(repo_root=tmp_path, ledger_path=tmp_path / "tasks" / "tdd.json")

    asyncio.run(executor.run_codex_async(["arg"]))

    assert calls[0]["timeout"] is None
    assert init_kwargs[0]["call_timeout"] is None


# ---------------------------------------------------------------------------
# 3. run_codex_async uses CODEX_BIN env var as first argument
# ---------------------------------------------------------------------------

def test_run_codex_async_uses_codex_bin_env(tmp_path, monkeypatch):
    _calls, init_kwargs = _install_fake_codex_mcp_client(monkeypatch)
    monkeypatch.setenv("CODEX_BIN", "/usr/bin/true")
    executor = MirExecutor(repo_root=tmp_path, ledger_path=tmp_path / "tasks" / "tdd.json")
    result = asyncio.run(executor.run_codex_async(["myarg"]))
    assert init_kwargs[0]["codex_bin"] == "/usr/bin/true"
    assert result.command[0] == "/usr/bin/true"


# ---------------------------------------------------------------------------
# 4. run_codex_async propagates asyncio.TimeoutError (not subprocess.TimeoutExpired)
# ---------------------------------------------------------------------------

def test_run_codex_async_propagates_timeout(tmp_path, monkeypatch):
    _install_fake_codex_mcp_client(
        monkeypatch,
        side_effect=CodexMcpTimeoutError("mcp timed out"),
    )
    executor = MirExecutor(repo_root=tmp_path, ledger_path=tmp_path / "tasks" / "tdd.json")

    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(executor.run_codex_async(["arg"], timeout_seconds=0))


def test_run_codex_async_default_init_timeout_is_normal_mcp_failure(
    tmp_path,
    monkeypatch,
):
    _install_fake_codex_mcp_client(
        monkeypatch,
        enter_side_effect=CodexMcpTimeoutError("initialize timed out after 10s"),
    )
    executor = MirExecutor(repo_root=tmp_path, ledger_path=tmp_path / "tasks" / "tdd.json")

    result = asyncio.run(executor.run_codex_async(["arg"]))

    assert result.exit_code == 1
    assert result.stderr == "initialize timed out after 10s"


# ---------------------------------------------------------------------------
# 5. run_codex_async raises FileNotFoundError with clear message when binary missing
# ---------------------------------------------------------------------------

def test_run_codex_async_raises_file_not_found_when_codex_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_BIN", "/nonexistent/codex")
    _install_fake_codex_mcp_client(
        monkeypatch,
        side_effect=FileNotFoundError("no such file"),
    )
    executor = MirExecutor(repo_root=tmp_path, ledger_path=tmp_path / "tasks" / "tdd.json")

    with pytest.raises(FileNotFoundError, match="Codex binary not found"):
        asyncio.run(executor.run_codex_async(["--help"]))


# ---------------------------------------------------------------------------
# 6. execute_async combines run_codex_async and update_ledger
# ---------------------------------------------------------------------------

def test_execute_async_combines_run_and_update(tmp_path, monkeypatch):
    _install_fake_codex_mcp_client(
        monkeypatch,
        result=CodexMcpResult(
            content_text="async-ok",
            thread_id="thread-test",
            raw_result={},
        ),
    )
    ledger_path = _make_ledger(tmp_path, {"unit": {"status": "planned"}})
    executor = MirExecutor(repo_root=tmp_path, ledger_path=ledger_path)

    result, update = asyncio.run(
        executor.execute_async("test-change-id", "unit", ["--help"])
    )

    assert isinstance(result, SubprocessResult)
    assert isinstance(update, LedgerUpdate)
    assert result.exit_code == 0
    assert update.new_status == "pass"

    reloaded = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert reloaded["changes"][0]["categories"]["unit"]["status"] == "pass"


# ---------------------------------------------------------------------------
# 7. execute_async fails fast on unknown change_id — Codex MCP not called
# ---------------------------------------------------------------------------

def test_execute_async_fast_fails_on_unknown_change_id_BEFORE_running_codex(
    tmp_path, monkeypatch
):
    calls, _init_kwargs = _install_fake_codex_mcp_client(monkeypatch)
    ledger_path = _make_ledger(tmp_path, {"unit": {"status": "planned"}})
    executor = MirExecutor(repo_root=tmp_path, ledger_path=ledger_path)

    with pytest.raises(KeyError, match="unknown change_id"):
        asyncio.run(executor.execute_async("WRONG-ID", "unit", ["--help"]))

    assert calls == [], "Codex MCP must NOT be called when change_id is invalid."


# ---------------------------------------------------------------------------
# 8. CLI --async flag dispatches to execute_async path
# ---------------------------------------------------------------------------

def test_cli_with_async_flag_dispatches_to_async_path(tmp_path, monkeypatch):
    calls, _init_kwargs = _install_fake_codex_mcp_client(
        monkeypatch,
        result=CodexMcpResult(
            content_text="cli-async-ok",
            thread_id="thread-test",
            raw_result={},
        ),
    )
    ledger_path = _make_ledger(tmp_path, {"unit": {"status": "planned"}})

    from tools.mir_executor.cli import main

    argv = [
        "execute",
        "--async",
        "--change-id", "test-change-id",
        "--category", "unit",
        "--codex-args", "exec --help",
        "--repo-root", str(tmp_path),
    ]
    main(argv)

    reloaded = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert reloaded["changes"][0]["categories"]["unit"]["status"] == "pass"
    assert calls[0]["timeout"] is None


# ---------------------------------------------------------------------------
# 9. CLI handles asyncio.TimeoutError gracefully: rc=1, stderr mentions "async timeout"
# ---------------------------------------------------------------------------

def test_cli_handles_asyncio_timeout_error_gracefully(tmp_path, monkeypatch, capsys):
    _install_fake_codex_mcp_client(
        monkeypatch,
        side_effect=CodexMcpTimeoutError("mcp timed out"),
    )
    _make_ledger(tmp_path, {"unit": {"status": "planned"}})

    from tools.mir_executor.cli import main

    argv = [
        "execute",
        "--async",
        "--change-id", "test-change-id",
        "--category", "unit",
        "--codex-args", "exec pytest",
        "--timeout", "0",
        "--repo-root", str(tmp_path),
    ]
    with pytest.raises(SystemExit) as exc_info:
        main(argv)

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "async timeout" in captured.err


# ---------------------------------------------------------------------------
# 10. run_codex_async passes lightweight MCP options
# ---------------------------------------------------------------------------

def test_run_codex_async_passes_lightweight_mcp_options(tmp_path, monkeypatch):
    calls, _init_kwargs = _install_fake_codex_mcp_client(monkeypatch)
    executor = MirExecutor(repo_root=tmp_path, ledger_path=tmp_path / "tasks" / "tdd.json")

    result = asyncio.run(
        executor.run_codex_async(
            ["exec", "--sandbox", "workspace-write", "--skip-git-repo-check", "hello"],
            timeout_seconds=3,
        )
    )

    assert result.exit_code == 0
    assert calls[0]["prompt"] == "hello"
    assert calls[0]["cwd"] == pathlib.Path.cwd().resolve()
    assert calls[0]["sandbox"] == "danger-full-access"
    assert calls[0]["approval_policy"] == "never"
    assert calls[0]["base_instructions"] == _MCP_DISPATCH_BASE_INSTRUCTIONS
    assert calls[0]["config"] == {"project_doc_max_bytes": 0}
    assert calls[0]["timeout"] == 3.0


def test_run_codex_async_passes_model_and_reasoning_effort(tmp_path, monkeypatch):
    calls, _init_kwargs = _install_fake_codex_mcp_client(monkeypatch)
    executor = MirExecutor(repo_root=tmp_path, ledger_path=tmp_path / "tasks" / "tdd.json")

    result = asyncio.run(
        executor.run_codex_async(
            ["exec", "hello"],
            model="medium",
            reasoning_effort="high",
        )
    )

    assert result.exit_code == 0
    assert calls[0]["model"] == "medium"
    assert calls[0]["config"] == {
        "project_doc_max_bytes": 0,
        "model_reasoning_effort": "high",
    }
    assert calls[0]["base_instructions"] == _MCP_DISPATCH_BASE_INSTRUCTIONS


def test_run_codex_async_maps_mcp_timeout_to_timeout_error(tmp_path, monkeypatch):
    _install_fake_codex_mcp_client(
        monkeypatch,
        side_effect=CodexMcpTimeoutError("mcp timed out"),
    )
    executor = MirExecutor(repo_root=tmp_path, ledger_path=tmp_path / "tasks" / "tdd.json")

    with pytest.raises((asyncio.TimeoutError, TimeoutError)):
        asyncio.run(executor.run_codex_async(["arg"], timeout_seconds=0.01))
