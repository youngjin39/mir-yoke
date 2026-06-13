"""DispatchBrief contract for execution-lane handoff and durable resume."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DispatchBriefSourceRefs(BaseModel):
    """Source references used to derive a dispatch brief."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    task_spec: str = Field(min_length=1)
    plan: str = Field(default="tasks/plan.md")
    phase: str = Field(min_length=1)


class DispatchBrief(BaseModel):
    """Execution-ready handoff artifact for one target agent and one slice."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int = Field(default=1)
    task_id: str = Field(min_length=1)
    phase_id: str | None = None
    slice_id: str = Field(min_length=1)
    target_agent: str = Field(min_length=1)
    user_intent: str = Field(min_length=1)
    expanded_goal: str = Field(min_length=1)
    owned_scope: tuple[str, ...] = Field(min_length=1)
    out_of_scope: tuple[str, ...] = ()
    verification_commands: tuple[str, ...] = Field(min_length=1)
    stop_conditions: tuple[str, ...] = Field(min_length=1)
    handoff_refs: tuple[str, ...] = ()
    tdd_change_refs: tuple[str, ...] = ()
    resume_state_ref: str = Field(min_length=1)
    source_refs: DispatchBriefSourceRefs

    @model_validator(mode="after")
    def _validate_contract(self) -> DispatchBrief:
        if self.version != 1:
            raise ValueError("DispatchBrief.version must be 1")
        expected_resume_ref = f"tasks/dispatch/{self.task_id}/{self.slice_id}.json"
        if self.resume_state_ref != expected_resume_ref:
            raise ValueError(
                "DispatchBrief.resume_state_ref must match "
                f"{expected_resume_ref!r}"
            )
        if self.source_refs.plan != "tasks/plan.md":
            raise ValueError("DispatchBrief.source_refs.plan must be 'tasks/plan.md'")
        return self
