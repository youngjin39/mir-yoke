---
phase: 1
title: Start Harness
status: consolidated-v1
depends_on: phase-0-foundations
---

# Phase 1 — Start Harness

> **Purpose**: Ensure all requests follow the same startup procedure. Task classification + 5 mandatory declarations + routing decision.

## 0.5 Design Goals (R9 anchor)

> This phase's connection to the [3-axis fleet goals](applications/fleet-catalog.md). When adding a new phase or cherry-picking for a family, the `design` skill (R9-T11) requires `design_goals` as a mandatory input.

**3-axis contribution**:
- **Axis I (your-harness hardening)**: main-orchestrator auto-estimates 5 elements + risk_level auto-determination hook
- **Axis II (public template sync)**: template default 5-element declaration + risk_level determination table (family cherry-pick base)
- **Axis III (fleet central governance / back-propagation)**: family JSON 5-element fields + family_type-specific risk_level threshold overrides

**Inter-phase contract**:
- **Input** (consumes): phase-0 (4 task classifications + terminology SoT) + user request + family profile
- **Output** (provides): 5-element declaration (task_type / risk_level / required_reads / required_tools / required_checks) → phase-2 enforcement routing

## 1. Start Harness Role

Start-harness is not a general-purpose worker. It is a router + guardrail.

1. Task classification
2. Context selection
3. Execution path decision
4. Assigning verification and reporting criteria

It does not write code directly. It decides who works on what flow.

## 2. Input

- User request
- Project metadata (CLAUDE.md / AGENTS.md / family profile)
- Current task state (`tasks/phase.json`, last-run, etc.)
- Available tools, skills, and sub-agent catalog
- Prohibited lines and danger zones (deny-list, hook policy)

## 3. Required Output — 5-Element Declaration

Start-harness must declare the following 5 items on every task entry. Missing any one is treated as a start failure.

```yaml
task_type: code_execution | research_planning | review | ops
risk_level: low | medium | high
required_reads:
  - path/to/doc.md
required_tools:
  - read
  - edit
required_checks:
  - lint
  - test
route_to:
  - executor_lane | review_lane | planning_flow | ops_flow
report_contract: concise_report_v1
```

`required_reads` follows the selective injection rules in [[phase-3-memory-context]]. `required_checks` is verified by hook results from [[phase-2-enforcement]]. `route_to` is used for the Worker Isolation decision in [[phase-5-subagents]].

### 3-1. risk_level Determination Rules (R8 — Slice B BLOCKER resolution)

Previously only `low | medium | high` enum was defined without a determination subject or rules. This §3-1 is the source of truth.

| risk_level | Determination criteria (any one condition met triggers this level) | Example |
|---|---|---|
| **low** | (1) read-only tools only (2) `dry_run: true` or user sandbox only (3) idempotent local file work (test add / docs edit / log output) (4) user explicitly stated reversible (single git revert to recover) | docs edit, lint fix, test addition |
| **medium** | (1) single file modify (partial code surface) (2) internal state change (memory entry update, task_state update) (3) single-family config change (4) worker dispatch with no external effects | function rename, schema migration (single family), memory addition |
| **high** | (1) external side effects (publish / push / migrate / API write) (2) **permanent user data change/delete** (D operation in CRUD, schema DROP, file delete) (3) simultaneous multi-family changes (4) external git repo access for sealed families (5) your-harness code surface changes (violates Codex execution lane) (6) not reversible if revert window > 1 week | publish (API/service), git push, external apply to sealed families, schema rename across all families |

**Determination subject**: `main-orchestrator` auto-determines at task entry (Claude lane). When determination is ambiguous, request user confirm (default escalate to medium).

**Determination timing**: Once at task start + auto-escalate when tool calls during ACT match high criteria (medium → high transition).

## 4. Classification Decision Rules

### code_execution

- Includes file modification, creation, or deletion
- Requires test and build verification
- Code surface (`src/`, `tools/`, `scripts/`) is the target of change

### research_planning

- Core is fact investigation, comparison, design, or planning
- Code modification is secondary or absent
- Output is `docs/`, `tasks/plan.md`

### review

- Examining defects, gaps, and risks in existing artifacts
- Purpose is verification and feedback, not direct implementation
- Output is a review report

### ops

- Environment inspection, logs, status diagnosis, runtime operations
- Changes, if any, are to state and config rather than code

## 5. Default Routing Order

1. Read user request carefully
2. Determine whether code modification is needed
3. No modification → classify as research / review / ops
4. Read only documents and skills matching the classification ([[phase-3-memory-context]])
5. Declare verification procedure in advance ([[phase-2-enforcement]])
6. Determine execution path ([[phase-5-subagents]])

## 6. Default Flow by Classification

### code_execution flow
Goal → danger zone check → read relevant files → change plan → modify → verify → report remaining tasks. Detailed SM in [[phase-4-state-machine]].

### research_planning flow
Refine question → gather evidence → separate facts/interpretation → recommend → state uncertainty.

### review flow
Confirm scope → confirm evaluation criteria → separate defects/risks/gaps → severity → propose fixes.

### ops flow
Check state → separate changes → report state.

## 7. Routing Failure Conditions

Any of the following is a routing failure. Immediately reclassify or ask the user.

- Code modification but not routed through executor lane
- Verification needed but `required_checks` is empty
- Investigation but facts/opinions not separated
- Review but evaluation criteria absent

## 8. Absolute Responsibilities

The 5 things start-harness must always do — the 5-element declaration in §3 is the absolute responsibility.

## 9. Things to Avoid

- Accumulating all domain knowledge inside itself
- Injecting memory verbatim without limit
- Allowing execution paths without verification
- Overusing sub-agents (violates [[phase-5-subagents]] §3 usage conditions)
- Trusting only document rules while omitting code enforcement ([[phase-2-enforcement]] violation)

## 10. Application State

| Item | Status | Location |
|---|---|---|
| 4 task classifications | land | `CLAUDE.md` §Orchestration Presets |
| 5-element declaration | partial land | main-orchestrator (`risk_level` / `report_contract` not standardized) |
| Routing failure detection | partial land | verifier scripts, advisory level |
| executor / review lane separation | land | Codex execution lane + codex-final-reviewer |
| start-harness single entry point | land | main-orchestrator |

**Gap**: `risk_level` standard definition + 5-element declaration enforcement hook absent → linkage with Phase 2 enforcement needed.

### 10-1. Prompt Cache Impact (R7-A-W4)

The 5-element declaration + required_reads order in this phase determines the cache hit rate of [Phase 3 §6 Cache Stability](phase-3-memory-context.md). Therefore, start-harness stage has these obligations:

- **required_reads order fixed** — same task_type reads in same order. Order change → entire prompt prefix change → cache miss.
- **5-element declaration stable** — risk_level / route_to / report_contract value changes must not be exposed in the prefix; place at the tail of task_state.
- **Per-task_type prefix template** — same classification uses the same system prompt template (no boilerplate variations).

Violations of this §10-1 are detected as an acute drop in Phase 6 §2 metric 8 (cache hit estimate). On detection, re-examine routing code in this phase (`main-orchestrator`).

## 11. Exit Criterion

For 3 sample requests (code / research / review), the 5-element declaration is output without gaps, and each classification routes to the correct flow with actual verification.

**R7-A-W3 supplement (machine verification path)**:
- `pytest tests/test_start_harness_5_elements.py` — validates completeness of 5-element declaration for 3 sample fixtures
- `scripts/verify_routing.py` — validates task_type classification → expected route mapping consistency

## 12. Next Steps

Proceed to [Phase 2 — Enforcement](phase-2-enforcement.md).
