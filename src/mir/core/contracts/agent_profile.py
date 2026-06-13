"""AgentProfile - CAO 14-field pydantic model + .fork() API.

design §4.1.3 · O8 silent-pass block.
BORROWED-FROM: awslabs/cli-agent-orchestrator@cd06a5a12680e82e7b2e19ade08ff40a7115f164
                src/cli_agent_orchestrator/models/agent_profile.py#AgentProfile
License: Apache-2.0
Status: adapted (preserves the 14-field signature + extra='forbid' + fork)
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AgentProfile(BaseModel):
    """CAO 14 fields plus the harness-specific `.fork()` helper."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    # === CAO 14 fields (preserve original order and types) ===
    name: str
    slug: str                                    # family slug
    model: Literal["opus", "sonnet", "haiku"]
    description: str
    role_binding: Literal[
        "conductor", "executor", "reviewer", "planner", "tester"
    ] = "executor"
    system_prompt: str
    tools: tuple[str, ...] = ()                  # allowed MCP tool names (namespaced)
    forbidden_tools: tuple[str, ...] = ()
    context_budget_tokens: int = Field(ge=1000, le=200000)
    temperature: float = Field(ge=0.0, le=2.0, default=0.2)
    max_output_tokens: int = Field(ge=256, le=16000, default=4096)
    stop_sequences: tuple[str, ...] = ()
    allowed_files: tuple[str, ...] = ()          # glob pattern
    provenance: dict[str, str] = Field(default_factory=dict)

    def fork(self, **overrides) -> AgentProfile:
        """Create a new instance from this profile with selected 14-field overrides."""
        return self.model_copy(update=overrides)
