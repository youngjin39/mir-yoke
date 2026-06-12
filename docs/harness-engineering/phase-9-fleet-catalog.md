---
phase: 9
title: Fleet Catalog
status: design-v1
depends_on: [phase-0, phase-7]
date: 2026-05-23
---

# Phase 9 — Fleet Catalog (Central Management)

> **Purpose**: your-harness centrally tracks the harness engineering adoption state of all fleet families in a single catalog. For managed repositories, it applies harness and agent patches directly. The public template is the starting point for new projects. your-harness is the state cache + drift tracking + direct-apply management + reporting hub.

## 0.5 Design Goals (R9 anchor)

> This phase's connection to the [3-axis fleet goals](applications/fleet-catalog.md). When adding a new phase or cherry-picking for a family, the `design` skill (R9-T11) requires `design_goals` as a mandatory input.

**3-axis contribution**:
- **Axis I (your-harness hardening)**: your-harness manages its own + all fleet family adoption states in a single catalog (resolves the current distributed tracking SoT gap)
- **Axis II (public template sync)**: template repository is the SoT for each family's blueprint (recommended phases / hooks / agents), 1:1 cross-referenced with your-harness state cache
- **Axis III (fleet central governance / back-propagation)**: **core of this phase**. Fleet family state matrix + drift detection + direct apply management + verification/reporting

**Inter-phase contract**:
- **Input** (consumes): phase-7 (family adoption decisions + family_type labels) + phase-6 (per-family 7-axis observability rollup)
- **Output** (provides): `config/fleet-harness-state.json` (state cache) + `config/fleet-drift-log/<family>-<ts>.json` (history) → phase-10 rollout share pipeline + phase-11 back-propagation input

## 1. Two Storage Responsibilities

> **User refinement (2026-05-23)**: "Harness engineering information for other repositories is in the public template repository, and your-harness centrally manages it with improvement tracking and back-propagation [via json / folders / files]"

| Storage | Location | Contents | Owner | Refresh |
|---|---|---|---|---|
| **Public Template** | `github.com/<your-org>/claude-codex-harness/families/<family>/` | blueprint (recommended_phases / recommended_hooks / recommended_agents / family_type strictness) — starting point for new projects | your-harness (sync via `scripts/verify_codex_sync.py`) | When your-harness lands + share decision is made |
| **your-harness State Cache** | `config/fleet-harness-state.json` | Each family's actual adoption state, last_sync, drift, innovations | your-harness auto-updated | Daily (fleet_observe scan) |
| **your-harness Drift Log** | `config/fleet-drift-log/<family>-<ts>.json` | Time series of differences between template baseline and family state | your-harness auto | Weekly snapshot |
| **Per-family local** | `<family-repo>/.claude/` | Family's own hooks / skills / agents | your-harness central manager | your-harness direct apply + verify |

**Principles**:
- Template = reference for "start here" (blueprint).
- your-harness state cache = tracking for "who has adopted what now" (state).
- your-harness must know the current harness structure of each managed family, apply minimum patches directly, and verify them.
- Families are centrally managed by your-harness's inspection/apply/verify/report loop, independently of the template/reference.

## 2. `fleet-harness-state.json` Schema (Overview)

This §2 is a schema overview. The formal definition is in [`docs/templates/_schema/fleet_harness_state.schema.json`](../templates/_schema/fleet_harness_state.schema.json) (R9-T06 new).

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "version": "1.0",
  "last_updated": "2026-05-23T03:00:00Z",
  "families": {
    "your-harness": {
      "family_type": "SE-meta",
      "adoption": {
        "phase-0": { "status": "adopted", "last_sync": "2026-05-23", "drift": "none" },
        "phase-1": { "status": "adopted", "last_sync": "2026-05-23", "drift": "minor:risk_level_hook_missing" },
        "...": "..."
      },
      "innovations": [
        { "id": "design-goals-capture-2026-05-23", "phase": "design-process", "share_status": "recommended", "source": "your-harness" }
      ],
      "recommendations_received": []
    },
    "example-video": {
      "family_type": "hybrid_pipeline",
      "adoption": { "...": "..." },
      "innovations": [
        { "id": "scene-render-pipeline-2026-05-20", "phase": "phase-5", "share_status": "candidate", "source": "example-video" }
      ],
      "recommendations_received": [
        { "id": "design-goals-capture-2026-05-23", "decision": "pending", "due": "2026-06-05" }
      ]
    }
  }
}
```

**Field meanings**:
- `adoption.status` enum: `not_adopted | in_review | patch_planned | patch_applied | verified | exception | n_a`.
- `adoption.drift`: free text for difference from template baseline. `none / minor:<reason> / major:<reason>`.
- `innovations`: new patterns originating in this family. your-harness catalogs as share candidates.
- `recommendations_received`: innovation share history surface. Even after the direct-apply policy, this can be maintained as a reference history — but the actual rollout SoT for active managed repos is the inspection/apply/verify/report cycle.

## 3. Fleet Family × 13 Rollout-Phase Adoption Matrix (+ phase-13 closure lane)

[`applications/fleet-catalog.md`](applications/fleet-catalog.md) is the visualization view (R9-T03 companion new). This §3 is the schema-side SoT.

| Family | Type | P0 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | P9 | P10 | P11 | P12 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| your-harness | SE-meta | ⬜ | ⬜ | 🟡 | ⬜ | ⬜ | 🟡 | 🟡 | 🟡 | 🟡 | 🟡 | 🟡 | 🟡 | 🟡 |
| template-harness | template | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| (remaining fleet rows) | ... | ... | ... | ... | ... | ... | ... | ... | ... | ... | ... | ... | ... | ... |

**Legend**: ✅ adopted / 🟡 opt_in_pending or partial / ⬜ not adopted / ⬛ n_a (not applicable for this family_type).

`phase-13` is not included in the rollout matrix. In the catalog it exists as a separate closure lane — currently only `your-harness` / `template-harness` have meaningful verdicts.

## 4. Drift Detection (phase-11 integration)

your-harness compares template baseline with family state to detect drift. Input for Phase 11 (back-propagation).

### 4-1. Detection Types
- **Template-ahead drift**: new phases / hooks landed in template are not applied in a family → share recommendation candidates.
- **Family-ahead drift**: family uses new patterns not in template → innovation candidates (share-back).
- **Conflict drift**: implementation of the same phase is incompatible between template and family → decision required (user escalate).

### 4-2. drift_log Entry Example
```json
{
  "family": "example-video",
  "detected_at": "2026-05-23T04:00:00Z",
  "drift_type": "family-ahead",
  "phase": "phase-5",
  "diff": { "added_skills": ["scene-render", "media-pipeline-build"] },
  "share_decision": "candidate"
}
```

## 5. Fleet Management Flow

> **User directive (2026-05-23)**: "For example, if a video-related skill is improved in a video director family, it gets shared to other agents via your-harness. That kind of flow. Not forced."

### 5-1. Operating Procedure
1. Drift detector and inspection update each family's current state.
2. your-harness determines repository type and exception status.
3. your-harness writes a minimum patch plan.
4. your-harness applies patches directly to the target repository.
5. your-harness runs verification commands and records results.
6. Catalog and per-repo report are updated.

### 5-2. Compatibility Determination (automated by your-harness)
- Compatibility matrix between innovation source family_type and target family_type:

| Source → Target | SE-meta | code_app | SE-product | hybrid_pipeline | content_app |
|---|---|---|---|---|---|
| SE-meta | ✓ | ✓ | ✓ | ✓ | △ |
| code_app | ✓ | ✓ | ✓ | △ | ✗ |
| SE-product | △ | △ | ✓ | △ | ✗ |
| hybrid_pipeline | ✗ | ✗ | △ | ✓ | △ |
| content_app | ✗ | ✗ | ✗ | △ | ✓ |

✓ compatible (auto recommend) / △ conditional (user review) / ✗ incompatible (skip).

**Footnote (R10-T13 — Slice D Scenario 4 contradiction resolution)**: This matrix is for **auto recommendation compatibility determination only**. Triage decisions ([phase-11 §3-1](phase-11-back-propagation.md)) with manual override (user explicitly states "absorb to your-harness" / "promote to template directly") are outside this matrix — user decision takes precedence. Example: `scene-render` skill from example-video (hybrid_pipeline) would not be auto-recommended under hybrid_pipeline→SE-meta ✗, but if the user explicitly states "absorb to your-harness" via a Triage decision, it is possible. See [share-back-runbook §5](applications/share-back-runbook.md).

### 5-3. Declined / Ignored Handling
- When a family makes a `declined` decision, record the reason in the catalog (your-harness does not repeat the same recommendation).
- After 30 days with status `pending`, automatically `declined`.
- After decline, if the source changes significantly, your-harness re-advises (1 time).

## 6. Update Cadence

| Job | Frequency | Output | Trigger |
|---|---|---|---|
| `mir_manage.py --check-family` bundle | user-triggered / manual cadence | family health + verifier bundle | CLI |
| `fleet_observe scan` | available, operational cadence selectable | `fleet-harness-state.json` update | managed runner / CLI |
| `drift_detector run` | available, operational cadence selectable | `fleet-drift-log/<family>-<ts>.json` append | managed runner / CLI |
| `share_dispatcher` | available, operational cadence selectable | new share candidate user notification (Discord) | managed runner / CLI |
| `full_audit` | available, operational cadence selectable | catalog consistency check + cleanup | managed runner / CLI |

Automated schedule assets can live under `scripts/cron/`, but the current default operational path is a user-triggered bundle based on `mir_manage.py`.

## 7. Application State (as of 2026-05-23)

| Item | Status | Location |
|---|---|---|
| fleet-harness-state.json | **landed** (R24-T05 corrected 2026-05-24) | `config/fleet-harness-state.json` (all fleet family rows) |
| fleet_harness_state.schema.json | **landed** (R24-T05 corrected 2026-05-24) | `docs/templates/_schema/fleet_harness_state.schema.json` |
| drift detector | **landed** (R24-T05 corrected 2026-05-24) | `tools/fleet_observe/harness_drift.py` (551 LOC) |
| share catalog UI | **partially landed** (Discord notification partial) | Discord notification (manual) + your-harness catalog doc |
| applications/fleet-catalog.md | **landed** (R24-T05 corrected 2026-05-24) | generated from json (R9-T03 companion) |
| family_type compatibility matrix | This §5-2 SoT | `docs/templates/_schema/family_compatibility.schema.json` (deferred) |

**Gap**: The major SoTs of this phase (fleet-harness-state.json + schema + drift detector + applications/fleet-catalog.md) are all landed. The remaining work is share notification automation and cadence operational standardization.

## 8. family_type Application Exceptions

| family_type | In fleet-harness-state.json | Drift tracking | Share candidates | Reason |
|---|---|---|---|---|
| SE-meta (your-harness) | ✓ | ✓ | ✓ (many sources) | Reference for dogfooding |
| code_app | ✓ | ✓ | ✓ | High value for extracting shared infra patterns |
| SE-product | ✓ | ✓ | ✓ | App pattern sharing |
| hybrid_pipeline | ✓ | ✓ | ✓ (content pipeline patterns) | User example (video director) |
| content_app | ✓ | △ | △ | Personal/content domain, careful sharing |
| **sealed** | ✓ (state read only) | △ | ✗ | Sealed policy, share-out blocked |

## 9. SE-meta Self-Stop Verification

your-harness itself (your-harness) is also one row in fleet-harness-state.json. For this phase to land, your-harness's own adoption state must be recorded honestly. As of the 2026-05-25 snapshot, your-harness self rollout phases have 11 `adopted` and 2 `opt_in_pending` (`phase-7`, `phase-8`), and the closure lane `phase-13` is also `adopted`.

**Potential violation**: your-harness pushing bulk patches without inspection, or recording applied/verified without verification. Prevention: enforce the §5-1 order of inspection → minimum patch plan → verify → report.

## 10. ADR Candidates

ADR-25 — Fleet Catalog introduction. ADR-48 — Central Fleet Management and Direct Apply Policy.

## 11. Exit Criterion

Conditions for this phase to be judged done:
1. `config/fleet-harness-state.json` exists, all fleet families have at least 1 row.
2. `docs/templates/_schema/fleet_harness_state.schema.json` exists + json is schema-valid.
3. `applications/fleet-catalog.md` visualization doc generated, §3 matrix 100% filled.
4. Drift detector script run once as measured dry-run (before fleet_observe integration).
5. ADR-25 published.
6. User review passed (central direct-apply policy confirmed).

As of the current implementation, the drift detector code is in landed state. The remaining work is cadence automation and user-triggered bundle operational protocol stabilization.

## 12. Next Steps

Proceed to [Phase 10 — Rollout Pipeline](phase-10-rollout-pipeline.md). Phase 9 (catalog) handles state tracking; Phase 10 defines the pipeline for state transitions (your-harness → template → fleet).
