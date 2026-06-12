---
phase: 13
title: Applied-State Closure
status: design-v1
depends_on: [phase-9, phase-10, phase-11, phase-12]
date: 2026-05-25
---

# Phase 13 — Applied-State Closure

> **Purpose**: Bind template applied-state judgment criteria into a single closure lane combining catalog, verifier, physical snapshot, and health output. Defines "done" with precision.

## 0.5 Design Goals (R13 anchor)

**3-axis contribution**:
- **Axis I (your-harness hardening)**: define a precise closure verdict for your-harness's own applied state — not "all phases exist" but "all phases are verified to pass"
- **Axis II (public template sync)**: template applied-state must also meet a multi-axis bar; closure criteria prevent premature "template is complete" declarations
- **Axis III (fleet central governance / back-propagation)**: closure criteria are the basis for fleet sync decisions — a family cannot be declared "fully adopted" without meeting closure criteria

**Inter-phase contract**:
- **Input** (consumes): phase-9 (fleet catalog + adoption matrix), phase-10 (rollout pipeline exit criteria), phase-11 (back-propagation triage), phase-12 (template lifecycle version state)
- **Output** (provides): `applied_state: pass | fail | partial` judgment for both your-harness and the template → fleet sync trigger / hand-off decision

## 1. Why a Separate Phase — Verdict Mismatch vs Alignment

Without a closure phase, two distinct failure modes are possible:

**Failure Mode A — Verdict Mismatch**: The catalog says `applied` but the physical repo state does not reflect it. Phase-13 exists to catch this mismatch.

**Failure Mode B — Verdict Meaning Mismatch** (addressed in phase-14): Even when catalog and physical state are aligned, the meaning of "applied" may differ between your-harness and the template. Phase-13 handles alignment; phase-14 handles consistent interpretation.

## 2. Two Check Targets

### 2-1. your-harness Self-Check (3-Axis)

| Axis | Check | Pass Criterion |
|---|---|---|
| Catalog axis | fleet-harness-state.json entries reflect actual repo state | 0 stale catalog entries; all `applied` entries have physical evidence |
| Verifier axis | `scripts/verify_repo_agent_management.py` | 0 WARN/ERROR |
| Health axis | `config/mir-agent-self-health.json` last updated within session | `status: healthy` + no critical gaps |

### 2-2. Template Applied-State Check (5-Axis)

| Axis | Check | Pass Criterion |
|---|---|---|
| Phase coverage | All 14 phases have baseline docs in template | 14 files exist + each has §0.5 + Exit Criterion |
| Schema validity | `fleet_harness_state.schema.json` + `memory_entry.schema.json` | Schema validates against reference |
| Hook executability | All hooks in template `.claude/hooks/` are executable | `sh -n` syntax pass + execute bit set |
| Sanitization gate | No private strings in template docs | 0 matches on private path / family name grep |
| Role-policy parity | Template CLAUDE.md role-policy table matches source of truth | diff 0 (or documented intentional divergence) |

## 3. 5 Precise Goals

1. Prevent "catalog says done, repo is not" divergence (Failure Mode A)
2. Provide a single composite verdict (`pass/fail/partial`) rather than per-phase scattered status
3. Make closure criteria reproducible — same check every session, same verdict
4. Enable fleet sync readiness declaration: "your-harness is at closure → template sync is safe"
5. Serve as the entry gate for Phase 14 (completion consistency check)

## 4. 6-Step Inspection Sequence

```text
Step 1: Catalog snapshot    — read fleet-harness-state.json current state
Step 2: Physical scan       — git ls-files on relevant surfaces
Step 3: Verifier run        — scripts/verify_repo_agent_management.py
Step 4: Template gate       — sanitization grep + schema validate
Step 5: Reconcile           — catalog vs physical vs verifier: any mismatch?
Step 6: Verdict             — composite pass/fail/partial + record in plan.md
```

Each step is a concrete command or read — no ambiguous "check the docs" steps. If a step fails, the closure verdict is `fail` or `partial` depending on severity.

## 5. Current Results (2026-05-25 baseline)

### your-harness Result
All 3 axes: **pass**
- Catalog: fleet-harness-state.json entries reflect physical state
- Verifier: 0 WARN/ERROR
- Health: `status: healthy`

### Template Result
All 5 axes: **pass**
- Phase coverage: 14/14 baseline docs present (phases 0–13 with this doc as phase-13)
- Schema validity: schemas validate
- Hook executability: hooks syntactically valid + executable
- Sanitization gate: 0 private strings (verified)
- Role-policy parity: aligned

**Overall composite verdict: pass** (as of 2026-05-25)

This baseline will drift over time as new phases or changes are made. The inspection sequence in §4 must be re-run to refresh the verdict.

## 6. Non-Goals

- Per-family rollout closure (that is fleet-catalog's scope, not this phase)
- Automated CI enforcement of closure criteria (out of scope for this design phase)
- Revert triggers (closure verdict is informational; rollback decisions are user-directed)
- Replacing phase-specific exit criteria (each phase retains its own; this phase adds a composite layer)

## 7. Exit Criterion

Phase done when:
1. 3-axis your-harness check defined and executable (§2-1)
2. 5-axis template check defined and executable (§2-2)
3. 6-step inspection sequence documented and runnable (§4)
4. At least 1 complete closure verdict recorded (§5)
5. Phase 14 (completion consistency) can reference this phase's verdict as input

## 8. Application State

| Item | Status | Location |
|---|---|---|
| 3-axis your-harness check | **landed** | This §2-1 + `config/mir-agent-self-health.json` |
| 5-axis template check | **landed** | This §2-2 + `scripts/verify_codex_sync.py` |
| 6-step inspection sequence | **landed** | This §4 |
| Baseline verdict (2026-05-25) | **recorded** | This §5 |
| Automated re-run cadence | **not implemented** | Follow-up — cron or pre-commit hook candidate |

## 9. Change History

| Date | Change |
|---|---|
| 2026-05-25 | Initial design + baseline verdict recorded |
| 2026-05-27 | Phase 14 (completion consistency) added as follow-on; non-goals clarified |
