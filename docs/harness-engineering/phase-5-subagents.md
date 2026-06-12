---
phase: 5
title: Subagents
status: consolidated-v1
depends_on: phase-4-state-machine
---

# Phase 5 — Subagents & Worker Isolation

> **Purpose**: Assign subagents only to tasks that can be cleanly separated. Avoid self-evaluation with the author ≠ verifier principle.

## 0.5 Design Goals (R9 anchor)

> This phase's connection to the [3-axis fleet goals](applications/fleet-catalog.md). When adding a new phase or cherry-picking for a family, the `design` skill (R9-T11) requires `design_goals` as a mandatory input.

**3-axis contribution**:
- **Axis I (your-harness hardening)**: Worker Isolation 4-step + executor-agent + codex-final-reviewer + 15+ agent registry
- **Axis II (public template sync)**: template subagent role catalog (identical role table + unified handoff schema)
- **Axis III (fleet central governance / back-propagation)**: family agent count tracking + cross-family agent reuse catalog (catalog axis)

**Inter-phase contract**:
- **Input** (consumes): phase-4 (current_lane + run_state) + phase-2 (lane routing results)
- **Output** (provides): subagent dispatch + handoff packet + result reply → phase-6 measurement trigger

## 1. Usage Principle

Subagents are not a feature to use because they look impressive. Use them only for tasks that can be safely separated from the main flow.

## 2. Usage Conditions (any one of the following)

1. Parallel processing has high value
2. Independent review is required (Worker Isolation)
3. There is a lot of repetitive work
4. It is safe to separate from the current flow

## 3. Allowed Roles

| Role | Definition | Output |
|---|---|---|
| review-subagent | Review artifacts for defects, gaps, and risks | Evaluation report |
| research-subagent | Supporting research and comparative analysis | Organized fact pack |
| test-subagent | Collect test results and summarize failures | Failure pattern summary |

Additional family-specific roles are defined according to the classification in [[phase-7-fleet-expansion]] §4.

## 4. Handoff Contract

What to hand off to a subagent:
- Clear goal (one line)
- Scope limits (which files/areas)
- List of files to read (absolute paths)
- Allowed tools
- Expected output format (schema)
- Time/token budget

What NOT to hand off to a subagent:
- Full session log
- Unnecessary global memory
- Excessive permissions from the parent
- Ambiguous instructions
- Global policy judgments

## 5. Worker Isolation 4-Step (Claude + Codex)

Standard flow for code work.

1. **Joint planning** (Claude + Codex): requirements, task breakdown, acceptance criteria
2. **Code writing** (Codex executor lane): local exploration, implementation, test writing
3. **First verification/fix** (Codex verification lane): sandbox tests + defect fixes
4. **Second verification/merge judgment** (Claude): final confirmation + merge

Self-evaluation by the same agent is prohibited. Verification must always be performed by a different lane.

## 6. fork_context Policy

Whether the subagent inherits parent context.

| Case | fork_context | Reason |
|---|---|---|
| Catalog/verifier checks | false | Main context protection |
| Narrow harness document area | false | Scope is clear |
| Worker Isolation step 2 (Codex executor lane, code writing) | **false** (R7-B-I2) | Code writing tasks inherit parent context (requirements/design/tests) without context explosion. Codex performs extensive reads within its own sandbox. |
| Worker Isolation step 3 (Codex verification lane, first verification) | **false** (R7-B-I2) | Shared context with step 2 enables write↔verify round-trip |
| Broad role-policy review | true | Full policy understanding needed |
| Independent final verification (codex-final-reviewer, part of step 4) | true | For missing detection — avoids self-evaluation |
| Runtime-contract review | true | Cross-impact assessment |

## 7. Resource Management

- Default concurrent subagent cap = 4
- Only raise cap when Claude / Codex lanes are independent and current lane is healthy
- Close completed, timed-out, or errored subagents before the next wave
- On spawn failure (capacity / thread limit): immediately stop parallel expansion, retry one at a time, record degraded mode

## 8. Avoiding Self-Evaluation

> "Self-evaluation has traps. Must verify with a new AI."

When the same session performs both writing and verification, both are bound to the same bias. Workarounds:

- Different model instances (Codex ↔ Claude)
- Same model but new session + no parent result sharing
- Or review-subagent with fork_context: true for independent context

## 9. Prohibitions

- Excessively fragmented subagents per feature
- Mandatory subagent for all work
- Delegating global policy judgments to subagents
- "Just figure it out" style dependency without a handoff contract
- Ending work with only self-evaluation
- Forking the entire parent context as-is

## 10. Introduction Timing

- Not immediately after Phase 1, but after [Phase 4 State Machine](phase-4-state-machine.md) is running
- Reason: increasing subagents without state tracking makes progress impossible to monitor
- Determination: immediately applicable after [[phase-4-state-machine]].

## 11. Application State

| Item | Status | Location |
|---|---|---|
| 3 allowed roles | land + extended | executor-agent / codex-final-reviewer / quality-agent + family-specific |
| Handoff contract | land | Each agent definition |
| Worker Isolation 4-step | land | Claude+Codex role policy |
| fork_context policy | land | CLAUDE.md Subagent Resource Management |
| Resource cap = 4 | land | Same CLAUDE.md section |
| Self-evaluation avoidance | land | Codex execution lane enforcement |
| Introduction timing | land (already in use) | ADR-09 |

**Gap**: Almost none. This phase is the most mature area of your-harness.

## 12. Exit Criterion

1 code task completed with Worker Isolation 4-step (Claude plan → Codex write → Codex verify → Claude merge) confirmed by observation. Self-evaluation avoidance confirmed (failure if the same lane performs both writing and verification even once).

## 13. Next Steps

Proceed to [Phase 6 — Observability](phase-6-observability.md).
