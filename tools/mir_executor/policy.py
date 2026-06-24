"""Sub-agent execution policy loading for mir_executor."""

from __future__ import annotations

import json
import os
import pathlib
from dataclasses import dataclass
from typing import Any, Literal

POLICY_ENV_VAR = "MIR_SUB_AGENT_POLICY"
POLICY_RELPATH = pathlib.Path("config") / "sub-agent-policy.json"
SUB_AGENT_POLICY_MODES = frozenset(
    {"force_codex", "force_claude", "select", "per_project"}
)

PolicyMode = Literal["force_codex", "force_claude", "select", "per_project"]


@dataclass(frozen=True)
class SubAgentPolicy:
    """Resolved sub-agent execution policy."""

    mode: PolicyMode
    per_project: dict[str, Any]


def _default_policy() -> SubAgentPolicy:
    return SubAgentPolicy(mode="force_codex", per_project={})


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
    return SubAgentPolicy(mode=mode, per_project=dict(per_project))


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
