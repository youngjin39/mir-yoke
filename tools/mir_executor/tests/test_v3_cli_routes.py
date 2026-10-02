"""Agent routes reach common CLI dispatch runners and finalization."""

import json
from types import SimpleNamespace

import pytest

from tools.mir_executor import cli, dispatch, policy


@pytest.fixture
def dispatch_model_options(tmp_path, monkeypatch):
    """Resolve real policy/agent definitions without starting a backend process."""
    config = tmp_path / "config"
    config.mkdir()
    agents = tmp_path / ".claude/agents"
    agents.mkdir(parents=True)
    (agents / "reviewer.md").write_text(
        "---\nexecution_backend: claude\nmodel: sonnet\neffort: high\n---\nReview.\n"
    )
    brief = tmp_path / "brief.json"
    calls = []
    monkeypatch.setattr(
        cli, "_build_dispatch_runner", lambda *a, **kw: calls.append(kw),
    )
    monkeypatch.setattr(dispatch, "run_dispatch", lambda *a, **kw: dispatch.DispatchOutcome(
        "completed", 1, False, None, SimpleNamespace(dispatch_id="review"),
    ))
    monkeypatch.setattr(dispatch, "finalize_dispatch", lambda *a, **kw: (
        dispatch.FinalizeResult("reviewed", "passed", [])
    ))

    def execute(mode, routing, flags=(), *, agent=True):
        (config / "sub-agent-policy.json").write_text(json.dumps({
            "delegation": {"mode": mode}, "routing": routing,
        }))
        brief.write_text(json.dumps({
            "expanded_goal": "Review", **({"target_agent": "reviewer"} if agent else {}),
        }))
        args = cli._build_parser().parse_args([
            "execute", "--dispatch", "--repo-root", str(tmp_path),
            "--dispatch-brief", str(brief), "--category", "unit", *flags,
        ])
        return cli._handle_dispatch(args, tmp_path), calls

    return execute


def test_should_use_category_model_when_force_codex_conflicts_with_agent_backend(
    dispatch_model_options,
):
    result, calls = dispatch_model_options("force_codex", {
        "by_category": {"unit": {"model": "gpt-category", "reasoning_effort": "medium"}},
    })
    assert result == 0
    assert calls[0]["backend"] == "codex"
    assert calls[0]["model"] == "gpt-category"
    assert calls[0]["reasoning_effort"] == "medium"


@pytest.mark.parametrize("model", ["user-model", "sonnet"])
def test_should_keep_explicit_options_when_force_codex_conflicts_with_agent_backend(
    dispatch_model_options, model,
):
    result, calls = dispatch_model_options("force_codex", {
        "default": {"model": "sonnet", "reasoning_effort": "medium"},
    }, ["--model", model, "--reasoning-effort", "user-effort"])
    assert result == 0
    assert calls[0]["backend"] == "codex"
    assert calls[0]["model"] == model
    assert calls[0]["reasoning_effort"] == "user-effort"


def test_should_keep_agent_options_when_mode_is_not_forced(dispatch_model_options):
    result, calls = dispatch_model_options("select", {
        "default": {"model": "gpt-default", "reasoning_effort": "medium"},
    })
    assert result == 0
    assert calls[0]["backend"] == "claude"
    assert calls[0]["model"] == "sonnet"
    assert calls[0]["reasoning_effort"] == "high"


def test_should_keep_explicit_effort_when_force_codex_ignores_agent_options(
    dispatch_model_options,
):
    result, calls = dispatch_model_options("force_codex", {
        "default": {"model": "gpt-default", "reasoning_effort": "medium"},
    }, ["--reasoning-effort", "user-effort"])
    assert result == 0
    assert calls[0]["model"] == "gpt-default"
    assert calls[0]["reasoning_effort"] == "user-effort"


def test_should_keep_matching_agent_options_when_mode_is_forced(dispatch_model_options):
    result, calls = dispatch_model_options("force_claude", {
        "default": {"model": "gpt-default", "reasoning_effort": "medium"},
    })
    assert result == 0
    assert calls[0]["backend"] == "claude"
    assert calls[0]["model"] == "sonnet"
    assert calls[0]["reasoning_effort"] == "high"


@pytest.mark.parametrize("mode, model", [
    ("force_codex", "gpt-default"), ("force_claude", "sonnet"),
    ("force_codex", "custom-model"), ("force_claude", "custom-model"),
])
def test_should_allow_policy_model_when_no_opposite_backend_is_known(
    dispatch_model_options, mode, model,
):
    result, calls = dispatch_model_options(mode, {
        "default": {"model": model, "reasoning_effort": "medium"},
    }, agent=False)
    assert result == 0
    assert calls[0]["model"] == model


@pytest.mark.parametrize("source", ["category", "prefer", "default", "flat_default"])
@pytest.mark.parametrize("mode, model", [
    ("force_codex", "sonnet"), ("force_codex", "opus"),
    ("force_codex", "fable"), ("force_codex", "haiku"),
    ("force_codex", "claude-sonnet-test"), ("force_claude", "gpt-test"),
])
def test_should_fail_before_runner_when_forced_policy_model_belongs_to_other_backend(
    dispatch_model_options, capsys, source, mode, model,
):
    route = {"model": model, "reasoning_effort": "medium"}
    routing = {
        "category": {"by_category": {"unit": route}},
        "prefer": {"by_category": {"unit": {"prefer": [route]}}},
        "default": {"default": route},
        "flat_default": {"default_model": model, "default_reasoning_effort": "medium"},
    }[source]
    result, calls = dispatch_model_options(mode, routing, agent=False)
    assert result == 1
    assert calls == []
    error = capsys.readouterr().err
    assert mode in error
    assert model in error
    assert "model" in error and "backend" in error


def _route(backend="codex", sandbox="read-only"):
    return dispatch.AgentRoute(
        "reviewer", backend, "route-model", "high", "agents/reviewer.md",
        "digest", "Review the owned scope.", sandbox,
    )


@pytest.mark.parametrize("backend", ["codex", "claude"])
def test_should_pass_agent_route_when_building_dispatch_runner(tmp_path, backend):
    calls = []
    module = SimpleNamespace(
        build_codex_mcp_runner=lambda *a, **kw: calls.append(kw),
        build_claude_runner=lambda *a, **kw: calls.append(kw),
    )
    route = _route(backend)
    cli._build_dispatch_runner(
        module, backend=backend, repo_root=tmp_path, prompt="review",
        timeout_seconds=12, model="route-model", reasoning_effort="high",
        agent_route=route,
    )
    assert calls[0]["agent_route"] is route


@pytest.mark.parametrize("backend_flag", [None, "codex", "claude"])
@pytest.mark.parametrize("mode", ["force_codex", "force_claude", "user_command_priority"])
@pytest.mark.parametrize("route_options", [("route-model", "high"), (None, None)])
@pytest.mark.parametrize("source", ["persisted", "validated_object", "validated_dict"])
@pytest.mark.parametrize("backend", ["codex", "claude"])
def test_should_use_agent_route_when_dispatch_brief_names_agent(
    tmp_path, monkeypatch, source, backend, route_options, mode, backend_flag,
):
    route_model, route_effort = route_options
    brief = tmp_path / "brief.json"
    brief.write_text(json.dumps({
        "expanded_goal": "Review the code", **(
            {"target_agent": "reviewer"} if source == "persisted" else {}
        ),
    }))
    hooks_dir = tmp_path / "tools/mir_executor"
    hooks_dir.mkdir(parents=True)
    (hooks_dir / "local.py").write_text(
        "from tools.mir_executor.dispatch import AgentRoute\n"
        "def resolve_agent_route(root, target):\n"
        "    assert target == 'reviewer'\n"
        f"    return AgentRoute(target, {backend!r}, {route_model!r}, {route_effort!r}, "
        "'agents/reviewer.md', 'digest', 'Review the owned scope.', 'read-only')\n"
        + (
            "def validate_brief(path, root):\n"
            + (
                "    from types import SimpleNamespace\n"
                "    return SimpleNamespace(target_agent='reviewer')\n"
                if source == "validated_object" else
                "    return {'target_agent': 'reviewer'}\n"
            )
            if source != "persisted" else ""
        )
    )
    monkeypatch.setattr(policy, "load_sub_agent_policy", lambda root: SimpleNamespace(
        mode=mode, resolve_category=lambda category: {
            "model": "policy-model", "reasoning_effort": "medium",
        },
    ))
    calls = []
    monkeypatch.setattr(
        dispatch, "build_codex_mcp_runner", lambda *a, **kw: calls.append(("codex", kw)),
    )
    monkeypatch.setattr(
        dispatch, "build_claude_runner", lambda *a, **kw: calls.append(("claude", kw)),
    )
    monkeypatch.setattr(dispatch, "run_dispatch", lambda *a, **kw: dispatch.DispatchOutcome(
        "completed", 1, False, None, SimpleNamespace(dispatch_id="review"),
    ))
    final_calls = []
    monkeypatch.setattr(dispatch, "finalize_dispatch", lambda *a, **kw: (
        final_calls.append(kw) or dispatch.FinalizeResult("reviewed", "passed", [])
    ))
    argv = [
        "execute", "--dispatch", "--repo-root", str(tmp_path),
        "--dispatch-brief", str(brief), "--expect-changes",
    ]
    if backend_flag is not None:
        argv.extend(["--execution-backend", backend_flag])
    args = cli._build_parser().parse_args(argv)
    assert cli._handle_dispatch(args, tmp_path) == 0
    if mode in {"force_codex", "force_claude"}:
        expected_backend = mode.removeprefix("force_")
    else:
        expected_backend = backend_flag or backend
    assert calls[0][0] == expected_backend
    assert calls[0][1]["agent_route"].target_agent == "reviewer"
    assert calls[0][1]["agent_route"].sandbox == "read-only"
    uses_agent_options = expected_backend == backend
    assert calls[0][1]["model"] == (
        route_model if uses_agent_options and route_model else "policy-model"
    )
    assert calls[0][1]["reasoning_effort"] == (
        route_effort if uses_agent_options and route_effort else "medium"
    )
    assert final_calls[0]["expect_changes"] is False


def test_should_dispatch_without_route_when_brief_agent_definition_missing(
    tmp_path, monkeypatch, capsys,
):
    brief = tmp_path / "brief.json"
    brief.write_text(json.dumps({"expanded_goal": "Review", "target_agent": "missing"}))
    monkeypatch.setattr(policy, "load_sub_agent_policy", lambda root: SimpleNamespace(
        mode="force_codex", resolve_category=lambda category: {
            "model": "policy-model", "reasoning_effort": "medium",
        },
    ))
    calls = []
    monkeypatch.setattr(dispatch, "build_codex_mcp_runner", lambda *a, **kw: calls.append(kw))
    monkeypatch.setattr(dispatch, "run_dispatch", lambda *a, **kw: dispatch.DispatchOutcome(
        "completed", 1, False, None, SimpleNamespace(dispatch_id="unrouted"),
    ))
    monkeypatch.setattr(dispatch, "finalize_dispatch", lambda *a, **kw: (
        dispatch.FinalizeResult("reviewed", "passed", [])
    ))
    args = cli._build_parser().parse_args([
        "execute", "--dispatch", "--repo-root", str(tmp_path),
        "--dispatch-brief", str(brief),
    ])
    assert cli._handle_dispatch(args, tmp_path) == 0
    assert calls[0].get("agent_route") is None
    assert "warning" in capsys.readouterr().err.lower()


@pytest.mark.parametrize("entry", ["dispatch", "execute", "background"])
@pytest.mark.parametrize("option,value", [("--timeout", "11"), ("--stall-timeout", "1")])
def test_should_reject_cli_timeout_before_job_or_provider_actions(
    tmp_path, monkeypatch, entry, option, value,
):
    (tmp_path / "config").mkdir()
    (tmp_path / "config/mir-executor.local.json").write_text(
        json.dumps({"timeout_seconds_range": [2, 10]})
    )
    monkeypatch.setattr(cli, "_prepare_execute_root", lambda args: tmp_path)
    monkeypatch.setattr(policy, "load_sub_agent_policy", lambda root: SimpleNamespace(
        mode="force_codex", resolve_category=lambda category: {
            "model": "m", "reasoning_effort": "high",
        },
    ))
    calls = []
    monkeypatch.setattr(cli, "MirExecutor", lambda *a, **kw: calls.append("executor"))
    monkeypatch.setattr(dispatch, "build_codex_mcp_runner", lambda *a, **kw: calls.append("runner"))
    argv = ["execute", "--repo-root", str(tmp_path), "--codex-args", "task", option, value]
    if entry == "dispatch":
        argv.append("--dispatch")
    else:
        argv.extend(["--change-id", "X", "--category", "unit"])
        if entry == "background":
            argv.append("--background")
    args = cli._build_parser().parse_args(argv)
    result = (
        cli._handle_dispatch(args, tmp_path)
        if entry == "dispatch" else cli._handle_execute(args)
    )
    assert result == 1
    assert calls == []
    assert not (tmp_path / "tasks/jobs.db").exists()


def test_should_reject_finalize_timeout_before_dispatch_actions(tmp_path, monkeypatch):
    (tmp_path / 'config').mkdir()
    (tmp_path / 'config/mir-executor.local.json').write_text(
        json.dumps({'timeout_seconds_range': [2, 10]})
    )
    monkeypatch.setattr(cli, '_prepare_execute_root', lambda args: tmp_path)
    monkeypatch.setattr(policy, 'load_sub_agent_policy', lambda root: SimpleNamespace(
        mode='force_codex', resolve_category=lambda category: {
            'model': 'm', 'reasoning_effort': 'high',
        },
    ))
    calls = []
    monkeypatch.setattr(dispatch, 'build_codex_mcp_runner',
                        lambda *a, **kw: calls.append('runner'))
    args = cli._build_parser().parse_args([
        'execute', '--dispatch', '--repo-root', str(tmp_path), '--codex-args', 'task',
        '--finalize-lock-timeout', '11',
    ])
    assert cli._handle_dispatch(args, tmp_path) == 1
    assert calls == []
    assert not (tmp_path / 'tasks/jobs.db').exists()
