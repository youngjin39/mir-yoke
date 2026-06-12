---
phase: 4
title: State Machine Application
status: done
family: your-harness (SE-meta)
blueprint: ../../phase-4-state-machine.md
priority: P1 (largest gap) — COMPLETE
r18_landed: 2026-05-24
r18_artifacts:
  - tools/run_orchestrator/state_machine.py (13-state SM, parallel layer)
  - tools/run_orchestrator/run_orchestrator.py (run_state.json driver)
  - src/your_harness/core/engine/structured_error.py (phase-4 §5)
  - src/your_harness/core/engine/tool_contract.py (phase-4 §4)
  - src/your_harness/core/engine/interrupt_handler.py (phase-4 §7, stash-based)
  - docs/decisions/adr-44-13-state-sm-migration-2026-05-24.md (parent ADR)
  - docs/harness-engineering/applications/example-harness/phase-4-5tier-execution-units.md
  - docs/harness-engineering/applications/example-harness/phase-4-approval-discord-delegation.md
r20_landed: 2026-05-24
r20_artifacts:
  - .claude/hooks/pre-tool-use.sh — validate_tool_contract.py wire (env-gated)
  - docs/templates/_schema/run_state.schema.json — session_id + current_step_id ULID
  - docs/templates/_schema/tool_event.schema.json — turn_id required, step_id optional
  - docs/templates/_schema/task_state.schema.json — origin_session_id optional
  - tools/run_orchestrator/cli.py — --use-13-state dual-mode + transitions-list subcommand
  - tools/run_orchestrator/approval_gate.py — request/parse/apply Discord-delegated approval
  - docs/templates/_schema/approval.schema.json — DENIED/DELAYED + discord_chat_id + reasons
r21_deferred:
  - remaining 7-state cleanup / default-flip hardening for residual callers — resolved per ADR-44 §9 (parallel 7-state removed, default-flip done R20; 2026-06-04)
  - worktree-based interrupt (currently stash-only, parallel ACT support)
  - Fleet phase-4 rollout (deploy 13-state SM + modules to family repos)
  - Discord plugin reply parser integration (session-start.sh)
---

# Phase 4 — State Machine Application (example-harness)

> **Priority P1**. This was the largest implementation gap in your-harness, and is now the core phase whose your-harness closeout is complete.

## 1. Blueprint Reference

[`../../phase-4-state-machine.md`](../../phase-4-state-machine.md) full. Key sections: §1 13-State SM, §3 JSON schema 5 types, §4 tool contract mandatory fields, §6 retry budget, §7 interrupt atomicity.

**Related Supplementary Documents**:
- [`../autonomous-execution.md`](../autonomous-execution.md) — this phase is the SM foundation for autonomous operation. Once the 13-State SM is complete, the autonomous reply loop can run.
- [`../design-process.md`](../design-process.md) — apply the 5-step + iteration requirement when writing ADR-24 for this phase.

## 2. Current State (closeout snapshot)

| Item | Blueprint Location | your-harness State |
|---|---|---|
| 13-State SM | §1 | land — `tools/run_orchestrator/state_machine.py` + CLI/daemon dual-path |
| `run_state.schema.json` | §3-1 | land — run tracking schema + orchestrator driver |
| `task_state.schema.json` | §3-2 | land — run/report contract fields consumed |
| `tool_event.schema.json` | §3-3 | land — tool contract validator + structured error path |
| `approval.schema.json` | §3-4 | land — Discord-delegated approval object + parser |
| `memory_entry.schema.json` | §3-5 | partial land — supplemented by Phase 3 work |
| Tool contract mandatory fields | §4 | land — `validate_tool_contract.py` + `tool_contract.py` + required env wire |
| Structured error | §5 | land — `structured_error.py` + tool-event mapping |
| Retry budget | §6 | partial land — `run_state.retry_count` + VERIFY→BLOCKED seam landed, broader hardening follow-up |
| Interrupt atomicity | §7 | partial land — stash-based handler landed, worktree path follow-up |
| 5-tier execution units | §8 | land — turn/step/run/task/session identifiers reflected in schema/docs |
| `execute.py` pattern | §9 | land — `harness_executor` |
| Phase JSON | §10 | land — `tasks/phase.json` |

**Gap**: worktree-based interrupt, residual 7-state cleanup/default flip hardening (resolved per ADR-44 §9 — parallel 7-state removed, default-flip done R20; 2026-06-04), family rollout, Discord reply parser integration.

## 3. Application Work Steps (historical closeout path)

| Step | Work | Dependency | Status |
|---|---|---|---|
| 4-1 | 13-State SM ADR/design documentation | – | done |
| 4-2 | 5 JSON schema newly added | 4-1 | done |
| 4-3 | `run_state` SoT implementation | 4-2 | done |
| 4-4 | Tool contract mandatory fields + hook wire | 4-2 | done |
| 4-5 | Structured error standardization | 4-2 | done |
| 4-6 | Interrupt atomicity phase 1 (stash-based) | 4-3 | partial |
| 4-7 | 5-tier execution unit identifier integration | 4-3 | done |
| 4-8 | TDD/regression verification | 4-3, 4-4, 4-5, 4-6 | done |
| 4-9 | `approval` interactive path (Discord delegated) | 4-2 | done |

**Total Estimate**: approximately 43h (1.5 weeks of work), ±10h depending on step 4-9 decision.

## 4. Files to Modify

| Path | Type |
|---|---|
| `docs/decisions/adr-24-13-state-sm-2026-MM-DD.md` | create |
| `docs/templates/_schema/run_state.schema.json` | create |
| `docs/templates/_schema/task_state.schema.json` | create |
| `docs/templates/_schema/tool_event.schema.json` | create |
| `docs/templates/_schema/approval.schema.json` | create |
| `docs/templates/_schema/memory_entry.schema.json` | create |
| `src/your_harness/core/engine/run_orchestrator.py` | create |
| `src/your_harness/core/engine/state_machine.py` | create |
| `src/your_harness/core/engine/tool_contract.py` | create |
| `src/your_harness/core/engine/structured_error.py` | create |
| `src/your_harness/core/engine/interrupt_handler.py` | create |
| `.claude/hooks/pre-tool-use.sh` and all other hooks | edit (add tool contract fields) |
| `tests/test_state_machine.py` | create |
| `tests/test_run_orchestrator.py` | create |
| `tests/test_tool_contract.py` | create |
| `tests/test_interrupt_handler.py` | create |
| `tasks/phase.json` | edit (can add run_id field) |

## 5. Verification Procedure

Blueprint §13 Exit Criterion: "Sample task 1 can track DISCOVER → DONE transitions as JSON file through all 13 states. One intentional interrupt results in CANCELLING → ROLLBACK → INTERRUPTED recovery path measured. Tool call events are recorded in `tool_event` log and tools without `idempotency_key` are blocked at ACT stage."

Verification methods:
1. Dummy code task → confirm run_state.json records all DISCOVER → PLAN → ACT → VERIFY → REPORT → DONE transitions
2. Ctrl-C during ACT → confirm run_state.status changes in order CANCELLING → ROLLBACK → INTERRUPTED
3. On ROLLBACK, measure whether git worktree reverts changes
4. Intentional tool call without `idempotency_key` → confirm ACT blocked
5. Intentional retry_budget exceeded → confirm BLOCKED entry (integrate with Phase 2 §2-2)

## 6. Cross-repo Propagation Exceptions

| Case | Rule |
|---|---|
| code_app | enforced — 5 schema + tool contract + interrupt atomicity applied identically |
| SE-product | warn — 5 schema recommended, tool contract enforced, interrupt atomicity git worktree only |
| hybrid_pipeline | warn — `run_state` enforced only, rest advisory (content workflow protection) |
| SE-product | off — personal workspace repositories: minimal state tracking recommended only |
| Family uses its own SM | your-harness schema not enforced, but `run_state` equivalent field mapping is mandatory |

[`../exceptions.md`](../exceptions.md) §3 Phase 4 row consistent.

**Specific Exceptions**:
- `example-infra` (code_app) → same enforced as your-harness, infra work requires strong tracking
- `example-notes` (SE-product) → code work enforced, light tasks like note writing are warn
- `example-content` (hybrid_pipeline) → run_state for writing tasks only, tool_event off (writing has few tool calls)
- `example-personal` (SE-product personal) → entirely off

## 7. SE-meta self-stop Check

Can your-harness apply the 13-State SM to itself? → After work ✓ yes. But (a) keep separate axis that doesn't conflict with existing `tasks/phase.json` P0-F~P14 ledger + (b) update ADR-09 invocation pattern so all calls from the Codex execution lane satisfy the new schema.

**Potential Violation Risk**:
- If tool contract mandatory fields are too strict, all existing your-harness hooks temporarily blocked. Therefore phased introduction — apply to new hooks first, existing hooks get 1-week migration period.
- If 5 schemas reject existing `tasks/phase.json` with stricter validation, backfill migration required.
- If `approval` UI requires user confirm for every high-risk operation, your-harness work itself blocked → §3-9 decision pending.

## 8. Work Status

- **Status**: done (R18 + R20 land 2026-05-24 — 13-state SM, structured error, tool contract + hook wire, interrupt handler, 5-tier IDs spec+schema, approval gate Discord parser, cli dual-mode all applied to your-harness. Parallel 7-state maintained as compatibility path; residual items are residual default-flip hardening (resolved per ADR-44 §9 — parallel 7-state removed, default-flip done R20; 2026-06-04), fleet rollout, worktree interrupt, Discord reply parser integration)
- **Completion Date**: 2026-05-25
- **Verification Evidence**: `./.venv/bin/python -m pytest tools/run_orchestrator/tests/test_state_machine.py tests/test_tool_contract.py tests/test_validate_tool_contract.py -q` → `52 passed` (updated 2026-06-04: now 48 passed — ADR-44 R21 cleanup removed 4 tests)
- **Revert Reason**: –

## 9. Next Steps

Proceed to [Phase 5 Subagents](phase-5-application.md) (can run in parallel: Phase 6).
