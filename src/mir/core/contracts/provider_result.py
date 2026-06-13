"""ProviderResult - Worker dispatch result.

design §4.1.5. frozen + audit reproducibility.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ProviderResult(BaseModel):
    """Single dispatch result from a provider (Claude Code / Codex / ...)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["success", "failed", "timeout", "cancelled"]
    exit_code: int
    stdout_tail: str = Field(max_length=16384)
    stderr_tail: str = Field(max_length=16384)
    artifacts: tuple[dict, ...] = ()              # [{path, sha256, kind}]
    tokens_used: dict[str, int] = Field(default_factory=dict)
    wall_seconds: float = Field(ge=0.0)
    session_uuid: str                             # Engine-minted (R2)
    provider: str                                 # Registry entry_point name
    argv_snapshot: tuple[str, ...] = ()           # for R9/H3 guide reproduction
