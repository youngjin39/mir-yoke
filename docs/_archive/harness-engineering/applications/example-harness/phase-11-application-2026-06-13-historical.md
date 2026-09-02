---
phase: 11
title: Back-Propagation Application
status: done
family: your-harness (SE-meta)
blueprint: ../../phase-11-back-propagation.md
depends_on: [phase-9-application.md, phase-10-application.md]
---

# Phase 11 — Back-Propagation Application (example-harness)

## 1. Blueprint Reference

[`../../phase-11-back-propagation.md`](../../phase-11-back-propagation.md) full. Key sections: §1 3-way share-back flow, §2 Innovation detection (`harness_drift.py`), §3 Innovation triage (4 decisions), §4 5 sync directions, §5 template sync runbook.

**Design goals (3-axis)**:
- Axis I: Family innovation absorbed to your-harness (user review required — not automatic).
- Axis II: Generalizable innovations promoted to template baseline via phase-10 Stage 2.
- Axis III: **Core of this phase** — family ↔ your-harness ↔ family 3-way share-back catalog + drift detection.

## 2. Current State (Pre-measure)

| Item | Blueprint | your-harness State |
|---|---|---|
| `harness_drift.py` | §2 spec | land — real multi-family scan executed and report written |
| `share_dispatcher.py` | §1 flow | land — live absorb queue dispatch and live fleet recommendation dispatch both executed |
| Triage UI (Discord weekly digest) | §3-2 | land at your-harness layer boundary — `--discord-notify` report path exercised; actual push delegated to your-harness Code layer |
| Innovation catalog (`innovations` arrays) | §2 output | land — multiple live innovation entries present, including your-harness-sourced terse-output recommendation |
| 5 sync directions operational | §4 | partial — Backward-1 (family→your-harness) is live; remaining directions stay user-directed |
| Template sync runbook (3 viewpoints) | §5 | ✅ — doc published in blueprint |
| ADR-27 (Back-Propagation) | §8 | ✅ published — `docs/decisions/adr-27-back-propagation-2026-05-23.md` |
| False-positive skip globs | §2-4 | ✅ — `FAMILY_SPECIFIC_SKIP_GLOBS` in `harness_drift.py` |

**Gap**: Content drift / config evolution remain deferred by design, but the operational evidence gap against the Exit Criterion is resolved.

## 3. Operational State

| Artifact | Doc landed | Code landed | Cron / Scan active |
|---|---|---|---|
| `tools/fleet_observe/harness_drift.py` | ✅ phase-11 §2 spec | ✅ R11-T03 `f197dc9` | ✅ 2026-05-25 real scan executed |
| Innovation dataclass (frozen, typed) | ✅ §2-2 | ✅ in `harness_drift.py` | — |
| File-existence detection algorithm | ✅ §2-3 | ✅ skills/hooks/agents diff | ✅ real family scan complete |
| Content drift detection | ✅ §2-3 deferred | ❌ deferred to post-R11 | ❌ |
| Config evolution detection | ✅ §2-3 deferred | ❌ deferred | ❌ |
| False-positive skip globs | ✅ §2-4 | ✅ `FAMILY_SPECIFIC_SKIP_GLOBS` | — |
| `tools/fleet_observe/share_dispatcher.py` | ✅ §1 flow | ✅ R11-T08 `f28d577` | ✅ absorb queue dispatch executed |
| Triage 4-decision UI | ✅ §3-1 doc | ✅ `--discord-notify` dispatch report | ✅ on-demand |
| Innovation catalog live data | ✅ schema | ✅ 1+ live entries | ✅ |
| ADR-27 | ✅ §8 candidate | ✅ published | — |

**Honest summary**: the phase is now operational in user-directed mode. Family-sourced innovation detection and your-harness-sourced share recommendation dispatch both have live evidence.

## 4-a. Additional 2026-05-28 Evidence

- `terse-output-policy-2026-05-28` registered as a your-harness-sourced innovation in `fleet-harness-state.json`
- `uv run python -m tools.fleet_observe.share_dispatcher --innovation-id terse-output-policy-2026-05-28 --decision share_to_fleet ...` executed
- 13 target families received `recommendations_received[]` entries
- dispatch evidence recorded in `tasks/reports/share_dispatch_terse_output_2026-05-28.md`
- `design-goals-capture-2026-05-23` recommendation decisions were closed to `adopted` for all 8 target families after repo-side design-first routing was confirmed
- adoption evidence recorded in `tasks/reports/design_goals_capture_adoption_2026-05-28.md`
- repo-side adoption completed for all 13 target families after corrected external paths for `example-infra` and `example-service` were confirmed and applied
- adoption evidence recorded in `tasks/reports/terse_output_adoption_2026-05-28.md`

## 4. Implementation Status

| Tool | R-Task | Commit | Status |
|---|---|---|---|
| `tools/fleet_observe/harness_drift.py` | R11-T03 | `f197dc9` | landed — Innovation detection spec (phase-11 §2) |
| `tools/fleet_observe/share_dispatcher.py` | R11-T08 | `f28d577` | landed — share-back-runbook §Step 4 + ADR-27 compliance |
| share_dispatcher bypass-warn (no families) | R12-T08 | `e09a559` | refinement — graceful no-op when catalog is empty |

## 5. Activation Gap

| Gap | Required action |
|---|---|
| Weekly scan cron | optional hardening backlog |
| Content drift detection | deferred by design (false-positive risk) |
| Config evolution detection | deferred by design |

## 6. Exit Criterion

Per blueprint §9:
1. ✅ `harness_drift.py` spec published (code landed R11-T03).
2. ✅ Triage 4-decision procedure doc-published (blueprint §3-1).
3. ✅ 5 sync directions and all triggers specified (blueprint §4).
4. ✅ User review pass (R30 full-apply directive + first live dispatch evidence).

**Strict done gate**: satisfied by `tasks/reports/harness_drift_2026-05-25.json`, catalog entry `example-story/chapter-review-2026-05-24`, and `tasks/reports/share_dispatch_chapter_review_2026-05-25.json`. Current state = done.
