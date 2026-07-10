"""harness orchestrator 13-state SM (phase-4)."""
from __future__ import annotations

from enum import StrEnum


class RunState(StrEnum):
    """Phase-4 13-state state machine for a single run.

    See docs/harness-engineering/phase-4-state-machine.md §1.
    """

    IDLE = "IDLE"
    DISCOVER = "DISCOVER"
    PLAN = "PLAN"
    NEED_APPROVAL = "NEED_APPROVAL"
    ACT = "ACT"
    VERIFY = "VERIFY"
    REPORT = "REPORT"
    DONE = "DONE"
    REPLAN = "REPLAN"
    BLOCKED = "BLOCKED"
    CANCELLING = "CANCELLING"
    ROLLBACK = "ROLLBACK"
    INTERRUPTED = "INTERRUPTED"


# Transition table per phase-4-state-machine.md §1 table
RUN_TRANSITIONS: dict[RunState, set[RunState]] = {
    RunState.IDLE:          {RunState.DISCOVER},
    RunState.DISCOVER:      {RunState.PLAN, RunState.BLOCKED},
    RunState.PLAN:          {RunState.NEED_APPROVAL, RunState.ACT, RunState.REPLAN},
    RunState.NEED_APPROVAL: {RunState.ACT, RunState.CANCELLING},
    RunState.ACT:           {RunState.VERIFY, RunState.INTERRUPTED, RunState.CANCELLING},
    RunState.VERIFY:        {RunState.REPORT, RunState.REPLAN, RunState.BLOCKED},
    RunState.REPORT:        {RunState.DONE},
    RunState.DONE:          set(),  # terminal
    RunState.REPLAN:        {RunState.PLAN},
    RunState.BLOCKED:       {RunState.DISCOVER, RunState.CANCELLING, RunState.REPLAN},
    RunState.CANCELLING:    {RunState.ROLLBACK, RunState.DONE},
    RunState.ROLLBACK:      {RunState.INTERRUPTED, RunState.DONE},
    RunState.INTERRUPTED:   {RunState.IDLE, RunState.DONE},
}


class InvalidRunTransitionError(Exception):
    """Raised when an invalid 13-state transition is attempted."""


def is_valid_run_transition(from_state: RunState, to_state: RunState) -> bool:
    """True iff from->to is in RUN_TRANSITIONS table."""
    return to_state in RUN_TRANSITIONS.get(from_state, set())


def get_allowed_next_run_states(state: RunState) -> set[RunState]:
    """Set of states reachable from state."""
    return RUN_TRANSITIONS.get(state, set())


def is_terminal_run(state: RunState) -> bool:
    """True iff state has no outgoing transitions."""
    return len(RUN_TRANSITIONS.get(state, set())) == 0


# Mapping 7-state (TaskState) -> 13-state (RunState) per ADR-44 §2
SEVEN_TO_THIRTEEN: dict[str, RunState] = {
    "clarification": RunState.DISCOVER,
    "design": RunState.PLAN,
    "codex_delegation": RunState.ACT,
    "running": RunState.ACT,
    "review": RunState.VERIFY,
    "completed": RunState.DONE,
    "blocked": RunState.BLOCKED,
}
