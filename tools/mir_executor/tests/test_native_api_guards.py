"""Python execution APIs refuse native-only policy before loading hooks or mutating."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from tools.mir_executor import dispatch, executor, local_hooks


@pytest.fixture
def guarded_repo(tmp_path):
    (tmp_path / "config").mkdir()
    hooks = tmp_path / "tools/mir_executor"
    hooks.mkdir(parents=True)
    (hooks / "local.py").write_text(
        "raise AssertionError('local hooks loaded before native policy guard')\n"
    )
    return tmp_path


def write_policy(root, field):
    (root / "config/mir-executor.local.json").write_text(
        json.dumps({"native_policy": {"version": 1, field: {}}})
    )


@pytest.mark.parametrize(
    "field", ["target_admission", "verifier_aliases", "agent_route", "unknown"]
)
@pytest.mark.parametrize("entrypoint", [
    "execute", "execute_async", "run_codex", "run_codex_async", "run_agent_async",
    "run_dispatch", "finalize_dispatch", "resolve_agent_route",
])
def test_refuse_unsupported_policy_before_api_effects(guarded_repo, field, entrypoint):
    root = guarded_repo
    write_policy(root, field)
    runner = executor.MirExecutor(root, target_agent="reviewer")
    with pytest.raises(ValueError, match="native_policy"):
        if entrypoint == "execute":
            runner.execute("change", "unit", ["exec", "go"])
        elif entrypoint == "execute_async":
            asyncio.run(runner.execute_async("change", "unit", ["exec", "go"]))
        elif entrypoint == "run_codex":
            runner.run_codex(["exec", "go"], cwd=root)
        elif entrypoint == "run_codex_async":
            asyncio.run(runner.run_codex_async(["exec", "go"], cwd=root))
        elif entrypoint == "run_agent_async":
            asyncio.run(runner.run_agent_async(["exec", "go"]))
        elif entrypoint == "resolve_agent_route":
            dispatch.resolve_agent_route(root, "reviewer")
        elif entrypoint == "run_dispatch":
            dispatch.run_dispatch(root, "guard-test", codex_runner=lambda *_: None)
        else:
            dispatch.finalize_dispatch(
                SimpleNamespace(path=root), root, SimpleNamespace(status="failed"),
                allowlist=[], verification_commands=[],
            )
    assert not (root / "tasks").exists()
    assert not (root / ".mir-dispatch").exists()


@pytest.mark.parametrize("entrypoint", ["run_codex", "run_codex_async"])
def test_cwd_policy_checked_before_provider(guarded_repo, tmp_path, entrypoint):
    target = guarded_repo / "target"
    (target / "config").mkdir(parents=True)
    write_policy(target, "agent_route")
    runner = executor.MirExecutor(guarded_repo)
    with pytest.raises(ValueError, match="native_policy"):
        result = getattr(runner, entrypoint)(["exec", "go"], cwd=target)
        if entrypoint.endswith("async"):
            asyncio.run(result)


@pytest.mark.parametrize("target_hooks", [False, True])
def test_invoking_home_policy_checked_before_target_hooks(guarded_repo, monkeypatch, target_hooks):
    import subprocess

    home = guarded_repo / "home"
    (home / "config").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(home)], check=True)
    write_policy(home, "target_admission")
    if target_hooks:
        (guarded_repo / "config/mir-executor.local.json").write_text(json.dumps({
            "native_policy": {"version": 1, "hooks": {
                "executable": "host", "argv": [], "sha256": "0" * 64,
                "hooks": ["writer_scope"],
            }},
        }))
    monkeypatch.setattr(local_hooks, "__file__", str(home / "tools/mir_executor/local_hooks.py"))
    with pytest.raises(ValueError, match="native_policy"):
        executor.MirExecutor(guarded_repo).execute("change", "unit", ["exec", "go"])


@pytest.mark.parametrize(
    "field", ["target_admission", "verifier_aliases", "agent_route", "unknown"]
)
def test_resume_saved_target_refused_before_registry_write(
    guarded_repo, monkeypatch, capsys, field,
):
    from tools.mir_executor import cli
    from tools.mir_executor.jobs import JobRegistry
    from tools.mir_executor.tests.test_resume_v2 import prepare_resume

    root = guarded_repo
    _, _, args = prepare_resume(root)
    invoke = root / "invoking"
    invoke.mkdir()
    args.repo_root = invoke
    args.jobs_db = str(root / "tasks/jobs.db")
    write_policy(root, field)

    def registry_effect(*_args, **_kwargs):
        raise AssertionError("registry opened for write before saved target guard")

    monkeypatch.setattr(JobRegistry, "__init__", registry_effect)
    assert cli._handle_resume(args) == 1
    assert "native_policy" in capsys.readouterr().err


@pytest.mark.parametrize("with_hooks", [False, True])
def test_version_and_hooks_policy_allowed_by_execution_api(guarded_repo, monkeypatch, with_hooks):
    root = guarded_repo
    (root / "tools/mir_executor/local.py").unlink()
    policy = {"version": 1}
    if with_hooks:
        policy["hooks"] = {
            "executable": "tools/native-hook", "argv": [], "sha256": "0" * 64,
            "hooks": ["writer_scope", "on_job_event"],
        }
    (root / "config/mir-executor.local.json").write_text(json.dumps({"native_policy": policy}))
    runner = executor.MirExecutor(root)
    expected = object()
    monkeypatch.setattr(executor, "_guard_codex_main_worktree", lambda *_: None)
    monkeypatch.setattr(runner, "_run_codex_mcp_for_async", lambda *_: expected)
    assert runner.run_codex(["exec", "go"], cwd=root) is expected


@pytest.mark.parametrize("backend", ["codex", "claude", "review"])
@pytest.mark.parametrize(
    "field", ["target_admission", "verifier_aliases", "agent_route", "unknown"]
)
def test_direct_read_only_provider_runner_refuses_policy_before_effects(
    guarded_repo, monkeypatch, backend, field,
):
    root = guarded_repo
    (root / "tools/mir_executor/local.py").unlink()
    write_policy(root, field)
    effects = []

    def provider_effect(*_args, **_kwargs):
        effects.append("provider")
        raise AssertionError("provider invoked before native policy guard")

    route = dispatch.AgentRoute(
        target_agent="reviewer", execution_backend=backend, model=None,
        reasoning_effort=None, definition_path="", definition_sha256="",
        base_instructions="review only", sandbox="read-only",
    )
    if backend == "codex":
        runner = dispatch.build_codex_mcp_runner(
            root, "review", agent_route=route, client_factory=provider_effect,
        )
    elif backend == "review":
        runner = dispatch.build_codex_review_runner(root, client_factory=provider_effect)
    else:
        monkeypatch.setattr(dispatch, "_run_claude_adapter", provider_effect)
        runner = dispatch.build_claude_runner(root, agent_route=route)
    with pytest.raises(ValueError, match="native_policy"):
        runner(SimpleNamespace(path=root, dispatch_id="direct-read-only"), 1)
    assert effects == []
    assert not (root / ".mir-dispatch").exists()
