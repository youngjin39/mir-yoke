---
phase: 0
title: Foundations Application
status: done
family: your-harness (SE-meta)
blueprint: ../../phase-0-foundations.md
---

# Phase 0 — Foundations Application (example-harness)

## 1. Blueprint Reference

[`../../phase-0-foundations.md`](../../phase-0-foundations.md) in full. In particular §2 four pillars, §3 five layers, §4 HOW NOT, §8 decision vs. shelved table.

**Related reinforcement docs**: When updating the decision vs. shelved table for this phase, apply the 5-step + iteration requirement from [`../design-process.md`](../design-process.md).

## 2. Current State (Pre-measurement)

| Item | Blueprint location | your-harness state |
|---|---|---|
| Four pillars | §2 | landed (distributed across 4 phases) |
| Five-layer separation | §3 | landed (`CLAUDE.md` Hook Policy Boundary) |
| Four task classifications | §6 | landed (`CLAUDE.md` §Orchestration Presets) |
| HOW NOT priority approach | §4 | partially landed (failure-patterns.md partial) |
| Compass not Encyclopedia | §5 | partially landed (memory-map.md) |
| Decision vs. shelved table | §8 | landed (this consolidated doc + Appendix A) |
| Term anchoring | §9 | landed |

**Gap assessment**: No substantive gaps against the Exit Criterion. HOW NOT / Compass descriptions are distributed across multiple documents, but the term/decision-table/new-family-JSON-creatable state is already satisfied.

## 3. Application Work Steps

| Step | Work | Dependency | Estimate |
|---|---|---|---|
| 0-1 | Promote HOW NOT patterns to a standard section in `failure-patterns.md` | – | 1h |
| 0-2 | Add Compass principle explicitly to §1 introduction of `CLAUDE.md` or `memory-map.md` | 0-1 | 30m |
| 0-3 | Update `example-harness/README.md` ledger table to `phase 0 = done` | 0-2 | 10m |

Each step applies the Worker Isolation from [Phase 5 Subagents](../../phase-5-subagents.md) — Claude writes, Codex verifies.

## 4. Files to Change

| Path | Type |
|---|---|
| `tasks/lessons.md` or `.ai-harness/failure-patterns.md` | edit (add HOW NOT standard section) |
| `docs/memory-map.md` or `CLAUDE.md` | edit (Compass principle §1) |
| `docs/harness-engineering/applications/example-harness/README.md` | edit (ledger update) |

Documentation changes only, no code changes.

## 5. Verification Procedure

Blueprint §11 Exit Criterion: "Terms from §9 and the decision table from §8 agreed with user. New family's family profile JSON can be created."

Verification method:
1. This consolidated doc + Appendix A's decision table + term table are user-agreed → this work is that artifact
2. Whether new family JSON can be created → existing `config/repos/*.json` (current fleet count) already exist, so pass

## 6. Cross-Repo Propagation Exceptions

| Case | Rule |
|---|---|
| Require HOW NOT pattern addition in external families | off (advisory only, not enforced) |
| Require five-layer specification in external family CLAUDE.md | warn (cadence reminder only) |
| External family uses a different term system | allowed (only your-harness 6-Type classification must be compatible) |

[`../exceptions.md`](../exceptions.md) §3 matrix Phase 0 row: all types **doc-strict** (R4 term update, previously advisory-strict). No hook implementation at this stage + docs/terms/decision-agreement scope, so blocking is not possible — only consistency verification + user confirm on changes.

## 7. SE-meta Self-Stop Check

Can your-harness apply HOW NOT patterns to itself? → ✓ `failure-patterns.md` already exists.
Has your-harness explicitly stated five-layer separation in its own CLAUDE.md? → ✓ Stated in the Hook Policy Boundary section.

**No self-stop violation**. Phase 0 may proceed.

## 8. Work Status

- **Status**: done
- **Completion date**: 2026-05-25
- **Verification evidence**: `docs/harness-engineering/phase-0-foundations.md` §8/§9 + `config/repos/*.json` fleet family profiles + `CLAUDE.md` Hook Policy Boundary / Orchestration Presets
- **Revert reason**: –

## 9. Next Steps

Proceed to [Phase 1 Application](phase-1-application.md).
