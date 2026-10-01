"""Agent routes reach common CLI dispatch runners and finalization."""

import json
from types import SimpleNamespace

import pytest

from tools.mir_executor import cli, dispatch, policy


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


@pytest.mark.parametrize("route_options", [("route-model", "high"), (None, None)])
@pytest.mark.parametrize("source", ["persisted", "validated_object", "validated_dict"])
@pytest.mark.parametrize("backend", ["codex", "claude"])
def test_should_use_agent_route_when_dispatch_brief_names_agent(
    tmp_path, monkeypatch, source, backend, route_options,
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
        mode="force_codex", resolve_category=lambda category: {
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
    args = cli._build_parser().parse_args([
        "execute", "--dispatch", "--repo-root", str(tmp_path),
        "--dispatch-brief", str(brief), "--expect-changes",
    ])
    assert cli._handle_dispatch(args, tmp_path) == 0
    assert calls[0][0] == backend
    assert calls[0][1]["agent_route"].target_agent == "reviewer"
    assert calls[0][1]["agent_route"].sandbox == "read-only"
    assert calls[0][1]["model"] == (route_model or "policy-model")
    assert calls[0][1]["reasoning_effort"] == (route_effort or "medium")
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
