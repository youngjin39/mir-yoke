"""Sub-agent execution policy loading for mir_executor."""

from __future__ import annotations

import json
import os
import pathlib
from dataclasses import dataclass, field
from typing import Any, Literal, cast

POLICY_ENV_VAR = "MIR_SUB_AGENT_POLICY"
POLICY_RELPATH = pathlib.Path("config") / "sub-agent-policy.json"
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
    return SubAgentPolicy(mode="force_codex", per_project={}, routing={}, monitoring={})


def _read_json_object(path: pathlib.Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("sub-agent policy must be a JSON object")
    return data


def _resolve_policy(data: dict[str, Any]) -> SubAgentPolicy:
    mode = data.get("mode")
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


def load_sub_agent_policy(repo_root: pathlib.Path) -> SubAgentPolicy:
    """Load sub-agent policy, fail-closed to force_codex on invalid inputs."""
    try:
        data = _read_json_object(repo_root / POLICY_RELPATH)
        overlay_env = os.environ.get(POLICY_ENV_VAR)
        if overlay_env:
            overlay_path = pathlib.Path(overlay_env).expanduser()
            if overlay_path.exists():
                data = {**data, **_read_json_object(overlay_path)}
        return _resolve_policy(data)
    except (OSError, ValueError, json.JSONDecodeError):
        return _default_policy()
