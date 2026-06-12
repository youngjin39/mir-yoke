---
status: design-v1
date: 2026-05-20
scope: phase autonomous execution mechanism — Claude + Codex concurrent operation model
audience: your-harness control plane
---

# Autonomous Execution

> **Purpose**: Define the autonomous execution model for phase implementation — how Claude (main agent) and delegated execution lanes (Codex-first) operate concurrently to apply harness phases without manual hand-off at every step.

## 1. Five Autonomy Definitions

Autonomous execution is not a binary property. The harness uses 5 graduated autonomy levels:

| Level | Name | Description |
|---|---|---|
| A0 | Manual | Every step requires explicit user approval |
| A1 | Guided | Main agent proposes next step; user approves before execution |
| A2 | Delegated | Main agent delegates to execution lane; user approves plan before start |
| A3 | Supervised | Main agent orchestrates full pipeline; user approves only at stage boundaries |
| A4 | Autonomous | Main agent runs full pipeline end-to-end; reports result + exceptions only |

Default operating level: **A2** (delegated). Upgrade to A3 for multi-family rollout waves. A4 requires explicit user authorization.

## 2. Main Agent vs Delegated Execution Lane Split

### Main Agent Responsibilities (Claude control plane)

- Requirements clarification and design approval
- Architecture decisions and ADR authorship
- Orchestration: which phases apply to which families
- Dispatch: issuing DispatchBrief to execution lane
- Exception handling: any abort rule trigger → escalate to user
- Verification synthesis: read execution lane results, judge pass/fail
- Final merge judgment: accept or reject patches

### Delegated Execution Lane Responsibilities (Codex-first)

- Implementation within a bounded, approved plan
- Composite TDD execution (write + run + pass)
- Deterministic verification (pytest, verifier scripts, sanitization gate)
- Code review within the repository's review scope
- Per-family patch apply + verify + report

**Key contract**: The execution lane operates only within an approved DispatchBrief. Any deviation from the brief triggers a halt and escalation to the main agent.

## 3. Autonomous Feedback Loop

```text
┌─────────────────────────────────────────────────────────────────┐
│  Main Agent (Claude)                                            │
│                                                                 │
│  1. Design phase                                                │
│  2. Approve DispatchBrief                                       │
│  3. Dispatch to execution lane ──────────────────────────────┐  │
│                                                               │  │
│  8. Receive result ◄──────────────────────────────────────────┤  │
│  9. Verify + judge                                            │  │
│  10. Accept / reject / escalate                               │  │
└───────────────────────────────────────────────────────────────┼─┘
                                                                │
                    ┌───────────────────────────────────────────▼─┐
                    │  Execution Lane (Codex-first)                │
                    │                                              │
                    │  4. Receive DispatchBrief                    │
                    │  5. Implement bounded plan                   │
                    │  6. Run TDD + verifier                       │
                    │  7. Report result or halt on exception       │
                    └──────────────────────────────────────────────┘
```

The loop is synchronous at stage boundaries (design approval, plan approval, result judgment) and asynchronous within each execution lane run.

## 4. Six User-Intervention Triggers

The following events require immediate escalation to the user — execution lane halts:

| Trigger | Description | Response |
|---|---|---|
| R1 — Scope creep | Execution lane finds the bounded plan requires changes outside the approved DispatchBrief | Halt. Report scope delta. Main agent re-designs. |
| R2 — Verification failure | Any required verification step (pytest, verifier, sanitization gate) returns non-zero | Halt. Report exact failure. Do not attempt self-repair beyond documented recovery steps. |
| R3 — Conflict detection | Patch conflicts with existing code or policy that the DispatchBrief did not anticipate | Halt. Report conflict. Main agent adjudicates. |
| R4 — Hook block | Pre-tool-use hook blocks an action inside the execution lane | Halt immediately. Report blocked action + hook message. Never bypass hooks. |
| R5 — State divergence | Physical repo state diverges from fleet-harness-state.json during execution | Halt. Report divergence. Main agent re-inspects before proceeding. |
| R6 — External side effects | Execution would affect external services, deployments, or cross-repo targets beyond those listed in the DispatchBrief | Halt. Explicit main agent approval required before any external write. |

## 5. SE-meta Self-Stop Rule

For your-harness (SE-meta family type), the following additional self-stop condition applies:

> **SE-meta self-stop**: If the execution lane determines that a proposed change would alter hook enforcement, pre-commit gates, or the harness's own verification contract — halt unconditionally. These surfaces require explicit user review, not execution lane autonomy.

This applies even if the change is within the approved DispatchBrief scope.

## 6. Implementation Priority Steps

Ordered by implementation readiness:

| Step | Action | Status |
|---|---|---|
| AE-1 | DispatchBrief schema finalized | complete |
| AE-2 | Execution lane halt + report contract defined | complete |
| AE-3 | 6 user-intervention triggers documented | complete |
| AE-4 | SE-meta self-stop rule enforced in hooks | partial land |
| AE-5 | Autonomy level selection per phase documented | planned |
| AE-6 | R6 external side effects trigger tested end-to-end | planned |

## 7. Per-Family-Type Exception Table

Not all family types support the same autonomy level. Exceptions are recorded here:

| Family Type | Default Level | Override | Reason |
|---|---|---|---|
| SE-meta (your-harness) | A2 | Lower to A1 for hook/enforcement changes | Hook changes affect all families — require tighter approval |
| SE-product | A2 | — | Standard delegated execution |
| code_app | A2 | Upgrade to A3 for harness-only changes | Low blast-radius for harness-only patches |
| hybrid_pipeline | A2 | Lower to A1 for runtime-touching changes | Pipeline runtime changes need tighter gating |
| template | A1 | — | Template changes propagate fleet-wide — always require approval |

### Family-Specific Notes

- **example-notes** (`code_app`): Standard A2. Harness-only patches can use A3.
- **example-content** (`hybrid_pipeline`): A2 default. Content pipeline runtime changes require A1.
- **example-infra** (`code_app`): A2 default. Infra-adjacent changes lower to A1 (runtime blast radius).
- **example-personal** (`SE-product`): A2. Personal workspace — content structure is low blast-radius.

## 8. Non-Goals

- Full autonomous operation without any user checkpoints (A4 is exceptional, not the default)
- Execution lane self-repair of hook blocks (hooks are enforcement — never bypass)
- Lateral family-to-family autonomous sync without main agent mediation

## 9. Exit Criterion

This mechanism is operational when:

1. DispatchBrief schema is live (AE-1)
2. Execution lane halt contract is enforced (AE-2)
3. All 6 intervention triggers are documented and tested (AE-3, AE-6)
4. SE-meta self-stop is enforced at the hook level (AE-4)
