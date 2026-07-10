---
phase: 7
title: Fleet Expansion Application
status: done
family: your-harness (SE-meta)
blueprint: ../../phase-7-fleet-expansion.md
priority: P4
---

# Phase 7 — Fleet Expansion Application (example-harness)

> **Core point**: Applying this phase is the core purpose of a "meta-harness that affects other repositories." This is the phase where the exceptions.md matrix activates.

## 1. Blueprint Reference

[`../../phase-7-fleet-expansion.md`](../../phase-7-fleet-expansion.md) full. Key sections: §1 6-Type classification, §3 SE-Meta Self-Stop, §6 migration procedure 8-step, §7 Strictness differentiation.

**Related Supplementary Documents**: [`../template-cherrypick.md`](../template-cherrypick.md) — this phase is the infrastructure layer for the cherry-pick model. The 5-layer cherry-pick (Phase/Skill/Agent/Hook/Config) + your-harness reference sync policy runs in this phase.

## 2. Current State (pre-measurement)

| Item | Blueprint Location | your-harness State |
|---|---|---|
| 6-Type classification | §1 | land — `family_type` schema + fleet families config populated |
| Inheritance graph | §2 | **not implemented** — flat catalog only |
| SE-meta self-stop | §3 | partial land — `enabled_phases` consumer verifier + advisory self-stop warning landed, stronger halt enforcement incomplete |
| Dogfooding priority | §4 | land — your-harness applied first |
| Fleet families rollout | §5 | land — `config/repos/*.json` |
| Migration procedure 8-step | §6 | land — survey / classify / migrate / observe |
| Strictness differentiation | §7 | partial land — each family JSON hooks configuration |
| Cross-pollination | §8 | land — external agents/skills catalog |
| Public template sync | §9 | land — mir-yoke operation |

**Gap**: No exit-criterion-level blockers. Inheritance graph visualization enhancement may remain as a follow-up improvement item, but fleet-wide parity direct-apply and verifier-clean registry state satisfy phase exit.

**Blueprint gap**: The family_type descriptions and some family examples in the §5 matrix diverge from the current `config/repos/*.json` SoT. This ledger treats `config/repos/*.json` as the source of truth.

## 3. Application Work Steps

| Step | Work | Dependency | Estimate |
|---|---|---|---|
| 7-1 | 6-Type classification naming ADR (`adr-26-6-type-classification-2026-MM-DD.md`) | – | 2h |
| 7-2 | Add `family_type: SE-meta \| code_app \| SE-product \| hybrid_pipeline \| content_app \| template` field to `config/repos/<family>.json` | 7-1 | 2h |
| 7-3 | Fleet families `family_type` backfill — apply [`../../phase-7-fleet-expansion.md`](../../phase-7-fleet-expansion.md) §5 matrix | 7-2 | 1h |
| 7-4 | Inheritance graph schema introduction — `inherits_from` field + `scripts/verify_repo_agent_management.py` advisory | 7-2 | 3h |
| 7-5 | `enabled_phases` field consumer verifier — read each family's opt-in strictness in management verification | 7-3 | 2h |
| 7-6 | SE-meta self-stop automation — advisory verification that your-harness's same phase is done when `enabled_phases` is enforced or doc-strict applied, with future block promotion | 7-5 | 4h |
| 7-7 | Strictness matrix automatic verification — encode exceptions.md §3 table as code + advisory | 7-2, 7-3 | 3h |
| 7-8 | New family 1 (if any) 8-step migration procedure dry-run | 7-4~7-7 | 1 week |

## 4. Files to Modify

| Path | Type |
|---|---|
| `docs/decisions/adr-26-6-type-classification-2026-MM-DD.md` | create |
| `config/repo-agent-management.schema.json` | landed (`family_type` / `enabled_phases` / `self_stop_acknowledged`) |
| `config/repos/*.json` (fleet families files) | edit (`family_type` backfill) |
| `scripts/verify_repo_agent_management.py` | edit (inheritance + self-stop + strictness verification) |
| `tools/fleet_observe/measure/family_type.py` | create |
| `tasks/checklist.md` | edit (cadence reminder) |

## 5. Verification Procedure

Blueprint §12 Exit Criterion: "SE-meta dogfooding 1 pass (all Phase 0~6 decisions applied to your-harness with no self-stop condition violations). New family 1 migration 8-step completed + fleet_observe advisory 1 week with no warnings."

Verification methods:
1. your-harness Phase 0~6 application complete → all entries in this ledger [`README.md`](README.md) marked `done`
2. Automatic verification that families registered in `enabled_phases` as enforced (or doc-strict) have the corresponding phase done in the your-harness self ledger
3. Full-fleet direct apply complete: all active / sealed / bootstrap-only / skip-migrate targets reflect the parity contract in actual repo source and are verified by repo-local or central verifier
4. `uv run python scripts/verify_repo_agent_management.py` warning for phase-7 self-stop BLOCK should disappear

## 6. Cross-repo Propagation Exceptions

This phase itself is the "propagation" control phase, so exceptions.md entire document is this §6.

| Case | Rule |
|---|---|
| All families | enforced — type classification + enabled_phases mandatory |
| Family refuses to specify `family_type` | family JSON rejected, `config/repo-agent-management.json` registration blocked |
| Family violates inheritance graph (e.g., code_app not inheriting SE-meta) | warn → block (1-week migration grace period) |
| Public template (mir-yoke) | sanitize mandatory + enforced |

**Specific Exceptions**:
- `example-infra` → code_app backfill
- `example-notes` / `example-game` / `example-app` → code_app
- `example-brand` (greenfield) → code_app, new application dry-run target
- `example-content` / `example-story` → hybrid_pipeline
- `example-video` / `example-stock` → hybrid_pipeline (director specialization complete — 2026-05-22)
- `example-learning` / `example-personal` → SE-product

## 7. SE-meta self-stop Check

Can your-harness apply the 6-Type classification system to itself? → ✓ your-harness = SE-meta self-classification possible.
Does your-harness recognize itself as the top of the SE-meta inheritance graph? → ✓ specified in §2 graph.
Is family rollout blocked if your-harness's phase is not done? → After work ✓ §3-6 automation.

**Potential Violation Risk**:
- If self-stop automation is too strict, external family rollout itself stops. Therefore §3-6 verification uses "warn 1 week → block" gradual introduction.
- If user consent is not obtained before auto-classifying family_type backfill for fleet families, errors occur. Therefore §3-3 backfill is applied after user confirmation.

## 8. Work Status

- **Status**: done (fleet catalog/registry, `enabled_phases` schema, advisory self-stop verifier, template parity gate, and full-fleet direct apply all completed)
- **Completion Date**: 2026-05-29
- **Verification Evidence**: fleet families catalog + `verify_repo_agent_management.py` + parity direct-apply across all `config/repos/*.json` targets + repo-local verifier passes on repos that ship `scripts/verify_codex_sync.py`
- **Revert Reason**: –

## 9. Next Steps

Proceed to [Phase 8 Garbage Collection](phase-8-application.md).
