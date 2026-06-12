---
phase: 4
title: State Machine
status: consolidated-v1
depends_on: phase-2-enforcement
---

# Phase 4 -- State Machine & Run Orchestration

> **Purpose**: Track task progress through a JSON schema + state machine, not through the model's natural-language responses. Handle interrupts, failures, and restarts deterministically.

## 0.5 Design Goals (R9 anchor)

**3-axis contribution**:
- **Axis I (self-harness hardening)**: 13-state SM code running (`run_orchestrator.py`, P1 priority)
- **Axis II (public template sync)**: template 5 schemas + identical 13-state SM definition + families must satisfy schema
- **Axis III (fleet central management)**: family run_state central catalog (your-harness aggregates family run_states -> fleet-harness-state.json)

**Inter-phase contract**:
- **Input** (consumes): phase-2 (hook firing result) + phase-3 (memory_refs + context)
- **Output** (provides): run_state.json transitions + tool_event log -> phase-5 subagent entry + phase-6 measurement trigger

## 1. 13-State Machine

The actual enum has 13 values -- this is the canonical count. All references in this document use 13.

```text
IDLE -> DISCOVER -> PLAN -> NEED_APPROVAL -> ACT -> VERIFY -> REPORT -> DONE
                                             |
              REPLAN <- BLOCKED <- CANCELLING <- ROLLBACK <- INTERRUPTED
```

| State | Meaning | Valid next states |
|---|---|---|
| IDLE | No active task | DISCOVER |
| DISCOVER | Collecting context and requirements | PLAN, BLOCKED |
| PLAN | Building plan | NEED_APPROVAL, ACT, REPLAN |
| NEED_APPROVAL | Waiting for user approval | ACT, CANCELLING |
| ACT | Executing | VERIFY, INTERRUPTED, CANCELLING |
| VERIFY | Verifying | REPORT, REPLAN, BLOCKED |
| REPORT | Writing report | DONE |
| DONE | Completed | (terminal) |
| REPLAN | Plan rebuild required | PLAN |
| BLOCKED | Waiting on external dependency | DISCOVER, CANCELLING, REPLAN |
| CANCELLING | Cancellation in progress | ROLLBACK, DONE |
| ROLLBACK | Recovering partial changes | INTERRUPTED, DONE |
| INTERRUPTED | Force stopped | IDLE, DONE |

## 2. Source-of-Truth Principle

- Do not use the model's natural-language responses as state SoT.
- File change facts are confirmed **only via tool results or git diff**.
- State transitions commit **only via JSON file updates**.
- The update owner is **the orchestration script** (LLM must not directly edit JSON -- risk of schema corruption).

### 2-1. Abnormal transition guard hook

Transitions not listed in the table above are blocked by hook.

| Abnormal transition | Detection hook | Action |
|---|---|---|
| DONE -> DISCOVER (escaping terminal) | `.claude/hooks/sm-transition-guard.sh` | exit 1, "DONE is terminal, create new run_state instead" |
| ACT entry without NEED_APPROVAL resolved | same | exit 1, block ACT entry without approval_id (approval.status != APPROVED) |
| REPORT entry without VERIFY result | same | exit 1, "Cannot enter REPORT without VERIFY pass" |
| Multiple ACT transitions for same run_id (lane collision) | same | exit 1, block without current_lane declared |
| Direct mutation of terminal state (DONE/INTERRUPTED) | same | exit 1, append-only ledger required |

**Current implementation**: All 5 detections above are **not yet implemented**. The prohibition on LLM directly editing JSON state files is enforced manually. To be landed with run_orchestrator.py (P1 stage).

## 3. JSON Schemas (5 types)

All 5 schemas are defined in `docs/templates/_schema/` as JSON Schema Draft 2020-12. The YAML blocks below are summaries only -- see schema files for full field definitions, constraints, and required fields.

**Additional schemas** (from R7):
- `docs/templates/_schema/report_contract.schema.json` -- report contract (phase-6 §9)
- `docs/templates/_schema/family_config.schema.json` -- family opt-in fields

### 3-1. `run_state.schema.json`
Single execution unit. Full definition: `docs/templates/_schema/run_state.schema.json`

```yaml
run_id: <ulid>                # required, ULID 26-char
task_id: <ulid ref>           # required
status: <13-state enum>       # required
started_at: <iso-datetime>    # required
last_transition: <iso>        # required
current_step: <step_id>       # optional
current_lane: claude|codex|shared  # optional; required during ACT/VERIFY
retry_count: {total, verify_failures, patch_conflicts, tool_failures_same_type}
artifacts: [<path>]
tool_events: [<ulid>]
approval_id: <ulid>            # if status was NEED_APPROVAL
blocked_reason: <string>       # required if status == BLOCKED
rollback_target: <git ref>     # required if status in [ROLLBACK, INTERRUPTED]
```

### 3-2. `task_state.schema.json`
Task itself (multiple runs possible). Full definition: `docs/templates/_schema/task_state.schema.json`

```yaml
task_id: <ulid>               # required
title: <string 1-200>         # required
task_type: <4-way enum>       # required (phase-1 section 4)
risk_level: low|medium|high   # required
status: ACTIVE|NEEDS_FIX|BLOCKED|COMPLETED|ARCHIVED  # required
required_reads: [<path>]      # 5-element declaration
required_tools: [<name>]      # 5-element declaration
required_checks: [<check>]    # 5-element declaration
route_to: executor_lane|review_lane|planning_flow|ops_flow
report_contract: <name>       # phase-6 section 9
runs: [<ulid>]
created: <iso>                # required
updated: <iso>
completed_at: <iso>           # required if status == COMPLETED
```

### 3-3. `tool_event.schema.json`
Tool call event. Full definition: `docs/templates/_schema/tool_event.schema.json`

```yaml
event_id: <ulid>              # required
run_id: <ulid ref>            # required
tool: <name>                  # required
idempotency_key: <hex hash>   # required, 16-64 chars
precondition: <expr>
dry_run: bool
side_effect_summary: <string 0-500>
ts: <iso>                     # required
duration_ms: <int>
result: ok|already_applied|error|denied|timeout  # required
error: {type, recoverable, summary, details_ref}  # required if result in [error,denied,timeout]
```

### 3-4. `approval.schema.json`
Approval object. Full definition: `docs/templates/_schema/approval.schema.json`

```yaml
approval_id: <ulid>           # required
run_id: <ulid ref>            # required
status: PENDING|APPROVED|REJECTED|EXPIRED  # required
risk_level: low|medium|high   # required
auto_policy: auto|conditional|required     # required
requested_at: <iso>           # required
decided_at: <iso>             # required if status != PENDING
decided_by: <user>            # required if APPROVED/REJECTED
expires_at: <iso>
summary: <string 0-1000>
details_ref: <path|id>
```

### 3-5. `memory_entry.schema.json`
Memory entry (see [Phase 3 section 4](phase-3-memory-context.md)). Full definition: `docs/templates/_schema/memory_entry.schema.json`

```yaml
id: <slug>                    # required, kebab/snake-case
type: user|feedback|project|reference|incident  # required
body: <markdown>              # required
status: active|deprecated|superseded|critical|expired  # required, default=active
superseded_by: <id ref>       # required if status == superseded
valid_until: <date>           # optional; permanent if absent
tags: [<string>]
owner: <user|agent|"shared">
sot: global|personal|project
created: <iso>                # required
updated: <iso>
linked: [<id ref>]
```

## 4. Tool Contract Mandatory Fields

All side-effect tools must provide these 5 fields.

| Field | Meaning |
|---|---|
| `idempotency_key` | Same input -> same result. Safe to re-run. |
| `precondition` | Pre-execution validation condition |
| `dry_run` | Preview mode |
| `side_effect_summary` | One-line description of what changes |
| Return `already_applied: bool` | Idempotency result indicator |

Without this contract, retries, rollbacks, and interrupts are non-deterministic.

## 5. Structured Errors

All tool errors carry these 4 fields.

```yaml
error:
  type: validation|precondition|runtime|timeout|denied|injection
  recoverable: bool
  summary: <one-line>
  details_ref: <path or id>
```

Full definition: `docs/templates/_schema/tool_event.schema.json` `error` field.

`recoverable: true` -> retry eligible. `recoverable: false` -> Circuit Breaker or INTERRUPTED entry.

## 6. Retry Budget

Same as [Phase 2 section 5](phase-2-enforcement.md) Circuit Breaker. Counter increments during SM ACT -> VERIFY loop. Quantitative values use phase-2 section 5 YAML block as single source of truth.

Budget exceeded -> BLOCKED -> user intervention or ROLLBACK.

## 7. Interrupt Atomicity

On user interrupt (Ctrl-C, kill) during ACT:

1. Immediately transition ACT -> CANCELLING
2. If incomplete tool calls are idempotent: safe; otherwise enter ROLLBACK
3. ROLLBACK -> recover via diff snapshot or git worktree
4. Recovery complete -> INTERRUPTED -> IDLE

4 atomicity mechanisms:
- diff snapshot (captured at task start)
- patch backup (auto-generated by tool)
- git worktree (for large changes)
- file checksum (for verification)

## 8. 5-Layer Execution Units

```
Turn < Step < Run < Task < Session
```

| Layer | Definition | User terminology |
|---|---|---|
| Turn | One LLM response | (none) |
| Step | One SM state | (none) |
| Run | One DISCOVER->DONE cycle | "slide unit" / "small unit phase" |
| Task | One user-assigned task (multiple runs) | "Phase" (concept) / "Phase ledger" (implementation: `tasks/phase.json`) |
| Session | One conversation (multiple tasks possible) | (none) |

Each layer has its own ID and JSON file.

## 9. `execute.py` Pattern

Main session is preserved; each phase runs as subprocess -- protects main context while achieving worker isolation simultaneously.

```python
# pseudo-code
for phase in phases:
    result = subprocess.run(
        ["claude", "-p", phase.prompt],
        env={**env, "PHASE_ID": phase.id},
    )
    update_run_state(phase.id, result)
    if result.failed: break
```

`mir_executor` implements this pattern.

## 10. Phase JSON Hard-pinning

Record state in JSON when splitting phases -- natural language decisions are prohibited.

```yaml
phase:
  id: P0-F
  goal: <one-line>
  status: pending|active|done|blocked
  artifacts: [<path>]
  verification: [<check>]
  tdd_links: [<test_path>]
```

`tasks/phase.json` is the concrete implementation of this design.

## 11. Prohibitions

- LLM directly editing JSON state files
- Treating model natural language "complete" as a reason for SM transition
- State transition without verifying tool results
- Skipping CANCELLING/ROLLBACK transient states and jumping directly to IDLE on interrupt
- Using tools without `idempotency_key` in the ACT stage

## 12. Application Status

| Item | Status | Location |
|---|---|---|
| 13-State SM | landed | `tools/run_orchestrator/state_machine.py` 13-state SM + `tasks/phase.json` ledger |
| `run_state` schema | partial | `docs/templates/_schema/run_state.schema.json` + run_orchestrator.py state writer/transition paths landed; full SoT closeout pending |
| `task_state` schema | partial | `docs/templates/_schema/task_state.schema.json` + `tasks/phase.json`/orchestrator partial absorption |
| `tool_event` schema | partial | `docs/templates/_schema/tool_event.schema.json` + hook/orchestrator event path landed; full trace closeout pending |
| `approval` schema | partial | `docs/templates/_schema/approval.schema.json` + `approval_gate.py` record/apply paths landed |
| `memory_entry` schema | partial | `docs/templates/_schema/memory_entry.schema.json` + store lifetime fields landed |
| Tool contract mandatory fields | landed | `src/<harness>/core/engine/tool_contract.py` |
| Structured errors | landed | `src/<harness>/core/engine/structured_error.py` |
| Retry budget | partial | `retry_count` schema exists; end-to-end phase-level evidence lacking |
| Interrupt atomicity | partial | git diff/restore manual |
| 5-layer execution units | partial | Task + Session layers only |
| `execute.py` pattern | landed | executor script |
| Phase JSON | landed | `tasks/phase.json` |

## 13. Exit Criterion

One sample task can be traced from DISCOVER -> DONE through JSON file SM 13-state transitions. One intentional interrupt (Ctrl-C) takes the CANCELLING -> ROLLBACK -> INTERRUPTED recovery path. Tool call events are logged in `tool_event`, and tools without `idempotency_key` are blocked in the ACT stage.

## 14. Next Step

[Phase 5 -- Subagents](phase-5-subagents.md)
