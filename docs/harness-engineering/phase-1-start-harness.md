---
phase: 1
title: Start Harness
status: consolidated-v1
depends_on: phase-0-foundations
---

# Phase 1 -- Start Harness

> **Purpose**: Ensure all requests follow the same start procedure. Task classification + 5 required declarations + routing decision.

## 0.5 Design Goals (R9 anchor)

> Connection of this phase to the [3-axis fleet goals](applications/fleet-catalog.md). When adding new phases or cherry-picking for a family, the `design` skill (R9-T11) mandates `design_goals` as required input.

**3-axis contribution**:
- **Axis I (your-harness strengthening)**: Automatic 5-element estimation + risk_level automatic determination hook in main-orchestrator
- **Axis II (Public template sync)**: Default 5-element declaration + risk_level determination table in template (family cherry-pick base)
- **Axis III (Fleet central management / back-propagation)**: 5-element fields in family JSON + family_type-specific risk_level threshold overrides

**Inter-phase contract**:
- **Input** (consumed): phase-0 (4 task classifications + terminology SoT) + user request + family profile
- **Output** (provided): 5-element declaration (task_type / risk_level / required_reads / required_tools / required_checks) → phase-2 enforcement routing

## 1. Role of Start Harness

start-harness is not an omnipotent worker. It is a router + guardrail.

1. Task classification
2. Select necessary context
3. Determine execution path
4. Assign verification and reporting criteria

It does not write code directly. It decides who works in what flow.

## 2. Input

- User request
- Project metadata (CLAUDE.md / AGENTS.md / family profile)
- Current task state (`tasks/phase.json`, last-run, etc.)
- Available tools, skills, and sub-agent catalog
- Prohibition lines and danger zones (deny-list, hook policy)

## 3. Required Output -- 5-Element Declaration

start-harness must declare the following 5 items when entering any task. If any one is missing, it is treated as a start failure.

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

`required_reads` follows the selective injection rules of [[phase-3-memory-context]]. `required_checks` is validated by hook results in [[phase-2-enforcement]]. `route_to` is used for Worker Isolation decisions in [[phase-5-subagents]].

### 3-1. risk_level Determination Rules (R8 added -- Slice B BLOCKER resolution)

Previously, only the `low | medium | high` enum was defined without a determining authority or rules. This §3-1 is the source of truth.

| risk_level | Determination criteria (meeting any one criterion qualifies) | Example |
|---|---|---|
| **low** | (1) Only read-only tools used (2) `dry_run: true` or user sandbox limited (3) Idempotent local file operations (test add / docs modification / log output) (4) User explicitly reversible (recoverable with a single git revert) | docs modification, lint fix, test addition |
| **medium** | (1) Single file modify (partial code surface) (2) Internal state change (memory entry update, task_state update) (3) Config change for a single family (4) Worker dispatch without external effects | function rename, schema migration (single family), memory addition |
| **high** | (1) External side effects (publish / push / migrate / API write) (2) **Permanent user data modification/deletion** (D operation in CRUD, destructive schema operations, file delete) (3) Simultaneous changes to multiple families (4) Access to external git repositories of sealed families (5) Code surface changes in your-harness itself (Codex execution lane violation) (6) Reversibility window exceeds 1 week | publish, git push, applying to sealed families, schema rename across all families |

**Determining authority**: `main-orchestrator` automatically determines at task entry (Claude lane). If determination is ambiguous, request user confirmation (default escalate to medium).

**Determination timing**: Once at task start + automatic escalate when tool calls during ACT match the above high criteria (medium → high transition).

## 4. Classification Decision Rules

### code_execution

- Includes file modification, creation, deletion
- Test and build verification required
- Code surface (`src/`, `tools/`, `scripts/`) is the target of change

### research_planning

- Fact investigation, comparison, design, planning is the core
- Code modification is secondary or absent
- Artifacts are in `docs/`, `tasks/plan.md`

### review

- Examining defects, omissions, risks in existing artifacts
- Purpose is verification and feedback rather than direct implementation
- Artifacts are review reports

### ops

- Environment checks, logs, state diagnosis, runtime operations
- Changes are to state and configuration, not code

## 5. Default Routing Sequence

1. Read user request carefully
2. Determine if code modification is needed
3. No modification → classify as one of research / review / ops
4. Read only documents and skills matching the classification ([[phase-3-memory-context]])
5. Pre-declare verification procedure ([[phase-2-enforcement]])
6. Decide execution path ([[phase-5-subagents]])

## 6. Default Flow by Classification

### code_execution flow
Goal → check prohibition zones → read related files → change plan → modify → verify → report remaining tasks. Detailed SM in [[phase-4-state-machine]].

### research_planning flow
Refine question → gather evidence → separate facts/interpretations → recommendations → explicitly state uncertainty.

### review flow
Confirm scope → confirm evaluation criteria → separate defects/risks/omissions → severity → suggest fixes.

### ops flow
Check state → separate changes → report state.

## 7. Routing Failure Conditions

Any of the following means routing failure. Immediately reclassify or ask the user.

- Code modification but not going through executor lane
- Verification required but `required_checks` is empty
- Investigation but no fact/opinion separation
- Review but no evaluation criteria

## 8. Absolute Responsibilities

5 things start-harness must perform -- the 5-element declaration in §3 is itself the absolute responsibility.

## 9. Things Not to Do

- Accumulating all domain knowledge inside itself
- Injecting memory source text without limits
- Allowing execution paths without verification
- Overusing sub-agents (violates [[phase-5-subagents]] §3 usage conditions)
- Trusting document rules alone and omitting code enforcement ([[phase-2-enforcement]] violation)

## 10. Application Status

| Item | Status | Location |
|---|---|---|
| 4 task classifications | landed | `CLAUDE.md` §Orchestration Presets |
| 5-element declaration | partial land | main-orchestrator (`risk_level` / `report_contract` not standardized) |
| Routing failure detection | partial land | verifier scripts, advisory level |
| executor / review lane separation | landed | Codex execution lane + codex-final-reviewer |
| start-harness single entry point | landed | main-orchestrator |

**Gap**: Missing `risk_level` standard definition + 5-element declaration enforcement hook → needs linking with Phase 2 enforcement.

### 10-1. Prompt Cache Impact (R7-A-W4 added)

The 5-element declaration and `required_reads` order in this phase determines the cache hit rate for [Phase 3 §6 Cache Stability](phase-3-memory-context.md). Therefore the following obligations at the start-harness stage:

- **required_reads order fixed** -- Same task_type reads in the same order. Changing order → entire prompt prefix changes → cache miss.
- **5-element declaration stable** -- Position risk_level / route_to / report_contract value changes at the tail of task_state so they do not appear in the prefix.
- **task_type-specific prefix template** -- Same classification uses same system prompt template (boilerplate variation prohibited).

## 11. Exit Criterion

For 3 sample requests (code / research / review), verify that the 5-element declaration is output without omissions, and confirm actual routing to the flow matching each classification.

Machine verification hook definition:
- `pytest tests/test_start_harness_5_elements.py` -- 5-element declaration completeness verification for 3 sample fixtures
- `scripts/verify_routing.py` -- task_type classification → expected route mapping consistency verification

## 12. Next Step

Proceed to [Phase 2 -- Enforcement](phase-2-enforcement.md).
