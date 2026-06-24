"""Tests for ADR-60 dispatch helper attempt, fallback, and CLI routing policy."""

from __future__ import annotations

import json
import pathlib
import subprocess

import pytest

from tools.mir_executor import cli
from tools.mir_executor.dispatch import (
    OUTAGE_THRESHOLD,
    CodexAttempt,
    DispatchOutcome,
    FinalizeResult,
    MergeGate,
    _last_json_line,
    _resolve_harness_self_modify,
    _run_guarded,
    build_claude_fallback,
    build_claude_runner,
    build_codex_runner,
    count_consecutive_codex_failures,
    evaluate_merge_gate,
    finalize_dispatch,
    force_full_access_sandbox,
    reap_node_repl,
    run_dispatch,
)
from tools.mir_executor.jobs import JobRecord, JobRegistry
from tools.mir_executor.worktree import (
    DispatchWorktree,
    MergeOutcome,
    cleanup_worktree,
    create_dispatch_worktree,
    write_result,
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


def _write_fake_codex_bin(tmp_path: pathlib.Path) -> pathlib.Path:
    """Write a fake codex executable that records argv and dispatch session env."""
    fake_bin = tmp_path / "codex"
    fake_bin.write_text(
        "\n".join(
            [
                "#!/bin/sh",
                "{",
                "  printf 'argv:'",
                "  for arg in \"$@\"; do printf '<%s>' \"$arg\"; done",
                "  printf '\\n'",
                "  printf 'session:%s\\n' \"$MIR_CODEX_SESSION_ID\"",
                "  printf 'events:%s\\n' \"$CODEX_EVENTS_FILE\"",
                "} >> \"$FAKE_CODEX_RECORD\"",
                "exit \"$FAKE_CODEX_EXIT\"",
                "",
            ]
        ),
        encoding="utf-8",
    )
    fake_bin.chmod(0o755)
    return fake_bin


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


def test_build_codex_runner_no_double_exec_and_marks_session(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    repo = _make_repo(tmp_path)
    record_path = tmp_path / "fake-codex-record.txt"
    fake_codex = _write_fake_codex_bin(tmp_path)
    monkeypatch.setenv("CODEX_BIN", str(fake_codex))
    monkeypatch.setenv("FAKE_CODEX_RECORD", str(record_path))
    monkeypatch.setenv("FAKE_CODEX_EXIT", "7")
    (repo / "tasks" / "codex-exec-events.jsonl").write_text(
        json.dumps({"exit_code": 0, "error_sig": "stale"}) + "\n",
        encoding="utf-8",
    )

    wt = create_dispatch_worktree(repo, "real-runner")
    try:
        per_dispatch_events = wt.path / ".mir-dispatch" / "events.jsonl"
        per_dispatch_events.write_text(
            json.dumps({"exit_code": 7, "error_sig": "local"}) + "\n",
            encoding="utf-8",
        )
        runner = build_codex_runner(repo, ["exec", "hi"], timeout_seconds=5)
        attempt = runner(wt, 1)

        assert attempt.exit_code == 7
        assert attempt.error_sig == "local"
        assert record_path.read_text(encoding="utf-8").splitlines() == [
            "argv:<exec><hi>",
            f"session:{wt.dispatch_id}",
            f"events:{per_dispatch_events}",
        ]
    finally:
        cleanup_worktree(wt)


def test_force_full_access_sandbox_rewrites_long_workspace_write() -> None:
    assert force_full_access_sandbox(["exec", "--sandbox", "workspace-write"]) == [
        "exec",
        "--sandbox",
        "danger-full-access",
    ]


def test_force_full_access_sandbox_rewrites_short_workspace_write() -> None:
    assert force_full_access_sandbox(["exec", "-s", "workspace-write"]) == [
        "exec",
        "-s",
        "danger-full-access",
    ]


def test_force_full_access_sandbox_leaves_read_only() -> None:
    assert force_full_access_sandbox(["exec", "--sandbox", "read-only"]) == [
        "exec",
        "--sandbox",
        "read-only",
    ]


def test_force_full_access_sandbox_returns_shallow_copy_without_flag() -> None:
    codex_args = ["exec", "hi"]

    result = force_full_access_sandbox(codex_args)

    assert result == codex_args
    assert result is not codex_args


def test_force_full_access_sandbox_is_idempotent_for_danger_full_access() -> None:
    assert force_full_access_sandbox(["exec", "--sandbox", "danger-full-access"]) == [
        "exec",
        "--sandbox",
        "danger-full-access",
    ]


def test_reap_node_repl_is_best_effort(monkeypatch) -> None:
    def raise_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise OSError("pkill unavailable")

    monkeypatch.setattr("tools.mir_executor.dispatch.subprocess.run", raise_run)

    result = reap_node_repl()

    assert isinstance(result, int)
    assert result == -1


def test_build_codex_runner_reaps_node_repl_before_retry(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    repo = _make_repo(tmp_path)
    reap_calls = 0
    run_calls: list[list[str]] = []

    def fake_reap() -> int:
        nonlocal reap_calls
        reap_calls += 1
        return 0

    def fake_run(
        command: list[str],
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        run_calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    wt = create_dispatch_worktree(repo, "reap-retry")
    try:
        with monkeypatch.context() as patch:
            patch.setenv("CODEX_BIN", "codex")
            patch.setattr("tools.mir_executor.dispatch.reap_node_repl", fake_reap)
            patch.setattr("tools.mir_executor.dispatch.subprocess.run", fake_run)
            runner = build_codex_runner(repo, ["exec", "hi"], timeout_seconds=5)

            first = runner(wt, 1)
            assert first.exit_code == 0
            assert reap_calls == 0

            second = runner(wt, 2)
            assert second.exit_code == 0
            assert reap_calls == 1
            assert run_calls == [["codex", "exec", "hi"], ["codex", "exec", "hi"]]
    finally:
        cleanup_worktree(wt)


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
    fake_codex = _write_fake_codex_bin(tmp_path)
    fake_claude = _write_fake_claude_bin(tmp_path)
    monkeypatch.setenv("CODEX_BIN", str(fake_codex))
    monkeypatch.setenv("FAKE_CODEX_RECORD", str(tmp_path / "fake-codex-record.txt"))
    monkeypatch.setenv("FAKE_CODEX_EXIT", "9")
    monkeypatch.setenv("CLAUDE_BIN", str(fake_claude))
    monkeypatch.setenv("FAKE_CLAUDE_RECORD", str(tmp_path / "fake-claude-record.txt"))
    monkeypatch.setenv("FAKE_CLAUDE_EXIT", "2")

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
    fake_codex = _write_fake_codex_bin(tmp_path)
    monkeypatch.setenv("CODEX_BIN", str(fake_codex))
    monkeypatch.setenv("FAKE_CODEX_RECORD", str(tmp_path / "fake-codex-record.txt"))
    monkeypatch.setenv("FAKE_CODEX_EXIT", "0")

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
        registry = JobRegistry(db_path)
        try:
            jobs = registry.list_jobs()
            assert len(jobs) == 1
            job = jobs[0]
            assert job.status == "completed"
            assert job.exit_code == 0
            assert job.stdout is not None
            assert "artifacts=tasks/dispatch/" in job.stdout
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
    fake_codex = _write_fake_codex_bin(tmp_path)
    monkeypatch.setenv("CODEX_BIN", str(fake_codex))
    monkeypatch.setenv("FAKE_CODEX_RECORD", str(tmp_path / "fake-codex-record.txt"))
    monkeypatch.setenv("FAKE_CODEX_EXIT", "0")

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
        registry = JobRegistry(db_path)
        try:
            jobs = registry.list_jobs()
            assert len(jobs) == 1
            job = jobs[0]
            assert job.status == "completed"
            assert job.exit_code == 1
            assert job.stdout == f"artifacts=tasks/dispatch/{job.job_id}"
        finally:
            registry.close()
    finally:
        _cleanup_repo_dispatch_worktrees(repo)


def test_fallback_success_still_counts_as_codex_failure(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    repo = _make_repo(tmp_path)
    _make_ledger(repo, change_id="C")
    db_path = tmp_path / "jobs.db"
    fake_codex = _write_fake_codex_bin(tmp_path)
    fake_claude = _write_fake_claude_bin(tmp_path)
    monkeypatch.setenv("CODEX_BIN", str(fake_codex))
    monkeypatch.setenv("FAKE_CODEX_RECORD", str(tmp_path / "fake-codex-record.txt"))
    monkeypatch.setenv("FAKE_CODEX_EXIT", "9")
    monkeypatch.setenv("CLAUDE_BIN", str(fake_claude))
    monkeypatch.setenv("FAKE_CLAUDE_RECORD", str(tmp_path / "fake-claude-record.txt"))
    monkeypatch.setenv("FAKE_CLAUDE_EXIT", "0")

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


def test_result_json_surfaced_on_success(tmp_path: pathlib.Path) -> None:
    repo = _make_repo(tmp_path)

    def codex_runner(wt: DispatchWorktree, _attempt: int) -> CodexAttempt:
        write_result(wt, {"ok": 1})
        return CodexAttempt(0)

    outcome = run_dispatch(
        repo,
        "result-surfaced",
        codex_runner=codex_runner,
    )
    try:
        assert outcome.status == "completed"
        assert outcome.result == {"ok": 1}
    finally:
        _cleanup(outcome)


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


def test_finalize_persists_artifacts_before_cleanup(tmp_path: pathlib.Path) -> None:
    repo = _make_repo(tmp_path)
    wt = create_dispatch_worktree(repo, "persist-clean")
    try:
        (wt.path / "pkg" / "mod.py").write_text("x = 8\n", encoding="utf-8")
        write_result(wt, {"ok": True})

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
    wt = create_dispatch_worktree(repo, "gate-merge-error")

    def fake_merge_result(_wt: DispatchWorktree, **_kwargs: object) -> object:
        (repo / "pkg" / "mod.py").write_text("partial merge\n", encoding="utf-8")
        raise RuntimeError("boom")

    monkeypatch.setattr("tools.mir_executor.dispatch.merge_result", fake_merge_result)

    try:
        (wt.path / "pkg" / "mod.py").write_text("x = 10\n", encoding="utf-8")

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
    finally:
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
    ) -> MergeGate:
        _ = allowlist, verification_commands, verify_timeout
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
    assert calls[0]["main_repo_root"] == repo.resolve()
    kwargs = calls[0]["kwargs"]
    assert kwargs["brief_text"] == "exec hi"
    assert kwargs["claude_fallback"] is None
    assert len(finalize_calls) == 1
    assert finalize_calls[0]["kwargs"]["allowlist"] == ["pkg/"]
    assert finalize_calls[0]["kwargs"]["verification_commands"] == ["true"]
    assert finalize_calls[0]["kwargs"]["expect_changes"] is True


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

    def fake_build_codex_runner(
        _repo_root: pathlib.Path,
        _codex_args: list[str],
        *,
        timeout_seconds: int = 600,
    ):
        _ = timeout_seconds
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
        assert kwargs["codex_runner"] is (
            claude_runner if expected_backend == "claude" else codex_runner
        )
        return DispatchOutcome("completed", 1, False, None, wt)

    def fake_finalize(*_args: object, **_kwargs: object) -> FinalizeResult:
        return FinalizeResult("merged", "approved", ["pkg/mod.py"])

    monkeypatch.setattr(
        "tools.mir_executor.dispatch.build_codex_runner",
        fake_build_codex_runner,
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
    _write_repo_profile_slug(repo, "your-harness")
    _write_sub_agent_policy(repo, "per_project", {"your-harness": "claude"})
    db_path = tmp_path / "jobs.db"
    wt = create_dispatch_worktree(repo, "cli-policy-profile-slug")
    selected: list[str] = []

    def codex_runner(_wt: DispatchWorktree, _attempt: int) -> CodexAttempt:
        return CodexAttempt(0)

    def claude_runner(_wt: DispatchWorktree, _attempt: int) -> CodexAttempt:
        return CodexAttempt(0)

    def fake_build_codex_runner(
        _repo_root: pathlib.Path,
        _codex_args: list[str],
        *,
        timeout_seconds: int = 600,
    ):
        _ = timeout_seconds
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
        "tools.mir_executor.dispatch.build_codex_runner",
        fake_build_codex_runner,
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
        assert repo.name != "your-harness"
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
            assert job.exit_code == 0
        finally:
            registry.close()
    finally:
        cleanup_worktree(wt)
