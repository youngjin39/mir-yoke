"""CompiledJob - TaskSpec -> Engine compile output.

design §4.1.6 · §9.11 Compile Stage.
v0.5.3: upgraded from dataclass to frozen pydantic for audit integrity.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .route_decision import RouteDecision
from .task_spec import TaskSpec


class CompiledJob(BaseModel):
    """Execution plan that passed compile; input to the actual Worker spawn."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    spec: TaskSpec
    route: RouteDecision
    resolved_files: dict[str, str]          # path -> sha256 (pinned at compile time)
    required_tools: tuple[str, ...]
    session_plan: dict[str, str]            # role → session_uuid (R2 Engine-minted)
    guides_plan: dict[str, tuple[str, ...]] # "type" → argv list (R9/H3)
    budget: dict[str, int]
    workdir: str                            # git-worktree path (ccswarm pattern)
    role: str                               # executor / reviewer / planner / tester
    session_uuid: str                       # session occupied by this CompiledJob
