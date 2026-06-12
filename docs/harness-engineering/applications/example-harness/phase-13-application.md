---
phase: 13
title: Applied-State Closure Application
status: done
family: your-harness (SE-meta)
blueprint: ../../phase-13-applied-state-closure.md
depends_on: [phase-9-application.md, phase-10-application.md, phase-11-application.md, phase-12-application.md]
---

# Phase 13 — Applied-State Closure Application (example-harness)

## 1. Blueprint Reference

[`../../phase-13-applied-state-closure.md`](../../phase-13-applied-state-closure.md) full. Key sections: §2 closure targets, §3 exact goals, §4 inspection order, §7 exit criteria.

**Design goals (3-axis)**:
- Axis I: Connect the done/block verdict in the your-harness self-baseline to evidence.
- Axis II: Align the public template applied-state claim with charter, verifier, and physical snapshot.
- Axis III: Maintain honest numbers at both reference points that external families use.

## 2. Current State (Pre-measure)

| Item | Blueprint | your-harness State |
|---|---|---|
| your-harness-self ledger vs catalog row | §2-1 | ✅ aligned — phase-13 ledger/app/catalog verdict synchronized |
| `verify_self_stop.py` gate | §2-1 | ✅ available — closure uses `verify_applied_state_closure.py` as single entry point |
| template row vs physical snapshot | §2-2 | ✅ aligned — catalog claim now matches physical pass verdict |
| ADR-39 applied-state charter | §2-2 | ✅ accepted |
| ADR-42 verifier spec / script | §2-2 | ✅ available — template verifier result consumed by closure runner |
| dedicated closure runbook | §4 | ✅ closure runner added |

## 3. Operational State

| Surface | Status | Detail |
|---|---|---|
| `applications/your-harness-self/README.md` ledger | done | phase-13 row marked done with closure date |
| `config/fleet-harness-state.json` `phase-13` | adopted | `your-harness` + template closure verdict recorded |
| `scripts/verify_self_stop.py` | available | your-harness-self share gate decision tool |
| `scripts/verify_template_applied_state.py` | available | template applied-state verifier |
| `applications/template-repo/current-state.md` | available | live snapshot refreshed to 2026-05-25 |
| dedicated closure command | available | `scripts/verify_applied_state_closure.py` |

**Honest summary**: phase-13 is now closed with stronger semantics. The template physical baseline actually rose to verifier `pass/applied`, and the catalog, snapshot, and verifier all point to the same verdict.

## 4. Activation Gap

| Gap | Required action |
|---|---|
| template physical completion | closed in the current workspace baseline |

## 5. Exit Criterion

Per blueprint §7:
1. ✅ your-harness ledger and catalog row phase-13 verdict semantics match.
2. ✅ phase-13 closure evidence recorded via snapshot + verifier + catalog reconcile.
3. ✅ Single verdict path for template applied-state exists (`verify_applied_state_closure.py`).
4. ✅ Conflict between template catalog row and physical snapshot removed.
5. ✅ External families do not directly roll out this phase (`n_a`).

**Done gate**: satisfied. The template physical completion backlog is also resolved in the current workspace baseline.
