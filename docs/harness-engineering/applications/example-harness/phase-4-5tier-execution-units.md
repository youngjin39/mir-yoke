---
phase: 4
sub_topic: execution_unit_hierarchy
status: design-v1
related: [adr-44, phase-4-state-machine.md, phase-4-application.md]
date: 2026-05-24
round: R18
---

# Phase-4 — 5-Tier Execution Unit IDs

> **R18-T07 deliverable**. Spec for the 5-tier hierarchy:
> `Turn ⊂ Step ⊂ Run ⊂ Task ⊂ Session`.

## 1. Hierarchy

```
Session (a single user conversation, days-to-weeks lifetime)
└── Task (a unit of user-given work, hours-to-days)
    └── Run (one execution attempt of the Task, minutes-to-hours)
        └── Step (a SM phase within a Run, seconds-to-minutes)
            └── Turn (a single LLM round-trip or tool call, seconds)
```

Lifetimes:
| Tier | Typical lifetime | Cardinality per parent |
|---|---|---|
| Session | days-to-weeks (until /clear or compact-reset) | N/A (root) |
| Task | hours-to-days (until COMPLETED/ARCHIVED) | 1..many per Session |
| Run | minutes-to-hours (DISCOVER → DONE) | 1..many per Task (retries) |
| Step | seconds-to-minutes (1 SM state transition) | 5..50 per Run |
| Turn | seconds (1 LLM call or 1 tool invoke) | 1..many per Step |

## 2. Identifier scheme

All 5 tiers use **ULID** (Crockford base32, 26 chars, monotonic-friendly).
Each tier has its own variable name + JSON field:

| Tier | Field | Schema location |
|---|---|---|
| Session | `session_id` | `run_state.schema.json` (header), `task_state.schema.json` (origin_session) |
| Task | `task_id` | `task_state.schema.json` (primary), `run_state.schema.json` (parent) |
| Run | `run_id` | `run_state.schema.json` (primary) |
| Step | `step_id` | `run_state.schema.json` (`current_step`, will be promoted to ULID) |
| Turn | `turn_id` | `tool_event.schema.json` (added in this round) |

## 3. Why 5 tiers (not 3 or 7)?

**Session** is needed for cross-Run continuity. A your-harness conversation may span
many Tasks (e.g., "first fix X, then do Y") within one session. Without
Session, we lose the conversational context grouping.

**Task** is the user-facing unit ("I asked your-harness to do X"). Already established.

**Run** is the retry unit. If a Task fails verification 3 times, that's 3
Runs against 1 Task. Already established.

**Step** is the SM phase. DISCOVER, PLAN, ACT, VERIFY etc. are all Steps
within a Run. Currently `current_step` is free-form text; promote to ULID
so it can be referenced by tool_events.

**Turn** is the atomic operation. 1 LLM round-trip = 1 Turn. 1 tool call =
1 Turn. We need this granularity for tool_event correlation and replay.

Going below Turn (e.g., "single token") is too granular — LLM operations are
not addressable at sub-call level. Going above Session (e.g., "User") would
overlap with auth/identity which is out of phase-4 scope.

## 4. Cross-reference rules

- Every Turn MUST reference its parent Step (`turn.step_id`).
- Every Step MUST reference its parent Run (`step.run_id`).
- Every Run MUST reference its parent Task (`run.task_id`).
- Every Task SHOULD reference its origin Session (`task.origin_session_id`).
  Optional because a Task may be created outside an explicit session (cron,
  external trigger).
- Session has NO parent reference (root).

Validation: jsonschema for each tier MUST enforce ULID pattern
`^[0-9A-HJKMNP-TV-Z]{26}$`.

## 5. Schema impact (R18 scope)

**R18 ships**: documentation + schema field reservations. Actual code
enforcement is R19+ (after `run_orchestrator.py` 13-state cutover).

**R18 schema additions** (deferred to T08 codex slice — schema edits
require regression test pass):

- `run_state.schema.json`:
  - ADD optional `session_id` (ULID pattern)
  - PROMOTE `current_step` from free-form string to ULID pattern
    (BREAKING: requires migration of any existing run_state.json — but
     `tasks/run_state.json` does not exist yet in R18, so no migration)
- `task_state.schema.json`:
  - ADD optional `origin_session_id` (ULID pattern)
- `tool_event.schema.json`:
  - ADD required `turn_id` (ULID pattern)
  - ADD required `step_id` (ULID pattern)

## 6. Backward compatibility (7-state coexistence) — historical

> **historical — 7-state layer + active_task.json removed in ADR-44 R21; this section is historical (2026-06-04)**

Per ADR-44 §2, existing 7-state `active_task.json` does not have any of
these 5-tier fields. That's fine — the 7-state layer doesn't need them.
Only the new 13-state `run_state.json` layer uses 5-tier IDs.

Migration: when a caller transitions from 7-state to 13-state (R19+), it
generates fresh ULIDs for `session_id`, `step_id`, `turn_id` and keeps the
existing `task_id`.

## 7. Implementation pointers

- ULID generation: prefer `python-ulid` package (already a transitive dep
  via mcp[anyio]). Fallback: `time.time_ns() + secrets.token_bytes(10)`
  inline (see ADR-44 acceptance, `tools/run_orchestrator/run_orchestrator.py`).
- Session ID source: Claude Code provides `--session-id` flag. Use that as the canonical session_id.
- Step ID generation: assign at SM transition time, store in
  `run_state.current_step_id` (renamed from `current_step`).
- Turn ID generation: 1 per tool call. Hooks emit Turn ULID to stderr +
  log to tool_event JSONL.

## 8. Verification

R18-T10 (round close) verifies:

1. This doc exists.
2. Schema field reservations documented (not implemented in R18 by
   convention — actual schema edits are R19 work).
3. ULID pattern documented as `^[0-9A-HJKMNP-TV-Z]{26}$` everywhere.

## 9. Out of scope

- Cross-Session aggregation (different concern, not 5-tier).
- ID compression (ULIDs are 26 chars; tokens are not a concern for JSONL).
- Distributed your-harness (multi-machine) — Session ID would need salt for
  uniqueness; deferred.

## 10. Related

- [[ADR-44]] 13-state SM migration
- `phase-4-state-machine.md` §8 (5-tier hierarchy — referenced but not detailed)
- `tool_event.schema.json` (will receive `turn_id` + `step_id` in R19)
- `run_state.schema.json` (will receive `session_id` in R19)
