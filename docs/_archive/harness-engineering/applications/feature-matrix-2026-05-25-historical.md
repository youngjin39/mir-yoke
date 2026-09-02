---
status: design-v1
date: 2026-05-25
scope: 16-feature integration SoT matrix
audience: your-harness operators + external family adopters
---

# Feature Matrix — 16-Feature Integration SoT

> Single source of truth for feature integration status across all harness phases.

## 1. Purpose

This document answers: "Which phases implement which features, and to what depth?" It is the authoritative cross-reference between the phase blueprint and the feature set. When a new phase ships or an existing phase expands its feature coverage, this matrix must be updated first.

The matrix covers 16 core harness features. Each feature is tracked by adoption depth (full / partial / design-only / not-started) per repository surface.

## 2. Feature × Phase Matrix

| Feature | P0 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | P9 | P10 | P11 | P12 | P13 | P14 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Multi-agent | – | – | – | – | ✓ | ✓ | – | – | – | – | – | – | – | – | – |
| Phase Design + Development | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Orchestration | – | – | – | – | ✓ | ✓ | ✓ | – | – | ✓ | ✓ | – | – | – | – |
| TDD Closed-loop | – | – | ✓ | – | ✓ | – | – | – | – | – | – | – | – | – | – |
| Slice/Phase Unit Split | – | – | – | – | ✓ | – | – | – | – | – | – | – | – | – | – |
| Design Progress 2–3x Verification | – | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | – | – | – | – | – | – | – | – |
| Hook Reinforcement | – | – | ✓ | – | – | – | – | – | – | – | – | – | – | – | – |
| your-harness Design | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| External Modification Allowed | – | – | – | – | – | – | – | – | – | ✓ | ✓ | – | – | – | – |
| Memory Management | – | – | – | ✓ | – | – | – | – | ✓ | – | – | – | – | – | – |
| Measurement / Evaluation | – | – | – | – | – | – | ✓ | – | – | – | – | – | – | – | – |
| Autonomous Operation | – | – | – | – | – | – | – | ✓ | – | – | – | – | – | – | – |
| Central Template | – | – | – | – | – | – | – | – | – | ✓ | – | – | – | – | – |
| Back-propagation | – | – | – | – | – | – | – | – | – | – | ✓ | – | – | – | – |
| Security Baseline | – | – | ✓ | – | – | – | – | – | – | – | – | – | – | – | – |
| Incident Response | – | – | – | – | – | – | – | – | – | – | – | ✓ | – | – | – |

Legend: ✓ = full implementation, ~ = partial, D = design-only, – = not applicable

## 3. Feature Dependency Graph

```
Phase Design + Development (all phases)
    └── your-harness Design (all phases)

TDD Closed-loop (P2, P4)
    └── Hook Reinforcement (P2)

Multi-agent (P4, P5)
    └── Orchestration (P4, P5, P6, P9, P10)
        └── Slice/Phase Unit Split (P4)

Design Progress 2–3x Verification (P1–P6)
    └── Measurement / Evaluation (P6)

Memory Management (P3, P8)
    └── Autonomous Operation (P7)

External Modification Allowed (P9, P10)
    └── Central Template (P9)
        └── Back-propagation (P10)
            └── Share-back runbook

Security Baseline (P2)
    └── Incident Response (P11)
```

## 4. Additional Features (Extended Set)

| Feature | Phase | Depth | Notes |
|---|---|---|---|
| Evaluation harness | P6 §9a | full | Golden dataset + score threshold |
| Fleet catalog | P9 §1 | full | Adoption matrix view |
| Share-back dispatcher | P10–P11 | partial | Manual today; scripted R11 |
| Prompt injection validator | P2 §3-4 | advisory | `src/core/engine/workflow/prompt_injection_advisory.py` |
| WebFetch hostname allow-list | P2 | advisory | `tools/security/webfetch_hostname.py` |
| Self-stop verification | P7 §3 | full | ADR-41 |
| Circuit breaker | P4 §3 | full | Same-error N-times block |
| Context assembly | P0/all | full | ADR-53 — current-only core + on-demand retrieval |
| Native memory DB | P3/P8 | full | ADR-50 — SQLite + FTS5 + sqlite-vec canonical |

## 5. your-harness Implementation Score

Current feature coverage score for your-harness: **14 / 16** core features fully implemented.

| Feature | Status |
|---|---|
| Multi-agent | ✓ full |
| Phase Design + Development | ✓ full |
| Orchestration | ✓ full |
| TDD Closed-loop | ✓ full |
| Slice/Phase Unit Split | ✓ full |
| Design Progress 2–3x Verification | ✓ full |
| Hook Reinforcement | ✓ full |
| your-harness Design | ✓ full |
| External Modification Allowed | ✓ full |
| Memory Management | ✓ full |
| Measurement / Evaluation | ✓ full |
| Autonomous Operation | ✓ full |
| Central Template | ✓ full |
| Back-propagation | ~ partial (R11 code land pending) |
| Security Baseline | ~ partial (advisory, not enforced) |
| Incident Response | ✓ full (runbook live, IR-5 hook landed) |

## 6. Gap Analysis

Two features remain partial:

**Back-propagation (P10–P11)**:
- Design complete (phase-10, phase-11 blueprints, share-back runbook)
- `share_dispatcher.py` and `family_decision.py` landed
- Discord weekly digest cron not yet live (R27 scope)
- Manual fallback procedure operational

**Security Baseline (P2)**:
- Prompt injection validator landed as advisory
- WebFetch hostname allow-list landed as advisory
- Neither is fully enforced (hook-enforced block not yet)
- Design complete; code enforcement deferred to R-next

## 7. Per-Family-Type Feature Applicability

Some features have reduced or modified applicability by family type.

| Feature | SE-meta | code_app | SE-product | hybrid_pipeline |
|---|---|---|---|---|
| Multi-agent | full | full | partial | partial |
| TDD Closed-loop | full | full | partial | off |
| your-harness Design | full | partial | partial | partial |
| Autonomous Operation | full | full | warn | warn |
| Incident Response | full | full | full | warn |
| Memory Management | full | full | partial | partial |
| Central Template | full | off | off | off |
| Back-propagation | full | full | full | full |

your-harness maintains full coverage of all 16 features as the control plane.

## 8. your-harness Code Implementation Priority

For features that are partially implemented, this is the recommended completion order:

1. **Back-propagation Discord cron** — R27 scope. Highest user-visible payoff.
2. **Security Baseline enforcement** — Phase 2 hook enforcement. Converts advisory to enforced.
3. **IR-6 Tripwire Retrospective automation** — Phase 8 integration. Closes the incident feedback loop.
4. **Per-call permission scope (ADR candidate 31)** — Advanced sandboxing. Currently deferred.

## 9. Ledger Reference

Feature adoption evidence lives in the example-harness README.md ledger (`applications/example-harness/README.md`). The ledger is the single source of truth for phase-by-phase feature evidence for the reference implementation.

The your-harness ledger lives in `tasks/tdd.json` (keyed composite-TDD records per tool function).

## 10. Change Policy

This matrix is updated when:

1. A new phase blueprint is merged.
2. A feature implementation is promoted from design-only to partial or full.
3. A new feature is added to the harness capability set.
4. A phase's feature coverage changes due to a retroactive design decision.

Updates must include the date and the ADR or R-number that drove the change.
