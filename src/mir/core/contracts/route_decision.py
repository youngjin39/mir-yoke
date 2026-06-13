"""RouteDecision - Router classification result.

design §4.1.7 · §7.1 Router.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class RouteDecision(BaseModel):
    """Decision produced by Router after analyzing a TaskSpec."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal[
        "bugfix", "feature", "refactor", "security", "research", "unknown"
    ] | None
    mode: Literal["deterministic", "supervisor_needed"]
    signals: dict[str, bool]               # {"file_path": bool, "function_name": bool, ...}
    executor_provider: str                 # Registry entry_point name
    reviewer_provider: str | None          # §9.15 ReviewerSelector result (may degenerate)
