"""Read-only agent constraints survive local route overrides."""

import pytest

from tools.mir_executor import dispatch


@pytest.mark.parametrize("backend", ["codex", "claude"])
@pytest.mark.parametrize("hook_sandbox", ["default", None, "workspace-write"])
@pytest.mark.parametrize("constraint", ["frontmatter", "reviewer"])
def test_should_return_read_only_route_when_agent_is_restricted(
    tmp_path, backend, hook_sandbox, constraint,
):
    name = "codex-final-reviewer" if constraint == "reviewer" else "auditor"
    agents = tmp_path / ".claude/agents"
    agents.mkdir(parents=True)
    (agents / f"{name}.md").write_text(
        f"---\nexecution_backend: {backend}\nmodel: sonnet\n"
        + ("disallowedTools: Write, Edit\n" if constraint == "frontmatter" else "")
        + "---\nReview the owned scope.\n"
    )
    if hook_sandbox != "default":
        hooks = tmp_path / "tools/mir_executor"
        hooks.mkdir(parents=True)
        (hooks / "local.py").write_text(
            "from tools.mir_executor.dispatch import AgentRoute\n"
            "def resolve_agent_route(root, name):\n"
            f"    return AgentRoute(name, {backend!r}, 'hook-model', 'high', "
            f"'hook-definition', 'digest', 'Hook instructions', {hook_sandbox!r})\n"
        )
    route = dispatch.resolve_agent_route(tmp_path, name)
    assert route.sandbox == "read-only"
    assert dispatch.agent_route_expects_changes(route) is False
    if hook_sandbox != "default":
        assert route.model == "hook-model"
        assert route.base_instructions == "Hook instructions"


@pytest.mark.parametrize("sandbox", [None, "read-only"])
def test_should_preserve_hook_route_when_agent_has_no_read_only_constraint(tmp_path, sandbox):
    hooks = tmp_path / "tools/mir_executor"
    hooks.mkdir(parents=True)
    (hooks / "local.py").write_text(
        "from tools.mir_executor.dispatch import AgentRoute\n"
        "def resolve_agent_route(root, name):\n"
        "    return AgentRoute(name, 'codex', None, None, 'local', 'sha', "
        f"'instructions', {sandbox!r})\n"
    )
    route = dispatch.resolve_agent_route(tmp_path, "implementer")
    assert route.sandbox == sandbox
    assert dispatch.agent_route_expects_changes(route) is (sandbox != "read-only")


def test_should_return_read_only_hook_route_when_reviewer_definition_is_absent(tmp_path):
    hooks = tmp_path / "tools/mir_executor"
    hooks.mkdir(parents=True)
    (hooks / "local.py").write_text(
        "from tools.mir_executor.dispatch import AgentRoute\n"
        "def resolve_agent_route(root, name):\n"
        "    return AgentRoute(name, 'codex', None, None, 'local', 'sha', 'review')\n"
    )
    route = dispatch.resolve_agent_route(tmp_path, "codex-final-reviewer")
    assert route.sandbox == "read-only"
    assert dispatch.agent_route_expects_changes(route) is False
