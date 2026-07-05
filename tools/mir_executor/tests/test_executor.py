"""Tests for tools.mir_executor.executor and tools.mir_executor.cli."""

from __future__ import annotations

import json
import pathlib
import subprocess

import pytest

from tools.mir_executor.codex_mcp_client import (
    CodexMcpError,
    CodexMcpResult,
    CodexMcpTimeoutError,
)
from tools.mir_executor.dispatch import _MCP_DISPATCH_BASE_INSTRUCTIONS
from tools.mir_executor.executor import LedgerUpdate, MirExecutor, SubprocessResult

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


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
                "scope": "synthetic test entry",
                "targets": ["tasks/tdd.json"],
                "categories": categories,
            }
        ],
    }
    ledger_path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    return ledger_path


def _make_mapping_ledger(tmp_path: pathlib.Path, categories: dict) -> pathlib.Path:
    """Write a minimal top-level-mapping tdd.json with no changes[] list."""
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = tasks_dir / "tdd.json"
    ledger = {
        "version": 1,
        "mapping-change-id": {
            "scope": "synthetic mapping test entry",
            "targets": ["tasks/tdd.json"],
            "categories": categories,
        },
    }
    ledger_path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    return ledger_path


def _install_fake_codex_mcp_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    result: CodexMcpResult | None = None,
    side_effect: BaseException | None = None,
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


def _write_dispatch_brief(tmp_path: pathlib.Path) -> pathlib.Path:
    brief_path = tmp_path / "tasks" / "dispatch" / "dispatch-task" / "executor-slice.json"
    brief_path.parent.mkdir(parents=True, exist_ok=True)
    brief_path.write_text(
        json.dumps(
            {
                "version": 1,
                "task_id": "dispatch-task",
                "phase_id": "phase-4",
                "slice_id": "executor-slice",
                "target_agent": "executor-agent",
                "user_intent": "Fix src/foo.py",
                "expanded_goal": "Fix src/foo.py [role=executor, stack=python]",
                "owned_scope": ["src/foo.py"],
                "out_of_scope": ["docs/**"],
                "verification_commands": [
                    "uv run pytest -q tools/mir_executor/tests/test_executor.py"
                ],
                "stop_conditions": ["Stop if the change requires files outside owned_scope."],
                "handoff_refs": [],
                "tdd_change_refs": ["tasks/tdd.json#test-change-id"],
                "resume_state_ref": "tasks/dispatch/dispatch-task/executor-slice.json",
                "source_refs": {
                    "task_spec": "runtime://task-spec/dispatch-task",
                    "plan": "tasks/plan.md",
                    "phase": "tasks/phase.json",
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return brief_path


# ---------------------------------------------------------------------------
# 1. SubprocessResult exit_code pass
# ---------------------------------------------------------------------------

def test_subprocess_result_exit_code_pass(tmp_path, monkeypatch):
    _install_fake_codex_mcp_client(monkeypatch)
    executor = MirExecutor(repo_root=tmp_path)
    result = executor.run_codex(["--help"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# 2. CodexMcpResult content maps to stdout and stderr stays empty
# ---------------------------------------------------------------------------

def test_subprocess_result_maps_mcp_content_to_stdout(tmp_path, monkeypatch):
    _install_fake_codex_mcp_client(
        monkeypatch,
        result=CodexMcpResult(
            content_text="out text",
            thread_id="thread-test",
            raw_result={},
        ),
    )
    executor = MirExecutor(repo_root=tmp_path)
    result = executor.run_codex(["--help"])
    assert result.stdout == "out text"
    assert result.stderr == ""


# ---------------------------------------------------------------------------
# 3. CODEX_BIN env var is used
# ---------------------------------------------------------------------------

def test_run_codex_uses_codex_bin_env_var(tmp_path, monkeypatch):
    _calls, init_kwargs = _install_fake_codex_mcp_client(monkeypatch)
    monkeypatch.setenv("CODEX_BIN", "/usr/bin/true")
    executor = MirExecutor(repo_root=tmp_path)
    result = executor.run_codex(["arg1"])
    assert init_kwargs[0]["codex_bin"] == "/usr/bin/true"
    assert result.command[0] == "/usr/bin/true"


# ---------------------------------------------------------------------------
# 4. Default codex bin when CODEX_BIN unset
# ---------------------------------------------------------------------------

def test_run_codex_default_codex_bin_when_env_unset(tmp_path, monkeypatch):
    _calls, init_kwargs = _install_fake_codex_mcp_client(monkeypatch)
    monkeypatch.delenv("CODEX_BIN", raising=False)
    executor = MirExecutor(repo_root=tmp_path)
    result = executor.run_codex(["--help"])
    assert init_kwargs[0]["codex_bin"] == "codex"
    assert result.command[0] == "codex"


def test_run_codex_uses_dispatch_brief_goal_when_direct_args_empty(tmp_path, monkeypatch):
    calls, _init_kwargs = _install_fake_codex_mcp_client(monkeypatch)
    brief_path = _write_dispatch_brief(tmp_path)
    executor = MirExecutor(repo_root=tmp_path, dispatch_brief_path=brief_path)

    executor.run_codex([])

    assert calls[0]["prompt"] == "Fix src/foo.py [role=executor, stack=python]"


def test_run_codex_uses_explicit_codex_args_when_dispatch_brief_is_present(tmp_path, monkeypatch):
    calls, _init_kwargs = _install_fake_codex_mcp_client(monkeypatch)
    brief_path = _write_dispatch_brief(tmp_path)
    executor = MirExecutor(repo_root=tmp_path, dispatch_brief_path=brief_path)

    executor.run_codex(["status"])

    assert calls[0]["prompt"] == "status"


def test_run_codex_passes_lightweight_mcp_options(tmp_path, monkeypatch):
    calls, _init_kwargs = _install_fake_codex_mcp_client(monkeypatch)
    executor = MirExecutor(repo_root=tmp_path)

    result = executor.run_codex(
        ["exec", "--sandbox", "workspace-write", "--skip-git-repo-check", "hello"],
    )

    assert result.exit_code == 0
    assert calls[0]["prompt"] == "hello"
    assert calls[0]["cwd"] == pathlib.Path.cwd().resolve()
    assert calls[0]["sandbox"] == "danger-full-access"
    assert calls[0]["approval_policy"] == "never"
    assert calls[0]["base_instructions"] == _MCP_DISPATCH_BASE_INSTRUCTIONS
    assert calls[0]["config"] == {"project_doc_max_bytes": 0}
    assert calls[0]["timeout"] == 600.0


def test_run_codex_passes_model_and_reasoning_effort(tmp_path, monkeypatch):
    calls, _init_kwargs = _install_fake_codex_mcp_client(monkeypatch)
    executor = MirExecutor(repo_root=tmp_path)

    result = executor.run_codex(
        ["exec", "hello"],
        model="low",
        reasoning_effort="xhigh",
    )

    assert result.exit_code == 0
    assert calls[0]["model"] == "low"
    assert calls[0]["config"] == {
        "project_doc_max_bytes": 0,
        "model_reasoning_effort": "xhigh",
    }
    assert calls[0]["base_instructions"] == _MCP_DISPATCH_BASE_INSTRUCTIONS


def test_run_codex_maps_mcp_error_to_subprocess_result(tmp_path, monkeypatch):
    _install_fake_codex_mcp_client(
        monkeypatch,
        side_effect=CodexMcpError("mcp unavailable"),
    )
    executor = MirExecutor(repo_root=tmp_path)

    result = executor.run_codex(["exec", "hello"])

    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr == "mcp unavailable"


# ---------------------------------------------------------------------------
# 5. FileNotFoundError propagated with clear message
# ---------------------------------------------------------------------------

def test_run_codex_raises_file_not_found_when_codex_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_BIN", "/nonexistent/codex")
    _install_fake_codex_mcp_client(
        monkeypatch,
        side_effect=FileNotFoundError("no such file"),
    )
    executor = MirExecutor(repo_root=tmp_path)
    with pytest.raises(FileNotFoundError, match="Codex binary not found"):
        executor.run_codex(["--help"])


# ---------------------------------------------------------------------------
# 6. TimeoutExpired propagated
# ---------------------------------------------------------------------------

def test_run_codex_propagates_timeout(tmp_path, monkeypatch):
    _install_fake_codex_mcp_client(
        monkeypatch,
        side_effect=CodexMcpTimeoutError("mcp timed out"),
    )
    executor = MirExecutor(repo_root=tmp_path)
    with pytest.raises(subprocess.TimeoutExpired):
        executor.run_codex(["--help"], timeout_seconds=1)


# ---------------------------------------------------------------------------
# 7. update_ledger sets status=pass on exit_code=0
# ---------------------------------------------------------------------------

def test_update_ledger_sets_status_pass_on_exit_zero(tmp_path):
    ledger_path = _make_ledger(tmp_path, {"unit": {"status": "planned"}})
    executor = MirExecutor(repo_root=tmp_path, ledger_path=ledger_path)
    result = SubprocessResult(
        exit_code=0, stdout="", stderr="", duration_seconds=0.1, command=["codex", "exec"]
    )
    update = executor.update_ledger("test-change-id", "unit", result)
    assert update.new_status == "pass"
    reloaded = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert reloaded["changes"][0]["categories"]["unit"]["status"] == "pass"


def test_validate_and_update_ledger_support_top_level_mapping_schema(tmp_path):
    ledger_path = _make_mapping_ledger(tmp_path, {"unit": {"status": "planned"}})
    executor = MirExecutor(repo_root=tmp_path, ledger_path=ledger_path)
    result = SubprocessResult(
        exit_code=0, stdout="", stderr="", duration_seconds=0.1, command=["codex", "exec"]
    )

    entry = executor._validate_ledger_entry("mapping-change-id", "unit")
    assert entry["scope"] == "synthetic mapping test entry"

    update = executor.update_ledger("mapping-change-id", "unit", result)
    assert update.new_status == "pass"
    reloaded = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert "changes" not in reloaded
    assert reloaded["mapping-change-id"]["categories"]["unit"]["status"] == "pass"


# ---------------------------------------------------------------------------
# 8. update_ledger sets status=fail on nonzero exit
# ---------------------------------------------------------------------------

def test_update_ledger_sets_status_fail_on_nonzero_exit(tmp_path, monkeypatch):
    ledger_path = _make_ledger(tmp_path, {"unit": {"status": "planned"}})
    executor = MirExecutor(repo_root=tmp_path, ledger_path=ledger_path)
    result = SubprocessResult(
        exit_code=1, stdout="", stderr="boom", duration_seconds=0.2, command=["codex"]
    )
    update = executor.update_ledger("test-change-id", "unit", result)
    assert update.new_status == "fail"
    reloaded = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert reloaded["changes"][0]["categories"]["unit"]["status"] == "fail"


# ---------------------------------------------------------------------------
# 9. update_ledger writes command field
# ---------------------------------------------------------------------------

def test_update_ledger_writes_command_field(tmp_path):
    ledger_path = _make_ledger(tmp_path, {"unit": {"status": "planned"}})
    executor = MirExecutor(repo_root=tmp_path, ledger_path=ledger_path)
    result = SubprocessResult(
        exit_code=0,
        stdout="",
        stderr="",
        duration_seconds=0.1,
        command=["codex", "exec pytest"],
    )
    executor.update_ledger("test-change-id", "unit", result)
    reloaded = json.loads(ledger_path.read_text(encoding="utf-8"))
    cmd_field = reloaded["changes"][0]["categories"]["unit"]["command"]
    assert "codex" in cmd_field
    assert "exec" in cmd_field


# ---------------------------------------------------------------------------
# 10. update_ledger writes notes with rc= and stderr excerpt
# ---------------------------------------------------------------------------

def test_update_ledger_writes_notes_with_rc_and_stderr_excerpt(tmp_path):
    ledger_path = _make_ledger(tmp_path, {"unit": {"status": "planned"}})
    executor = MirExecutor(repo_root=tmp_path, ledger_path=ledger_path)
    long_stderr = "x" * 300
    result = SubprocessResult(
        exit_code=42,
        stdout="",
        stderr=long_stderr,
        duration_seconds=0.1,
        command=["codex"],
    )
    executor.update_ledger("test-change-id", "unit", result)
    reloaded = json.loads(ledger_path.read_text(encoding="utf-8"))
    notes = reloaded["changes"][0]["categories"]["unit"]["notes"]
    assert "rc=42" in notes
    assert "x" * 200 in notes
    assert "x" * 201 not in notes


# ---------------------------------------------------------------------------
# 11. update_ledger returns previous_status
# ---------------------------------------------------------------------------

def test_update_ledger_returns_previous_status(tmp_path):
    ledger_path = _make_ledger(tmp_path, {"unit": {"status": "in_progress"}})
    executor = MirExecutor(repo_root=tmp_path, ledger_path=ledger_path)
    result = SubprocessResult(
        exit_code=0, stdout="", stderr="", duration_seconds=0.0, command=["codex"]
    )
    update = executor.update_ledger("test-change-id", "unit", result)
    assert update.previous_status == "in_progress"


# ---------------------------------------------------------------------------
# 12. update_ledger raises KeyError on unknown change_id
# ---------------------------------------------------------------------------

def test_update_ledger_raises_key_error_on_unknown_change_id(tmp_path):
    ledger_path = _make_ledger(tmp_path, {"unit": {"status": "planned"}})
    executor = MirExecutor(repo_root=tmp_path, ledger_path=ledger_path)
    result = SubprocessResult(
        exit_code=0, stdout="", stderr="", duration_seconds=0.0, command=["codex"]
    )
    with pytest.raises(KeyError, match="unknown change_id"):
        executor.update_ledger("nonexistent-id", "unit", result)


# ---------------------------------------------------------------------------
# 13. update_ledger raises KeyError on unknown category (no silent add)
# ---------------------------------------------------------------------------

def test_update_ledger_raises_key_error_on_unknown_category(tmp_path):
    ledger_path = _make_ledger(tmp_path, {"unit": {"status": "planned"}})
    executor = MirExecutor(repo_root=tmp_path, ledger_path=ledger_path)
    result = SubprocessResult(
        exit_code=0, stdout="", stderr="", duration_seconds=0.0, command=["codex"]
    )
    with pytest.raises(KeyError, match="not in entry"):
        executor.update_ledger("test-change-id", "integration", result)


# ---------------------------------------------------------------------------
# 14. update_ledger raises FileNotFoundError when ledger missing
# ---------------------------------------------------------------------------

def test_update_ledger_raises_file_not_found_when_ledger_missing(tmp_path):
    missing = tmp_path / "tasks" / "tdd.json"
    executor = MirExecutor(repo_root=tmp_path, ledger_path=missing)
    result = SubprocessResult(
        exit_code=0, stdout="", stderr="", duration_seconds=0.0, command=["codex"]
    )
    with pytest.raises(FileNotFoundError, match="Ledger not found"):
        executor.update_ledger("any-id", "unit", result)


# ---------------------------------------------------------------------------
# 15. update_ledger atomic write — result file is valid JSON, no .tmp left
# ---------------------------------------------------------------------------

def test_update_ledger_atomic_write(tmp_path):
    ledger_path = _make_ledger(tmp_path, {"unit": {"status": "planned"}})
    executor = MirExecutor(repo_root=tmp_path, ledger_path=ledger_path)
    result = SubprocessResult(
        exit_code=0, stdout="", stderr="", duration_seconds=0.1, command=["codex"]
    )
    executor.update_ledger("test-change-id", "unit", result)

    # Ledger must be valid JSON after write
    parsed = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert parsed["changes"][0]["categories"]["unit"]["status"] == "pass"

    # No .tmp files should remain in the ledger directory
    tmp_files = list(ledger_path.parent.glob("*.tmp"))
    assert tmp_files == [], f"Unexpected .tmp files: {tmp_files}"


# ---------------------------------------------------------------------------
# 16. execute() convenience method calls both run_codex and update_ledger
# ---------------------------------------------------------------------------

def test_execute_combines_run_and_update(tmp_path, monkeypatch):
    _install_fake_codex_mcp_client(
        monkeypatch,
        result=CodexMcpResult(
            content_text="ok",
            thread_id="thread-test",
            raw_result={},
        ),
    )
    ledger_path = _make_ledger(tmp_path, {"unit": {"status": "planned"}})
    executor = MirExecutor(repo_root=tmp_path, ledger_path=ledger_path)
    result, update = executor.execute(
        change_id="test-change-id",
        category="unit",
        codex_args=["--help"],
    )
    assert isinstance(result, SubprocessResult)
    assert isinstance(update, LedgerUpdate)
    assert result.exit_code == 0
    assert update.new_status == "pass"
    reloaded = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert reloaded["changes"][0]["categories"]["unit"]["status"] == "pass"


# ---------------------------------------------------------------------------
# 17. CLI execute subcommand invokes executor and updates ledger
# ---------------------------------------------------------------------------

def test_cli_execute_subcommand_invokes_executor(tmp_path, monkeypatch):
    calls, _init_kwargs = _install_fake_codex_mcp_client(
        monkeypatch,
        result=CodexMcpResult(
            content_text="cli-ok",
            thread_id="thread-test",
            raw_result={},
        ),
    )
    ledger_path = _make_ledger(tmp_path, {"unit": {"status": "planned"}})

    from tools.mir_executor.cli import main

    argv = [
        "execute",
        "--change-id", "test-change-id",
        "--category", "unit",
        "--codex-args", "exec --help",
        "--repo-root", str(tmp_path),
        "--model", "medium",
        "--reasoning-effort", "high",
    ]
    # Inject the ledger_path by pointing repo_root to tmp_path — ledger is at tasks/tdd.json
    main(argv)

    reloaded = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert reloaded["changes"][0]["categories"]["unit"]["status"] == "pass"
    assert calls[0]["model"] == "medium"
    assert calls[0]["config"] == {
        "project_doc_max_bytes": 0,
        "model_reasoning_effort": "high",
    }


# ---------------------------------------------------------------------------
# 18. execute() fails fast on unknown change_id — Codex never invoked (W3)
# ---------------------------------------------------------------------------

def test_execute_fails_fast_on_unknown_change_id_BEFORE_running_codex(tmp_path, monkeypatch):
    ledger_path = _make_ledger(tmp_path, {"unit": {"status": "planned"}})
    calls, _init_kwargs = _install_fake_codex_mcp_client(monkeypatch)
    executor = MirExecutor(repo_root=tmp_path, ledger_path=ledger_path)

    with pytest.raises(KeyError, match="unknown change_id"):
        executor.execute("WRONG-ID", "unit", ["--help"])

    assert calls == [], "Codex MCP must NOT be called when change_id is invalid."


# ---------------------------------------------------------------------------
# 19. execute() fails fast on unknown category — Codex never invoked (W3)
# ---------------------------------------------------------------------------

def test_execute_fails_fast_on_unknown_category_BEFORE_running_codex(tmp_path, monkeypatch):
    ledger_path = _make_ledger(tmp_path, {"unit": {"status": "planned"}})
    calls, _init_kwargs = _install_fake_codex_mcp_client(monkeypatch)
    executor = MirExecutor(repo_root=tmp_path, ledger_path=ledger_path)

    with pytest.raises(KeyError, match="not in entry"):
        executor.execute("test-change-id", "e2e", ["--help"])

    assert calls == [], "Codex MCP must NOT be called when category is invalid."


# ---------------------------------------------------------------------------
# 20. CLI exits rc=1 with 'timeout' in stderr on TimeoutExpired (W4)
# ---------------------------------------------------------------------------

def test_cli_handles_timeout_expired_gracefully(tmp_path, monkeypatch, capsys):
    _make_ledger(tmp_path, {"unit": {"status": "planned"}})
    _install_fake_codex_mcp_client(
        monkeypatch,
        side_effect=CodexMcpTimeoutError("mcp timed out"),
    )

    from tools.mir_executor.cli import main

    argv = [
        "execute",
        "--change-id", "test-change-id",
        "--category", "unit",
        "--codex-args", "exec pytest",
        "--repo-root", str(tmp_path),
    ]
    with pytest.raises(SystemExit) as exc_info:
        main(argv)

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "timeout" in captured.err.lower()


# ---------------------------------------------------------------------------
# 21. CLI exits rc=1 with parse error on unclosed shlex quote (W4)
# ---------------------------------------------------------------------------

def test_cli_handles_value_error_from_shlex_unclosed_quote(tmp_path, capsys):
    _make_ledger(tmp_path, {"unit": {"status": "planned"}})

    from tools.mir_executor.cli import main

    argv = [
        "execute",
        "--change-id", "test-change-id",
        "--category", "unit",
        "--codex-args", "unclosed '",
        "--repo-root", str(tmp_path),
    ]
    with pytest.raises(SystemExit) as exc_info:
        main(argv)

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "argument parse error" in captured.err or "ValueError" in captured.err


# ---------------------------------------------------------------------------
# 22. CLI exits rc=1 with 'not_applicable' in stderr on guarded category (W5)
# ---------------------------------------------------------------------------

def test_cli_handles_not_applicable_category(tmp_path, monkeypatch, capsys):
    _make_ledger(
        tmp_path,
        {"e2e": {"status": "not_applicable", "reason": "no e2e surface"}},
    )
    monkeypatch.setenv("CODEX_BIN", "/usr/bin/true")

    from tools.mir_executor.cli import main

    argv = [
        "execute",
        "--change-id", "test-change-id",
        "--category", "e2e",
        "--codex-args", "exec pytest",
        "--repo-root", str(tmp_path),
    ]
    with pytest.raises(SystemExit) as exc_info:
        main(argv)

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "not_applicable" in captured.err
