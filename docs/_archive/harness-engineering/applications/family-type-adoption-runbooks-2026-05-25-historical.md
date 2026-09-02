---
status: design-v1
date: 2026-05-25
scope: 6 family_type mini adoption runbooks
audience: fleet adopters (per family_type) + your-harness Role A
---

# Family-Type Adoption Runbooks

> Per-family-type mini runbooks. Condensed adoption guides for each family_type category.

## 0.5 Purpose

your-harness uses these runbooks as the basis for type-based adoption recommendations, replacing the prior approach where fleet families received uniform advice. Recommendations generated from these runbooks are auto-applied across all fleet families.

## 1. SE-meta

> Applies to: `your-harness`, `template-harness`

### 1-1. Overview

SE-meta families are self-referential harness management repositories. They host the control plane logic, phase blueprint, and governance layer for all other fleet families.

### 1-2. Phase adoption order

Phase 0 through 14 in sequence. No phases are optional; all phases are load-bearing for SE-meta.

### 1-3. Mandatory gates

- All 13 verifier rules from ADR-51 must pass before a phase is marked adopted.
- TDD ledger (`tasks/tdd.json`) must record evidence for every tool function change.
- `tasks/tdd.json` compaction must not drop historical records.
- Cross-repo fleet writes must use Bash channel + fleet-admin elevation record.

### 1-4. Known live families

- `your-harness` (SE-meta primary — this repo)
- `template-harness` (public sanitized template)

## 2. code_app

> Applies to: `example-notes`, `example-game`, `example-brand`, `example-infra`, `example-service`

### 2-1. Overview

code_app families are product or infrastructure code repositories. They may be Flutter mobile apps, backend services, or infrastructure repos. Harness adoption improves AI-assisted development, but the product codebase is the primary concern.

### 2-2. Phase adoption order

Recommended order: 0 → 1 → 2 → 3 → 4 → 5 → 9 → 10 → 7 → 8 → 6 → 11 → 12 → 13 → 14.

Rationale: phases 0–5 establish the foundation, phase 9 (rollout pipeline) enables fleet integration, phase 10 (back-propagation) enables innovation sharing, phases 11–14 add advanced autonomy and security layers.

### 2-3. Mandatory gates

- `verify_context_paths.py` must pass before any phase beyond 3 is marked adopted.
- `verify_codex_sync.py` must pass for all phases that include Codex execution.
- For Flutter repos: `flutter analyze` must pass and `flutter test` must be green.
- For infra/service repos: deploy smoke test must pass.

### 2-4. Known live families

- `example-notes` (Flutter — Phase A verification target)
- `example-game` (Flutter — Phase A verification target)
- `example-brand` (product app — discovery phase first)
- `example-infra` (infrastructure — Phase C)
- `example-service` (service layer — Phase C)

### 2-5. Special considerations for Flutter repos

- Do not edit pubspec.yaml without confirming `flutter pub get` still resolves cleanly.
- Keep harness hooks out of the Flutter build pipeline (`lib/`, `android/`, `ios/`).
- Hook enforcement should apply only to `.claude/`, `tools/`, `scripts/` paths.

## 3. SE-product

> Applies to: `example-app`, `example-personal`, `example-learning`

### 3-1. Overview

SE-product families are user-facing product repositories with a personal or learning domain angle. The harness layer is lighter than SE-meta, and user autonomy is higher.

### 3-2. Phase adoption order

Recommended order: 0 → 1 → 2 → 3 → 5 → 9 → 10 → 4 → 7 → 8 → 6 → 11 → 12 → 13 → 14.

Phases 13–14 (advanced autonomy) require explicit user review before adoption in personal-domain families.

### 3-3. Mandatory gates

- `verify_context_paths.py` and `verify_codex_sync.py` for all applicable phases.
- For personal/learning families: no auto-escalation to critical/high incident severity. User decides.
- For sealed families: only bounded operational fixes allowed; no new phase adoption without unsealing.

### 3-4. Known live families

- `example-app` (Flutter reader — Phase A)
- `example-personal` (personal workspace)
- `example-learning` (learning workspace — sealed)

### 3-5. Personal domain rules

- Auto critical/high incident escalation is prohibited.
- All fleet-wide policies that would force user decisions are presented as options, not requirements.
- Memory entries from personal context stay in user-trusted namespace.

## 4. hybrid_pipeline

> Applies to: `example-video`, `example-content`, `example-story`, `example-stock`

### 4-1. Overview

hybrid_pipeline families combine code execution with content/media generation pipelines. They may run media generation, text synthesis, or analysis pipelines alongside a standard code layer. The harness must not interrupt active pipeline runs.

### 4-2. Phase adoption order

Recommended order: 0 → 1 → 2 → 3 → 5 → 9 → 6 → 10 → 4 → 7 → 8 → 11 → 12 → 13 → 14.

Phase 6 (observability) is promoted earlier because pipeline runs are harder to debug without structured observation.

### 4-3. Mandatory gates

- `verify_context_paths.py` and `verify_codex_sync.py`.
- Do not apply harness hooks to pipeline execution directories unless you have confirmed they do not interrupt active runs.
- CONTAIN SLA is 2x extended for hybrid_pipeline (creative work protection — interrupt burden is high).

### 4-4. Known live families

- `example-video` (short video pipeline — Phase A)
- `example-content` (content writing pipeline — Phase A)
- `example-story` (fiction writing pipeline — Phase A, lowest baseline score)
- `example-stock` (stock analysis pipeline — Phase B, sealed)

### 4-5. Pipeline-specific rules

- Harness enforcement should apply only to `.claude/`, `tools/`, `scripts/` paths.
- Do not add deny-list entries that would block pipeline media processing commands.
- Cross-family sharing of pipeline innovations requires explicit compatibility check against the character clustering table in `families-overview.md §7`.

## 5. SE-product personal workspace

> Applies to: `example-personal`

### 5-1. Overview

Personal workspace families are the narrowest autonomy boundary. The harness provides structure, but the user decides every consequential action.

### 5-2. Phase adoption order

Same as SE-product, but phases 11–14 are explicitly user-gated.

### 5-3. Rules

- No automatic advisory log entries of sensitive personal content.
- All AI score improvements are presented as options, not auto-applied.
- Incident response follows the SE-product personal row in the severity table: best-effort + user decision required.

## 6. Example-memory

`example-memory` is a specialist agent, not a family_type. It does not follow these runbooks.

For example-memory adoption, see the federated second-brain documentation in `docs/memory-map.md` and the `example-memory` agent profile.

## 7. SE-meta (your-harness reference)

This section records the current your-harness adoption status against its own runbook.

| Phase | your-harness status |
|---|---|
| 0 | adopted |
| 1 | adopted |
| 2 | adopted |
| 3 | adopted |
| 4 | adopted |
| 5 | adopted |
| 6 | adopted |
| 7 | adopted |
| 8 | adopted |
| 9 | adopted |
| 10 | adopted |
| 11 | adopted |
| 12 | partial — R11 code land pending |
| 13 | partial — R13 code land pending |
| 14 | partial — R14 code land pending |

## 8. Cross-Type Innovation Compatibility Matrix

When an innovation from one family type is considered for sharing to another family type, this matrix determines auto-dispatch eligibility. User override always takes precedence.

| Source type | Target type | Auto-dispatch | Notes |
|---|---|---|---|
| SE-meta | code_app | ✓ | Standard propagation |
| SE-meta | SE-product | ✓ | Standard propagation |
| SE-meta | hybrid_pipeline | ✓ | Standard propagation |
| code_app | SE-meta | ✓ | Absorb path available |
| code_app | code_app | ✓ | Direct share |
| code_app | hybrid_pipeline | ✓ | Compatible |
| hybrid_pipeline | SE-meta | ✗ (user override only) | Requires explicit review |
| hybrid_pipeline | code_app | ✓ | Compatible |
| hybrid_pipeline | hybrid_pipeline | ✓ | High affinity |
| SE-product | SE-meta | ✓ | Absorb path available |

## 9. Main-Agent Parity

All family types listed above share the same main-agent contract with your-harness: requirements clarification, architecture, design approval, orchestration, planning, dispatch, exception handling, verification synthesis, and final merge judgment.

Known families requiring parity verification (in order of last scan):

- `example-notes`
- `example-app`
- `example-brand`
- `example-game`
- `example-personal`
- `example-video`
- `example-content`
- `example-story`
- `example-stock`
- `example-learning`
- `example-infra`
- `example-service`

## 10. your-harness Application Status

| Item | Status |
|---|---|
| Runbook foundation | done — this doc |
| Per-family-type auto-recommendation | partial — `fleet_observe/share_dispatcher.py` dispatches by type |
| Sealed family exception gates | live — `config/fleet-harness-state.json` `sealed` field |
| Personal domain auto-escalation block | live — incident runbook `§3-1` |
| Example-memory specialist separation | done — tracked separately from family catalog |

## 11. Exit Criterion

A family is considered fully onboarded when:

1. All applicable phases for its type are marked adopted in its ledger.
2. `verify_context_paths.py` passes.
3. `verify_codex_sync.py` passes (if Codex execution is part of its profile).
4. At least one innovation has been shared or received through the share-back pipeline.
5. At least one incident response drill has been run or a real incident has been recorded.

## 12. Next Steps

1. Run operational verification for all Phase A families (`example-notes` through `example-story`).
2. Record baseline AI scores.
3. Choose one bounded improvement seam per family.
4. Re-run verification and record score delta.
5. Queue Phase B families after Phase A is complete.
