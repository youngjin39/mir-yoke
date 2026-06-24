"""Tests for async methods in tools.mir_executor.executor and async CLI path."""

from __future__ import annotations

import asyncio
import json
import pathlib

import pytest

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


# ---------------------------------------------------------------------------
# 1. run_codex_async returns SubprocessResult on success
# ---------------------------------------------------------------------------

def test_run_codex_async_returns_subprocess_result(tmp_path, monkeypatch):
    async def fake_create_subprocess_exec(*args, **kwargs):
        class Proc:
            returncode = 0

            async def communicate(self):
                return (b"ok", b"")

        return Proc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    executor = MirExecutor(repo_root=tmp_path, ledger_path=tmp_path / "tasks" / "tdd.json")
    result = asyncio.run(executor.run_codex_async(["exec", "--help"]))
    assert isinstance(result, SubprocessResult)
    assert result.exit_code == 0
    assert result.stdout == "ok"


# ---------------------------------------------------------------------------
# 2. run_codex_async captures both stdout and stderr
# ---------------------------------------------------------------------------

def test_run_codex_async_captures_stdout_stderr(tmp_path, monkeypatch):
    async def fake_create_subprocess_exec(*args, **kwargs):
        class Proc:
            returncode = 0

            async def communicate(self):
                return (b"stdout text", b"stderr text")

        return Proc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    executor = MirExecutor(repo_root=tmp_path, ledger_path=tmp_path / "tasks" / "tdd.json")
    result = asyncio.run(executor.run_codex_async(["arg"]))
    assert result.stdout == "stdout text"
    assert result.stderr == "stderr text"


# ---------------------------------------------------------------------------
# 3. run_codex_async uses CODEX_BIN env var as first argument
# ---------------------------------------------------------------------------

def test_run_codex_async_uses_codex_bin_env(tmp_path, monkeypatch):
    captured_args = []

    async def fake_create_subprocess_exec(*args, **kwargs):
        captured_args.extend(args)

        class Proc:
            returncode = 0

            async def communicate(self):
                return (b"", b"")

        return Proc()

    monkeypatch.setenv("CODEX_BIN", "/usr/bin/true")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    executor = MirExecutor(repo_root=tmp_path, ledger_path=tmp_path / "tasks" / "tdd.json")
    asyncio.run(executor.run_codex_async(["myarg"]))
    assert captured_args[0] == "/usr/bin/true"


# ---------------------------------------------------------------------------
# 4. run_codex_async propagates asyncio.TimeoutError (not subprocess.TimeoutExpired)
# ---------------------------------------------------------------------------

def test_run_codex_async_propagates_timeout(tmp_path, monkeypatch):
    async def fake_create_subprocess_exec(*args, **kwargs):
        class Proc:
            returncode = None

            async def communicate(self):
                # Simulate a long-running process.
                await asyncio.sleep(9999)
                return (b"", b"")  # pragma: no cover

            def kill(self):
                pass

        return Proc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    executor = MirExecutor(repo_root=tmp_path, ledger_path=tmp_path / "tasks" / "tdd.json")

    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(executor.run_codex_async(["arg"], timeout_seconds=0))


# ---------------------------------------------------------------------------
# 5. run_codex_async raises FileNotFoundError with clear message when binary missing
# ---------------------------------------------------------------------------

def test_run_codex_async_raises_file_not_found_when_codex_missing(tmp_path, monkeypatch):
    async def fake_create_subprocess_exec(*args, **kwargs):
        raise FileNotFoundError("no such file")

    monkeypatch.setenv("CODEX_BIN", "/nonexistent/codex")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    executor = MirExecutor(repo_root=tmp_path, ledger_path=tmp_path / "tasks" / "tdd.json")

    with pytest.raises(FileNotFoundError, match="Codex binary not found"):
        asyncio.run(executor.run_codex_async(["--help"]))


# ---------------------------------------------------------------------------
# 6. execute_async combines run_codex_async and update_ledger
# ---------------------------------------------------------------------------

def test_execute_async_combines_run_and_update(tmp_path, monkeypatch):
    async def fake_create_subprocess_exec(*args, **kwargs):
        class Proc:
            returncode = 0

            async def communicate(self):
                return (b"async-ok", b"")

        return Proc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
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
# 7. execute_async fails fast on unknown change_id — create_subprocess_exec NOT called
# ---------------------------------------------------------------------------

def test_execute_async_fast_fails_on_unknown_change_id_BEFORE_running_codex(
    tmp_path, monkeypatch
):
    call_count = []

    async def fake_create_subprocess_exec(*args, **kwargs):
        call_count.append(args)

        class Proc:
            returncode = 0

            async def communicate(self):
                return (b"", b"")

        return Proc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    ledger_path = _make_ledger(tmp_path, {"unit": {"status": "planned"}})
    executor = MirExecutor(repo_root=tmp_path, ledger_path=ledger_path)

    with pytest.raises(KeyError, match="unknown change_id"):
        asyncio.run(executor.execute_async("WRONG-ID", "unit", ["--help"]))

    assert len(call_count) == 0, (
        "create_subprocess_exec must NOT be called when change_id is invalid."
    )


# ---------------------------------------------------------------------------
# 8. CLI --async flag dispatches to execute_async path
# ---------------------------------------------------------------------------

def test_cli_with_async_flag_dispatches_to_async_path(tmp_path, monkeypatch):
    async def fake_create_subprocess_exec(*args, **kwargs):
        class Proc:
            returncode = 0

            async def communicate(self):
                return (b"cli-async-ok", b"")

        return Proc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
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


# ---------------------------------------------------------------------------
# 9. CLI handles asyncio.TimeoutError gracefully: rc=1, stderr mentions "async timeout"
# ---------------------------------------------------------------------------

def test_cli_handles_asyncio_timeout_error_gracefully(tmp_path, monkeypatch, capsys):
    async def fake_create_subprocess_exec(*args, **kwargs):
        class Proc:
            returncode = None

            async def communicate(self):
                await asyncio.sleep(9999)
                return (b"", b"")  # pragma: no cover

            def kill(self):
                pass

        return Proc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
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
# 10. run_codex_async calls proc.wait() after proc.kill() on timeout
# ---------------------------------------------------------------------------

def test_run_codex_async_calls_wait_after_kill_on_timeout(tmp_path, monkeypatch):
    wait_called = []

    async def fake_create_subprocess_exec(*args, **kwargs):
        class Proc:
            returncode = None

            async def communicate(self):
                await asyncio.sleep(9999)
                return (b"", b"")  # pragma: no cover

            def kill(self):
                pass

            async def wait(self):
                wait_called.append(True)

        return Proc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    executor = MirExecutor(repo_root=tmp_path, ledger_path=tmp_path / "tasks" / "tdd.json")

    with pytest.raises((asyncio.TimeoutError, TimeoutError)):
        asyncio.run(executor.run_codex_async(["arg"], timeout_seconds=0.01))

    assert len(wait_called) >= 1, "proc.wait() must be called after proc.kill() on timeout"


def test_run_codex_async_drains_communicate_after_kill_on_timeout(tmp_path, monkeypatch):
    communicate_calls = []

    async def fake_create_subprocess_exec(*args, **kwargs):
        class Proc:
            returncode = None

            async def communicate(self):
                communicate_calls.append(True)
                if len(communicate_calls) == 1:
                    await asyncio.sleep(9999)
                return (b"", b"")

            def kill(self):
                pass

            async def wait(self):
                return None

        return Proc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    executor = MirExecutor(repo_root=tmp_path, ledger_path=tmp_path / "tasks" / "tdd.json")

    with pytest.raises((asyncio.TimeoutError, TimeoutError)):
        asyncio.run(executor.run_codex_async(["arg"], timeout_seconds=0.01))

    assert len(communicate_calls) >= 2, (
        "timeout cleanup must re-await communicate() after kill() to drain subprocess pipes"
    )
