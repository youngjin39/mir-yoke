---
phase: 10
title: Rollout / Share Pipeline Application
status: done
family: your-harness (SE-meta)
blueprint: ../../phase-10-rollout-pipeline.md
depends_on: [phase-9-application.md]
---

# Phase 10 — Rollout / Share Pipeline Application (example-harness)

## 1. Blueprint Reference

[`../../phase-10-rollout-pipeline.md`](../../phase-10-rollout-pipeline.md) full. Key sections: §1 3-stage pipeline overview, §2 Stage 1 (your-harness land + stability), §3 Stage 2 (template baseline update + sanitize), §4 Stage 3 (fleet opt-in), §5 greenfield bootstrap.

**Design goals (3-axis)**:
- Axis I: Stage 1 exit criteria + promote trigger codified.
- Axis II: Stage 2 sanitize + sync runbook executed (template baseline update).
- Axis III: Stage 3 fleet opt-in — not enforced, family self-decides.

## 2. Current State (Pre-measure)

| Item | Blueprint | your-harness State |
|---|---|---|
| 3-stage pipeline doc | §1 | land — `phase-10-rollout-pipeline.md` |
| `sanitize_for_template.py` | §3-2 sanitize | ✅ landed + exercised — Stage 2 baseline raise completed in workspace |
| `template_health.py` | §5 CI | ✅ landed — verifier-clean template baseline now available to Role B flow |
| `verify_codex_sync.py` sanitize integration | §3-3 step 2 | **partial** — sync check exists; sanitize auto-run not wired |
| `bootstrap.py` family-type defaults | §5-3 | **partial** — base bootstrap exists; family_type default enabled_phases missing |
| share dispatcher Stage 3 | §4 | **partial** — `share_dispatcher.py` code landed; Stage 3 catalog auto-dispatch not active |
| `fleet-harness-state.json` `recommendations_received` | §4-1 | ✅ — real recommendations registered (`design-goals-capture-2026-05-23`, `terse-output-policy-2026-05-28`) |
| template workspace promote | §3-3 | ✅ — template physical baseline updated in-place in shared workspace |
| revert window automation | §4-4 | ❌ — manual only |
| ADR-26 (Rollout Pipeline) | §8 | ❌ not published |

**Gap**: Stage 2 execution is now complete in the shared workspace and Stage 3 has real recommendation evidence. Remaining work is mainly automation/cadence polish, not absence of rollout/share proof.

## 3. Operational State

| Artifact | Doc landed | Code landed | Cron / Automation active |
|---|---|---|---|
| `scripts/sanitize_for_template.py` | ✅ phase-10 §3-2 | ✅ R11-T05 `07487d2` | ❌ not wired to auto-run |
| `--review` / `--apply` modes | ✅ R12 spec | ✅ R12-T10 `644f649` | ❌ manual invocation only |
| `tools/fleet_observe/template_health.py` | ✅ ADR-40 §4 | ✅ R11-T04 `a12d38b` | ❌ not scheduled |
| cross-doc consistency checks | ✅ R12 spec | ✅ R12-T09 `644f649` | ❌ manual only |
| `share_dispatcher.py` Stage 3 | ✅ phase-10 §4 | ✅ R11-T08 `f28d577` | ❌ not scheduled |
| Template promote (Stage 2 actual run) | ✅ §3-3 procedure | ✅ workspace baseline raised to verifier pass | ✅ manual execution evidence |
| `recommendations_received` live data | ✅ schema §4 | ✅ 2 live recommendation ids in catalog | ✅ manual dispatch exercised |
| ADR-26 | ✅ §8 candidate | ❌ not published | — |

**Honest summary**: Stage 2 is no longer theoretical. The template physical baseline was actually raised and `verify_template_applied_state.py` now returns `pass`. Stage 3 remains lighter-weight and still not fully automated.

## 4. Implementation Status

| Tool | R-Task | Commit | Status |
|---|---|---|---|
| `scripts/sanitize_for_template.py` | R11-T05 | `07487d2` | landed |
| `tools/fleet_observe/template_health.py` | R11-T04 | `a12d38b` | landed |
| sanitize `--review` + `--apply` test coverage | R12-T10 | `644f649` | refinement landed |
| template_health cross-doc consistency | R12-T09 | `644f649` | refinement landed |
| `share_dispatcher.py` (Stage 3 dispatch) | R11-T08 | `f28d577` | landed |
| share_dispatcher bypass-warn for no families | R12-T08 | `e09a559` | refinement landed |

## 5. Activation Gap

| Gap | Required action |
|---|---|
| Stage 2 actual execution | complete in current workspace baseline |
| Template version bump + tag | workspace bumped to `0.4.0`; commit/tag remains follow-up |
| `recommendations_received` live data | complete — live Stage 3 recommendation evidence now exists in catalog |
| `template_health.py` scheduled run | `.claude/cron/daily-template-health.sh` |
| `bootstrap.py` family-type defaults | `scripts/bootstrap.py` update for `enabled_phases` per family_type |
| ADR-26 publication | ADR draft → user review → publish |

## 6. Exit Criterion

Per blueprint §9:
1. ✅ 3-stage doc published (this phase doc + blueprint).
2. ✅ Stage 2 sanitize + sync procedure is runnable (manual).
3. ✅ Stage 2 actual template baseline raise executed.
4. ✅ `fleet-harness-state.json` `recommendations_received` is now non-empty with real Stage 3 dispatch evidence.
5. ✅ current user instruction serves as Stage-2 review direction for this workspace execution.

**Done gate**: satisfied for the Stage 2 apply objective and the Stage 3 evidence objective. Full automation remains a follow-up, but the rollout/share pipeline itself is now exercised end-to-end through the template baseline raise plus live recommendation dispatch.
