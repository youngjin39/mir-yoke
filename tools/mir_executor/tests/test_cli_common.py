"""Common CLI contracts, independent of repository application packages."""

from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace

import pytest

from tools.mir_executor import cli, dispatch
from tools.mir_executor.jobs import JobRecord, JobRegistry


def test_common_optional_parser_options(tmp_path):
    args = cli._build_parser().parse_args(
        ["execute", "--dispatch", "--family", "docs", "--artifacts-dir", str(tmp_path)]
    )
    assert args.family == "docs"
    assert args.artifacts_dir == tmp_path


def test_backend_uses_policy_order_and_project_data(tmp_path):
    (tmp_path / ".mir").mkdir()
    (tmp_path / ".mir/repo-profile.toml").write_text('[execution]\nbackend="claude"\n')
    policy = SimpleNamespace(
        mode="user_command_priority",
        default_backend="codex",
        resolution_order=["project_declaration", "user_command", "default_backend"],
    )
    assert (
        cli._resolve_dispatch_backend(
            policy, requested_backend="codex", repo_root=tmp_path
        )
        == "claude"
    )


def test_codex_dispatch_missing_route_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(dispatch, "build_codex_mcp_runner", lambda *a, **kw: "unsafe")
    with pytest.raises(ValueError, match="model.*effort"):
        cli._build_dispatch_runner(
            dispatch,
            backend="codex",
            repo_root=tmp_path,
            prompt="task",
            timeout_seconds=None,
        )


def test_dispatch_exception_marks_job_failed(tmp_path, monkeypatch):
    from tools.mir_executor import policy

    monkeypatch.setattr(
        policy,
        "load_sub_agent_policy",
        lambda root: SimpleNamespace(
            mode="force_codex",
            resolve_category=lambda category: {
                "model": "m",
                "reasoning_effort": "high",
            },
        ),
    )
    monkeypatch.setattr(dispatch, "build_codex_mcp_runner", lambda *a, **kw: object())

    def fail(*a, **kw):
        raise RuntimeError("dispatch exploded")

    monkeypatch.setattr(dispatch, "run_dispatch", fail)
    args = cli._build_parser().parse_args(
        ["execute", "--dispatch", "--repo-root", str(tmp_path), "--codex-args", "task"]
    )
    assert cli._handle_dispatch(args, tmp_path) == 1
    registry = JobRegistry(tmp_path / "tasks/jobs.db")
    job = registry.list_jobs()[0]
    registry.close()
    assert job.status == "failed"
    assert "dispatch exploded" in job.stderr


def test_execute_propagates_command_exit(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    class Executor:
        def __init__(self, **kw):
            pass

        def execute(self, **kw):
            return SimpleNamespace(
                exit_code=7, duration_seconds=0, command=[], stdout="", stderr=""
            ), SimpleNamespace(
                change_id="X",
                category="unit",
                previous_status="todo",
                new_status="failed",
                notes="",
            )

    monkeypatch.setattr(cli, "MirExecutor", Executor)
    args = cli._build_parser().parse_args(
        [
            "execute",
            "--repo-root",
            str(tmp_path),
            "--change-id",
            "X",
            "--category",
            "unit",
            "--codex-args",
            "task",
        ]
    )
    assert cli._handle_execute(args) == 7


def test_resume_redispatches_existing_job(tmp_path, monkeypatch):
    brief = tmp_path / "brief.json"
    brief.write_text(json.dumps({"expanded_goal": "task"}))
    registry = JobRegistry(tmp_path / "tasks/jobs.db")
    registry.insert(
        JobRecord(
            job_id="resume-job",
            change_id="dispatch-old",
            category="unclassified",
            family="docs",
            repo_root=str(tmp_path),
            codex_args=["task"],
            dispatch_brief_path=str(brief),
            timeout_seconds=600,
            status="failed",
        )
    )
    registry.close()
    calls = []

    def redispatch(args, root, codex_args=None):
        calls.append((args, root, codex_args))
        return 9

    monkeypatch.setattr(cli, "_handle_dispatch", redispatch)
    args = cli._build_parser().parse_args(
        ["resume", "--job-id", "resume-job", "--repo-root", str(tmp_path)]
    )
    assert cli._handle_resume(args) == 9
    assert calls[0][0].resume_job_id == "resume-job"
    assert calls[0][0].change_id is None


def test_background_propagates_persisted_exit(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    class Executor:
        def __init__(self, **kwargs):
            pass

        def _validate_ledger_entry(self, *args):
            pass

        async def run_codex_async(self, *args, **kwargs):
            return SimpleNamespace(
                exit_code=6, stdout="", stderr="", duration_seconds=0
            )

        def update_ledger(self, *args):
            pass

    monkeypatch.setattr(cli, "MirExecutor", Executor)
    args = cli._build_parser().parse_args(
        [
            "execute",
            "--background",
            "--repo-root",
            str(tmp_path),
            "--change-id",
            "X",
            "--category",
            "unit",
            "--codex-args",
            "task",
        ]
    )
    assert cli._handle_execute(args) == 6


def test_dispatch_propagates_attempt_exit_and_metadata(tmp_path, monkeypatch):
    from tools.mir_executor import policy

    monkeypatch.setattr(
        policy,
        "load_sub_agent_policy",
        lambda root: SimpleNamespace(
            mode="force_codex",
            resolve_category=lambda category: {
                "model": "m",
                "reasoning_effort": "high",
            },
        ),
    )
    monkeypatch.setattr(dispatch, "build_codex_mcp_runner", lambda *a, **kw: object())
    monkeypatch.setattr(
        dispatch,
        "run_dispatch",
        lambda *a, **kw: dispatch.DispatchOutcome(
            "blocked",
            1,
            False,
            "attempt-failed",
            None,
            tokens_used=(("total", 10),),
            model_id="m",
            mcp_protocol="app-server",
            exit_code=8,
        ),
    )
    args = cli._build_parser().parse_args(
        [
            "execute",
            "--dispatch",
            "--repo-root",
            str(tmp_path),
            "--codex-args",
            "task",
        ]
    )
    assert cli._handle_dispatch(args, tmp_path) == 8
    registry = JobRegistry(tmp_path / "tasks/jobs.db")
    try:
        job = registry.list_jobs()[0]
        assert job.exit_code == 8
        assert job.ai_run_metadata["model_id"] == "m"
        assert job.ai_run_metadata["tokens_used"] == {"total": 10}
    finally:
        registry.close()


def test_main_loads_execute_options_from_explicit_target(tmp_path, monkeypatch):
    hook_dir = tmp_path / "tools/mir_executor"
    hook_dir.mkdir(parents=True)
    (hook_dir / "local.py").write_text(
        'def register_execute_options(parser):\n    parser.add_argument("--local-route")\n'
    )
    monkeypatch.setattr(
        cli, "_handle_execute", lambda args: 0 if args.local_route == "unit" else 1
    )
    assert (
        cli.main(["execute", "--repo-root", str(tmp_path), "--local-route", "unit"])
        == 0
    )


def test_resume_restores_route_and_local_execution_scope(tmp_path, monkeypatch):
    hook_dir = tmp_path / "tools/mir_executor"
    hook_dir.mkdir(parents=True)
    marker = tmp_path / "hooks.txt"
    (hook_dir / "local.py").write_text(
        "from contextlib import contextmanager\n"
        'def pre_execute(args, root):\n    (root / "hooks.txt").write_text("pre")\n'
        "@contextmanager\ndef writer_scope(root):\n"
        '    (root / "hooks.txt").write_text("enter")\n'
        "    yield\n"
        '    with (root / "hooks.txt").open("a") as stream: stream.write("exit")\n'
    )
    brief = tmp_path / "brief.json"
    brief.write_text(json.dumps({"expanded_goal": "task"}))
    registry = JobRegistry(tmp_path / "tasks/jobs.db")
    registry.insert(
        JobRecord(
            job_id="route-job",
            change_id="old",
            category="unit",
            family=None,
            repo_root=str(tmp_path),
            codex_args=["task"],
            timeout_seconds=600,
            status="failed",
            dispatch_brief_path=str(brief),
            execution_backend="claude",
            resolved_model="persisted-model",
            resolved_reasoning_effort="high",
        )
    )
    registry.close()
    observed = []
    monkeypatch.setattr(
        cli, "_handle_dispatch", lambda args, *a: observed.append(args) or 0
    )
    args = cli._build_parser().parse_args(
        ["resume", "--job-id", "route-job", "--repo-root", str(tmp_path)]
    )
    assert cli._handle_resume(args) == 0
    assert marker.read_text() == "preexit"
    assert observed[0].execution_backend == "claude"
    assert observed[0].model == "persisted-model"
    assert observed[0].reasoning_effort == "high"


def test_failed_dispatch_resume_allocates_new_worktree(tmp_path, monkeypatch):
    import subprocess

    from tools.mir_executor import policy
    from tools.mir_executor.worktree import cleanup_worktree

    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    for name, value in [("user.email", "test@example.com"), ("user.name", "Test")]:
        subprocess.run(["git", "-C", str(tmp_path), "config", name, value], check=True)
    (tmp_path / "pkg.py").write_text("value = 1\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "pkg.py"], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-m", "init"],
        check=True,
        capture_output=True,
    )
    brief = tmp_path / "brief.json"
    brief.write_text(json.dumps({"expanded_goal": "task"}))
    monkeypatch.setattr(
        policy,
        "load_sub_agent_policy",
        lambda root: SimpleNamespace(
            mode="force_codex",
            resolve_category=lambda category: {
                "model": "m",
                "reasoning_effort": "high",
            },
        ),
    )
    worktrees = []

    def runner(wt, attempt):
        worktrees.append(wt)
        return dispatch.CodexAttempt(9, error_sig="task-error")

    monkeypatch.setattr(dispatch, "build_codex_mcp_runner", lambda *a, **kw: runner)
    args = cli._build_parser().parse_args(
        [
            "execute",
            "--dispatch",
            "--repo-root",
            str(tmp_path),
            "--dispatch-brief",
            str(brief),
        ]
    )
    try:
        assert cli._handle_dispatch(args, tmp_path) != 0
        registry = JobRegistry(tmp_path / "tasks/jobs.db")
        job = registry.list_jobs()[0]
        registry.close()
        resume = cli._build_parser().parse_args(
            ["resume", "--repo-root", str(tmp_path), "--job-id", job.job_id]
        )
        assert cli._handle_resume(resume) != 0
        assert cli._handle_resume(resume) != 0
        assert len(worktrees) == 3
        registry = JobRegistry(tmp_path / "tasks/jobs.db")
        try:
            resumed = registry.get(job.job_id)
            assert resumed.ai_run_metadata["dispatch_ids"] == [
                wt.dispatch_id for wt in worktrees
            ]
        finally:
            registry.close()
        assert worktrees[0].path != worktrees[1].path
        assert worktrees[0].path.exists()
    finally:
        for worktree in worktrees:
            cleanup_worktree(worktree)


def test_configured_declaration_fields_reject_ambiguous_backend(tmp_path):
    (tmp_path / "profile.toml").write_text('[custom]\nprovider="use_claude"\n')
    policy = SimpleNamespace(
        mode="user_command_priority",
        default_backend="codex",
        delegation={
            "project_declaration": {
                "path": "profile.toml",
                "section": "custom",
                "fields": ["provider"],
            }
        },
    )
    assert (
        cli._resolve_dispatch_backend(
            policy, requested_backend=None, repo_root=tmp_path
        )
        == "claude"
    )
    (tmp_path / "profile.toml").write_text('[custom]\nprovider="claude_or_codex"\n')
    assert (
        cli._resolve_dispatch_backend(
            policy, requested_backend=None, repo_root=tmp_path
        )
        == "codex"
    )


def test_cli_dispatch_constructs_opt_in_reviewer(tmp_path, monkeypatch):
    from tools.mir_executor import policy

    (tmp_path / "config").mkdir()
    (tmp_path / "config/mir-executor.local.json").write_text('{"require_review": true}')
    monkeypatch.setattr(
        policy,
        "load_sub_agent_policy",
        lambda root: SimpleNamespace(
            mode="force_codex",
            resolve_category=lambda category: {
                "model": "m",
                "reasoning_effort": "high",
            },
        ),
    )
    reviewer = object()
    monkeypatch.setattr(dispatch, "build_codex_mcp_runner", lambda *a, **kw: object())
    monkeypatch.setattr(
        dispatch, "build_codex_review_runner", lambda *a, **kw: reviewer
    )
    monkeypatch.setattr(
        dispatch,
        "run_dispatch",
        lambda *a, **kw: dispatch.DispatchOutcome(
            "completed", 1, False, None, object()
        ),
    )
    observed = []

    def finalize(*args, **kwargs):
        observed.append(kwargs)
        return dispatch.FinalizeResult("reviewed", "approved", [])

    monkeypatch.setattr(dispatch, "finalize_dispatch", finalize)
    args = cli._build_parser().parse_args(
        ["execute", "--dispatch", "--repo-root", str(tmp_path), "--codex-args", "task"]
    )
    assert cli._handle_dispatch(args, tmp_path) == 0
    assert observed[0]["reviewer"] is reviewer


def test_cli_sweep_includes_terminal_artifact_report(tmp_path, monkeypatch, capsys):
    from tools.mir_executor import sweep

    monkeypatch.setattr(sweep, "sweep_run_state", lambda *a, **kw: {"overdue_jobs": []})
    monkeypatch.setattr(
        sweep, "sweep_terminal_artifacts", lambda *a, **kw: {"candidates": ["terminal"]}
    )
    args = cli._build_parser().parse_args(["sweep", "--repo-root", str(tmp_path)])
    assert cli._handle_sweep(args) == 0
    assert json.loads(capsys.readouterr().out)["terminal_artifacts"]["candidates"] == [
        "terminal"
    ]
