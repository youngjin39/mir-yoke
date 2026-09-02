---
phase: 5
title: Subagents
status: consolidated-v1
depends_on: phase-4-state-machine
---

# Phase 5 -- Subagents & Worker Isolation

> **Purpose**: Delegate to subagents only for tasks that can be safely isolated. Avoid self-evaluation through the author != verifier principle.

## 0.5 Design Goals (R9 anchor)

**3-axis contribution**:
- **Axis I (self-harness hardening)**: Worker Isolation 4-step + executor-agent + codex-final-reviewer + 15+ agent registry
- **Axis II (public template sync)**: template subagent role catalog (identical role table + unified handoff schema)
- **Axis III (fleet central management)**: family agent count tracking + cross-family agent reuse catalog

**Inter-phase contract**:
- **Input** (consumes): phase-4 (current_lane + run_state) + phase-2 (lane routing result)
- **Output** (provides): subagent dispatch + handoff packet + result reply -> phase-6 measurement trigger

## 1. Usage Principle

Subagents are not a feature to use because they look impressive. Use them only for tasks that can be safely isolated from the main flow.

## 2. Usage Conditions (any one qualifies)

1. Parallel processing value is high
2. Independent review is required (Worker Isolation)
3. There is repetitive work
4. Separation from the main flow is safe

## 3. Permitted Roles

| Role | Definition | Output |
|---|---|---|
| review-subagent | Review defects, omissions, and risks in outputs | Evaluation report |
| research-subagent | Supplemental research and comparative analysis | Organized fact pack |
| test-subagent | Collect test results and summarize failures | Failure pattern summary |

Additional family-specific roles are defined according to the classification in [Phase 7 Fleet Expansion](phase-7-fleet-expansion.md) section 4.

## 4. Handoff Contract

What to pass to a subagent:
- Clear objective (one line)
- Scope limit (which files/areas)
- File list to read (absolute paths)
- Permitted tools
- Expected output format (schema)
- Time and token budget

What NOT to pass to a subagent:
- Full session log
- Unnecessary global memory
- Excessive parent permissions
- Ambiguous instructions
- Global policy judgment

## 5. Worker Isolation 4-Step (Claude + Codex)

Standard flow for code tasks.

1. **Joint planning** (Claude + Codex): requirements, task decomposition, acceptance criteria
2. **Code writing** (Codex executor lane): local exploration, implementation, test writing
3. **First-pass verification and fixes** (Codex review lane): sandbox testing + defect fixing
4. **Second-pass verification and merge judgment** (Claude): final check + merge

Self-evaluation by the same agent is prohibited. Verification must always be performed by a different lane.

## 6. fork_context Policy

Whether a subagent inherits parent context.

| Case | fork_context | Reason |
|---|---|---|
| Catalog / verifier inspection | false | Protect main context |
| Narrow harness doc area | false | Clear scope |
| Worker Isolation step 2 (Codex executor lane, code writing) | **false** | Code writing tasks can inherit parent context (requirements, design, tests) without context explosion. Codex performs broad reads within its own sandbox. |
| Worker Isolation step 3 (Codex review lane, first-pass verification) | **false** | Same context sharing as step 2 for write-verify round-trip |
| Broad role-policy review | true | Needs full policy understanding |
| Independent final verification (codex-final-reviewer, part of step 4) | true | For missing-item detection -- avoid self-evaluation |
| Runtime-contract review | true | Cross-impact assessment |

## 7. Resource Management

- Default concurrent subagent cap = 4
- Raise cap only when Claude/Codex lanes are clearly independent and the current lane is healthy
- Close completed, timed-out, or errored subagents before the next wave
- On spawn failure (capacity / thread limit): immediately stop parallel expansion, retry one at a time, record degraded mode

## 8. Self-Evaluation Avoidance

> "Self-evaluation has bias. You need to re-verify with a fresh AI."

When the same session performs both writing and verification, it is bound by the same bias. Workarounds:
- Different model instances (Codex <-> Claude)
- Even with the same model: new session + parent result not shared
- Or review-subagent with `fork_context: true` for independent context

## 9. Prohibitions

- Excessively granular multiple subagents per feature
- Unconditionally using subagents for every task
- Delegating global policy judgment to subagents
- "Figure it out" style dependency without a handoff contract
- Ending a task with only self-evaluation
- Forking the entire parent context as-is

## 10. Introduction Timing

- Not immediately after Phase 1, but after [Phase 4 State Machine](phase-4-state-machine.md) is running
- Reason: without state tracking, increasing subagents makes progress tracking impossible

## 11. Application Status

| Item | Status | Location |
|---|---|---|
| 3 permitted roles | landed + extended | executor-agent / codex-final-reviewer / quality-agent + family-specific |
| Handoff contract | landed | each agent definition |
| Worker Isolation 4-step | landed | Claude+Codex role policy |
| fork_context policy | landed | CLAUDE.md Subagent Resource Management |
| Resource cap = 4 | landed | CLAUDE.md same section |
| Self-evaluation avoidance | landed | Codex execution lane enforcement |
| Introduction timing | landed (already in use) | architecture decision record |

**Gap**: Minimal. This phase is the most mature area of the harness.

## 12. Exit Criterion

One code task completes the Worker Isolation 4-step (Claude plan -> Codex write -> Codex verify -> Claude merge) with confirmation. Self-evaluation avoidance confirmed (failure if the same lane performs both writing and verification even once).

## 13. Next Step

[Phase 6 -- Observability](phase-6-observability.md)
