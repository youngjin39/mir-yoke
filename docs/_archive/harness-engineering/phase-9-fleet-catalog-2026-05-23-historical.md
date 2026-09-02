---
phase: 9
title: Fleet Catalog
status: design-v1
depends_on: [phase-0, phase-7]
date: 2026-05-23
---

# Phase 9 -- Fleet Catalog (Central Management)

> **Purpose**: Track the harness engineering adoption state of N families in a central catalog managed by your harness. The public template is the starting point for new projects; your harness is the state cache + drift tracker + direct-apply manager + reporting hub.

## 0.5 Design Goals (R9 anchor)

**3-axis contribution**:
- **Axis I (self-harness hardening)**: manage adoption state of your harness + N families in a single catalog (resolve SoT absence in distributed tracking)
- **Axis II (public template sync)**: template repository is the SoT for each family's blueprint (recommended phases / hooks / agents / family_type strictness); 1:1 cross-reference with central state cache
- **Axis III (fleet central management)**: **core of this phase**. N-family state matrix + drift detection + direct apply management + verification/reporting

**Inter-phase contract**:
- **Input** (consumes): phase-7 (family adoption decision + family_type label) + phase-6 (per-family 7-axis observability rollup)
- **Output** (provides): `config/fleet-harness-state.json` (state cache) + `config/fleet-drift-log/<family>-<ts>.json` (history) -> phase-10 rollout share pipeline + phase-11 back-propagation input

## 1. Two-Storage Responsibility Separation

| Storage | Location | Content | Owner | Refresh |
|---|---|---|---|---|
| **Public Template** | `github.com/<org>/mir-yoke/families/<family>/` | blueprint (recommended_phases / recommended_hooks / recommended_agents / family_type strictness) -- starting point for new projects | central harness (sync via `scripts/verify_codex_sync.py`) | After central harness lands and share decision made |
| **Central State Cache** | `config/fleet-harness-state.json` | actual adoption state per family, last_sync, drift, innovations | central harness auto-update | Daily (fleet_observe scan) |
| **Drift Log** | `config/fleet-drift-log/<family>-<ts>.json` | time-series of differences between template baseline and family state | central harness auto | Weekly snapshot |
| **Per-family local** | `<family-repo>/.claude/` | family's own hook / skill / agent files | central manager | direct apply + verify |

**Principles**:
- Template = reference for "how to start" (blueprint).
- Central state cache = tracking "who adopted what right now" (state).
- Central harness must know the current harness structure of managed families, apply minimal patches directly, and verify.
- Families are centrally managed by the inspection/apply/verify/report loop, separate from template/reference.

## 2. `fleet-harness-state.json` Schema (overview)

This section is a schema overview. Formal definition: `docs/templates/_schema/fleet_harness_state.schema.json`.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "version": "1.0",
  "last_updated": "<timestamp>",
  "families": {
    "your-harness": {
      "family_type": "SE-meta",
      "adoption": {
        "phase-0": { "status": "adopted", "last_sync": "<date>", "drift": "none" },
        "phase-1": { "status": "adopted", "last_sync": "<date>", "drift": "minor:risk_level_hook_missing" }
      },
      "innovations": [
        { "id": "design-goals-capture-<date>", "phase": "design-process", "share_status": "recommended", "source": "your-harness" }
      ],
      "recommendations_received": []
    },
    "example-pipeline": {
      "family_type": "hybrid_pipeline",
      "adoption": {},
      "innovations": [
        { "id": "scene-render-pipeline-<date>", "phase": "phase-5", "share_status": "candidate", "source": "example-pipeline" }
      ],
      "recommendations_received": [
        { "id": "design-goals-capture-<date>", "decision": "pending", "due": "<date>" }
      ]
    }
  }
}
```

**Field meanings**:
- `adoption.status` enum: `not_adopted | in_review | patch_planned | patch_applied | verified | exception | n_a`.
- `adoption.drift`: free text of difference from template baseline. `none / minor:<reason> / major:<reason>`.
- `innovations`: new patterns that emerged in this family. Central harness catalogs as share candidates.
- `recommendations_received`: innovation share history surface.

## 3. N-family x Phase Adoption Matrix

`applications/fleet-catalog.md` is the visualization view. This section is the schema-side SoT.

Populate the matrix for your own fleet. Legend: `adopted` / `opt_in_pending` or partial / `not_adopted` / `n_a` (not applicable for this family_type).

`phase-13` is not included in the rollout matrix. It exists as a separate closure lane in the catalog.

## 4. Drift Detection (phase-11 link)

Central harness compares template baseline with family state to detect drift. Input for Phase 11 (back-propagation).

### 4-1. Detection types
- **Template-ahead drift**: new phase / hook landed in template but not applied in family -> share recommendation candidate.
- **Family-ahead drift**: family uses new pattern not in template -> innovation candidate (share-back).
- **Conflict drift**: same phase implementation incompatible between template and family -> decision required (escalate to operator).

### 4-2. drift_log entry example
```json
{
  "family": "example-pipeline",
  "detected_at": "<timestamp>",
  "drift_type": "family-ahead",
  "phase": "phase-5",
  "diff": { "added_skills": ["scene-render", "media-pipeline-build"] },
  "share_decision": "candidate"
}
```

## 5. Fleet Management Flow

### 5-1. Operating Procedure
1. Drift detector and inspection update family current state.
2. Central harness determines repository type and exception status.
3. Central harness writes minimum patch plan.
4. Central harness directly applies patch to target repository.
5. Central harness runs verification commands and records results.
6. Update catalog and per-repo report.

### 5-2. Compatibility Determination

Innovation source family_type vs target family_type compatibility matrix:

| Source -> Target | SE-meta | code_app | SE-product | hybrid_pipeline | content_app |
|---|---|---|---|---|---|
| SE-meta | yes | yes | yes | yes | conditional |
| code_app | yes | yes | yes | conditional | no |
| SE-product | conditional | conditional | yes | conditional | no |
| hybrid_pipeline | no | no | conditional | yes | conditional |
| content_app | no | no | no | conditional | yes |

`yes` = auto recommend / `conditional` = operator review required / `no` = skip.

**Note**: This matrix governs auto recommendation compatibility only. Manual operator override (e.g., operator explicitly directs "absorb to self-harness") takes precedence over this matrix. See share-back-runbook section 5.

### 5-3. Decline / Ignore Handling
- When a family `declined`, record reason in catalog (central harness does not repeat same recommendation).
- `pending` decisions auto-expire to `declined` after 30 days.
- After decline, if source has a major change, central harness re-advises once.

## 6. Update Cadence

| Job | Frequency | Output | Trigger |
|---|---|---|---|
| `mir_manage.py --check-family` bundle | user-triggered / manual cadence | family health + verifier bundle | CLI |
| `fleet_observe scan` | available, cadence operator choice | `fleet-harness-state.json` update | managed runner / CLI |
| `drift_detector run` | available, cadence operator choice | `fleet-drift-log/<family>-<ts>.json` append | managed runner / CLI |
| `share_dispatcher` | available, cadence operator choice | new share candidate user notification | managed runner / CLI |
| `full_audit` | available, cadence operator choice | catalog consistency check + cleanup | managed runner / CLI |

Default operating path is user-triggered bundle via `mir_manage.py`. Automatic schedules can be placed under `scripts/cron/`.

## 7. Application Status

| Item | Status | Location |
|---|---|---|
| fleet-harness-state.json | landed | `config/fleet-harness-state.json` |
| fleet_harness_state.schema.json | landed | `docs/templates/_schema/fleet_harness_state.schema.json` |
| drift detector | landed | `tools/fleet_observe/harness_drift.py` |
| share catalog UI | partial (Discord notification partial) | Discord notification (manual) + catalog doc |
| applications/fleet-catalog.md | landed | generated from json |
| family_type compatibility matrix | this section SoT | `docs/templates/_schema/family_compatibility.schema.json` (deferred) |

**Gaps**: Main SoTs (fleet-harness-state.json + schema + drift detector + applications/fleet-catalog.md) all landed. Remaining: share notification automation and cadence operations standardization.

## 8. family_type Application Exceptions

| family_type | In fleet-harness-state.json | Drift tracking | Share candidate | Reason |
|---|---|---|---|---|
| SE-meta (your harness) | yes | yes | yes (many sources) | dogfooding reference |
| code_app | yes | yes | yes | high value for common infra pattern extraction |
| SE-product | yes | yes | yes | app pattern sharing |
| hybrid_pipeline | yes | yes | yes (content pipeline patterns) | example: pipeline directors |
| content_app | yes | conditional | conditional | personal/content area, share carefully |
| **sealed** families | yes (state read only) | conditional | no | seal policy, share-out blocked |

## 9. SE-meta Self-Stop Verification

The central harness itself is also one row in fleet-harness-state.json. For this phase to land, the adoption state of the central harness itself must be recorded honestly. Adoption status by phase is tracked in the catalog.

**Potential violation**: Central harness pushing bulk patches without inspection, or recording applied/verified without verification. Prevention: enforce the inspection -> minimum patch plan -> verify -> report order in section 5-1.

## 10. Exit Criterion

This phase is judged done when:
1. `config/fleet-harness-state.json` exists with 1+ row for all managed families.
2. `docs/templates/_schema/fleet_harness_state.schema.json` exists + JSON is schema-valid.
3. `applications/fleet-catalog.md` visualization doc generated with matrix fully populated.
4. drift detector script dry-run verified once.
5. ADR for fleet catalog published.
6. Operator review passed (central direct-apply policy confirmed).

## 11. Next Step

[Phase 10 -- Rollout Pipeline](phase-10-rollout-pipeline.md). Phase 9 (catalog) handles state tracking; Phase 10 defines the pipeline for state transitions (self-harness -> template -> fleet).
