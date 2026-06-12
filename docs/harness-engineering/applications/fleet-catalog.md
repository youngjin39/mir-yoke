---
status: design-v1
date: 2026-05-25
scope: all fleet families × 13 rollout-phase adoption matrix view
audience: your-harness operators + fleet adopters
---

# Fleet Catalog — Adoption Matrix

> Visualizes the adoption state of all fleet families across the 13 rollout phases. Source of truth: `config/fleet-harness-state.json`.

## 0.5 Design Goals

- Provide a single view of where every family stands in phase adoption.
- Identify adoption gaps quickly.
- Support your-harness strengthening decisions by surfacing families that have fallen behind.
- Drive recommendations: which family should adopt which phase next.
- Replace the prior manual spreadsheet with a generated view tied to the JSON state.

## 1. Adoption Matrix

| Family | P0 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | P9 | P10 | P11 | P12 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `your-harness` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ~ |
| `template-harness` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ~ | ~ | – |
| `example-harness` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ~ |
| `example-notes` | ✓ | ✓ | ✓ | ~ | ~ | ~ | – | – | – | – | – | – | – |
| `example-game` | ✓ | ✓ | ✓ | ~ | ~ | – | – | – | – | – | – | – | – |
| `example-brand` | ✓ | ✓ | ✓ | ✓ | ~ | ~ | – | – | – | – | – | – | – |
| `example-infra` | ✓ | ✓ | ✓ | ✓ | ~ | ~ | ~ | – | – | – | – | – | – |
| `example-service` | ✓ | ✓ | ✓ | ~ | ~ | – | – | – | – | – | – | – | – |
| `example-app` | ✓ | ✓ | ✓ | ~ | ~ | ~ | – | – | – | – | – | – | – |
| `example-personal` | ✓ | ✓ | ~ | ~ | – | – | – | – | – | – | – | – | – |
| `example-learning` | ✓ | ✓ | ✓ | ~ | ~ | – | – | – | – | – | – | – | – |
| `example-video` | ✓ | ✓ | ✓ | ~ | ~ | ~ | – | – | – | – | – | – | – |
| `example-content` | ✓ | ✓ | ✓ | ~ | ~ | – | – | – | – | – | – | – | – |
| `example-story` | ✓ | ✓ | ~ | – | – | – | – | – | – | – | – | – | – |
| `example-stock` | ✓ | ✓ | ✓ | ~ | ~ | – | – | – | – | – | – | – | – |

Legend: ✓ = adopted, ~ = partial, – = not started

> Note: This table is a snapshot. Authoritative state is in `config/fleet-harness-state.json`. The example-harness ledger (`applications/example-harness/README.md`) is the per-phase feature evidence source for the reference implementation.

## 1-a. Character Clustering

Families cluster by `family_type` which determines auto-recommendation compatibility. See `families-overview.md §7` for the full clustering table.

| Cluster | Members | Recommendation affinity |
|---|---|---|
| SE-meta | `your-harness`, `template-harness`, `example-harness` | Full mutual |
| Flutter/mobile | `example-notes`, `example-game`, `example-app` | High |
| Content pipeline | `example-video`, `example-content`, `example-story` | High |
| Analysis pipeline | `example-stock` | Medium |
| Infrastructure | `example-infra`, `example-service` | High |
| Personal workspace | `example-personal`, `example-learning` | Low (user-gated) |
| Brand/product | `example-brand` | Medium |

## 1-bis. SoT Reconciliation Rule

When `config/fleet-harness-state.json` and this catalog diverge, the JSON is authoritative.

Reconciliation procedure:

```python
# SoT reconciliation — run when catalog appears stale
import json

state = json.load(open("config/fleet-harness-state.json"))

for family_slug, family in state["families"].items():
    ledger = family.get("phase_ledger", {})
    for phase, phase_data in ledger.items():
        status = phase_data.get("status", "not_started")
        # Regenerate catalog row from JSON rather than editing catalog by hand

# Skip the source family when checking if your-harness's own innovations need share
def should_share(recommendation):
    return recommendation.source_family != "your-harness"

# example-harness ledger is the evidence store for the reference implementation
# your-harness's ledger is tasks/tdd.json
```

`your-harness-as-agent` refers to the harness running in agent mode, as distinct from the harness as a governance document.

## 2. Sealed Family Policy

Sealed families receive no new phase adoption pushes. Bounded operational fixes are allowed when:
1. The fix is confined to harness verification or hook layer.
2. No new phase is marked adopted as a result.
3. The sealed flag in `config/fleet-harness-state.json` is not removed.

| Family | Sealed | Reason | Re-activation condition |
|---|---|---|---|
| `example-stock` | yes | Partial adoption; restricted | User decision |
| `example-learning` | yes | Learning workspace; bounded fixes | User decision |
| `example-brand` | yes (2026-06-11) | Temporary seal | User decision |
| `example-service` (openclaw) | yes | Infra/runtime; late-wave | User decision |
| `example-service` (router-control) | yes | Effectively suspended | Explicit reactivation |

## 3. Active Innovations

Innovations registered in the catalog pending triage or dispatch.

| Innovation ID | Source family | Kind | Phase | Share status | Registered |
|---|---|---|---|---|---|
| `terse-output-policy-2026-05-28` | `your-harness` | policy | phase-10 | share_to_fleet | 2026-05-28 |
| `context-assembly-adr53-2026-06-06` | `your-harness` | architecture | phase-0 | absorbed | 2026-06-06 |
| `scene-render-pipeline-2026-05-20` | `example-video` | skill | phase-5 | candidate | 2026-05-20 |
| `stock-analysis-backtest-2026-05-15` | `example-stock` | tool | phase-4 | archived | 2026-05-15 |

## 4. Active Recommendations

Recommendations dispatched to families, awaiting decision.

| Innovation ID | Target families | Dispatched | Decision deadline |
|---|---|---|---|
| `terse-output-policy-2026-05-28` | `example-notes`, `example-game`, `example-app`, `example-brand`, `example-personal`, `example-video`, `example-content`, `example-story`, `example-stock`, `example-learning`, `example-infra`, `example-service`, `example-harness` | 2026-05-28 | 2026-06-28 |

Decision options per recommendation: `adopted`, `declined`, `deferred`.

## 5. Update Cadence

| Event | Update trigger | Who |
|---|---|---|
| Phase adopted in a family | Immediate — update `config/fleet-harness-state.json` | your-harness Role A |
| New innovation detected | Immediate — `harness_drift.py` (scripted) or manual notify | your-harness Role A or family owner |
| Weekly share digest | Sunday 12:00 (scripted R27, manual until then) | your-harness Role A |
| Monthly catalog review | Monthly user-directed cadence (ADR-15 §S5) | your-harness Role A + user |
| Fleet-wide scan | On demand or after fleet-wide deploy | your-harness Role A |

## 6. Regeneration

The catalog table in §1 is generated from `config/fleet-harness-state.json`. To regenerate:

```bash
python tools/fleet_observe/render_catalog.py --output docs/harness-engineering/applications/fleet-catalog.md
```

When `render_catalog.py` is not yet available, update the table manually and record the manual update in `tasks/plan.md`.

## 7. Exit Criterion

The catalog is considered current when:

1. All families have a row in the §1 matrix.
2. All sealed families are listed in §2.
3. All active innovations have a triage status in §3.
4. All dispatched recommendations have a decision deadline in §4.
5. The JSON state and this table are consistent.
