---
phase: 12
title: Template Lifecycle Application
status: done
family: your-harness (SE-meta)
blueprint: ../../phase-12-template-lifecycle.md
depends_on: [phase-9-application.md, phase-10-application.md]
---

# Phase 12 — Template Lifecycle Application (example-harness)

## 1. Blueprint Reference

[`../../phase-12-template-lifecycle.md`](../../phase-12-template-lifecycle.md) full. Key sections: §1 4 lifecycle stages (CREATE/MAINTAIN/DEPRECATE/SUNSET), §2 version-lag detection, §3 upgrade migration runbook (PATCH/MINOR/MAJOR), §4 hand-off protocol, §5 template CI/pre-commit.

**Design goals (3-axis)**:
- Axis I: your-harness-as-agent (Role B) template lifecycle automation.
- Axis II: Template version change → fleet migration procedure specified.
- Axis III: Fleet families `adopted_version` tracking + version-lag detection + upgrade orchestration.

## 2. Current State (Pre-measure)

| Item | Blueprint | your-harness State |
|---|---|---|
| 4 lifecycle stage doc | §1 | ✅ land — blueprint §1 published |
| `template_health.py` | §5-1 daily health | ✅ landed — supporting runtime for template lifecycle checks |
| `verify_template_applied_state.py` | §2 / self-stop | ✅ landed + passing against current template workspace |
| `verify_self_stop.py` | §1-3 DEPRECATE gate | ✅ landed — runtime gate available |
| version-lag detector (6th kind) | §2 | ✅ land — R29-T03 complete, `harness_drift.py` supports `version_lag` |
| Upgrade migration runbook | §3 | ✅ land — blueprint §3 published (PATCH/MINOR/MAJOR procedures) |
| Sunset procedures | §1-4 | ✅ land — blueprint §1-4 published |
| Hand-off protocol | §4 | ✅ land — blueprint §4 published |
| Template CI `.github/workflows/` | §5-1 | ✅ present in template repo |
| Template repo `tests/` | §5-3 | ✅ present in template repo |
| Template `MIGRATION.md` | §3 | ✅ present in template repo |
| `fleet-harness-state.json` `adopted_version` field | §2-1 | ✅ schema field present, family backfill remains partial |
| ADR-42 (Template Lifecycle) | §6 | ✅ published (`design`, code landed R11) |
| ADR-43 (Template CI charter) | §6 | ✅ published |

**Gap**: Procedural docs and lifecycle tooling are now coupled to a verifier-clean template baseline. Remaining lifecycle work is operational cadence, not baseline completeness.

## 3. Operational State

| Artifact | Doc landed | Code landed | Cron / Automation active |
|---|---|---|---|
| `tools/fleet_observe/template_health.py` | ✅ ADR-40 §4 spec | ✅ R11-T04 `a12d38b` | ⚠️ on-demand in current workspace |
| Verdict StrEnum (lowercase + PARTIAL) | ✅ R13 spec | ✅ R13-T06 `b3e1642` | — |
| `scripts/verify_template_applied_state.py` | ✅ ADR-42 6-check spec | ✅ R11-T01 `2322bf2` | ✅ on-demand pass against template workspace |
| Verdict enum alignment | ✅ R12 spec | ✅ R12-T11 `771d235` | — |
| auto-reconcile atomic write | ✅ R13 spec | ✅ R13-T01 `6e4fd4d` | ❌ not triggered |
| `scripts/verify_self_stop.py` | ✅ ADR-41 spec | ✅ R11-T02 `62c5e9c` | ❌ not scheduled |
| atomic behavior (advisory → warn) | ✅ R12 spec | ✅ R12-T07 `e09a559` | — |
| `version_lag` 6th innovation kind | ✅ phase-12 §2 spec | ✅ R29-T03 landed | ✅ detector available |
| `adopted_version` field in fleet-state | ✅ §2-1 spec | ✅ in schema | ❌ family backfill partial |
| Template CI workflows | ✅ §5-1 spec | ✅ present | ✅ repository baseline present |
| Template `tests/` | ✅ §5-3 spec | ✅ present | ✅ repository baseline present |
| Template `MIGRATION.md` | ✅ §3 spec | ✅ present | ✅ repository baseline present |

**Honest summary**: Core runtime verification tools, template CI/tests, and the template physical baseline are all present. The current workspace reaches the lifecycle baseline expected by phase-12.

## 4. Implementation Status

| Tool | R-Task | Commit | Status |
|---|---|---|---|
| `tools/fleet_observe/template_health.py` | R11-T04 | `a12d38b` | landed |
| `scripts/verify_template_applied_state.py` | R11-T01 | `2322bf2` | landed |
| `scripts/verify_self_stop.py` | R11-T02 | `62c5e9c` | landed |
| verify_self_stop atomic behavior | R12-T07 | `e09a559` | refinement landed |
| verify_template_applied verdict enum align | R12-T11 | `771d235` | refinement landed |
| template_health + verify cross-doc consistency | R12-T09 | `644f649` | refinement landed |
| auto_reconcile atomic write | R13-T01 | `6e4fd4d` | refinement landed |
| Verdict StrEnum values + PARTIAL | R13-T06 | `b3e1642` | refinement landed — final R13 task |

## 5. Activation Gap

| Gap | Required action |
|---|---|
| `adopted_version` family backfill | optional fleet hygiene follow-up |
| scheduled runs | optional cadence hardening (`template_health`, `verify_template_applied_state`, `verify_self_stop`) |

## 6. Exit Criterion

Per blueprint §8:
1. ✅ 4 lifecycle stages specified + each stage owner = your-harness-as-agent Role B.
2. ✅ version-lag detector landed and template baseline now verifies cleanly.
3. ✅ Upgrade migration runbook (PATCH/MINOR/MAJOR) published (blueprint §3).
4. ✅ Hand-off protocol published (blueprint §4).
5. ✅ Template CI / tests spec implemented in template repo.
6. ✅ Template physical promote executed in the shared workspace and verifier passes.

**Done gate**: satisfied in the current workspace baseline.
