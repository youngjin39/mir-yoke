"""Tests for ADR-60 dispatch helper attempt, fallback, and CLI routing policy."""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows is not a target
    fcntl = None  # type: ignore[assignment]

import pytest

from tools.mir_executor import cli
from tools.mir_executor import dispatch as dispatch_module
from tools.mir_executor.codex_mcp_client import (
    CodexMcpProcessError,
    CodexMcpResult,
    CodexMcpTimeoutError,
)
from tools.mir_executor.dispatch import (
    _MCP_DISPATCH_BASE_INSTRUCTIONS,
    OUTAGE_THRESHOLD,
    CodexAttempt,
    DispatchOutcome,
    FinalizeResult,
    MergeGate,
    _finalize_lock,
    _last_json_line,
    _resolve_harness_self_modify,
    _run_guarded,
    build_claude_fallback,
    build_claude_runner,
    build_codex_mcp_runner,
    count_consecutive_codex_failures,
    evaluate_merge_gate,
    finalize_dispatch,
    run_dispatch,
)
from tools.mir_executor.executor import LedgerUpdate, MirExecutor, SubprocessResult
from tools.mir_executor.jobs import JobRecord, JobRegistry
from tools.mir_executor.worktree import (
    DispatchWorktree,
    MergeOutcome,
    cleanup_worktree,
    create_dispatch_worktree,
)


def _git(repo_root: pathlib.Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run git in a temp test repository."""
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _make_repo(tmp_path: pathlib.Path) -> pathlib.Path:
    """Build a real temp git repo with a plan cursor and one code file."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@e")
    _git(repo, "config", "user.name", "t")

    (repo / "tasks").mkdir()
    (repo / "pkg").mkdir()
    (repo / "tasks" / "plan.md").write_text("MAIN-PLAN-V1\n", encoding="utf-8")
    (repo / "pkg" / "mod.py").write_text("x = 1\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "init")
    return repo


def _write_repo_file(repo_root: pathlib.Path, path: str, text: str) -> None:
    target = repo_root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def _write_repo_profile(repo_root: pathlib.Path, repository_type: str) -> None:
    profile_path = repo_root / ".mir" / "repo-profile.toml"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(
        f'[repo]\nrepository_type = "{repository_type}"\n',
        encoding="utf-8",
    )


def _write_repo_profile_slug(repo_root: pathlib.Path, slug: str) -> None:
    profile_path = repo_root / ".mir" / "repo-profile.toml"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(f'[repo]\nslug = "{slug}"\n', encoding="utf-8")


def _read_events(path: pathlib.Path) -> list[dict]:
    """Read dispatch JSONL events."""
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _cleanup(outcome: DispatchOutcome) -> None:
    """Remove a retained dispatch worktree from a test outcome."""
    if outcome.worktree is not None:
        cleanup_worktree(outcome.worktree)


def _make_ledger(repo: pathlib.Path, change_id: str = "X") -> None:
    """Seed the minimal ledger shape required by the execute CLI."""
    tasks_dir = repo / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    ledger = {
        "version": 1,
        "changes": [
            {
                "id": change_id,
                "scope": "dispatch CLI test",
                "targets": ["tools/mir_executor/dispatch.py"],
                "categories": {"unit": {"status": "planned"}},
            }
        ],
    }
    (tasks_dir / "tdd.json").write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    _git(repo, "add", "tasks/tdd.json")
    _git(repo, "commit", "-m", "seed ledger")


def _write_sub_agent_policy(
    repo: pathlib.Path,
    mode: str,
    per_project: dict[str, str] | None = None,
) -> None:
    policy_path = repo / "config" / "sub-agent-policy.json"
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(
        json.dumps({"mode": mode, "per_project": per_project or {}}),
        encoding="utf-8",
    )


def _write_fake_claude_edit_bin(tmp_path: pathlib.Path) -> pathlib.Path:
    """Write a fake claude executable that records cwd and edits a worktree file."""
    fake_bin = tmp_path / "claude-edit"
    fake_bin.write_text(
        "\n".join(
            [
                "#!/bin/sh",
                "{",
                "  printf 'argv:'",
                "  for arg in \"$@\"; do printf '<%s>' \"$arg\"; done",
                "  printf '\\n'",
                "  printf 'pwd:%s\\n' \"$PWD\"",
                "  printf 'project:%s\\n' \"$CLAUDE_PROJECT_DIR\"",
                "  printf 'session:%s\\n' \"$MIR_CODEX_SESSION_ID\"",
                "} >> \"$FAKE_CLAUDE_RECORD\"",
                "printf 'x = 44\\n' > pkg/mod.py",
                "exit 0",
                "",
            ]
        ),
        encoding="utf-8",
    )
    fake_bin.chmod(0o755)
    return fake_bin


def _write_fake_claude_bin(tmp_path: pathlib.Path) -> pathlib.Path:
    """Write a fake claude executable that records argv, env, cwd, and brief file."""
    fake_bin = tmp_path / "claude"
    fake_bin.write_text(
        "\n".join(
            [
                "#!/bin/sh",
                "{",
                "  printf 'argv:'",
                "  for arg in \"$@\"; do printf '<%s>' \"$arg\"; done",
                "  printf '\\n'",
                "  printf 'pwd:%s\\n' \"$PWD\"",
                "  printf 'project:%s\\n' \"$CLAUDE_PROJECT_DIR\"",
                "  printf 'session:%s\\n' \"$MIR_CODEX_SESSION_ID\"",
                "  printf 'depth:%s\\n' \"$MIR_DISPATCH_FALLBACK_DEPTH\"",
                "  printf 'brief:%s\\n' \"$(cat .mir-dispatch/brief.md 2>/dev/null)\"",
                "} >> \"$FAKE_CLAUDE_RECORD\"",
                "exit \"$FAKE_CLAUDE_EXIT\"",
                "",
            ]
        ),
        encoding="utf-8",
    )
    fake_bin.chmod(0o755)
    return fake_bin


def _read_fake_record(record_path: pathlib.Path) -> dict[str, str]:
    """Read the fake claude record as key/value lines."""
    lines = record_path.read_text(encoding="utf-8").splitlines()
    return dict(line.split(":", 1) for line in lines)


def _patch_mcp_runner(monkeypatch, attempt_result):
    """Patch the default dispatch Codex backend and record builder calls."""
    calls: list[dict[str, object]] = []

    def fake_build_codex_mcp_runner(
        repo_root: pathlib.Path,
        prompt: str,
        *,
        timeout_seconds: int = 600,
        model: str | None = None,
        reasoning_effort: str | None = None,
        stall_timeout: float | None = None,
    ):
        calls.append(
            {
                "repo_root": repo_root,
                "prompt": prompt,
                "timeout_seconds": timeout_seconds,
                "model": model,
                "reasoning_effort": reasoning_effort,
                "stall_timeout": stall_timeout,
            }
        )

        def runner(wt: DispatchWorktree, attempt: int) -> CodexAttempt:
            if callable(attempt_result):
                return attempt_result(wt, attempt)
            return attempt_result

        return runner

    monkeypatch.setattr(
        "tools.mir_executor.dispatch.build_codex_mcp_runner",
        fake_build_codex_mcp_runner,
    )
    return calls


def _write_dispatch_brief_json(tmp_path: pathlib.Path, expanded_goal: str) -> pathlib.Path:
    """Write a minimal valid DispatchBrief JSON fixture."""
    path = tmp_path / "dispatch-brief.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "task_id": "dispatch-task",
                "phase_id": "phase",
                "slice_id": "slice",
                "target_agent": "executor-agent",
                "user_intent": "Test dispatch prompt resolution",
                "expanded_goal": expanded_goal,
                "owned_scope": ["tools/mir_executor/**"],
                "out_of_scope": ["docs/**"],
                "verification_commands": ["uv run pytest tools/mir_executor/tests -q"],
                "stop_conditions": ["Stop if scope expands."],
                "handoff_refs": [],
                "tdd_change_refs": ["tasks/tdd.json#X"],
                "resume_state_ref": "tasks/dispatch/dispatch-task/slice.json",
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
    return path


def _cleanup_repo_dispatch_worktrees(repo: pathlib.Path) -> None:
    """Remove dispatch worktrees retained by CLI-level tests."""
    current_path: pathlib.Path | None = None
    for line in _git(repo, "worktree", "list", "--porcelain").stdout.splitlines():
        if line.startswith("worktree "):
            current_path = pathlib.Path(line.removeprefix("worktree "))
            continue
        if line.startswith("branch refs/heads/mir-dispatch/") and current_path != repo.resolve():
            assert current_path is not None
            _git(repo, "worktree", "remove", "--force", str(current_path))
            current_path = None

    branches = _git(repo, "branch", "--list", "mir-dispatch/*").stdout.splitlines()
    for line in branches:
        branch = line.strip().lstrip("*").strip()
        if branch:
            _git(repo, "branch", "-D", branch)


def _completed_outcome(wt: DispatchWorktree) -> DispatchOutcome:
    """Build a completed dispatch outcome for finalize tests."""
    return DispatchOutcome("completed", 1, False, None, wt)


def test_codex_success_first_attempt(tmp_path: pathlib.Path) -> None:
    repo = _make_repo(tmp_path)
    events_path = tmp_path / "dispatch-events.jsonl"
    fallback_calls: list[DispatchWorktree] = []

    outcome = run_dispatch(
        repo,
        "success",
        codex_runner=lambda _wt, _attempt: CodexAttempt(0),
        claude_fallback=lambda wt: fallback_calls.append(wt) or CodexAttempt(0),
        dispatch_events_path=events_path,
    )
    try:
        assert outcome.status == "completed"
        assert outcome.attempts == 1
        assert outcome.fell_back is False
        assert fallback_calls == []
        assert any(event["kind"] == "codex_success" for event in _read_events(events_path))
    finally:
        _cleanup(outcome)


def test_three_codex_failures_trigger_one_fallback(tmp_path: pathlib.Path) -> None:
    repo = _make_repo(tmp_path)
    events_path = tmp_path / "dispatch-events.jsonl"
    codex_calls: list[int] = []
    fallback_calls: list[DispatchWorktree] = []

    def codex_runner(_wt: DispatchWorktree, attempt: int) -> CodexAttempt:
        codex_calls.append(attempt)
        return CodexAttempt(1, error_sig="e")

    def claude_fallback(wt: DispatchWorktree) -> CodexAttempt:
        fallback_calls.append(wt)
        return CodexAttempt(0)

    outcome = run_dispatch(
        repo,
        "fallback",
        codex_runner=codex_runner,
        claude_fallback=claude_fallback,
        dispatch_events_path=events_path,
    )
    try:
        assert codex_calls == [1, 2, 3]
        assert len(fallback_calls) == 1
        assert outcome.status == "fallback_completed"
        assert outcome.fell_back is True
        assert any(event["kind"] == "fallback" for event in _read_events(events_path))
    finally:
        _cleanup(outcome)


def test_failed_fallback_blocks(tmp_path: pathlib.Path) -> None:
    repo = _make_repo(tmp_path)
    events_path = tmp_path / "dispatch-events.jsonl"

    outcome = run_dispatch(
        repo,
        "fallback-failed",
        codex_runner=lambda _wt, _attempt: CodexAttempt(1, error_sig="e"),
        claude_fallback=lambda _wt: CodexAttempt(1),
        dispatch_events_path=events_path,
    )
    try:
        assert outcome.status == "blocked"
        assert outcome.blocked_reason == "fallback-failed"
        assert any(event["kind"] == "fallback_failed" for event in _read_events(events_path))
    finally:
        _cleanup(outcome)


def test_outage_guard_halts_without_fallback(tmp_path: pathlib.Path) -> None:
    repo = _make_repo(tmp_path)
    events_path = tmp_path / "dispatch-events.jsonl"
    fallback_calls: list[DispatchWorktree] = []

    outcome = run_dispatch(
        repo,
        "outage",
        codex_runner=lambda _wt, _attempt: CodexAttempt(1, error_sig="e"),
        claude_fallback=lambda wt: fallback_calls.append(wt) or CodexAttempt(0),
        dispatch_events_path=events_path,
        prior_consecutive_codex_failures=OUTAGE_THRESHOLD - 1,
    )
    try:
        assert outcome.status == "blocked"
        assert outcome.blocked_reason == "codex-outage"
        assert fallback_calls == []
        assert any(event["kind"] == "codex_outage_halt" for event in _read_events(events_path))
    finally:
        _cleanup(outcome)


def test_fallback_required_when_no_fallback(tmp_path: pathlib.Path) -> None:
    repo = _make_repo(tmp_path)
    events_path = tmp_path / "dispatch-events.jsonl"

    outcome = run_dispatch(
        repo,
        "no-fallback",
        codex_runner=lambda _wt, _attempt: CodexAttempt(1, error_sig="e"),
        claude_fallback=None,
        dispatch_events_path=events_path,
        prior_consecutive_codex_failures=0,
    )
    try:
        assert outcome.status == "blocked"
        assert outcome.blocked_reason == "fallback-required"
        assert any(event["kind"] == "fallback_required" for event in _read_events(events_path))
    finally:
        _cleanup(outcome)


def test_spinning_same_error_sig_short_circuits(tmp_path: pathlib.Path) -> None:
    repo = _make_repo(tmp_path)
    events_path = tmp_path / "dispatch-events.jsonl"
    codex_calls: list[int] = []

    def codex_runner(_wt: DispatchWorktree, attempt: int) -> CodexAttempt:
        codex_calls.append(attempt)
        return CodexAttempt(1, error_sig="same")

    outcome = run_dispatch(
        repo,
        "spinning",
        codex_runner=codex_runner,
        claude_fallback=None,
        dispatch_events_path=events_path,
        max_codex_attempts=5,
    )
    try:
        assert codex_calls == [1, 2, 3]
        assert outcome.status == "blocked"
        assert outcome.blocked_reason == "fallback-required"
    finally:
        _cleanup(outcome)


def test_count_consecutive_codex_failures(tmp_path: pathlib.Path) -> None:
    db_path = tmp_path / "jobs.db"
    registry = JobRegistry(db_path)
    try:
        rows = [
            ("old-completed", "completed", "2026-06-22T00:00:00+00:00"),
            ("mid-failed", "failed", "2026-06-22T00:01:00+00:00"),
            ("new-failed", "failed", "2026-06-22T00:02:00+00:00"),
        ]
        for job_id, status, started_at in rows:
            registry.insert(
                JobRecord(
                    job_id=job_id,
                    change_id="adr60-dispatch-helper",
                    category="unit",
                    family=None,
                    repo_root=str(tmp_path),
                    codex_args=["exec", "hi"],
                    timeout_seconds=600,
                    status=status,
                    started_at=started_at,
                )
            )
    finally:
        registry.close()

    assert count_consecutive_codex_failures(db_path) == 2


def test_finalize_failure_after_completed_dispatch_resets_codex_failure_run(
    tmp_path: pathlib.Path,
) -> None:
    db_path = tmp_path / "jobs.db"
    registry = JobRegistry(db_path)
    try:
        for job_id, started_at, stderr in (
            ("older-codex-failure", "2026-07-13T00:00:00+00:00", "transport failed"),
            (
                "newer-finalize-failure",
                "2026-07-13T00:01:00+00:00",
                "dispatch_status=completed finalize_action=blocked",
            ),
        ):
            registry.insert(
                JobRecord(
                    job_id=job_id,
                    change_id="X",
                    category="unit",
                    family=None,
                    repo_root=str(tmp_path),
                    codex_args=[],
                    timeout_seconds=60,
                    status="failed",
                    stderr=stderr,
                    started_at=started_at,
                )
            )
    finally:
        registry.close()

    assert count_consecutive_codex_failures(db_path) == 0


def test_last_json_line_best_effort(tmp_path: pathlib.Path) -> None:
    events_path = tmp_path / "events.jsonl"
    events_path.write_text(
        json.dumps({"exit_code": 7, "error_sig": "valid"}) + "\n" + '{"partial":',
        encoding="utf-8",
    )

    assert _last_json_line(events_path) == {"exit_code": 7, "error_sig": "valid"}

    malformed_path = tmp_path / "malformed.jsonl"
    malformed_path.write_text("not-json\n{\"partial\":\n", encoding="utf-8")

    assert _last_json_line(malformed_path) == {}


def test_run_codex_rewrites_short_workspace_write(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    calls: list[dict[str, object]] = []

    class FakeCodexMcpClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def __enter__(self) -> FakeCodexMcpClient:
            return self

        def __exit__(self, *_exc_info: object) -> None:
            return None

        def call_codex(self, **kwargs: object) -> CodexMcpResult:
            calls.append(kwargs)
            return CodexMcpResult(content_text="ok", thread_id="thread-test", raw_result={})

    monkeypatch.setenv("CODEX_BIN", "/usr/bin/true")
    monkeypatch.setenv("MIR_CODEX_MAIN", "1")
    monkeypatch.setattr("tools.mir_executor.executor.CodexMcpClient", FakeCodexMcpClient)

    executor = MirExecutor(tmp_path)
    result = executor.run_codex(
        ["exec", "-s", "workspace-write", "--skip-git-repo-check", "hello"],
        cwd=tmp_path,
    )

    assert calls[0]["prompt"] == "hello"
    assert calls[0]["sandbox"] == "danger-full-access"
    assert result.command == ["/usr/bin/true", "mcp-server", "codex", "hello"]


def test_run_codex_leaves_args_without_sandbox_flag(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    calls: list[dict[str, object]] = []

    class FakeCodexMcpClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def __enter__(self) -> FakeCodexMcpClient:
            return self

        def __exit__(self, *_exc_info: object) -> None:
            return None

        def call_codex(self, **kwargs: object) -> CodexMcpResult:
            calls.append(kwargs)
            return CodexMcpResult(content_text="ok", thread_id="thread-test", raw_result={})

    monkeypatch.setenv("CODEX_BIN", "/usr/bin/true")
    monkeypatch.setenv("MIR_CODEX_MAIN", "1")
    monkeypatch.setattr("tools.mir_executor.executor.CodexMcpClient", FakeCodexMcpClient)

    codex_args = ["exec", "--skip-git-repo-check", "hello"]
    executor = MirExecutor(tmp_path)
    result = executor.run_codex(codex_args, cwd=tmp_path)

    assert calls[0]["prompt"] == "hello"
    assert calls[0]["sandbox"] == "danger-full-access"
    assert result.command == ["/usr/bin/true", "mcp-server", "codex", "hello"]


def test_build_codex_mcp_runner_success_writes_stdout_and_event(
    tmp_path: pathlib.Path,
) -> None:
    repo = _make_repo(tmp_path)
    calls: list[dict[str, object]] = []
    init_kwargs: list[dict[str, object]] = []

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            init_kwargs.append(kwargs)

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *_exc_info: object) -> None:
            return None

        def call_codex(self, **kwargs: object) -> CodexMcpResult:
            calls.append(kwargs)
            progress_callback = kwargs.get("progress_callback")
            if callable(progress_callback):
                progress_callback("notifications/progress", {"message": "working"})
            return CodexMcpResult(
                content_text="mcp completed",
                thread_id="thread-abc",
                raw_result={},
            )

    wt = create_dispatch_worktree(repo, "mcp-success")
    try:
        runner = build_codex_mcp_runner(
            repo,
            "structured prompt",
            timeout_seconds=5,
            client_factory=FakeClient,
        )
        attempt = runner(wt, 1)
        events = _read_events(wt.path / ".mir-dispatch" / "events.jsonl")
        event = events[-1]

        assert attempt == CodexAttempt(exit_code=0, stdout="mcp completed")
        assert init_kwargs[0]["call_timeout"] == 5.0
        call = calls[0].copy()
        assert callable(call.pop("progress_callback"))
        assert [call] == [
            {
                "prompt": "structured prompt",
                "cwd": str(wt.path),
                "sandbox": "danger-full-access",
                "approval_policy": "never",
                "base_instructions": _MCP_DISPATCH_BASE_INSTRUCTIONS,
                "config": {"project_doc_max_bytes": 0},
                "timeout": 5.0,
            }
        ]
        assert events[0]["transport"] == "mcp"
        assert events[0]["event"] == "progress"
        assert events[0]["method"] == "notifications/progress"
        assert isinstance(events[0]["duration_s"], float)
        assert event["exit_code"] == 0
        assert event["transport"] == "mcp"
        assert event["threadId"] == "thread-abc"
        assert event["error_sig"] == ""
        assert isinstance(event["duration_s"], float)
    finally:
        cleanup_worktree(wt)


def test_build_codex_mcp_runner_passes_lightweight_context_options(
    tmp_path: pathlib.Path,
) -> None:
    repo = _make_repo(tmp_path)
    calls: list[dict[str, object]] = []

    class FakeClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *_exc_info: object) -> None:
            return None

        def call_codex(self, **kwargs: object) -> CodexMcpResult:
            calls.append(kwargs)
            return CodexMcpResult(
                content_text="mcp completed",
                thread_id="thread-abc",
                raw_result={},
            )

    wt = create_dispatch_worktree(repo, "mcp-lightweight-context")
    try:
        runner = build_codex_mcp_runner(
            repo,
            "structured prompt",
            timeout_seconds=5,
            client_factory=FakeClient,
        )
        attempt = runner(wt, 1)

        assert attempt.exit_code == 0
        assert calls[0]["base_instructions"] == _MCP_DISPATCH_BASE_INSTRUCTIONS
        assert calls[0]["config"] == {"project_doc_max_bytes": 0}
    finally:
        cleanup_worktree(wt)


def test_build_codex_mcp_runner_passes_model_and_reasoning_effort(
    tmp_path: pathlib.Path,
) -> None:
    repo = _make_repo(tmp_path)
    calls: list[dict[str, object]] = []

    class FakeClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *_exc_info: object) -> None:
            return None

        def call_codex(self, **kwargs: object) -> CodexMcpResult:
            calls.append(kwargs)
            return CodexMcpResult(
                content_text="mcp completed",
                thread_id="thread-abc",
                raw_result={},
            )

    wt = create_dispatch_worktree(repo, "mcp-performance-route")
    try:
        runner = build_codex_mcp_runner(
            repo,
            "structured prompt",
            timeout_seconds=5,
            model="high",
            reasoning_effort="xhigh",
            client_factory=FakeClient,
        )
        attempt = runner(wt, 1)

        assert attempt.exit_code == 0
        assert calls[0]["model"] == "high"
        assert calls[0]["config"] == {
            "project_doc_max_bytes": 0,
            "model_reasoning_effort": "xhigh",
        }
        assert calls[0]["base_instructions"] == _MCP_DISPATCH_BASE_INSTRUCTIONS
    finally:
        cleanup_worktree(wt)


def test_build_codex_mcp_runner_timeout_maps_to_124_and_event(
    tmp_path: pathlib.Path,
) -> None:
    repo = _make_repo(tmp_path)

    class TimeoutClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def __enter__(self) -> TimeoutClient:
            return self

        def __exit__(self, *_exc_info: object) -> None:
            return None

        def call_codex(self, **_kwargs: object) -> CodexMcpResult:
            raise CodexMcpTimeoutError("mcp timed out")

    wt = create_dispatch_worktree(repo, "mcp-timeout")
    try:
        runner = build_codex_mcp_runner(
            repo,
            "structured prompt",
            timeout_seconds=5,
            client_factory=TimeoutClient,
        )
        attempt = runner(wt, 1)
        event = _last_json_line(wt.path / ".mir-dispatch" / "events.jsonl")

        assert attempt.exit_code == 124
        assert "mcp timed out" in attempt.stderr
        assert len(attempt.error_sig) == 12
        assert event["exit_code"] == 124
        assert event["transport"] == "mcp"
        assert event["threadId"] is None
        assert event["error_sig"] == attempt.error_sig
    finally:
        cleanup_worktree(wt)


def test_build_codex_mcp_runner_transport_error_maps_to_nonzero(
    tmp_path: pathlib.Path,
) -> None:
    repo = _make_repo(tmp_path)

    class ErrorClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def __enter__(self) -> ErrorClient:
            return self

        def __exit__(self, *_exc_info: object) -> None:
            return None

        def call_codex(self, **_kwargs: object) -> CodexMcpResult:
            raise CodexMcpProcessError("mcp server died")

    wt = create_dispatch_worktree(repo, "mcp-error")
    try:
        runner = build_codex_mcp_runner(
            repo,
            "structured prompt",
            timeout_seconds=5,
            client_factory=ErrorClient,
        )
        attempt = runner(wt, 1)
        event = _last_json_line(wt.path / ".mir-dispatch" / "events.jsonl")

        assert attempt.exit_code != 0
        assert "mcp server died" in attempt.stderr
        assert len(attempt.error_sig) == 12
        assert event["exit_code"] == attempt.exit_code
        assert event["transport"] == "mcp"
        assert event["error_sig"] == attempt.error_sig
    finally:
        cleanup_worktree(wt)


@pytest.mark.parametrize(
    ("codex_args", "expected_prompt"),
    [
        (
            [
                "exec",
                "--sandbox",
                "workspace-write",
                "--skip-git-repo-check",
                "Implement ADR-66 S4",
            ],
            "Implement ADR-66 S4",
        ),
        (
            [
                "exec",
                "--sandbox=danger-full-access",
                "--approval-policy",
                "never",
                "--enable",
                "feature_x",
                "--image",
                "screenshot.png",
                "Run full tests",
            ],
            "Run full tests",
        ),
        (["exec", "--", "--literal prompt"], "--literal prompt"),
        (["Implement without exec token"], "Implement without exec token"),
    ],
)
def test_dispatch_prompt_from_codex_args_drops_exec_shape(
    codex_args: list[str],
    expected_prompt: str,
) -> None:
    assert cli._resolve_dispatch_prompt(codex_args, None) == expected_prompt


def test_dispatch_prompt_uses_dispatch_brief_when_codex_args_have_no_prompt(
    tmp_path: pathlib.Path,
) -> None:
    brief_path = _write_dispatch_brief_json(tmp_path, "Brief expanded goal")

    assert (
        cli._resolve_dispatch_prompt(
            ["exec", "--sandbox", "danger-full-access", "--skip-git-repo-check"],
            brief_path,
        )
        == "Brief expanded goal"
    )


def test_dispatch_prompt_falls_back_to_brief_pointer_when_no_prompt_source() -> None:
    assert ".mir-dispatch/brief.md" in cli._resolve_dispatch_prompt(["exec", "--help"], None)


def test_build_dispatch_runner_defaults_codex_backend_to_mcp(monkeypatch) -> None:
    selected: list[str] = []

    def mcp_runner(_wt: object, _attempt: int) -> CodexAttempt:
        return CodexAttempt(0)

    def fake_mcp_runner(
        _repo_root: pathlib.Path,
        prompt: str,
        *,
        timeout_seconds: int = 600,
    ):
        _ = timeout_seconds
        selected.append(f"mcp:{prompt}")
        return mcp_runner

    monkeypatch.setattr(
        "tools.mir_executor.dispatch.build_codex_mcp_runner",
        fake_mcp_runner,
    )

    runner = cli._build_dispatch_runner(
        __import__("tools.mir_executor.dispatch", fromlist=["dispatch"]),
        backend="codex",
        repo_root=pathlib.Path("/repo"),
        prompt="structured prompt",
        timeout_seconds=5,
    )

    assert selected == ["mcp:structured prompt"]
    assert runner is mcp_runner


def test_build_dispatch_runner_passes_performance_options_to_codex_mcp(
    monkeypatch,
) -> None:
    selected: list[dict[str, object]] = []

    def mcp_runner(_wt: object, _attempt: int) -> CodexAttempt:
        return CodexAttempt(0)

    def fake_mcp_runner(
        _repo_root: pathlib.Path,
        prompt: str,
        *,
        timeout_seconds: int = 600,
        model: str | None = None,
        reasoning_effort: str | None = None,
    ):
        selected.append(
            {
                "prompt": prompt,
                "timeout_seconds": timeout_seconds,
                "model": model,
                "reasoning_effort": reasoning_effort,
            }
        )
        return mcp_runner

    monkeypatch.setattr(
        "tools.mir_executor.dispatch.build_codex_mcp_runner",
        fake_mcp_runner,
    )

    runner = cli._build_dispatch_runner(
        __import__("tools.mir_executor.dispatch", fromlist=["dispatch"]),
        backend="codex",
        repo_root=pathlib.Path("/repo"),
        prompt="structured prompt",
        timeout_seconds=5,
        model="medium",
        reasoning_effort="high",
    )

    assert selected == [
        {
            "prompt": "structured prompt",
            "timeout_seconds": 5,
            "model": "medium",
            "reasoning_effort": "high",
        }
    ]
    assert runner is mcp_runner


def test_execute_parser_accepts_performance_options(tmp_path: pathlib.Path) -> None:
    parser = cli._build_parser()

    args = parser.parse_args(
        [
            "execute",
            "--change-id",
            "X",
            "--category",
            "unit",
            "--codex-args",
            "exec hi",
            "--repo-root",
            str(tmp_path),
            "--model",
            "low",
            "--reasoning-effort",
            "xhigh",
        ]
    )

    assert args.model == "low"
    assert args.reasoning_effort == "xhigh"


def test_execute_parser_rejects_both_codex_arg_sources(
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    parser = cli._build_parser()
    prompt_path = tmp_path / "prompt.txt"
    prompt_path.write_text("prompt", encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(
            [
                "execute",
                "--change-id",
                "X",
                "--category",
                "unit",
                "--codex-args",
                "exec hi",
                "--codex-args-file",
                str(prompt_path),
                "--repo-root",
                str(tmp_path),
            ]
        )

    assert exc_info.value.code == 2
    assert "not allowed with argument" in capsys.readouterr().err


def test_execute_without_codex_arg_source_fails_semantically(
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli.main(
            [
                "execute",
                "--change-id",
                "X",
                "--category",
                "unit",
                "--repo-root",
                str(tmp_path),
            ]
        )
    assert exc_info.value.code == 1
    assert "exactly one of --codex-args or --codex-args-file" in capsys.readouterr().err


def test_execute_parser_accepts_allow_harness_self_modify_flag(
    tmp_path: pathlib.Path,
) -> None:
    parser = cli._build_parser()

    base_args = [
        "execute",
        "--change-id",
        "X",
        "--category",
        "unit",
        "--codex-args",
        "exec hi",
        "--repo-root",
        str(tmp_path),
    ]

    assert parser.parse_args(base_args).allow_harness_self_modify is False
    assert (
        parser.parse_args([*base_args, "--allow-harness-self-modify"])
        .allow_harness_self_modify
        is True
    )


def test_run_guarded_uses_timeout_stdin_and_env(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    calls: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls["command"] = command
        calls.update(kwargs)
        return subprocess.CompletedProcess(command, 0, stdout="out", stderr="err")

    monkeypatch.setattr("tools.mir_executor.dispatch.subprocess.run", fake_run)

    completed = _run_guarded(["claude", "-p", "brief"], tmp_path, {"X": "Y"}, 42)

    assert completed.returncode == 0
    assert calls["command"] == ["claude", "-p", "brief"]
    assert calls["cwd"] == str(tmp_path)
    assert calls["env"] == {"X": "Y"}
    assert calls["timeout"] == 42
    assert calls["stdin"] == subprocess.DEVNULL
    assert calls["capture_output"] is True
    assert calls["text"] is True


def test_build_claude_fallback_invocation_and_env(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    repo = _make_repo(tmp_path)
    record_path = tmp_path / "fake-claude-record.txt"
    fake_claude = _write_fake_claude_bin(tmp_path)
    monkeypatch.setenv("CLAUDE_BIN", str(fake_claude))
    monkeypatch.setenv("FAKE_CLAUDE_RECORD", str(record_path))
    monkeypatch.setenv("FAKE_CLAUDE_EXIT", "13")

    wt = create_dispatch_worktree(repo, "claude-fallback", brief_text="brief body")
    try:
        fallback = build_claude_fallback(repo, timeout_seconds=5)
        attempt = fallback(wt)
        record = _read_fake_record(record_path)

        assert attempt.exit_code == 13
        assert record["argv"].startswith(
            "<-p><Read the task brief at .mir-dispatch/brief.md"
        )
        assert "brief body" not in record["argv"]
        assert record["pwd"] == str(wt.path)
        assert record["project"] == str(wt.path)
        assert record["session"] == wt.dispatch_id
        assert record["depth"] == "1"
        assert record["brief"] == "brief body"
    finally:
        cleanup_worktree(wt)


def test_build_claude_runner_invocation_and_env(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    repo = _make_repo(tmp_path)
    record_path = tmp_path / "fake-claude-record.txt"
    fake_claude = _write_fake_claude_bin(tmp_path)
    monkeypatch.setenv("CLAUDE_BIN", str(fake_claude))
    monkeypatch.setenv("FAKE_CLAUDE_RECORD", str(record_path))
    monkeypatch.setenv("FAKE_CLAUDE_EXIT", "0")

    wt = create_dispatch_worktree(repo, "claude-runner", brief_text="brief body")
    try:
        runner = build_claude_runner(repo, timeout_seconds=5)
        attempt = runner(wt, 1)
        record = _read_fake_record(record_path)

        assert attempt.exit_code == 0
        assert record["argv"].startswith(
            "<-p><Read the task brief at .mir-dispatch/brief.md"
        )
        assert "brief body" not in record["argv"]
        assert record["pwd"] == str(wt.path)
        assert record["project"] == str(wt.path)
        assert record["session"] == wt.dispatch_id
        assert record["depth"] == ""
        assert record["brief"] == "brief body"
    finally:
        cleanup_worktree(wt)


def test_fallback_depth_guard_refuses_nested(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    repo = _make_repo(tmp_path)
    record_path = tmp_path / "fake-claude-record.txt"
    fake_claude = _write_fake_claude_bin(tmp_path)
    monkeypatch.setenv("CLAUDE_BIN", str(fake_claude))
    monkeypatch.setenv("FAKE_CLAUDE_RECORD", str(record_path))
    monkeypatch.setenv("FAKE_CLAUDE_EXIT", "0")
    monkeypatch.setenv("MIR_DISPATCH_FALLBACK_DEPTH", "1")

    wt = create_dispatch_worktree(repo, "nested-fallback")
    try:
        fallback = build_claude_fallback(repo, timeout_seconds=5)
        attempt = fallback(wt)

        assert attempt.exit_code == 70
        assert attempt.stderr == "fallback-depth-exceeded"
        assert not record_path.exists()
    finally:
        cleanup_worktree(wt)


def test_run_dispatch_uses_real_fallback_once(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    repo = _make_repo(tmp_path)
    events_path = tmp_path / "dispatch-events.jsonl"
    record_path = tmp_path / "fake-claude-record.txt"
    fake_claude = _write_fake_claude_bin(tmp_path)
    monkeypatch.setenv("CLAUDE_BIN", str(fake_claude))
    monkeypatch.setenv("FAKE_CLAUDE_RECORD", str(record_path))
    monkeypatch.setenv("FAKE_CLAUDE_EXIT", "0")

    outcome = run_dispatch(
        repo,
        "real-fallback-once",
        brief_text="implement fallback",
        codex_runner=lambda _wt, _attempt: CodexAttempt(1, error_sig="e"),
        claude_fallback=build_claude_fallback(repo, timeout_seconds=5),
        dispatch_events_path=events_path,
    )
    try:
        lines = record_path.read_text(encoding="utf-8").splitlines()
        assert outcome.status == "fallback_completed"
        assert outcome.fell_back is True
        assert sum(1 for line in lines if line.startswith("argv:")) == 1
    finally:
        _cleanup(outcome)


def test_run_dispatch_blocks_when_real_fallback_fails(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    repo = _make_repo(tmp_path)
    events_path = tmp_path / "dispatch-events.jsonl"
    record_path = tmp_path / "fake-claude-record.txt"
    fake_claude = _write_fake_claude_bin(tmp_path)
    monkeypatch.setenv("CLAUDE_BIN", str(fake_claude))
    monkeypatch.setenv("FAKE_CLAUDE_RECORD", str(record_path))
    monkeypatch.setenv("FAKE_CLAUDE_EXIT", "2")

    outcome = run_dispatch(
        repo,
        "real-fallback-fails",
        codex_runner=lambda _wt, _attempt: CodexAttempt(1, error_sig="e"),
        claude_fallback=build_claude_fallback(repo, timeout_seconds=5),
        dispatch_events_path=events_path,
    )
    try:
        assert outcome.status == "blocked"
        assert outcome.fell_back is True
        assert outcome.blocked_reason == "fallback-failed"
        assert record_path.exists()
    finally:
        _cleanup(outcome)


def test_dispatch_records_jobregistry_and_outage_accumulates(
    tmp_path: pathlib.Path,
    monkeypatch,
    capsys,
) -> None:
    repo = _make_repo(tmp_path)
    _make_ledger(repo, change_id="C")
    db_path = tmp_path / "jobs.db"
    mcp_calls = _patch_mcp_runner(monkeypatch, CodexAttempt(9, error_sig="mcp-dead"))

    argv = [
        "execute",
        "--background",
        "--dispatch",
        "--change-id",
        "C",
        "--category",
        "unit",
        "--repo-root",
        str(repo),
        "--jobs-db",
        str(db_path),
        "--codex-args",
        "exec x",
        "--timeout",
        "5",
    ]
    try:
        for _ in range(OUTAGE_THRESHOLD):
            with pytest.raises(SystemExit) as excinfo:
                cli.main(argv)
            assert excinfo.value.code == 1
            capsys.readouterr()

        assert count_consecutive_codex_failures(db_path, change_id_prefix="C") >= OUTAGE_THRESHOLD

        with pytest.raises(SystemExit) as excinfo:
            cli.main(argv)
        assert excinfo.value.code == 1
        assert "reason='codex-outage'" in capsys.readouterr().out
        assert mcp_calls
        assert {call["prompt"] for call in mcp_calls} == {"x"}

        registry = JobRegistry(db_path)
        try:
            jobs = registry.list_jobs()
            assert len(jobs) == OUTAGE_THRESHOLD + 1
            assert {job.status for job in jobs} == {"failed"}
        finally:
            registry.close()
    finally:
        _cleanup_repo_dispatch_worktrees(repo)


def test_dispatch_records_exit_code_and_artifact(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    repo = _make_repo(tmp_path)
    _make_ledger(repo, change_id="C")
    db_path = tmp_path / "jobs.db"
    mcp_calls = _patch_mcp_runner(monkeypatch, CodexAttempt(0))

    try:
        rc = cli.main(
            [
                "execute",
                "--background",
                "--dispatch",
                "--change-id",
                "C",
                "--category",
                "unit",
                "--repo-root",
                str(repo),
                "--jobs-db",
                str(db_path),
                "--codex-args",
                "exec x",
                "--timeout",
                "5",
                "--no-expect-changes",
                "--allow-path",
                "pkg/",
                "--verify-cmd",
                "true",
            ]
        )

        assert rc == 0
        assert mcp_calls[0]["prompt"] == "x"
        registry = JobRegistry(db_path)
        try:
            jobs = registry.list_jobs()
            assert len(jobs) == 1
            job = jobs[0]
            assert job.status == "completed"
            assert job.exit_code == 0
            assert job.stdout is not None
            assert "artifacts=tasks/dispatch/" in job.stdout
            assert job.stderr is None
            assert (repo / "tasks" / "dispatch" / job.job_id / "status.json").exists()
        finally:
            registry.close()
    finally:
        _cleanup_repo_dispatch_worktrees(repo)


def test_dispatch_exit_code_reflects_finalize_block(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    repo = _make_repo(tmp_path)
    _make_ledger(repo, change_id="C")
    db_path = tmp_path / "jobs.db"
    mcp_calls = _patch_mcp_runner(monkeypatch, CodexAttempt(0))

    try:
        with pytest.raises(SystemExit) as excinfo:
            cli.main(
                [
                    "execute",
                    "--background",
                    "--dispatch",
                    "--change-id",
                    "C",
                    "--category",
                    "unit",
                    "--repo-root",
                    str(repo),
                    "--jobs-db",
                    str(db_path),
                    "--codex-args",
                    "exec x",
                    "--timeout",
                    "5",
                ]
            )

        assert excinfo.value.code == 1
        assert mcp_calls[0]["prompt"] == "x"
        registry = JobRegistry(db_path)
        try:
            jobs = registry.list_jobs()
            assert len(jobs) == 1
            job = jobs[0]
            assert job.status == "failed"
            assert job.exit_code == 1
            assert job.stdout == f"artifacts=tasks/dispatch/{job.job_id}"
            artifact_path = repo / job.stdout.removeprefix("artifacts=") / "status.json"
            assert artifact_path.exists()
            assert job.stderr is not None
            assert "dispatch_status=completed" in job.stderr
            assert "finalize_action=blocked" in job.stderr
            assert "blocked_reason=empty-diff fail-closed" in job.stderr
        finally:
            registry.close()
    finally:
        _cleanup_repo_dispatch_worktrees(repo)


def test_dispatch_records_fallback_merge_as_completed(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    repo = _make_repo(tmp_path)
    _make_ledger(repo, change_id="C")
    db_path = tmp_path / "jobs.db"
    _patch_mcp_runner(monkeypatch, CodexAttempt(0))
    wt = create_dispatch_worktree(repo, "cli-fallback-merged-status")

    monkeypatch.setattr(
        "tools.mir_executor.dispatch.run_dispatch",
        lambda *_args, **_kwargs: DispatchOutcome(
            "fallback_completed",
            4,
            True,
            None,
            wt,
        ),
    )
    monkeypatch.setattr(
        "tools.mir_executor.dispatch.finalize_dispatch",
        lambda *_args, **_kwargs: FinalizeResult("merged", "approved", ["pkg/mod.py"]),
    )

    try:
        assert (
            cli.main(
                [
                    "execute",
                    "--background",
                    "--dispatch",
                    "--change-id",
                    "C",
                    "--category",
                    "unit",
                    "--repo-root",
                    str(repo),
                    "--jobs-db",
                    str(db_path),
                    "--codex-args",
                    "exec x",
                ]
            )
            == 0
        )
        registry = JobRegistry(db_path)
        try:
            job = registry.list_jobs()[0]
            assert job.status == "completed"
            assert job.exit_code == 0
        finally:
            registry.close()
    finally:
        cleanup_worktree(wt)


def test_mcp_failure_still_counts_as_codex_failure(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    repo = _make_repo(tmp_path)
    _make_ledger(repo, change_id="C")
    db_path = tmp_path / "jobs.db"
    mcp_calls = _patch_mcp_runner(monkeypatch, CodexAttempt(9, error_sig="mcp-dead"))

    try:
        with pytest.raises(SystemExit) as excinfo:
            cli.main(
                [
                    "execute",
                    "--background",
                    "--dispatch",
                    "--change-id",
                    "C",
                    "--category",
                    "unit",
                    "--repo-root",
                    str(repo),
                    "--jobs-db",
                    str(db_path),
                    "--codex-args",
                    "exec x",
                    "--timeout",
                    "5",
                ]
            )

        assert excinfo.value.code == 1
        assert mcp_calls[0]["prompt"] == "x"
        registry = JobRegistry(db_path)
        try:
            jobs = registry.list_jobs()
            assert len(jobs) == 1
            job = jobs[0]
            assert job.status == "failed"
            assert job.exit_code == 1
            assert job.stdout == f"artifacts=tasks/dispatch/{job.job_id}"
        finally:
            registry.close()
    finally:
        _cleanup_repo_dispatch_worktrees(repo)


def test_spinning_emits_event(tmp_path: pathlib.Path) -> None:
    repo = _make_repo(tmp_path)
    events_path = tmp_path / "dispatch-events.jsonl"
    codex_calls: list[int] = []

    def codex_runner(_wt: DispatchWorktree, attempt: int) -> CodexAttempt:
        codex_calls.append(attempt)
        return CodexAttempt(1, error_sig="same")

    outcome = run_dispatch(
        repo,
        "spinning-event",
        codex_runner=codex_runner,
        claude_fallback=None,
        dispatch_events_path=events_path,
        max_codex_attempts=5,
    )
    try:
        assert codex_calls == [1, 2, 3]
        assert any(event["kind"] == "spinning" for event in _read_events(events_path))
    finally:
        _cleanup(outcome)


def test_evaluate_merge_gate_meta_harness_allows_source_in_allowlist(
    tmp_path: pathlib.Path,
) -> None:
    repo = _make_repo(tmp_path)
    wt = create_dispatch_worktree(repo, "gate-meta-source")
    path = ".claude/agents/example.md"
    try:
        _write_repo_file(wt.path, path, "WORKTREE\n")
        _git(wt.path, "add", path)
        _git(wt.path, "commit", "-m", "change harness source")

        gate = evaluate_merge_gate(
            wt,
            allowlist=[".claude/"],
            verification_commands=["true"],
            allow_harness_self_modify=True,
        )

        assert gate.approved is True
        assert gate.reason == "approved"
        assert gate.changed_files == [path]
    finally:
        cleanup_worktree(wt)


def test_evaluate_merge_gate_meta_harness_still_denies_plan(tmp_path: pathlib.Path) -> None:
    repo = _make_repo(tmp_path)
    wt = create_dispatch_worktree(repo, "gate-meta-plan")
    try:
        (wt.path / "tasks" / "plan.md").write_text("WORKTREE\n", encoding="utf-8")
        _git(wt.path, "add", "tasks/plan.md")
        _git(wt.path, "commit", "-m", "change plan")

        gate = evaluate_merge_gate(
            wt,
            allowlist=["tasks/"],
            verification_commands=["true"],
            allow_harness_self_modify=True,
        )

        assert gate.approved is False
        assert gate.reason.startswith("denied-harness:tasks/plan.md")
    finally:
        cleanup_worktree(wt)


def test_evaluate_merge_gate_default_denies_source(tmp_path: pathlib.Path) -> None:
    repo = _make_repo(tmp_path)
    wt = create_dispatch_worktree(repo, "gate-default-source")
    path = ".claude/agents/example.md"
    try:
        _write_repo_file(wt.path, path, "WORKTREE\n")
        _git(wt.path, "add", path)
        _git(wt.path, "commit", "-m", "change harness source")

        gate = evaluate_merge_gate(
            wt,
            allowlist=[".claude/"],
            verification_commands=["true"],
        )

        assert gate.approved is False
        assert gate.reason.startswith(f"denied-harness:{path}")
    finally:
        cleanup_worktree(wt)


def test_evaluate_merge_gate_meta_harness_source_out_of_allowlist(
    tmp_path: pathlib.Path,
) -> None:
    repo = _make_repo(tmp_path)
    wt = create_dispatch_worktree(repo, "gate-meta-source-out-of-allowlist")
    path = ".claude/agents/example.md"
    try:
        _write_repo_file(wt.path, path, "WORKTREE\n")
        _git(wt.path, "add", path)
        _git(wt.path, "commit", "-m", "change harness source")

        gate = evaluate_merge_gate(
            wt,
            allowlist=["pkg/"],
            verification_commands=["true"],
            allow_harness_self_modify=True,
        )

        assert gate.approved is False
        assert gate.reason.startswith(f"out-of-allowlist:{path}")
    finally:
        cleanup_worktree(wt)


def test_finalize_dispatch_default_denies_docs_even_when_allowlisted(
    tmp_path: pathlib.Path,
) -> None:
    repo = _make_repo(tmp_path)
    wt = create_dispatch_worktree(repo, "finalize-docs-default-denied")
    path = "docs/decisions/example.md"
    try:
        _write_repo_file(wt.path, path, "WORKTREE\n")

        final = finalize_dispatch(
            wt,
            repo,
            _completed_outcome(wt),
            allowlist=["docs/"],
            verification_commands=["true"],
        )

        assert final.action == "blocked"
        assert final.reason.startswith(f"denied-harness:{path}")
        assert not (repo / path).exists()
    finally:
        cleanup_worktree(wt)


def test_finalize_dispatch_allow_harness_self_modify_merges_docs_when_allowlisted(
    tmp_path: pathlib.Path,
) -> None:
    repo = _make_repo(tmp_path)
    wt = create_dispatch_worktree(repo, "finalize-docs-flag-allowed")
    path = "docs/decisions/example.md"
    try:
        _write_repo_file(wt.path, path, "WORKTREE\n")

        final = finalize_dispatch(
            wt,
            repo,
            _completed_outcome(wt),
            allowlist=["docs/"],
            verification_commands=["true"],
            allow_harness_self_modify=True,
        )

        assert final.action == "merged"
        assert final.reason == "approved"
        assert final.merged_files == [path]
        assert (repo / path).read_text(encoding="utf-8") == "WORKTREE\n"
    finally:
        cleanup_worktree(wt)


def test_finalize_dispatch_allow_harness_self_modify_still_denies_tasks(
    tmp_path: pathlib.Path,
) -> None:
    repo = _make_repo(tmp_path)
    wt = create_dispatch_worktree(repo, "finalize-tasks-flag-denied")
    try:
        (wt.path / "tasks" / "plan.md").write_text("WORKTREE\n", encoding="utf-8")

        final = finalize_dispatch(
            wt,
            repo,
            _completed_outcome(wt),
            allowlist=["tasks/"],
            verification_commands=["true"],
            allow_harness_self_modify=True,
        )

        assert final.action == "blocked"
        assert final.reason.startswith("denied-harness:tasks/plan.md")
        assert (repo / "tasks" / "plan.md").read_text(encoding="utf-8") == "MAIN-PLAN-V1\n"
    finally:
        cleanup_worktree(wt)


def test_resolve_harness_self_modify(tmp_path: pathlib.Path) -> None:
    meta = tmp_path / "meta"
    meta.mkdir()
    _write_repo_profile(meta, "meta_harness")

    content = tmp_path / "content"
    content.mkdir()
    _write_repo_profile(content, "content_app")

    missing = tmp_path / "missing"
    missing.mkdir()

    assert _resolve_harness_self_modify(meta) is True
    assert _resolve_harness_self_modify(content) is False
    assert _resolve_harness_self_modify(missing) is False


def test_merge_gate_approves_clean_allowlist_and_verify(tmp_path: pathlib.Path) -> None:
    repo = _make_repo(tmp_path)
    wt = create_dispatch_worktree(repo, "gate-approve")
    try:
        (wt.path / "pkg" / "mod.py").write_text("x = 2\n", encoding="utf-8")

        final = finalize_dispatch(
            wt,
            repo,
            _completed_outcome(wt),
            allowlist=["pkg/"],
            verification_commands=["true"],
        )

        assert final.action == "merged"
        assert final.reason == "approved"
        assert final.merged_files == ["pkg/mod.py"]
        assert (repo / "pkg" / "mod.py").read_text(encoding="utf-8") == "x = 2\n"
        assert str(wt.path) not in _git(repo, "worktree", "list").stdout
    finally:
        cleanup_worktree(wt)


def test_finalize_allows_unrelated_wip_and_preserves_its_index_and_status(
    tmp_path: pathlib.Path,
) -> None:
    repo = _make_repo(tmp_path)
    _write_repo_file(repo, "wip/staged.txt", "staged base\n")
    _write_repo_file(repo, "wip/unstaged.txt", "unstaged base\n")
    (repo / ".gitignore").write_text("*.ignored\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "seed unrelated wip paths")
    wt = create_dispatch_worktree(repo, "path-scoped-wip")
    try:
        (wt.path / "pkg" / "mod.py").write_text("x = 24\n", encoding="utf-8")

        (repo / "wip" / "staged.txt").write_text("staged wip\n", encoding="utf-8")
        _git(repo, "add", "wip/staged.txt")
        (repo / "wip" / "unstaged.txt").write_text("unstaged wip\n", encoding="utf-8")
        (repo / "wip" / "untracked.txt").write_text("untracked wip\n", encoding="utf-8")
        (repo / "wip" / "cache.ignored").write_text("ignored wip\n", encoding="utf-8")
        status_before = _git(
            repo,
            "status",
            "--porcelain",
            "--ignored",
            "--",
            "wip",
        ).stdout
        staged_before = _git(repo, "diff", "--cached", "--binary", "--", "wip").stdout
        unstaged_before = _git(repo, "diff", "--binary", "--", "wip").stdout

        final = finalize_dispatch(
            wt,
            repo,
            _completed_outcome(wt),
            allowlist=["pkg/mod.py"],
            verification_commands=["true"],
        )

        assert final == FinalizeResult("merged", "approved", ["pkg/mod.py"])
        assert (repo / "pkg" / "mod.py").read_text(encoding="utf-8") == "x = 24\n"
        assert _git(
            repo,
            "status",
            "--porcelain",
            "--ignored",
            "--",
            "wip",
        ).stdout == status_before
        assert _git(repo, "diff", "--cached", "--binary", "--", "wip").stdout == staged_before
        assert _git(repo, "diff", "--binary", "--", "wip").stdout == unstaged_before
    finally:
        cleanup_worktree(wt)


@pytest.mark.parametrize("ignored", [False, True], ids=["untracked", "ignored"])
def test_finalize_blocks_untracked_target_collision(
    tmp_path: pathlib.Path,
    ignored: bool,
) -> None:
    repo = _make_repo(tmp_path)
    target = "pkg/generated.ignored" if ignored else "pkg/generated.py"
    if ignored:
        (repo / ".gitignore").write_text("*.ignored\n", encoding="utf-8")
        _git(repo, "add", ".gitignore")
        _git(repo, "commit", "-m", "seed ignore rule")
    wt = create_dispatch_worktree(repo, f"target-collision-{ignored}")
    try:
        _write_repo_file(wt.path, target, "dispatch output\n")
        if ignored:
            _git(wt.path, "add", "-f", target)
            _git(wt.path, "commit", "-m", "add ignored dispatch output")
        _write_repo_file(repo, target, "main wip\n")

        final = finalize_dispatch(
            wt,
            repo,
            _completed_outcome(wt),
            allowlist=[target],
            verification_commands=["true"],
        )

        assert final.action == "blocked"
        assert final.reason.startswith("main-dirty")
        assert (repo / target).read_text(encoding="utf-8") == "main wip\n"
        assert wt.path.exists()
    finally:
        cleanup_worktree(wt)


def test_finalize_blocks_head_absent_parent_type_collision(tmp_path: pathlib.Path) -> None:
    repo = _make_repo(tmp_path)
    wt = create_dispatch_worktree(repo, "target-parent-type-collision")
    try:
        _write_repo_file(wt.path, "generated/output.py", "dispatch output\n")
        (repo / "generated").write_text("main file collision\n", encoding="utf-8")

        final = finalize_dispatch(
            wt,
            repo,
            _completed_outcome(wt),
            allowlist=["generated/output.py"],
            verification_commands=["true"],
        )

        assert final == FinalizeResult("blocked", "main-dirty", [])
        assert (repo / "generated").read_text(encoding="utf-8") == "main file collision\n"
        assert wt.path.exists()
    finally:
        (repo / "generated").unlink()
        cleanup_worktree(wt)


@pytest.mark.skipif(fcntl is None, reason="fcntl is unavailable")
def test_finalize_lock_is_mutually_exclusive_and_releases(
    tmp_path: pathlib.Path,
) -> None:
    repo = _make_repo(tmp_path)

    with _finalize_lock(repo, 0) as first_acquired:
        assert first_acquired is True
        with _finalize_lock(repo, 0) as second_acquired:
            assert second_acquired is False

    with _finalize_lock(repo, 0) as acquired_after_release:
        assert acquired_after_release is True


@pytest.mark.skipif(fcntl is None, reason="fcntl is unavailable")
def test_finalize_dispatch_times_out_on_held_lock_without_merging(
    tmp_path: pathlib.Path,
) -> None:
    repo = _make_repo(tmp_path)
    wt = create_dispatch_worktree(repo, "finalize-lock-timeout")
    lock_path = repo / ".mir" / "dispatch-finalize.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        (wt.path / "pkg" / "mod.py").write_text("x = 22\n", encoding="utf-8")
        with lock_path.open("a+") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            main_head = _git(repo, "rev-parse", "HEAD").stdout
            main_status = _git(repo, "status", "--porcelain").stdout
            final = finalize_dispatch(
                wt,
                repo,
                _completed_outcome(wt),
                allowlist=["pkg/"],
                verification_commands=["true"],
                finalize_lock_timeout=0,
            )

        assert final == FinalizeResult("blocked", "finalize-lock-timeout", [])
        assert _git(repo, "rev-parse", "HEAD").stdout == main_head
        assert set(_git(repo, "status", "--porcelain").stdout.splitlines()) == {
            *main_status.splitlines(),
            "?? tasks/dispatch/",
        }
        assert (repo / "pkg" / "mod.py").read_text(encoding="utf-8") == "x = 1\n"
        assert (
            repo / "tasks" / "dispatch" / wt.dispatch_id / "status.json"
        ).exists()
    finally:
        cleanup_worktree(wt)


def test_finalize_dispatch_with_free_lock_merges_normally(
    tmp_path: pathlib.Path,
) -> None:
    repo = _make_repo(tmp_path)
    wt = create_dispatch_worktree(repo, "finalize-lock-free")
    try:
        (wt.path / "pkg" / "mod.py").write_text("x = 23\n", encoding="utf-8")

        final = finalize_dispatch(
            wt,
            repo,
            _completed_outcome(wt),
            allowlist=["pkg/"],
            verification_commands=["true"],
            finalize_lock_timeout=0,
        )

        assert final == FinalizeResult("merged", "approved", ["pkg/mod.py"])
        assert (repo / "pkg" / "mod.py").read_text(encoding="utf-8") == "x = 23\n"
    finally:
        cleanup_worktree(wt)


def test_finalize_persists_artifacts_before_cleanup(tmp_path: pathlib.Path) -> None:
    repo = _make_repo(tmp_path)
    wt = create_dispatch_worktree(repo, "persist-clean")
    try:
        (wt.path / "pkg" / "mod.py").write_text("x = 8\n", encoding="utf-8")
        wt.result_path.write_text(json.dumps({"ok": True}) + "\n", encoding="utf-8")

        final = finalize_dispatch(
            wt,
            repo,
            _completed_outcome(wt),
            allowlist=["pkg/"],
            verification_commands=["true"],
        )

        artifact_dir = repo / "tasks" / "dispatch" / "persist-clean"
        assert final.action == "merged"
        assert (artifact_dir / "status.json").exists()
        assert json.loads((artifact_dir / "result.json").read_text(encoding="utf-8")) == {
            "ok": True
        }
        assert not wt.path.exists()
    finally:
        cleanup_worktree(wt)


def test_finalize_reports_post_merge_cleanup_failure(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    repo = _make_repo(tmp_path)
    wt = create_dispatch_worktree(repo, "cleanup-failed")

    def fail_cleanup(_wt: DispatchWorktree) -> None:
        raise RuntimeError("cleanup offline")

    monkeypatch.setattr("tools.mir_executor.dispatch.cleanup_worktree", fail_cleanup)

    try:
        (wt.path / "pkg" / "mod.py").write_text("x = 12\n", encoding="utf-8")

        final = finalize_dispatch(
            wt,
            repo,
            _completed_outcome(wt),
            allowlist=["pkg/"],
            verification_commands=["true"],
        )

        assert final.action == "merged-but-cleanup-failed"
        assert final.reason == "post-merge-error:cleanup offline"
        assert final.merged_files == ["pkg/mod.py"]
        assert (repo / "pkg" / "mod.py").read_text(encoding="utf-8") == "x = 12\n"
    finally:
        cleanup_worktree(wt)


def test_merge_gate_rejects_out_of_allowlist(tmp_path: pathlib.Path) -> None:
    repo = _make_repo(tmp_path)
    wt = create_dispatch_worktree(repo, "gate-out-of-allowlist")
    try:
        (wt.path / "other.py").write_text("y = 1\n", encoding="utf-8")

        final = finalize_dispatch(
            wt,
            repo,
            _completed_outcome(wt),
            allowlist=["pkg/"],
            verification_commands=["true"],
        )

        assert final.action == "blocked"
        assert final.reason.startswith("out-of-allowlist:")
        assert wt.path.exists()
        assert not (repo / "other.py").exists()
    finally:
        cleanup_worktree(wt)


@pytest.mark.parametrize(
    "denied_path",
    [
        ".claude/agents/executor-agent.md",
        "config/repo-agent-management.json",
        "docs/decisions/example.md",
    ],
)
def test_merge_gate_rejects_denied_harness_path_before_allowlist(
    tmp_path: pathlib.Path,
    denied_path: str,
) -> None:
    repo = _make_repo(tmp_path)
    _write_repo_file(repo, denied_path, "MAIN\n")
    _git(repo, "add", denied_path)
    _git(repo, "commit", "-m", "seed denied path")

    wt = create_dispatch_worktree(repo, f"gate-denied-{denied_path.split('/')[0].strip('.')}")
    try:
        _write_repo_file(wt.path, denied_path, "WORKTREE\n")
        _git(wt.path, "add", denied_path)
        _git(wt.path, "commit", "-m", "change denied path")

        gate = evaluate_merge_gate(
            wt,
            allowlist=[".claude/", "config/", "docs/"],
            verification_commands=["true"],
        )

        assert gate.approved is False
        assert gate.reason.startswith(f"denied-harness:{denied_path}")
        assert f"'{denied_path}'" in gate.reason
        assert gate.changed_files == [denied_path]
    finally:
        cleanup_worktree(wt)


def test_merge_gate_allows_tasks_tdd_json(tmp_path: pathlib.Path) -> None:
    repo = _make_repo(tmp_path)
    wt = create_dispatch_worktree(repo, "gate-tdd-json")
    try:
        (wt.path / "tasks" / "tdd.json").write_text('{"version": 1}\n', encoding="utf-8")
        _git(wt.path, "add", "tasks/tdd.json")
        _git(wt.path, "commit", "-m", "change tdd ledger")

        gate = evaluate_merge_gate(
            wt,
            allowlist=["tasks/tdd.json"],
            verification_commands=["true"],
        )

        assert gate.approved is True
        assert gate.reason == "approved"
        assert gate.changed_files == ["tasks/tdd.json"]
    finally:
        cleanup_worktree(wt)


def test_merge_gate_rejects_verification_failure(tmp_path: pathlib.Path) -> None:
    repo = _make_repo(tmp_path)
    wt = create_dispatch_worktree(repo, "gate-verify-failure")
    try:
        (wt.path / "pkg" / "mod.py").write_text("x = 3\n", encoding="utf-8")

        final = finalize_dispatch(
            wt,
            repo,
            _completed_outcome(wt),
            allowlist=["pkg/"],
            verification_commands=["false"],
        )

        assert final.action == "blocked"
        assert final.reason == "verification-failed:false"
        assert wt.path.exists()
        assert (repo / "pkg" / "mod.py").read_text(encoding="utf-8") == "x = 1\n"
    finally:
        cleanup_worktree(wt)


def test_merge_gate_rejects_verification_exit_five(tmp_path: pathlib.Path) -> None:
    repo = _make_repo(tmp_path)
    wt = create_dispatch_worktree(repo, "gate-verify-exit-five")
    try:
        (wt.path / "pkg" / "mod.py").write_text("x = 30\n", encoding="utf-8")
        final = finalize_dispatch(
            wt,
            repo,
            _completed_outcome(wt),
            allowlist=["pkg/"],
            verification_commands=["sh -c 'exit 5'"],
        )

        assert final.action == "blocked"
        assert final.reason == "verification-failed:sh -c 'exit 5'"
        assert (repo / "pkg" / "mod.py").read_text(encoding="utf-8") == "x = 1\n"
        assert wt.path.exists()
    finally:
        cleanup_worktree(wt)


def test_verification_mutation_is_isolated_from_dispatch_and_main(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    repo = _make_repo(tmp_path)
    (repo / ".gitignore").write_text("*.cache\n", encoding="utf-8")
    _git(repo, "add", ".gitignore")
    _git(repo, "commit", "-m", "seed ignored verification artifact")
    wt = create_dispatch_worktree(repo, "gate-verification-drift")
    monkeypatch.setattr(dispatch_module, "cleanup_worktree", lambda _wt: None)
    try:
        (wt.path / "pkg" / "mod.py").write_text("x = 33\n", encoding="utf-8")
        (wt.path / "pkg" / "local.cache").write_text("dispatch cache\n", encoding="utf-8")
        final = finalize_dispatch(
            wt,
            repo,
            _completed_outcome(wt),
            allowlist=["pkg/"],
            verification_commands=[
                "sh -c 'test ! -e pkg/local.cache && touch pkg/verify.tmp'"
            ],
        )
        assert final == FinalizeResult("merged", "approved", ["pkg/mod.py"])
        assert (repo / "pkg" / "mod.py").read_text(encoding="utf-8") == "x = 33\n"
        assert not (repo / "pkg" / "verify.tmp").exists()
        assert not (wt.path / "pkg" / "verify.tmp").exists()
        assert (wt.path / "pkg" / "local.cache").read_text(encoding="utf-8") == (
            "dispatch cache\n"
        )
    finally:
        cleanup_worktree(wt)


def test_verification_cleanup_failure_blocks_merge_and_persists_artifacts(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    repo = _make_repo(tmp_path)
    wt = create_dispatch_worktree(repo, "gate-verification-cleanup-failed")
    verification_base = tmp_path / "verification-temp"
    verification_root = verification_base / "worktree"
    real_git = dispatch_module._git

    def fixed_mkdtemp(*, prefix: str) -> str:
        assert prefix == "mir-verify-"
        verification_base.mkdir()
        return str(verification_base)

    def fail_verification_remove(
        repo_root: pathlib.Path,
        args: list[str],
        *,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        if args == ["worktree", "remove", "--force", str(verification_root)]:
            return subprocess.CompletedProcess(args, 1, "", "busy")
        return real_git(repo_root, args, check=check)

    monkeypatch.setattr(dispatch_module.tempfile, "mkdtemp", fixed_mkdtemp)
    monkeypatch.setattr(dispatch_module, "_git", fail_verification_remove)
    try:
        (wt.path / "pkg" / "mod.py").write_text("x = 34\n", encoding="utf-8")
        main_head = real_git(repo, ["rev-parse", "HEAD"]).stdout.strip()

        final = finalize_dispatch(
            wt,
            repo,
            _completed_outcome(wt),
            allowlist=["pkg/"],
            verification_commands=["true"],
        )

        assert final == FinalizeResult("blocked", "verification-cleanup-failed", [])
        assert real_git(repo, ["rev-parse", "HEAD"]).stdout.strip() == main_head
        assert (repo / "pkg" / "mod.py").read_text(encoding="utf-8") == "x = 1\n"
        assert verification_root.exists()
        assert (
            repo / "tasks" / "dispatch" / wt.dispatch_id / "status.json"
        ).exists()
    finally:
        monkeypatch.setattr(dispatch_module, "_git", real_git)
        real_git(
            repo,
            ["worktree", "remove", "--force", str(verification_root)],
            check=False,
        )
        shutil.rmtree(verification_base, ignore_errors=True)
        cleanup_worktree(wt)


def test_merge_gate_fail_closed_on_missing_verification(tmp_path: pathlib.Path) -> None:
    repo = _make_repo(tmp_path)
    wt = create_dispatch_worktree(repo, "gate-missing-verify")
    try:
        (wt.path / "pkg" / "mod.py").write_text("x = 4\n", encoding="utf-8")

        final = finalize_dispatch(
            wt,
            repo,
            _completed_outcome(wt),
            allowlist=["pkg/"],
            verification_commands=[],
        )

        assert final.action == "blocked"
        assert final.reason == "no-verification-commands (fail-closed)"
        assert wt.path.exists()
        assert (repo / "pkg" / "mod.py").read_text(encoding="utf-8") == "x = 1\n"
    finally:
        cleanup_worktree(wt)


def test_finalize_cannot_merge_changes_added_after_gate_approval(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    repo = _make_repo(tmp_path)
    wt = create_dispatch_worktree(repo, "gate-approved-commit-moved")
    real_evaluate_merge_gate = evaluate_merge_gate

    def approve_then_move_branch(
        worktree: DispatchWorktree,
        **kwargs: object,
    ) -> MergeGate:
        gate = real_evaluate_merge_gate(worktree, **kwargs)
        assert gate.approved is True
        (worktree.path / "pkg" / "broadened.py").write_text(
            "not gate approved\n",
            encoding="utf-8",
        )
        _git(worktree.path, "add", "pkg/broadened.py")
        _git(worktree.path, "commit", "-m", "move branch after gate")
        return gate

    monkeypatch.setattr(
        "tools.mir_executor.dispatch.evaluate_merge_gate",
        approve_then_move_branch,
    )

    try:
        (wt.path / "pkg" / "mod.py").write_text("x = 25\n", encoding="utf-8")

        final = finalize_dispatch(
            wt,
            repo,
            _completed_outcome(wt),
            allowlist=["pkg/mod.py"],
            verification_commands=["true"],
        )

        assert final.action == "blocked"
        assert final.reason == "dispatch-moved"
        assert not (repo / "pkg" / "broadened.py").exists()
        assert (repo / "pkg" / "mod.py").read_text(encoding="utf-8") == "x = 1\n"
    finally:
        cleanup_worktree(wt)


def test_finalize_blocks_uncommitted_dispatch_drift_after_gate(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    repo = _make_repo(tmp_path)
    wt = create_dispatch_worktree(repo, "dispatch-uncommitted-drift")
    real_gate = evaluate_merge_gate

    def approve_then_dirty(worktree: DispatchWorktree, **kwargs: object) -> MergeGate:
        gate = real_gate(worktree, **kwargs)
        (worktree.path / "pkg" / "late.py").write_text("late\n", encoding="utf-8")
        return gate

    monkeypatch.setattr(dispatch_module, "evaluate_merge_gate", approve_then_dirty)
    try:
        (wt.path / "pkg" / "mod.py").write_text("x = 32\n", encoding="utf-8")
        final = finalize_dispatch(
            wt,
            repo,
            _completed_outcome(wt),
            allowlist=["pkg/mod.py"],
            verification_commands=["true"],
        )
        assert final == FinalizeResult("blocked", "dispatch-dirty", [])
        assert (repo / "pkg" / "mod.py").read_text(encoding="utf-8") == "x = 1\n"
    finally:
        cleanup_worktree(wt)


def test_finalize_applies_approved_deletion_and_rename(tmp_path: pathlib.Path) -> None:
    repo = _make_repo(tmp_path)
    _write_repo_file(repo, "pkg/delete.py", "delete me\n")
    _write_repo_file(repo, "pkg/old.py", "rename me\n")
    _git(repo, "add", "pkg/delete.py", "pkg/old.py")
    _git(repo, "commit", "-m", "seed deletion and rename")
    wt = create_dispatch_worktree(repo, "deletion-rename")
    try:
        (wt.path / "pkg" / "delete.py").unlink()
        (wt.path / "pkg" / "old.py").rename(wt.path / "pkg" / "new.py")
        final = finalize_dispatch(
            wt,
            repo,
            _completed_outcome(wt),
            allowlist=["pkg/delete.py", "pkg/old.py", "pkg/new.py"],
            verification_commands=["true"],
        )
        assert final.action == "merged"
        assert set(final.merged_files) == {"pkg/delete.py", "pkg/old.py", "pkg/new.py"}
        assert not (repo / "pkg" / "delete.py").exists()
        assert not (repo / "pkg" / "old.py").exists()
        assert (repo / "pkg" / "new.py").read_text(encoding="utf-8") == "rename me\n"
    finally:
        cleanup_worktree(wt)


def test_finalize_treats_changed_filename_as_literal_pathspec(tmp_path: pathlib.Path) -> None:
    repo = _make_repo(tmp_path)
    literal_name = ":(literal)dispatch-output.txt"
    wt = create_dispatch_worktree(repo, "literal-pathspec")
    try:
        (wt.path / literal_name).write_text("literal output\n", encoding="utf-8")

        final = finalize_dispatch(
            wt,
            repo,
            _completed_outcome(wt),
            allowlist=[literal_name],
            verification_commands=["true"],
        )

        assert final == FinalizeResult("merged", "approved", [literal_name])
        assert (repo / literal_name).read_text(encoding="utf-8") == "literal output\n"
    finally:
        cleanup_worktree(wt)


def test_finalize_fail_closed_on_main_moved(tmp_path: pathlib.Path) -> None:
    repo = _make_repo(tmp_path)
    wt = create_dispatch_worktree(repo, "gate-main-moved")
    try:
        (wt.path / "pkg" / "mod.py").write_text("x = 5\n", encoding="utf-8")
        (repo / "pkg" / "main_only.py").write_text("z = 1\n", encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-m", "main moved")

        final = finalize_dispatch(
            wt,
            repo,
            _completed_outcome(wt),
            allowlist=["pkg/"],
            verification_commands=["true"],
        )

        assert final.action == "blocked"
        assert final.reason == "main-moved"
        assert wt.path.exists()
        assert (repo / "pkg" / "mod.py").read_text(encoding="utf-8") == "x = 1\n"
        assert (repo / "pkg" / "main_only.py").exists()
    finally:
        cleanup_worktree(wt)


def test_finalize_fail_closed_on_dirty_main(tmp_path: pathlib.Path) -> None:
    repo = _make_repo(tmp_path)
    wt = create_dispatch_worktree(repo, "gate-dirty-main")
    try:
        (wt.path / "pkg" / "mod.py").write_text("x = 5\n", encoding="utf-8")
        (repo / "pkg" / "mod.py").write_text("x = 99\n", encoding="utf-8")

        final = finalize_dispatch(
            wt,
            repo,
            _completed_outcome(wt),
            allowlist=["pkg/"],
            verification_commands=["true"],
        )

        assert final.action == "blocked"
        assert final.reason == "main-dirty"
        assert wt.path.exists()
        assert (repo / "pkg" / "mod.py").read_text(encoding="utf-8") == "x = 99\n"
    finally:
        cleanup_worktree(wt)


def test_finalize_rolls_back_on_merge_error(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    repo = _make_repo(tmp_path)
    _write_repo_file(repo, "wip/staged.txt", "staged base\n")
    _write_repo_file(repo, "wip/unstaged.txt", "unstaged base\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "seed rollback wip paths")
    (repo / ".git" / "info" / "exclude").write_text(
        ".mir/\n*.ignored\n",
        encoding="utf-8",
    )
    (repo / ".mir").mkdir()
    (repo / ".mir" / "keepme").write_text("runtime state\n", encoding="utf-8")
    wt = create_dispatch_worktree(repo, "gate-merge-error")

    def fake_merge_result(_wt: DispatchWorktree, **_kwargs: object) -> object:
        (repo / "pkg" / "mod.py").write_text("partial merge\n", encoding="utf-8")
        shutil.copy2(_wt.path / "pkg" / "new.py", repo / "pkg" / "new.py")
        _git(repo, "add", "pkg/mod.py", "pkg/new.py")
        raise RuntimeError("boom")

    monkeypatch.setattr("tools.mir_executor.dispatch.merge_result", fake_merge_result)

    try:
        (wt.path / "pkg" / "mod.py").write_text("x = 10\n", encoding="utf-8")
        (wt.path / "pkg" / "new.py").write_text("partial copy\n", encoding="utf-8")
        (repo / "wip" / "staged.txt").write_text("staged wip\n", encoding="utf-8")
        _git(repo, "add", "wip/staged.txt")
        (repo / "wip" / "unstaged.txt").write_text("unstaged wip\n", encoding="utf-8")
        (repo / "wip" / "untracked.txt").write_text("untracked wip\n", encoding="utf-8")
        (repo / "wip" / "cache.ignored").write_text("ignored wip\n", encoding="utf-8")
        wip_status_before = _git(
            repo,
            "status",
            "--porcelain",
            "--ignored",
            "--",
            "wip",
            ".mir",
        ).stdout
        wip_staged_before = _git(
            repo,
            "diff",
            "--cached",
            "--binary",
            "--",
            "wip",
        ).stdout
        wip_unstaged_before = _git(repo, "diff", "--binary", "--", "wip").stdout

        final = finalize_dispatch(
            wt,
            repo,
            _completed_outcome(wt),
            allowlist=["pkg/"],
            verification_commands=["true"],
        )

        assert final.action == "blocked"
        assert final.reason == "merge-error:boom"
        assert wt.path.exists()
        assert (repo / "pkg" / "mod.py").read_text(encoding="utf-8") == "x = 1\n"
        assert not (repo / "pkg" / "new.py").exists()
        assert (repo / ".mir" / "keepme").read_text(encoding="utf-8") == "runtime state\n"
        assert _git(
            repo,
            "status",
            "--porcelain",
            "--ignored",
            "--",
            "wip",
            ".mir",
        ).stdout == wip_status_before
        assert _git(
            repo,
            "diff",
            "--cached",
            "--binary",
            "--",
            "wip",
        ).stdout == wip_staged_before
        assert _git(repo, "diff", "--binary", "--", "wip").stdout == wip_unstaged_before
    finally:
        cleanup_worktree(wt)


def test_finalize_reports_rollback_failed_when_target_residue_remains(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    repo = _make_repo(tmp_path)
    wt = create_dispatch_worktree(repo, "gate-rollback-residue")

    def fail_after_partial_merge(_wt: DispatchWorktree, **_kwargs: object) -> object:
        (repo / "pkg" / "mod.py").write_text("residue\n", encoding="utf-8")
        raise RuntimeError("boom")

    real_dispatch_git = dispatch_module._git

    def refuse_target_restore(repo_root, args, *, check=True):
        if "restore" in args and args[-1] == "pkg/mod.py":
            return subprocess.CompletedProcess(args, 1, "", "restore refused")
        return real_dispatch_git(repo_root, args, check=check)

    monkeypatch.setattr(dispatch_module, "merge_result", fail_after_partial_merge)
    monkeypatch.setattr(dispatch_module, "_git", refuse_target_restore)
    try:
        (wt.path / "pkg" / "mod.py").write_text("x = 31\n", encoding="utf-8")
        final = finalize_dispatch(
            wt,
            repo,
            _completed_outcome(wt),
            allowlist=["pkg/mod.py"],
            verification_commands=["true"],
        )

        assert final.action == "blocked"
        assert final.reason.startswith("rollback-failed:merge-error:boom")
        assert (repo / "pkg" / "mod.py").read_text(encoding="utf-8") == "residue\n"
        assert wt.path.exists()
        assert (repo / "tasks" / "dispatch" / wt.dispatch_id / "status.json").exists()
    finally:
        _git(repo, "restore", "--staged", "--worktree", "pkg/mod.py")
        cleanup_worktree(wt)


def test_verify_command_timeout_blocks(tmp_path: pathlib.Path) -> None:
    repo = _make_repo(tmp_path)
    wt = create_dispatch_worktree(repo, "gate-verify-timeout")
    try:
        gate = evaluate_merge_gate(
            wt,
            allowlist=["pkg/"],
            verification_commands=["sleep 30"],
            verify_timeout=1,
            expect_changes=False,
        )

        assert gate.approved is False
        assert gate.reason == "verification-timeout"
    finally:
        cleanup_worktree(wt)


def test_merge_gate_empty_diff_fail_closed_by_default_and_opt_out_allows(
    tmp_path: pathlib.Path,
) -> None:
    repo = _make_repo(tmp_path)
    wt = create_dispatch_worktree(repo, "gate-empty-diff")
    try:
        blocked = evaluate_merge_gate(
            wt,
            allowlist=["pkg/"],
            verification_commands=["true"],
        )
        allowed = evaluate_merge_gate(
            wt,
            allowlist=["pkg/"],
            verification_commands=["true"],
            expect_changes=False,
        )

        assert blocked.approved is False
        assert blocked.reason == "empty-diff fail-closed"
        assert blocked.changed_files == []
        assert allowed.approved is True
        assert allowed.reason == "approved"
        assert allowed.changed_files == []
    finally:
        cleanup_worktree(wt)


def test_gate_ignores_duration_anomaly(tmp_path: pathlib.Path) -> None:
    repo = _make_repo(tmp_path)
    wt = create_dispatch_worktree(repo, "gate-duration-anomaly")
    try:
        events_path = wt.path / ".mir-dispatch" / "events.jsonl"
        events_path.write_text(
            "\n".join(
                [
                    json.dumps({"exit_code": 0, "duration_s": 60.0}),
                    json.dumps({"exit_code": 0, "duration_s": 300.0}),
                    "",
                ]
            ),
            encoding="utf-8",
        )
        (wt.path / "pkg" / "mod.py").write_text("x = 9\n", encoding="utf-8")

        final = finalize_dispatch(
            wt,
            repo,
            _completed_outcome(wt),
            allowlist=["pkg/"],
            verification_commands=["true"],
        )

        assert final.action == "merged"
        assert final.reason == "approved"
        assert (repo / "pkg" / "mod.py").read_text(encoding="utf-8") == "x = 9\n"
    finally:
        cleanup_worktree(wt)


def test_merge_gate_does_not_consult_agent_check(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    repo = _make_repo(tmp_path)
    wt = create_dispatch_worktree(repo, "gate-agent-check-observe-only")
    monkeypatch.setattr(
        "tools.mir_executor.dispatch.scan_codex_events",
        lambda _events_path: pytest.fail("merge gate must not consult agent-check"),
        raising=False,
    )
    try:
        events_path = wt.path / ".mir-dispatch" / "events.jsonl"
        events_path.parent.mkdir(parents=True, exist_ok=True)
        events_path.write_text(
            "\n".join(
                [
                    json.dumps({"exit_code": 142, "signal": "SIG14", "error_sig": None}),
                    json.dumps({"exit_code": 1, "signal": None, "error_sig": "same"}),
                    json.dumps({"exit_code": 1, "signal": None, "error_sig": "same"}),
                    json.dumps({"exit_code": 1, "signal": None, "error_sig": "same"}),
                    "",
                ]
            ),
            encoding="utf-8",
        )
        (wt.path / "pkg" / "mod.py").write_text("x = 7\n", encoding="utf-8")

        final = finalize_dispatch(
            wt,
            repo,
            _completed_outcome(wt),
            allowlist=["pkg/"],
            verification_commands=["true"],
        )

        assert final.action == "merged"
        assert final.reason == "approved"
        assert final.merged_files == ["pkg/mod.py"]
        assert (repo / "pkg" / "mod.py").read_text(encoding="utf-8") == "x = 7\n"
    finally:
        cleanup_worktree(wt)


def test_finalize_dispatch_threads_same_boolean_to_both_sites(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    repo = _make_repo(tmp_path)
    _write_repo_profile(repo, "meta_harness")
    _git(repo, "add", ".mir/repo-profile.toml")
    _git(repo, "commit", "-m", "seed profile")
    wt = create_dispatch_worktree(repo, "finalize-thread-meta-flag")
    gate_kwargs: list[bool] = []
    gate_expect_changes: list[bool] = []
    merge_kwargs: list[bool] = []

    def fake_evaluate_merge_gate(
        _wt: DispatchWorktree,
        *,
        allowlist: list[str],
        verification_commands: list[str],
        verify_timeout: int = 600,
        allow_harness_self_modify: bool = False,
        expect_changes: bool = True,
        source_commit: str | None = None,
    ) -> MergeGate:
        _ = allowlist, verification_commands, verify_timeout, source_commit
        gate_kwargs.append(allow_harness_self_modify)
        gate_expect_changes.append(expect_changes)
        return MergeGate(True, "approved", ["pkg/mod.py"])

    def fake_merge_result(
        _wt: DispatchWorktree,
        *,
        allow_harness_self_modify: bool = False,
        **_kwargs: object,
    ) -> MergeOutcome:
        merge_kwargs.append(allow_harness_self_modify)
        return MergeOutcome(merged_files=["pkg/mod.py"], skipped=[])

    monkeypatch.setattr(
        "tools.mir_executor.dispatch.evaluate_merge_gate",
        fake_evaluate_merge_gate,
    )
    monkeypatch.setattr("tools.mir_executor.dispatch.merge_result", fake_merge_result)

    try:
        (wt.path / "pkg" / "mod.py").write_text("x = 22\n", encoding="utf-8")

        final = finalize_dispatch(
            wt,
            repo,
            _completed_outcome(wt),
            allowlist=["pkg/"],
            verification_commands=["true"],
        )

        assert final.action == "merged"
        assert gate_kwargs == [True]
        assert gate_expect_changes == [True]
        assert merge_kwargs == [True]
    finally:
        cleanup_worktree(wt)


def test_finalize_dispatch_meta_harness_merges_claude_e2e(tmp_path: pathlib.Path) -> None:
    meta_repo = _make_repo(tmp_path)
    _write_repo_profile(meta_repo, "meta_harness")
    _git(meta_repo, "add", ".mir/repo-profile.toml")
    _git(meta_repo, "commit", "-m", "seed meta profile")

    wt = create_dispatch_worktree(meta_repo, "finalize-meta-claude")
    try:
        _write_repo_file(wt.path, ".claude/agents/example.md", "WORKTREE\n")

        final = finalize_dispatch(
            wt,
            meta_repo,
            _completed_outcome(wt),
            allowlist=[".claude/"],
            verification_commands=["true"],
        )

        assert final.action == "merged"
        assert (meta_repo / ".claude" / "agents" / "example.md").read_text(
            encoding="utf-8"
        ) == "WORKTREE\n"
    finally:
        cleanup_worktree(wt)

    wt = create_dispatch_worktree(meta_repo, "finalize-meta-plan")
    try:
        (wt.path / "tasks" / "plan.md").write_text("WORKTREE\n", encoding="utf-8")

        final = finalize_dispatch(
            wt,
            meta_repo,
            _completed_outcome(wt),
            allowlist=["tasks/"],
            verification_commands=["true"],
        )

        assert final.action == "blocked"
        assert final.reason.startswith("denied-harness:tasks/plan.md")
        assert (
            (meta_repo / "tasks" / "plan.md").read_text(encoding="utf-8")
            == "MAIN-PLAN-V1\n"
        )
    finally:
        cleanup_worktree(wt)

    content_repo = tmp_path / "content_repo"
    content_repo.mkdir()
    _git(content_repo, "init")
    _git(content_repo, "config", "user.email", "t@e")
    _git(content_repo, "config", "user.name", "t")
    (content_repo / "tasks").mkdir()
    (content_repo / "tasks" / "plan.md").write_text("MAIN-PLAN-V1\n", encoding="utf-8")
    _write_repo_profile(content_repo, "content_app")
    _git(content_repo, "add", "-A")
    _git(content_repo, "commit", "-m", "init content")

    wt = create_dispatch_worktree(content_repo, "finalize-content-claude")
    try:
        _write_repo_file(wt.path, ".claude/agents/example.md", "WORKTREE\n")

        final = finalize_dispatch(
            wt,
            content_repo,
            _completed_outcome(wt),
            allowlist=[".claude/"],
            verification_commands=["true"],
        )

        assert final.action == "blocked"
        assert final.reason.startswith("denied-harness:.claude/agents/example.md")
        assert not (content_repo / ".claude" / "agents" / "example.md").exists()
    finally:
        cleanup_worktree(wt)


def test_cli_dispatch_flag_routes_to_run_dispatch(tmp_path: pathlib.Path, monkeypatch) -> None:
    repo = _make_repo(tmp_path)
    _make_ledger(repo)
    calls: list[dict[str, object]] = []
    finalize_calls: list[dict[str, object]] = []
    mcp_calls = _patch_mcp_runner(monkeypatch, CodexAttempt(0))
    wt = create_dispatch_worktree(repo, "cli-route")

    def fake_run_dispatch(main_repo_root: pathlib.Path, dispatch_id: str, **kwargs: object):
        calls.append(
            {
                "main_repo_root": main_repo_root,
                "dispatch_id": dispatch_id,
                "kwargs": kwargs,
            }
        )
        return DispatchOutcome("completed", 1, False, None, wt)

    def fake_finalize(*args: object, **kwargs: object) -> FinalizeResult:
        finalize_calls.append({"args": args, "kwargs": kwargs})
        return FinalizeResult("merged", "approved", ["pkg/mod.py"])

    monkeypatch.setattr("tools.mir_executor.dispatch.run_dispatch", fake_run_dispatch)
    monkeypatch.setattr("tools.mir_executor.dispatch.finalize_dispatch", fake_finalize)

    try:
        rc = cli.main(
            [
                "execute",
                "--background",
                "--dispatch",
                "--change-id",
                "X",
                "--category",
                "unit",
                "--repo-root",
                str(repo),
                "--codex-args",
                "exec hi",
                "--allow-path",
                "pkg/",
                "--verify-cmd",
                "true",
            ]
        )
    finally:
        cleanup_worktree(wt)

    assert rc == 0
    assert len(calls) == 1
    assert mcp_calls[0]["prompt"] == "hi"
    assert calls[0]["main_repo_root"] == repo.resolve()
    kwargs = calls[0]["kwargs"]
    assert kwargs["brief_text"] == "hi"
    assert kwargs["claude_fallback"] is None
    assert len(finalize_calls) == 1
    assert finalize_calls[0]["kwargs"]["allowlist"] == ["pkg/"]
    assert finalize_calls[0]["kwargs"]["verification_commands"] == ["true"]
    assert finalize_calls[0]["kwargs"]["expect_changes"] is True


@pytest.mark.parametrize(
    "dispatch_mode",
    ["--dispatch", "--background --dispatch"],
    ids=["foreground", "background"],
)
def test_cli_dispatch_uses_brief_without_codex_args(
    tmp_path: pathlib.Path,
    monkeypatch,
    dispatch_mode: str,
) -> None:
    repo = _make_repo(tmp_path)
    _make_ledger(repo)
    brief_path = _write_dispatch_brief_json(tmp_path, "Brief goal from JSON")
    calls: list[dict[str, object]] = []
    brief_reads: list[pathlib.Path | None] = []
    mcp_calls = _patch_mcp_runner(monkeypatch, CodexAttempt(0))
    wt = create_dispatch_worktree(repo, "cli-brief-prompt")
    real_brief_reader = cli._prompt_from_dispatch_brief

    def read_brief_once(path: pathlib.Path | None) -> str:
        brief_reads.append(path)
        return real_brief_reader(path)

    def fake_run_dispatch(main_repo_root: pathlib.Path, dispatch_id: str, **kwargs: object):
        calls.append(
            {
                "main_repo_root": main_repo_root,
                "dispatch_id": dispatch_id,
                "kwargs": kwargs,
            }
        )
        return DispatchOutcome("completed", 1, False, None, wt)

    def fake_finalize(*_args: object, **_kwargs: object) -> FinalizeResult:
        return FinalizeResult("merged", "approved", ["pkg/mod.py"])

    monkeypatch.setattr("tools.mir_executor.dispatch.run_dispatch", fake_run_dispatch)
    monkeypatch.setattr("tools.mir_executor.dispatch.finalize_dispatch", fake_finalize)
    monkeypatch.setattr(cli, "_prompt_from_dispatch_brief", read_brief_once)

    try:
        rc = cli.main(
            [
                "execute",
                *dispatch_mode.split(),
                "--change-id",
                "X",
                "--category",
                "unit",
                "--repo-root",
                str(repo),
                "--dispatch-brief",
                str(brief_path),
            ]
        )
    finally:
        cleanup_worktree(wt)

    assert rc == 0
    assert mcp_calls[0]["prompt"] == "Brief goal from JSON"
    assert calls[0]["kwargs"]["brief_text"] == "Brief goal from JSON"
    assert brief_reads == [brief_path.resolve()]


@pytest.mark.parametrize(
    ("mode_args", "with_brief"),
    [
        (["--dispatch"], False),
        (["--background"], True),
        (["--background", "--dispatch"], False),
    ],
    ids=["foreground-dispatch", "non-dispatch", "dispatch-without-brief"],
)
def test_cli_codex_args_omission_fails_outside_effective_brief_dispatch(
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
    mode_args: list[str],
    with_brief: bool,
) -> None:
    brief_path = _write_dispatch_brief_json(tmp_path, "Brief goal")
    argv = [
        "execute",
        *mode_args,
        "--change-id",
        "X",
        "--category",
        "unit",
        "--repo-root",
        str(tmp_path),
    ]
    if with_brief:
        argv.extend(["--dispatch-brief", str(brief_path)])

    with pytest.raises(SystemExit) as exc_info:
        cli.main(argv)
    assert exc_info.value.code == 1
    assert "--codex-args" in capsys.readouterr().err


def test_cli_brief_only_dispatch_rejects_empty_expanded_goal_before_job_creation(
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    brief_path = _write_dispatch_brief_json(tmp_path, "   ")
    jobs_db = tmp_path / "jobs.db"

    with pytest.raises(SystemExit) as exc_info:
        cli.main(
            [
                "execute",
                "--background",
                "--dispatch",
                "--change-id",
                "X",
                "--category",
                "unit",
                "--repo-root",
                str(tmp_path),
                "--jobs-db",
                str(jobs_db),
                "--dispatch-brief",
                str(brief_path),
            ]
        )

    assert exc_info.value.code == 1
    assert "expanded_goal" in capsys.readouterr().err
    assert not jobs_db.exists()


def test_cli_dispatch_codex_args_file_persists_raw_prompt_for_resume(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    repo = _make_repo(tmp_path)
    _make_ledger(repo)
    db_path = tmp_path / "jobs.db"
    prompt = "Don't shlex \"quoted text\" or --flag-like words.\nKeep apostrophe's line."
    prompt_path = tmp_path / "prompt.txt"
    prompt_path.write_text(prompt, encoding="utf-8")
    brief_path = _write_dispatch_brief_json(tmp_path, "Brief fallback should not win")
    mcp_calls = _patch_mcp_runner(monkeypatch, CodexAttempt(0))
    persisted_briefs: list[str] = []

    def fake_finalize(
        wt: DispatchWorktree,
        *_args: object,
        **_kwargs: object,
    ) -> FinalizeResult:
        persisted_briefs.append(
            (wt.path / ".mir-dispatch" / "brief.md").read_text(encoding="utf-8")
        )
        return FinalizeResult("merged", "approved", ["pkg/mod.py"])

    monkeypatch.setattr("tools.mir_executor.dispatch.finalize_dispatch", fake_finalize)

    try:
        rc = cli.main(
            [
                "execute",
                "--background",
                "--dispatch",
                "--change-id",
                "X",
                "--category",
                "unit",
                "--repo-root",
                str(repo),
                "--jobs-db",
                str(db_path),
                "--codex-args-file",
                str(prompt_path),
                "--dispatch-brief",
                str(brief_path),
            ]
        )
    finally:
        _cleanup_repo_dispatch_worktrees(repo)

    assert rc == 0
    assert mcp_calls[0]["prompt"] == prompt
    assert persisted_briefs == [prompt]

    registry = JobRegistry(db_path)
    try:
        job = registry.list_jobs()[0]
    finally:
        registry.close()
    assert job.codex_args == [prompt]

    prompt_path.write_text("changed after dispatch", encoding="utf-8")
    resume_codex_args: list[list[str]] = []

    def fake_run_codex(
        self: MirExecutor,
        codex_args: list[str],
        timeout_seconds: int = 600,
        **_kwargs: object,
    ) -> SubprocessResult:
        _ = self
        _ = timeout_seconds
        resume_codex_args.append(list(codex_args))
        return SubprocessResult(
            exit_code=0,
            stdout="resume-ok",
            stderr="",
            duration_seconds=0.1,
            command=["codex", *codex_args],
        )

    def fake_update_ledger(
        self: MirExecutor,
        change_id: str,
        category: str,
        result: SubprocessResult,
    ) -> LedgerUpdate:
        _ = self
        _ = result
        return LedgerUpdate(
            change_id=change_id,
            category=category,
            previous_status="planned",
            new_status="pass",
            notes="resume test",
        )

    monkeypatch.setattr(MirExecutor, "run_codex", fake_run_codex)
    monkeypatch.setattr(MirExecutor, "update_ledger", fake_update_ledger)

    assert cli.main(["--jobs-db", str(db_path), "resume", "--job-id", job.job_id]) == 0
    assert resume_codex_args == [[prompt]]


def test_cli_dispatch_threads_allow_harness_self_modify_to_finalize_and_registry(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    repo = _make_repo(tmp_path)
    _make_ledger(repo)
    db_path = tmp_path / "jobs.db"
    wt = create_dispatch_worktree(repo, "cli-allow-harness-flag")
    finalize_calls: list[dict[str, object]] = []

    def fake_run_dispatch(
        _main_repo_root: pathlib.Path,
        dispatch_id: str,
        **_kwargs: object,
    ) -> DispatchOutcome:
        _ = dispatch_id
        return DispatchOutcome("completed", 1, False, None, wt)

    def fake_finalize(*args: object, **kwargs: object) -> FinalizeResult:
        finalize_calls.append({"args": args, "kwargs": kwargs})
        return FinalizeResult("merged", "approved", ["docs/decisions/example.md"])

    monkeypatch.setattr("tools.mir_executor.dispatch.run_dispatch", fake_run_dispatch)
    monkeypatch.setattr("tools.mir_executor.dispatch.finalize_dispatch", fake_finalize)

    try:
        rc = cli.main(
            [
                "execute",
                "--background",
                "--dispatch",
                "--allow-harness-self-modify",
                "--change-id",
                "X",
                "--category",
                "unit",
                "--repo-root",
                str(repo),
                "--jobs-db",
                str(db_path),
                "--codex-args",
                "exec hi",
                "--allow-path",
                "docs/",
                "--verify-cmd",
                "true",
            ]
        )

        assert rc == 0
        assert finalize_calls[0]["kwargs"]["allow_harness_self_modify"] is True

        registry = JobRegistry(db_path)
        try:
            job = registry.list_jobs()[0]
            assert job.allow_harness_self_modify is True
        finally:
            registry.close()
    finally:
        cleanup_worktree(wt)


@pytest.mark.parametrize(
    ("mode", "execution_backend_args", "expected_backend"),
    [
        ("force_codex", ["--execution-backend", "claude"], "codex"),
        ("force_claude", [], "claude"),
        ("select", ["--execution-backend", "claude"], "claude"),
        ("select", [], "codex"),
    ],
)
def test_cli_dispatch_policy_selects_runner(
    tmp_path: pathlib.Path,
    monkeypatch,
    mode: str,
    execution_backend_args: list[str],
    expected_backend: str,
) -> None:
    repo = _make_repo(tmp_path)
    _make_ledger(repo, change_id="X")
    _write_sub_agent_policy(repo, mode)
    db_path = tmp_path / "jobs.db"
    wt = create_dispatch_worktree(repo, f"cli-policy-{mode}-{expected_backend}")
    selected: list[str] = []

    def codex_runner(_wt: DispatchWorktree, _attempt: int) -> CodexAttempt:
        return CodexAttempt(0)

    def claude_runner(_wt: DispatchWorktree, _attempt: int) -> CodexAttempt:
        return CodexAttempt(0)

    def fake_build_codex_mcp_runner(
        _repo_root: pathlib.Path,
        prompt: str,
        *,
        timeout_seconds: int = 600,
        model: str | None = None,
        reasoning_effort: str | None = None,
        stall_timeout: float | None = None,
    ):
        _ = timeout_seconds, model, reasoning_effort, stall_timeout
        assert prompt == "hi"
        selected.append("codex")
        return codex_runner

    def fake_build_claude_runner(
        _repo_root: pathlib.Path,
        *,
        timeout_seconds: int = 600,
    ):
        _ = timeout_seconds
        selected.append("claude")
        return claude_runner

    def fake_run_dispatch(
        _main_repo_root: pathlib.Path,
        dispatch_id: str,
        **kwargs: object,
    ) -> DispatchOutcome:
        _ = dispatch_id
        if expected_backend == "claude":
            assert kwargs["codex_runner"] is claude_runner
        else:
            assert kwargs["codex_runner"](wt, 1) == CodexAttempt(0)
        return DispatchOutcome("completed", 1, False, None, wt)

    def fake_finalize(*_args: object, **_kwargs: object) -> FinalizeResult:
        return FinalizeResult("merged", "approved", ["pkg/mod.py"])

    monkeypatch.setattr(
        "tools.mir_executor.dispatch.build_codex_mcp_runner",
        fake_build_codex_mcp_runner,
    )
    monkeypatch.setattr(
        "tools.mir_executor.dispatch.build_claude_runner",
        fake_build_claude_runner,
    )
    monkeypatch.setattr("tools.mir_executor.dispatch.run_dispatch", fake_run_dispatch)
    monkeypatch.setattr("tools.mir_executor.dispatch.finalize_dispatch", fake_finalize)

    try:
        rc = cli.main(
            [
                "execute",
                "--background",
                "--dispatch",
                "--change-id",
                "X",
                "--category",
                "unit",
                "--repo-root",
                str(repo),
                "--jobs-db",
                str(db_path),
                "--codex-args",
                "exec hi",
                *execution_backend_args,
            ]
        )

        assert rc == 0
        assert selected == [expected_backend]
    finally:
        cleanup_worktree(wt)


def test_cli_dispatch_force_claude_policy_resolves_claude() -> None:
    policy = type("Policy", (), {"mode": "force_claude", "per_project": {}})()

    assert (
        cli._resolve_dispatch_backend(
            policy,
            requested_backend=None,
            repo_slug=None,
        )
        == "claude"
    )


def test_cli_dispatch_per_project_policy_selects_claude_for_repo_slug() -> None:
    policy = type(
        "Policy",
        (),
        {"mode": "per_project", "per_project": {"repo": "claude", "other": "unknown"}},
    )()

    assert (
        cli._resolve_dispatch_backend(
            policy,
            requested_backend=None,
            repo_slug="repo",
        )
        == "claude"
    )
    assert (
        cli._resolve_dispatch_backend(
            policy,
            requested_backend="claude",
            repo_slug="missing",
        )
        == "codex"
    )
    assert (
        cli._resolve_dispatch_backend(
            policy,
            requested_backend="claude",
            repo_slug="other",
        )
        == "codex"
    )


@pytest.mark.parametrize(
    "profile_text",
    [
        None,
        "not toml =",
        '[tool]\nslug = "repo"\n',
        '[repo]\nrepository_type = "meta_harness"\n',
        '[repo]\nslug = "  "\n',
    ],
)
def test_cli_dispatch_repo_policy_slug_fails_closed_for_missing_or_invalid_profile(
    tmp_path: pathlib.Path,
    profile_text: str | None,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    if profile_text is not None:
        profile_path = repo / ".mir" / "repo-profile.toml"
        profile_path.parent.mkdir(parents=True)
        profile_path.write_text(profile_text, encoding="utf-8")

    assert cli._resolve_repo_policy_slug(repo) is None


@pytest.mark.parametrize(
    "profile_text",
    [
        None,
        '[repo]\nrepository_type = "meta_harness"\n',
    ],
)
def test_cli_dispatch_per_project_policy_without_profile_slug_does_not_match_basename(
    tmp_path: pathlib.Path,
    profile_text: str | None,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    if profile_text is not None:
        profile_path = repo / ".mir" / "repo-profile.toml"
        profile_path.parent.mkdir(parents=True)
        profile_path.write_text(profile_text, encoding="utf-8")
    policy = type(
        "Policy",
        (),
        {"mode": "per_project", "per_project": {"repo": "claude"}},
    )()

    assert repo.name == "repo"
    assert (
        cli._resolve_dispatch_backend(
            policy,
            requested_backend=None,
            repo_slug=cli._resolve_repo_policy_slug(repo),
        )
        == "codex"
    )


def test_cli_dispatch_per_project_policy_uses_repo_profile_slug(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    repo = _make_repo(tmp_path)
    _make_ledger(repo, change_id="X")
    _write_repo_profile_slug(repo, "mir-harness")
    _write_sub_agent_policy(repo, "per_project", {"mir-harness": "claude"})
    db_path = tmp_path / "jobs.db"
    wt = create_dispatch_worktree(repo, "cli-policy-profile-slug")
    selected: list[str] = []

    def codex_runner(_wt: DispatchWorktree, _attempt: int) -> CodexAttempt:
        return CodexAttempt(0)

    def claude_runner(_wt: DispatchWorktree, _attempt: int) -> CodexAttempt:
        return CodexAttempt(0)

    def fake_build_codex_mcp_runner(
        _repo_root: pathlib.Path,
        prompt: str,
        *,
        timeout_seconds: int = 600,
    ):
        _ = timeout_seconds
        assert prompt == "hi"
        selected.append("codex")
        return codex_runner

    def fake_build_claude_runner(
        _repo_root: pathlib.Path,
        *,
        timeout_seconds: int = 600,
    ):
        _ = timeout_seconds
        selected.append("claude")
        return claude_runner

    def fake_run_dispatch(
        _main_repo_root: pathlib.Path,
        dispatch_id: str,
        **kwargs: object,
    ) -> DispatchOutcome:
        _ = dispatch_id
        assert kwargs["codex_runner"] is claude_runner
        return DispatchOutcome("completed", 1, False, None, wt)

    def fake_finalize(*_args: object, **_kwargs: object) -> FinalizeResult:
        return FinalizeResult("merged", "approved", ["pkg/mod.py"])

    monkeypatch.setattr(
        "tools.mir_executor.dispatch.build_codex_mcp_runner",
        fake_build_codex_mcp_runner,
    )
    monkeypatch.setattr(
        "tools.mir_executor.dispatch.build_claude_runner",
        fake_build_claude_runner,
    )
    monkeypatch.setattr("tools.mir_executor.dispatch.run_dispatch", fake_run_dispatch)
    monkeypatch.setattr("tools.mir_executor.dispatch.finalize_dispatch", fake_finalize)

    try:
        rc = cli.main(
            [
                "execute",
                "--background",
                "--dispatch",
                "--change-id",
                "X",
                "--category",
                "unit",
                "--repo-root",
                str(repo),
                "--jobs-db",
                str(db_path),
                "--codex-args",
                "exec hi",
            ]
        )

        assert rc == 0
        assert repo.name != "mir-harness"
        assert selected == ["claude"]
    finally:
        cleanup_worktree(wt)


def test_cli_dispatch_claude_backend_uses_worktree_and_merge_gate(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    repo = _make_repo(tmp_path)
    _make_ledger(repo, change_id="C")
    _write_sub_agent_policy(repo, "select")
    _git(repo, "add", "config/sub-agent-policy.json")
    _git(repo, "commit", "-m", "seed sub-agent policy")
    db_path = tmp_path / "jobs.db"
    record_path = tmp_path / "fake-claude-record.txt"
    fake_claude = _write_fake_claude_edit_bin(tmp_path)
    monkeypatch.setenv("CLAUDE_BIN", str(fake_claude))
    monkeypatch.setenv("FAKE_CLAUDE_RECORD", str(record_path))

    try:
        rc = cli.main(
            [
                "execute",
                "--background",
                "--dispatch",
                "--execution-backend",
                "claude",
                "--change-id",
                "C",
                "--category",
                "unit",
                "--repo-root",
                str(repo),
                "--jobs-db",
                str(db_path),
                "--codex-args",
                "exec x",
                "--timeout",
                "5",
                "--allow-path",
                "pkg/",
                "--verify-cmd",
                "true",
            ]
        )

        assert rc == 0
        record = _read_fake_record(record_path)
        assert record["pwd"] != str(repo)
        assert record["project"] == record["pwd"]
        assert (repo / "pkg" / "mod.py").read_text(encoding="utf-8") == "x = 44\n"
        registry = JobRegistry(db_path)
        try:
            job = registry.list_jobs()[0]
            assert job.status == "completed"
            assert job.exit_code == 0
        finally:
            registry.close()
    finally:
        _cleanup_repo_dispatch_worktrees(repo)


def test_cli_dispatch_blocked_prints_no_fallback_diagnostic(
    tmp_path: pathlib.Path,
    monkeypatch,
    capsys,
) -> None:
    repo = _make_repo(tmp_path)
    db_path = tmp_path / "jobs.db"

    def fake_run_dispatch(
        _main_repo_root: pathlib.Path,
        dispatch_id: str,
        **kwargs: object,
    ) -> DispatchOutcome:
        _ = dispatch_id
        assert kwargs["claude_fallback"] is None
        return DispatchOutcome("blocked", 3, False, "fallback-required", None)

    monkeypatch.setattr("tools.mir_executor.dispatch.run_dispatch", fake_run_dispatch)

    with pytest.raises(SystemExit) as excinfo:
        cli.main(
            [
                "execute",
                "--background",
                "--dispatch",
                "--change-id",
                "X",
                "--category",
                "unit",
                "--repo-root",
                str(repo),
                "--jobs-db",
                str(db_path),
                "--codex-args",
                "exec hi",
            ]
        )

    captured = capsys.readouterr()
    assert excinfo.value.code == 1
    assert "blocked with no fallback under sub-agent policy" in captured.err
    assert (
        "docs/harness-engineering/codex-dispatch-failure-diagnostic.md"
        in captured.err
    )


def test_cli_dispatch_cleanup_failed_action_returns_success(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    repo = _make_repo(tmp_path)
    _make_ledger(repo, change_id="X")
    db_path = tmp_path / "jobs.db"
    wt = create_dispatch_worktree(repo, "cli-cleanup-failed")

    def fake_run_dispatch(
        _main_repo_root: pathlib.Path,
        dispatch_id: str,
        **_kwargs: object,
    ) -> DispatchOutcome:
        _ = dispatch_id
        return DispatchOutcome("completed", 1, False, None, wt)

    def fake_finalize(*_args: object, **_kwargs: object) -> FinalizeResult:
        return FinalizeResult(
            "merged-but-cleanup-failed",
            "post-merge-error:cleanup offline",
            ["pkg/mod.py"],
        )

    monkeypatch.setattr("tools.mir_executor.dispatch.run_dispatch", fake_run_dispatch)
    monkeypatch.setattr("tools.mir_executor.dispatch.finalize_dispatch", fake_finalize)

    try:
        rc = cli.main(
            [
                "execute",
                "--background",
                "--dispatch",
                "--change-id",
                "X",
                "--category",
                "unit",
                "--repo-root",
                str(repo),
                "--jobs-db",
                str(db_path),
                "--codex-args",
                "exec hi",
            ]
        )

        assert rc == 0
        registry = JobRegistry(db_path)
        try:
            job = registry.list_jobs()[0]
            assert job.status == "completed"
            assert job.exit_code == 0
            assert job.stderr is not None
            assert "finalize_action=merged-but-cleanup-failed" in job.stderr
            assert "finalize_reason=post-merge-error:cleanup offline" in job.stderr
        finally:
            registry.close()
    finally:
        cleanup_worktree(wt)
