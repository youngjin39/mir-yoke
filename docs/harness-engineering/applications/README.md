---
status: active
scope: harness engineering application layer — execution ledger for the harness engineering rollout
audience: your-harness control plane + fleet families
---

# Applications — Harness Engineering Execution Ledger

> **Purpose**: This directory is the execution layer of the harness engineering blueprint. Each application document records how a specific family or shared mechanism applies the phase designs.

## 1. Directory Structure

```
applications/
├── README.md                          ← This file — the execution ledger
├── autonomous-execution.md            ← Phase autonomous execution mechanism
├── design-process.md                  ← Multi-subagent design process
├── dispatchbrief-defaults-2026-05-28.md ← DispatchBrief default triage contract
├── dispatchbrief-rollout-playbook-2026-05-28.md ← DispatchBrief rollout playbook
├── exceptions.md                      ← Cross-family enforcement exception matrix
├── external-repo-operational-verification-phase.md ← External repo verification prep
├── families-overview.md               ← Auto-generated fleet family cards
├── family-type-adoption-runbooks.md   ← Per-family-type adoption procedures
├── feature-matrix.md                  ← Phase-by-family-type feature matrix
├── fleet-catalog.md                   ← Fleet catalog design (3-axis goals)
├── fleet-rollout-report-contract-2026-05-28.md ← Rollout report contract
├── harness-review-criteria.md         ← Review criteria for harness changes
├── incident-response.md               ← Incident classification and response
├── security-baseline.md               ← Security baseline for harness
├── share-back-runbook.md              ← Share-back runbook for innovations
├── template-cherrypick.md             ← Template cherry-pick procedure
├── template-repo/                     ← Template repository sub-documents
│   ├── bootstrap-day-0.md
│   ├── bootstrap-interview-spec.md
│   ├── ci.md
│   ├── current-state.md
│   ├── sanitize-glossary.md
│   ├── upgrade-runbook.md
│   └── versioning.md
└── example-harness/                   ← example-harness per-phase application records
    ├── README.md
    ├── phase-0-application.md
    ├── ...
    └── phase-14-application.md
```

## 2. Dogfooding-First Principle

The harness engineering rollout follows a **dogfooding-first** principle:

1. **example-harness first**: Apply every phase to your-harness before rolling out to external families. example-harness serves as the living proof that the harness works.
2. **Validate on self**: If a phase cannot be clearly applied to your-harness, the design is not ready for fleet rollout.
3. **External families second**: After your-harness validates the phase, the rollout proceeds to external fleet families.

## 3. Standard Application Document Structure

Each `phase-N-application.md` in a family directory follows this structure:

```
---
phase: N
family: <family-name>
status: applied | partial | planned | not-applicable
date: YYYY-MM-DD
---

# Phase N Application — <Family Name>

## 1. Pre-conditions
## 2. Applied Changes
## 3. Verification Result
## 4. Gaps / Partial Land
## 5. Exit Criterion Status
```

## 4. Gate Progress

| Phase | example-harness | External Families (fleet) |
|---|---|---|
| Phase 0 | applied | partial (wave 1 in progress) |
| Phase 1 | applied | partial |
| Phase 2 | applied | partial |
| Phase 3 | applied | partial |
| Phase 4 | applied | partial |
| Phase 5 | applied | partial |
| Phase 6 | applied | partial |
| Phase 7 | applied | partial |
| Phase 8 | applied | partial |
| Phase 9 | applied | partial |
| Phase 10 | applied | partial |
| Phase 11 | applied | partial |
| Phase 12 | applied | partial |
| Phase 13 | applied | pass (2026-05-25) |
| Phase 14 | applied | partial (tracked gaps) |

## 5. ADR Candidates

Application experience has produced the following ADR candidates:

- **ADR-21**: Dogfooding-first principle — formal policy for self-application before fleet rollout
- **ADR-22**: Application document schema — standard structure for per-family phase application records
- **ADR-23**: Application gate definition — what "applied" means vs "partial" vs "planned"

## 6. Application Sequence

The fleet rollout proceeds in ordered waves:

### S1 — your-harness (self)
- Target: example-harness
- Gate: all 14 phases applied and verified

### S2 — Template Baseline
- Target: template-harness (public template repository)
- Gate: Stage 2 sanitize + template-sync-validator pass

### S3 — Phase A External (active product surfaces)
- Targets: example-notes, example-app, example-brand, example-game, example-personal, example-video, example-content, example-story

### S4 — Phase B External (partial adoption or learning-workspace)
- Targets: example-stock, example-learning

### S5 — Phase C/D External (infra/runtime or higher blast-radius)
- Targets: example-infra, example-service, sealed families (apply only when explicitly reactivated)

## 7. Shared Mechanisms

The following documents apply across all families (not family-specific):

- `autonomous-execution.md` — phase autonomous execution model
- `design-process.md` — mandatory multi-subagent design process
- `exceptions.md` — cross-family enforcement exception matrix
- `family-type-adoption-runbooks.md` — per-family-type adoption procedures
- `incident-response.md` — incident classification and response playbook
- `security-baseline.md` — shared security baseline for harness surfaces

## 8. Verification

Run the following to verify application state across the ledger:

```bash
# Verify all application docs are correctly registered
scripts/verify_repo_agent_management.py

# Check fleet adoption state
tools/fleet_observe/mir_manage.py --scan-all
```
