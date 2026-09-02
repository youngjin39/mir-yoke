---
phase: 14
title: Completion Consistency
status: design-v1
depends_on: [phase-13]
date: 2026-05-27
---

# Phase 14 — Completion Consistency

> **Purpose**: Prevent phase-13 applied-state truth-alignment from being over-interpreted as full your-harness completion. Fix "verdict meaning mismatch" — the second failure mode that phase-13 does not address.

## 0.5 Design Goals (R14 anchor)

**3-axis contribution**:
- **Axis I (your-harness hardening)**: your-harness knows precisely what "completion" means for itself — not just "phase-13 passes" but "the harness is operating at design intent across all active dimensions"
- **Axis II (public template sync)**: the template's "completion" bar is defined more strictly than your-harness's — template must be usable by any team, not just the original operator
- **Axis III (fleet central governance / back-propagation)**: fleet families referencing "completion" need a consistent definition — phase-14 provides the shared vocabulary

**Inter-phase contract**:
- **Input** (consumes): phase-13 composite verdict (pass/fail/partial)
- **Output** (provides): completion-consistency verdict — "phase-13 passed, AND the meaning of 'done' is consistently understood across your-harness, template, and fleet catalog"

## 1. Why a Separate Phase — Verdict Meaning Mismatch

Phase-13 catches **Failure Mode A** (catalog vs physical state divergence).

Phase-14 catches **Failure Mode B — Verdict Meaning Mismatch**:
- your-harness says "phase-N is applied" but means "the code landed"
- Template says "phase-N is baselined" but means "the doc exists"
- Fleet catalog says "family adopted phase-N" but means "the hook file was copied"

All three can be simultaneously true (no mismatch detected by phase-13) while the actual operational meaning of "completion" differs. Phase-14 enforces that all three mean the same thing: **the phase is producing its intended effect**.

## 2. Two Check Targets

### 2-1. your-harness Completion Visibility (4-Axis)

| Axis | Check | Pass Criterion |
|---|---|---|
| Operational evidence | Each "applied" phase has at least 1 observable output (log, metric, verifier pass) | No phase marked `applied` with zero observable evidence |
| Regression coverage | Each phase has at least 1 regression test or verifier rule | TDD ledger or verifier rule exists per phase |
| Intent alignment | Phase doc §0.5 design goals match actual behavior | No `design_goals` divergence > 1 session old without a tracked gap |
| Gap transparency | Known gaps are explicitly listed (not silently absent) | All `partial land` items in phase docs have a follow-up location |

### 2-2. Template Stronger Consistency (5-Axis)

| Axis | Check | Pass Criterion |
|---|---|---|
| Adopter usability | Each phase baseline doc is self-contained enough for a new team | No unresolved `your-harness`-specific references in template baseline |
| Cross-reference integrity | All intra-doc links resolve within the template repo | 0 broken links |
| Completion vocabulary | "applied", "land", "partial land" defined consistently across all phase docs | Vocabulary glossary exists OR consistent usage confirmed |
| Non-goal explicitness | Each phase doc has a Non-Goals section | 14/14 phase docs have explicit Non-Goals (or "not applicable" stated) |
| Exit criterion testability | Each phase's Exit Criterion can be verified mechanically | No subjective-only exit criteria |

## 3. 5 Precise Goals

1. Define what "completion" means operationally — beyond "the doc exists" or "the code landed"
2. Ensure your-harness and template use the same vocabulary for completion states
3. Prevent over-confident "done" declarations based on phase-13 pass alone
4. Make gaps explicit and tracked — "partial land" is not "unknown"
5. Provide a completion-consistency verdict as input to fleet sync decisions

## 4. 6-Step Inspection Sequence

```text
Step 1: Phase-13 verdict    — confirm phase-13 returns pass (prerequisite)
Step 2: Operational scan    — per-phase: does evidence exist? (log/metric/test)
Step 3: Gap audit           — all "partial land" items: is follow-up location recorded?
Step 4: Template vocabulary — consistency check across all 14 phase docs
Step 5: Exit criterion scan — all 14 phases: is the exit criterion mechanically testable?
Step 6: Verdict             — completion-consistency pass/fail/partial + record
```

Prerequisite: Step 1 must pass before proceeding. If phase-13 fails, phase-14 is not run.

## 5. Current Results (2026-05-27 baseline)

### your-harness Completion Visibility
All 4 axes: **aligned**
- Operational evidence: all applied phases have observable outputs (verifier + test suite)
- Regression coverage: TDD ledger + verifier rules cover all landed phases
- Intent alignment: §0.5 present in all consolidated phase docs
- Gap transparency: all `partial land` items have follow-up locations in `tasks/plan.md`

### Template Consistency
**Stronger gaps identified** (vs phase-13):
- Non-Goals sections: not uniformly present across all 14 phase docs
- Exit criterion testability: 2 phase docs have partially subjective exit criteria
- Completion vocabulary: "applied" vs "land" vs "landed" used inconsistently in 3 phase docs

These gaps are explicitly tracked — verdict is `partial` not `fail`.

**Overall completion-consistency verdict: partial** (as of 2026-05-27)
- your-harness: aligned
- Template: partial (tracked gaps above)

## 6. Non-Goals

- Per-family completion tracking (fleet catalog's scope)
- Automated enforcement of completion vocabulary (follow-up tooling)
- Reverting phases to incomplete state
- Replacing phase-13 (phase-13 remains the physical-state gate; phase-14 adds meaning consistency layer)

## 7. Exit Criterion

Phase done when:
1. 4-axis your-harness completion visibility check defined and executable (§2-1)
2. 5-axis template consistency check defined and executable (§2-2)
3. 6-step inspection sequence documented (§4)
4. At least 1 completion-consistency verdict recorded (§5)
5. Template partial gaps (§5) are tracked in `tasks/plan.md` or active handoff note

## 8. Application State

| Item | Status | Location |
|---|---|---|
| 4-axis your-harness check | **landed** | This §2-1 |
| 5-axis template check | **landed** | This §2-2 |
| Baseline verdict (2026-05-27) | **recorded** | This §5 |
| Template vocabulary gaps | **tracked** | `tasks/plan.md` follow-up items |
| Non-Goals section audit | **partial** | Follow-up: audit all 14 phase docs for Non-Goals uniformity |
| Exit criterion testability audit | **partial** | Follow-up: review 2 flagged phase docs |

## 9. Change History

| Date | Change |
|---|---|
| 2026-05-27 | Initial design. Separated from phase-13 to address Failure Mode B independently. |
| 2026-05-28 | Baseline verdict `partial` recorded — template gaps explicitly listed. |
