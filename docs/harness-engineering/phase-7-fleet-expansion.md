---
phase: 7
title: Fleet Expansion
status: consolidated-v1
depends_on: [phase-0, phase-1, phase-2, phase-3, phase-4, phase-5, phase-6]
---

# Phase 7 — Fleet Expansion & Classification

> **Purpose**: Dogfood with your-harness itself (SE-meta), then sequentially port to all fleet families. Apply strictness differentially using the 6-Type classification.

## 0.5 Design Goals (R9 anchor)

> This phase's connection to the [3-axis fleet goals](applications/fleet-catalog.md). When adding a new phase or cherry-picking for a family, the `design` skill (R9-T11) requires `design_goals` as a mandatory input.

**3-axis contribution**:
- **Axis I (your-harness hardening)**: 6-Type classification code + family_type schema land + dogfooding cadence
- **Axis II (public template sync)**: template family_type taxonomy + 8-step survey procedure + sealed family policy
- **Axis III (fleet central governance / back-propagation)**: fleet families rollout progress + SE-meta self-stop + revert window (phase-10 rollout pipeline stage 3 dispatcher)

**Inter-phase contract**:
- **Input** (consumes): phase-0~6 (your-harness full dogfooding verification) + phase-3 (family memory profile)
- **Output** (provides): family adoption decision + family JSON commit + family_type labeling → phase-8 GC cadence + phase-10 rollout schedule trigger

## 1. 6-Type Classification

Classified by repository artifact nature × failure risk × gate strictness axes.

| Type | Definition | Key Risk | Gate Strictness |
|---|---|---|---|
| **SE-meta** | Agent development tools (your-harness, template harness) | False sense of security | Destructively strict |
| **code_app** | Infrastructure/shared services / app codebase (home server, routing) | Spreads to all families | Very strict |
| **SE-product** | Product repositories targeting end users | Area-limited | Strict |
| **hybrid_pipeline** | Content/data pipeline (story, video, content, signals) | Fact/style | Medium |
| **content_app** | Personal/content-centric apps and workspaces | Privacy / context drift | Selectively strict |
| **template** | Public/sealed templates | Leakage when sanitization is absent | Very strict |

## 2. Inheritance Graph

```text
shared
  ├── SE-meta
  ├── code_app
  ├── SE-product
  ├── hybrid_pipeline
  ├── content_app
  └── template
```

`SE-meta` is the layer that controls itself, so it inherits strong gates at the `code_app` level and has additional stricter rules.

## 3. SE-Meta Self-Stop Condition

> If enforcement in an SE-meta family stops working on itself, halt the project.

- If a hook your-harness applied to itself stops working → stop; workarounds are prohibited
- Rules that cannot be applied to itself must not be imposed on other families
- 3 failures → force architectural redesign

This is the strongest cut line for SE-meta. Violation → return to Phase 0.

**R7-C-W3 clarification (enforcement status)**: The phrase "halt the project" in this §3 is currently **advisory**. `stop-failure-audit.sh` has no cumulative failure counter or automated project-halt code. Consistent with the self-admission in §11 "self-stop automation absent." Automation is blocked on ADR candidate 24 (`applications/example-harness/phase-7-application.md` step 7-6 dependency). Until then, all items in this condition are manually tracked by the user.

## 4. Dogfooding Priority

1. **Confirm own classification** — your-harness = SE-meta (confirmed)
2. **Design + apply SE-meta variant first**
3. **POC = complete 1 enforcement hook** (simultaneous 4-variant design prohibited)
4. **Dependency order**: shared → SE-meta → code_app → SE-product → hybrid_pipeline → content_app → template

### 4-1. Simultaneous vs Serial Rollout Conditions (R7-C-I2 new)

Selection criteria when rolling out to multiple families simultaneously vs serially.

| Condition | Decision | Reason |
|---|---|---|
| Same type (e.g., 2 code_app families) | **Simultaneous allowed** (conditional) — when fleet_observe advisory can observe 1 week apart | Same rules within type; low mutual impact |
| Between different types (e.g., code_app + hybrid_pipeline) | **Serial mandatory** | Strictness differential creates cross-family pollination risk |
| SE-meta body (your-harness) | Always **single serial** | self-stop obligation prohibits simultaneous changes with other families |
| Security patches (security-baseline.md 5 surfaces) | Simultaneous forced sync ([`applications/template-cherrypick.md`](applications/template-cherrypick.md) §6) | Prevent security gap exposure — type-agnostic |
| Family undergoing revert | Block other family rollout (serial) | Preemptively prevent revert reason from affecting other families |

Current §5 matrix's 10 `active` families are already in settled state as of R4 when this ledger was written. Apply this §4-1 when a new family (e.g., greenfield) enters.

## 5. Fleet Family Rollout Matrix

(2026-05-23 R8 single SoT unification)

This table cites 4 fields from `config/repos/*.json` (`family_type` (R8 P2 introduced), `repository_type`, `rollout_class`, `status`). If this table conflicts with the schema, schema is the SoT.

| Family | family_type (R8) | repository_type | rollout_class | status | External application |
|---|---|---|---|---|---|
| your-harness | SE-meta | meta_harness | immediate_migrate | active | self (dogfooding) |
| template-harness | SE-meta | template_transitional | partial_migrate | active | public sync |
| example-learning | SE-product | learning_workspace | immediate_migrate | sealed | **sealed — external push prohibited** |
| example-infra | code_app | infra_runtime | bootstrap_only | active | applied |
| example-service | code_app | infra_runtime | bootstrap_only | sealed | **sealed — external push prohibited** |
| example-notes | code_app | code_app | immediate_migrate | active | applied |
| example-game | code_app | code_app | skip_migrate_codex_active | active | applied |
| example-app | code_app | code_app | partial_migrate | active | applied |
| example-brand | code_app | code_app | bootstrap_only | active | applied (greenfield) |
| example-content | hybrid_pipeline | hybrid_pipeline | partial_migrate | active | applied |
| example-story | hybrid_pipeline | content_workspace | skip_migrate_codex_active | needs_work | port incomplete |
| example-video | hybrid_pipeline | hybrid_pipeline | partial_migrate | active | applied |
| example-stock | hybrid_pipeline | hybrid_pipeline | partial_migrate | active (config) | **sealed — external push prohibited** (ops policy) |
| example-personal | SE-product | content_workspace | skip_migrate_codex_active | active | applied |

**R8 corrections (R7-C/A/D BLOCKER resolution)**:
- Prior table used classification categories ("platform" / "content_pipeline" / "personal_context" / "code_app") in `rollout_class` column — ghost values not in schema enum. True `rollout_class` has 5 kinds: `bootstrap_only` / `partial_migrate` / `immediate_migrate` / `skip_migrate_codex_active` / `supersede`.
- This R8 separates `repository_type` + `rollout_class` into 2 columns and records measured values for all active families.
- New "External application" column added — explicitly marks sealed families where external push is prohibited.

**`example-story` `skip_migrate_codex_active` + `codex-final-reviewer` in active_agents (Slice C WARN resolution)**: `rollout_class: skip_migrate_codex_active` means Codex execution lane (code writing) is not applied. `codex-final-reviewer` is a read-only review lane so it can remain active. When called during the content review stage of a hybrid_pipeline family, no code changes occur. This ambiguity requires operational clarification — schema is consistent.

## 6. Adoption Procedure

Procedure for accepting 1 new family.

1. **survey** — investigate current family's code, rules, memory (use `tools/fleet_observe/`)
2. **classify** — decide one of §1 6-Types
3. **profile** — write `config/repos/<name>.json` (rollout_class, claude_role, codex_role, review_scope, tdd_scope)
4. **bootstrap** — `bootstrap.py registry_entry` auto-estimate + user confirmation
5. **dry-run** — `scripts/verify_repo_agent_management.py` advisory pass
6. **migrate** — apply actual hooks/rules (decision values from Phase 2~3)
7. **observe** — 1-week fleet_observe advisory observation
8. **gate** — same as your-harness self-stop; per-family cut line check

## 7. Strictness Differential

Adjust rule intensity per family type for each phase.

| Phase Rule | SE-meta | code_app | SE-product | hybrid_pipeline | content_app |
|---|---|---|---|---|---|
| pre-edit hook (code path) | enforced | enforced | enforced | warn | off |
| TDD ledger | enforced | enforced | warn | off | off |
| pre-commit lint/test | enforced | enforced | enforced | warn | off |
| Worker Isolation | enforced | enforced | warn | warn | off |
| sliding window | enforced | enforced | enforced | enforced | enforced |
| `/compact` cadence | enforced | enforced | enforced | enforced | enforced |

hybrid_pipeline and content_app have weak code enforcement, but memory/context enforcement is identical.

**R4 terminology update**: Changed "strict" in this table to `enforced`. Consistent with exceptions.md §3 matrix. `doc-strict` is Phase 0 only (no corresponding row in this §7; handled in exceptions.md §3 matrix).

## 8. Cross-pollination

Cross-family asset sharing catalog.

- Common skills → global `~/.claude/skills/` (Karpathy pattern)
- Common agents → `config/repo-agent-management.json` external agents
- Family-specific add_specialists / skill_overrides → each family JSON
- On change, fleet_observe checks catalog consistency

[[phase-8-garbage-collection]] detects unused cross-pollinated assets.

## 9. Public Template Sync

Synchronization with `template-harness` (public template).

- User-initiated only (automatic sync prohibited)
- Sanitization mandatory: Korean → English, family-specific → generic expressions, LICENSE unedit
- `scripts/verify_codex_sync.py` verification
- Dry-run with template-sync-validator subagent

## 10. Prohibitions

- Simultaneous 4-variant design
- SE-meta self-stop avoidance
- Accepting new family without classification
- Copy-pasting only hooks without profile
- Imposing own SoT on external families

## 11. Application State

| Item | Status | Location |
|---|---|---|
| 6-Type classification | land | `family_type` schema + all active families config populated |
| Inheritance graph | **not implemented** | flat catalog only |
| SE-meta self-stop | partial land (R31 consistency reflected) | `enabled_phases` consuming verifier + `verify_self_stop.py` advisory path landed; stronger halt enforcement is follow-up |
| Dogfooding priority | land | your-harness applied first |
| Fleet family rollout | land | `config/repos/*.json` |
| 8-step adoption procedure | land | survey / classify / migrate / observe |
| Strictness differential | partial land | hooks settings in each family JSON |
| Cross-pollination | land | external agents/skills catalog |
| Public template sync | land | template-harness in operation |

**Gap**: Inheritance graph introduction + stronger self-stop enforcement + 1 new family `1-week no-warning` measurement.

## 12. Exit Criterion

SE-meta dogfooding passed once (all Phase 0~6 decision values applied to your-harness with no self-stop condition violations). 1 new family adoption 8-step completed + fleet_observe advisory 1-week no-warning.

## 13. Next Steps

Proceed to [Phase 8 — Garbage Collection](phase-8-garbage-collection.md).
