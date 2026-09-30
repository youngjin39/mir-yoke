"""Sub-agent execution policy loading for mir_executor."""

from __future__ import annotations

import json
import os
import pathlib
import pwd
import sys
from dataclasses import dataclass, field
from typing import Any, Literal, cast

POLICY_ENV_VAR = "MIR_SUB_AGENT_POLICY"
POLICY_RELPATH = pathlib.Path("config") / "sub-agent-policy.json"
# ADR-88: rendered by Mir Harness `mir fleet model-routing`. Used when the environment
# does not name a policy, so a session without MIR_SUB_AGENT_POLICY still routes by
# category instead of silently resolving every route to null. Resolved from the
# account's passwd home, not $HOME, because agent sessions run with a HOME other
# than the account home.
DEFAULT_GLOBAL_POLICY_PATH = (
    pathlib.Path(pwd.getpwuid(os.getuid()).pw_dir) / ".mir/model-routing/sub-agent-policy.json"
)
SUB_AGENT_POLICY_MODES = frozenset(
    {
        "force_codex",
        "force_claude",
        "select",
        "obey_user",
        "unrestricted",
        "per_project",
    }
)

PolicyMode = Literal[
    "force_codex",
    "force_claude",
    "select",
    "obey_user",
    "unrestricted",
    "per_project",
]

# The central policy (Mir Harness ADR-88) spells this mode `user_command_priority`;
# dispatch compares against `obey_user`, so normalise the central word.
MODE_ALIASES: dict[str, PolicyMode] = {"user_command_priority": "obey_user"}


@dataclass(frozen=True)
class SubAgentPolicy:
    """Resolved sub-agent execution policy."""

    mode: PolicyMode
    per_project: dict[str, Any]
    routing: dict[str, Any] = field(default_factory=dict)
    monitoring: dict[str, Any] = field(default_factory=dict)

    def routing_default_model(self) -> str | None:
        """Return the policy default model route, if configured."""
        default = self._routing_default()
        return _string_value(default.get("model")) or _string_value(
            self.routing.get("default_model")
        )

    def routing_default_reasoning_effort(self) -> str | None:
        """Return the policy default reasoning effort route, if configured."""
        default = self._routing_default()
        return _string_value(default.get("reasoning_effort")) or _string_value(
            self.routing.get("default_reasoning_effort")
        )

    def routing_model_rank(self) -> list[str]:
        """Return global model routing priority from highest to lowest."""
        return _string_list(self.routing.get("model_rank"))

    def routing_effort_rank(self) -> list[str]:
        """Return global reasoning effort routing priority from highest to lowest."""
        return _string_list(self.routing.get("effort_rank"))

    def routing_by_category(self, category: str | None = None) -> dict[str, Any]:
        """Return all category-specific routing entries or one category route."""
        by_category = self.routing.get("by_category", {})
        if not isinstance(by_category, dict):
            return {}
        if category is not None:
            route = by_category.get(category, {})
            if not isinstance(route, dict):
                return {}
            return dict(route)
        return dict(by_category)

    def routing_for_category(self, category: str) -> dict[str, Any]:
        """Return the routing entry for one TDD category, if configured."""
        return self.routing_by_category(category)

    def routing_prefer_for_category(self, category: str) -> list[dict[str, Any]]:
        """Return ordered category routing preferences, if configured."""
        prefer = self.routing_by_category(category).get("prefer")
        if not isinstance(prefer, list):
            return []

        entries: list[dict[str, Any]] = []
        for item in prefer:
            if not isinstance(item, dict):
                continue
            entry: dict[str, Any] = {}
            model = _string_value(item.get("model"))
            if model is not None:
                entry["model"] = model
            reasoning_effort = _string_value(item.get("reasoning_effort"))
            if reasoning_effort is not None:
                entry["reasoning_effort"] = reasoning_effort
            if entry:
                entries.append(entry)
        return entries

    def resolve_category(self, category: str) -> dict[str, str | None]:
        """Resolve model/effort routing for one category."""
        category_route = self.routing_for_category(category)
        category_prefer = self.routing_prefer_for_category(category)
        primary_route = category_prefer[0] if category_prefer else category_route

        model = _string_value(primary_route.get("model"))
        reasoning_effort = _string_value(primary_route.get("reasoning_effort"))
        if model is None:
            model = self.routing_default_model()
        if reasoning_effort is None:
            reasoning_effort = self.routing_default_reasoning_effort()
        return {"model": model, "reasoning_effort": reasoning_effort}

    def monitoring_stall_timeout_seconds(self) -> float | None:
        """Return the no-progress stall timeout, if configured."""
        value = self.monitoring.get("stall_timeout_seconds")
        if isinstance(value, bool):
            return None
        if isinstance(value, int | float) and value > 0:
            return float(value)
        return None

    def _routing_default(self) -> dict[str, Any]:
        default = self.routing.get("default", {})
        if not isinstance(default, dict):
            return {}
        return default


def _string_value(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    strings: list[str] = []
    for item in value:
        string_item = _string_value(item)
        if string_item is not None:
            strings.append(string_item)
    return strings


def _default_policy() -> SubAgentPolicy:
    return SubAgentPolicy(mode="select", per_project={}, routing={}, monitoring={})


def _read_json_object(path: pathlib.Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("sub-agent policy must be a JSON object")
    return data


def _declared_mode(data: dict[str, Any]) -> Any:
    """Owner decision 1-A: the central `delegation.mode` decides; a top-level `mode` is legacy."""
    delegation = data.get("delegation")
    if isinstance(delegation, dict) and "mode" in delegation:
        return delegation.get("mode")
    return data.get("mode")


def _resolve_policy(data: dict[str, Any]) -> SubAgentPolicy:
    declared = _declared_mode(data)
    mode = MODE_ALIASES.get(declared, declared) if isinstance(declared, str) else declared
    per_project = data.get("per_project", {})
    if mode not in SUB_AGENT_POLICY_MODES or not isinstance(per_project, dict):
        return _default_policy()
    routing = data.get("routing", {})
    monitoring = data.get("monitoring", {})
    if not isinstance(routing, dict):
        routing = {}
    if not isinstance(monitoring, dict):
        monitoring = {}
    return SubAgentPolicy(
        mode=cast(PolicyMode, mode),
        per_project=dict(per_project),
        routing=dict(routing),
        monitoring=dict(monitoring),
    )


def default_global_policy_path() -> pathlib.Path:
    """Resolve the rendered policy location; tests replace this to stay off the host file."""
    return DEFAULT_GLOBAL_POLICY_PATH


def _overlay_policy_path() -> pathlib.Path:
    """Return the overlay named by ``MIR_SUB_AGENT_POLICY``, else the rendered policy (ADR-88).

    A variable naming a missing file (such as the retired home_server path) used to drop
    the overlay silently, so every route resolved to null; fall back and warn instead.
    """
    overlay_env = os.environ.get(POLICY_ENV_VAR)
    if overlay_env:
        named = pathlib.Path(overlay_env).expanduser()
        if named.exists():
            return named
        print(
            f"[mir policy] {POLICY_ENV_VAR} names a missing file: {named}; "
            "falling back to the rendered policy",
            file=sys.stderr,
        )
    return default_global_policy_path()


def load_sub_agent_policy(repo_root: pathlib.Path) -> SubAgentPolicy:
    """Load sub-agent preferences, falling back to selectable routing."""
    try:
        data = _read_json_object(repo_root / POLICY_RELPATH)
        overlay_path = _overlay_policy_path()
        if overlay_path.exists():
            data = {**data, **_read_json_object(overlay_path)}
        return _resolve_policy(data)
    except (OSError, ValueError, json.JSONDecodeError):
        return _default_policy()
