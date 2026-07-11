from __future__ import annotations

import json
import pathlib

from tools.mir_executor.codex_mcp_client import CodexMcpError
from tools.mir_executor.dispatch import (
    CodexAttempt,
    build_codex_mcp_runner,
    run_dispatch,
)
from tools.mir_executor.worktree import cleanup_worktree, create_dispatch_worktree


class _Client:
    def __init__(self, *, start_error: Exception | None = None, call_error: Exception | None = None):
        self.start_error = start_error
        self.call_error = call_error

    def __enter__(self):
        if self.start_error:
            raise self.start_error
        return self

    def __exit__(self, *_args):
        return None

    def call_codex(self, **_kwargs):
        if self.call_error:
            raise self.call_error
        raise AssertionError("not used")


class _Factory:
    def __init__(self, client):
        self.client = client

    def __call__(self, **_kwargs):
        return self.client


def _repo(tmp_path: pathlib.Path) -> pathlib.Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    import subprocess

    subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@e"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    (repo / "file").write_text("x\n")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"], check=True, capture_output=True)
    return repo


def test_runner_marks_context_start_failure_as_lane_unavailable(tmp_path):
    repo = _repo(tmp_path)
    runner = build_codex_mcp_runner(repo, "prompt", client_factory=_Factory(_Client(start_error=FileNotFoundError("missing"))))
    outcome = run_dispatch(repo, "start-failure", codex_runner=runner, max_codex_attempts=3)
    try:
        assert outcome.status == "blocked"
        assert outcome.attempts == 1
        events = [json.loads(line) for line in (outcome.worktree.path / ".mir-dispatch" / "events.jsonl").read_text().splitlines()]
        assert any(event.get("lane_unavailable") is True for event in events)
    finally:
        cleanup_worktree(outcome.worktree)


def test_runner_keeps_call_failure_as_task_failure(tmp_path):
    repo = _repo(tmp_path)
    runner = build_codex_mcp_runner(repo, "prompt", client_factory=_Factory(_Client(call_error=CodexMcpError("task"))))
    wt = create_dispatch_worktree(repo, "call-failure")
    try:
        result = runner(wt, 1)
        assert result.lane_unavailable is False
        assert result.exit_code == 1
    finally:
        cleanup_worktree(wt)


def test_run_dispatch_lane_unavailable_never_falls_back(tmp_path):
    repo = _repo(tmp_path)
    calls = []
    outcome = run_dispatch(
        repo,
        "blocked-lane",
        codex_runner=lambda _wt, attempt: (calls.append(attempt) or CodexAttempt(1, lane_unavailable=True)),
        claude_fallback=lambda _wt: (_ for _ in ()).throw(AssertionError("fallback called")),
    )
    try:
        assert (outcome.status, outcome.attempts, outcome.fell_back, outcome.blocked_reason) == (
            "blocked", 1, False, "lane-unavailable"
        )
        assert calls == [1]
        status = json.loads((outcome.worktree.path / ".mir-dispatch" / "status.json").read_text())
        assert status["reason"] == "lane-unavailable"
    finally:
        cleanup_worktree(outcome.worktree)
