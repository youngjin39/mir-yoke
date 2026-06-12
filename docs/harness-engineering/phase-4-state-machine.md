---
phase: 4
title: State Machine
status: consolidated-v1
depends_on: phase-2-enforcement
---

# Phase 4 — State Machine & Run Orchestration

> **Purpose**: Track task progress via JSON schema + state machine, not the model's natural-language response. Handle interrupts, failures, and resumption deterministically.

## 0.5 Design Goals (R9 anchor)

> This phase's connection to the [3-axis fleet goals](applications/fleet-catalog.md). When adding a new phase or cherry-picking for a family, the `design` skill (R9-T11) requires `design_goals` as a mandatory input.

**3-axis contribution**:
- **Axis I (your-harness hardening)**: 13-state SM running (`run_orchestrator.py` new, P1 priority)
- **Axis II (public template sync)**: template's 5 schemas + 13-state SM identical definition + family schema compliance obligation
- **Axis III (fleet central governance / back-propagation)**: central catalog of family run_states (your-harness aggregates run_states from all fleet families → fleet-harness-state.json)

**Inter-phase contract**:
- **Input** (consumes): phase-2 (hook firing results) + phase-3 (memory_refs + context)
- **Output** (provides): run_state.json transitions + tool_event log → phase-5 subagent entry + phase-6 measurement trigger

## 1. 13-State Machine

**R7-B-W1 correction**: The state count was inconsistently described as "9-State" (title) / "12-state" (§12 gap) / "13 enum" (schema) across 3 documents. Confirmed the actual 13 enums as truth — title + application state + run_state.schema.json all unified to 13.

```text
IDLE → DISCOVER → PLAN → NEED_APPROVAL → ACT → VERIFY → REPORT → DONE
                                           ↓
                  REPLAN ← BLOCKED ← CANCELLING ← ROLLBACK ← INTERRUPTED
```

| State | Meaning | Valid next states |
|---|---|---|
| IDLE | No active task | DISCOVER |
| DISCOVER | Collecting context and requirements | PLAN, BLOCKED |
| PLAN | Creating a plan | NEED_APPROVAL, ACT, REPLAN |
| NEED_APPROVAL | Awaiting user approval | ACT, CANCELLING |
| ACT | Executing | VERIFY, INTERRUPTED, **CANCELLING** (R7-B-W2: immediate interrupt transition path — aligned with §7 step 1) |
| VERIFY | Verifying | REPORT, REPLAN, BLOCKED |
| REPORT | Writing report | DONE |
| DONE | Finished | (terminal) |
| REPLAN | Plan revision needed | PLAN |
| BLOCKED | Waiting on external dependency | DISCOVER, CANCELLING, **REPLAN** (R7-B-W3: aligned with ASCII diagram — plan change path after dependency resolved) |
| CANCELLING | Cancellation in progress | ROLLBACK, DONE |
| ROLLBACK | Reverting partial changes | INTERRUPTED, DONE |
| INTERRUPTED | Forced stop | IDLE, DONE |

## 2. Source of Truth Principle

- Do not use the model's natural-language response as the state SoT.
- File change facts are confirmed only via **tool results or git diff**.
- State transitions are committed only via JSON file updates.
- Update owner is the **orchestration script** (LLM direct JSON editing prohibited — schema breakage risk).

### 2-1. Illegal Transition Prevention Hook (R7-B-I1)

Transition attempts not listed in the §1 transition table are blocked by hook.

| Illegal transition | Detection hook | Action |
|---|---|---|
| DONE → DISCOVER (terminal escape) | `.claude/hooks/sm-transition-guard.sh` (new, not implemented) | exit 1, "DONE is terminal, create new run_state instead" |
| ACT entry with unresolved NEED_APPROVAL | same | exit 1, block ACT entry without approval_id (approval.status != APPROVED) |
| REPORT entry without VERIFY results | same | exit 1, "Cannot enter REPORT without VERIFY pass" |
| Multiple ACT transitions on same run_id (lane conflict) | same | exit 1, block undeclared current_lane (linked with R7-B-I3 schema allOf) |
| Direct update of terminal states (DONE/INTERRUPTED) | same | exit 1, append-only ledger obligation |

**Current implementation status**: All 5 detections above are hook **not implemented**. "LLM must not directly edit JSON state files" from §11 is enforced manually by user. This hook lands simultaneously with Phase 1 stage (run_orchestrator.py new).

## 3. 5 JSON Schemas (+ R7 additions)

**R4 update (2026-05-23)**: All 5 schemas formally defined in JSON Schema Draft 2020-12 format in `docs/templates/_schema/`. The blocks below are summaries only — for full field definitions, constraints, and required fields, refer directly to the schema files.

**R7 additions (2026-05-23)**: 2 design schemas added beyond the original 5.
- [`docs/templates/_schema/report_contract.schema.json`](../../docs/templates/_schema/report_contract.schema.json) — report contract from phase-6 §9 (R7-C-I1)
- [`docs/templates/_schema/family_config.schema.json`](../../docs/templates/_schema/family_config.schema.json) — opt-in fields from applications/exceptions.md §5 (R7-D-W5)

### 3-1. `run_state.schema.json`
A single execution unit. Full definition: [`docs/templates/_schema/run_state.schema.json`](../../docs/templates/_schema/run_state.schema.json)

```yaml
run_id: <ulid>                # required, ULID 26-char
task_id: <ulid ref>           # required
status: <13-state enum>       # required
started_at: <iso-datetime>    # required
last_transition: <iso>        # required
current_step: <step_id>       # optional
current_lane: claude|codex|shared  # optional, required during ACT/VERIFY
retry_count: {total, verify_failures, patch_conflicts, tool_failures_same_type}
artifacts: [<path>]
tool_events: [<ulid>]
approval_id: <ulid>            # if status was NEED_APPROVAL
blocked_reason: <string>       # required if status == BLOCKED
rollback_target: <git ref>     # required if status in [ROLLBACK, INTERRUPTED]
```

### 3-2. `task_state.schema.json`
The task itself (multiple runs possible). Full definition: [`docs/templates/_schema/task_state.schema.json`](../../docs/templates/_schema/task_state.schema.json)

```yaml
task_id: <ulid>               # required
title: <string 1-200>         # required
task_type: <4-way enum>       # required, phase-1 §4
risk_level: low|medium|high   # required
status: ACTIVE | NEEDS_FIX | BLOCKED | COMPLETED | ARCHIVED   # required
required_reads: [<path>]      # 5-element declaration
required_tools: [<name>]      # 5-element declaration
required_checks: [<check>]    # 5-element declaration
route_to: executor_lane|review_lane|planning_flow|ops_flow
report_contract: <name>       # phase-6 §9
runs: [<ulid>]
created: <iso>                # required
updated: <iso>
completed_at: <iso>           # required if status == COMPLETED
```

### 3-3. `tool_event.schema.json`
Tool call event. Full definition: [`docs/templates/_schema/tool_event.schema.json`](../../docs/templates/_schema/tool_event.schema.json)

```yaml
event_id: <ulid>              # required
run_id: <ulid ref>            # required
tool: <name>                  # required
idempotency_key: <hex hash>   # required, 16-64 char
precondition: <expr>
dry_run: bool
side_effect_summary: <string 0-500>
ts: <iso>                     # required
duration_ms: <int>
result: ok|already_applied|error|denied|timeout   # required
error: {type, recoverable, summary, details_ref}  # required if result in [error,denied,timeout]
```

### 3-4. `approval.schema.json`
Approval object. Full definition: [`docs/templates/_schema/approval.schema.json`](../../docs/templates/_schema/approval.schema.json)

```yaml
approval_id: <ulid>           # required
run_id: <ulid ref>            # required
status: PENDING|APPROVED|REJECTED|EXPIRED   # required
risk_level: low|medium|high   # required
auto_policy: auto|conditional|required      # required
requested_at: <iso>           # required
decided_at: <iso>             # required if status != PENDING
decided_by: <user>            # required if APPROVED/REJECTED
expires_at: <iso>
summary: <string 0-1000>
details_ref: <path|id>
```

### 3-5. `memory_entry.schema.json`
Memory entry (see [[phase-3-memory-context]] §4). Full definition: [`docs/templates/_schema/memory_entry.schema.json`](../../docs/templates/_schema/memory_entry.schema.json)

```yaml
id: <slug>                    # required, kebab/snake-case
type: user|feedback|project|reference|incident  # required (incident added in R4)
body: <markdown>              # required
status: active|deprecated|superseded|critical|expired   # required, default=active
superseded_by: <id ref>       # required if status == superseded
valid_until: <date>           # optional; permanent if absent
tags: [<string>]
owner: <user|agent|"shared">
sot: global|personal|project
created: <iso>                # required
updated: <iso>
linked: [<id ref>]
```

**R4 reason**: Prior R1 review noted "examples only, type/constraint/required unspecified → not implementable." This update adds formal JSON Schema Draft 2020-12 definitions + 5 new files in `docs/templates/_schema/`.

## 4. Tool Contract Mandatory Fields

All side-effect tools require the following 5 fields.

| Field | Meaning |
|---|---|
| `idempotency_key` | Same input → same result. Safe to re-run. |
| `precondition` | Pre-execution validation condition |
| `dry_run` | Preview mode |
| `side_effect_summary` | One-line description of what changes |
| return `already_applied: bool` | Idempotency result indicator |

Without this contract, retries, rollbacks, and interrupts are non-deterministic.

## 5. Structured Errors

All tool errors have the following 4 fields.

```yaml
error:
  type: validation | precondition | runtime | timeout | denied | injection   # R4: injection added (when Phase 2 §3-4 prompt injection is blocked)
  recoverable: bool
  summary: <one-line>
  details_ref: <path or id>
```

Full definition: `error` field in [`docs/templates/_schema/tool_event.schema.json`](../../docs/templates/_schema/tool_event.schema.json).

`recoverable: true` → retry possible; `false` → Circuit Breaker or INTERRUPTED entry.

## 6. Retry Budget

Same as [[phase-2-enforcement]] §5 Circuit Breaker. Counter increments in the SM's ACT → VERIFY loop. Quantitative values use phase-2 §5 yaml block as the single source of truth.

Exceeded → BLOCKED → user intervention or ROLLBACK.

## 7. Interrupt Atomicity

On user interrupt (Ctrl-C, kill) during ACT:

1. Immediately transition ACT → CANCELLING
2. If incomplete tool calls are idempotent: safe; otherwise enter ROLLBACK
3. ROLLBACK → recover via diff snapshot or git worktree
4. Recovery complete → INTERRUPTED → IDLE

4 atomicity mechanisms:
- diff snapshot (captured at task start)
- patch backup (automatically generated by tool)
- git worktree (for large changes)
- file checksum (for verification)

## 8. 5 Execution Layers

```
Turn ⊂ Step ⊂ Run ⊂ Task ⊂ Session
```

| Layer | Definition | User terminology mapping (R6) |
|---|---|---|
| Turn | One LLM response | (N/A) |
| Step | One SM state | (N/A) |
| Run | One DISCOVER → DONE cycle | "slide unit" / "small phase unit" — user's "slide" term maps to this Run layer |
| Task | One user-assigned work item (multiple runs) | "Phase" (concept) / "Phase ledger" (implementation — `tasks/phase.json`) |
| Session | One conversation (multiple tasks possible) | (N/A) |

Each layer has a separate ID + JSON file.

**R6 terminology alignment**: When user specified "divide design and development into small slide units, Phase," "slide" maps to the Run unit (one cycle work division) and "Phase" maps to the Task unit (large work grouping) in this §8. This is a different axis from this document's conceptual "Phase 0–8," distinct from the two meanings of phase in [`../README.md` §2a](../README.md) and [Appendix A §3](appendix-a-sources.md).

## 9. `execute.py` Pattern

Main session is maintained; execute per phase as subprocess — achieves both main context protection and worker isolation.

```python
# pseudo
for phase in phases:
    result = subprocess.run(
        ["claude", "-p", phase.prompt],
        env={**env, "PHASE_ID": phase.id},
    )
    update_run_state(phase.id, result)
    if result.failed: break
```

Borrowed from `harness_framework`. your-harness's `mir_executor` implements this pattern.

## 10. Phase JSON Hard-Fixed

Record state in JSON when splitting into phases — natural-language decisions prohibited.

```yaml
phase:
  id: P0-F
  goal: <one-line>
  status: pending | active | done | blocked
  artifacts: [<path>]
  verification: [<check>]
  tdd_links: [<test_path>]
```

your-harness's `tasks/phase.json` is the embodiment of this concept.

## 11. Prohibitions

- LLM directly editing JSON state files
- Accepting model's natural-language "complete" as a reason for SM transition
- State transition without verifying tool results
- Skipping temporary states (CANCELLING/ROLLBACK) on interrupt and returning directly to IDLE
- Using tools without `idempotency_key` in the ACT stage

## 12. Application State

| Item | Status | Location |
|---|---|---|
| 13-State SM | **land** (R24-T05 correction 2026-05-24) | `tools/run_orchestrator/state_machine.py` 13-state SM + `tasks/phase.json` ledger. R18 land. |
| `run_state` schema | partial land | `docs/templates/_schema/run_state.schema.json` + `run_orchestrator.py` state writer/transition path landed; full SoT closeout remaining |
| `task_state` schema | partial land | `docs/templates/_schema/task_state.schema.json` + `tasks/phase.json`/orchestrator partially absorbed |
| `tool_event` schema | partial land | `docs/templates/_schema/tool_event.schema.json` + hook/orchestrator event path landed; full trace closeout remaining |
| `approval` schema | partial land | `docs/templates/_schema/approval.schema.json` + `approval_gate.py` record/apply path landed |
| `memory_entry` schema | partial land | `docs/templates/_schema/memory_entry.schema.json` + store lifetime fields landed; phase-level done evidence remaining |
| Tool contract mandatory fields | **land** (R24-T05 correction 2026-05-24) | `src/mir/core/engine/tool_contract.py` (R18 land, advisory log `MIR_TOOL_CONTRACT_LOG=1` R22 enabled) |
| Structured errors | **land** (R24-T05 correction 2026-05-24) | `src/mir/core/engine/structured_error.py` (R18 land) |
| Retry budget | partial land | `retry_count` schema exists; phase-level end-to-end evidence insufficient |
| Interrupt atomicity | partial land | git diff/restore manual |
| 5 execution layers | partial land | Task ⊂ Session only |
| `execute.py` pattern | land | `mir_executor` |
| Phase JSON | land | `tasks/phase.json` (P0-F and after) |

**Gap**: 13-state SM code + tool_contract + structured_error all landed in R18 (R24-T05 correction 2026-05-24). Remaining: actual SoT file activation for 5 schemas (run_state/task_state/approval etc. additional code paths needed).

## 13. Exit Criterion

1 sample task trackable from DISCOVER → DONE via SM 13-state transitions in JSON file (R8 correction: previous "9-state" → unified to 13-state). For 1 intentional interrupt (Ctrl-C): recovery confirmed via CANCELLING → ROLLBACK → INTERRUPTED path. Tool call events recorded in `tool_event` log; tools without `idempotency_key` blocked in ACT stage.

## 14. Next Steps

Proceed to [Phase 5 — Subagents](phase-5-subagents.md).
