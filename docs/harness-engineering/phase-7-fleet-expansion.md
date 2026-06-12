---
phase: 7
title: Fleet Expansion
status: consolidated-v1
depends_on: [phase-0, phase-1, phase-2, phase-3, phase-4, phase-5, phase-6]
---

# Phase 7 -- Fleet Expansion & Classification

> **Purpose**: Dogfood with your own SE-meta harness first, then port sequentially to N families. Apply strictness differentially using the 6-Type classification.

## 0.5 Design Goals (R9 anchor)

**3-axis contribution**:
- **Axis I (self-harness hardening)**: 6-Type classification code + family_type schema + dogfooding cadence
- **Axis II (public template sync)**: template family_type taxonomy + 8-step porting procedure + sealed family policy
- **Axis III (fleet central management)**: N-family rollout progress + SE-meta self-stop + revert window (phase-10 rollout pipeline stage-3 dispatcher)

**Inter-phase contract**:
- **Input** (consumes): phase-0~6 (your-harness complete dogfooding verification) + phase-3 (family memory profile)
- **Output** (provides): family adoption decision + family JSON commit + family_type label -> phase-8 GC cadence + phase-10 rollout schedule trigger

## 1. 6-Type Classification

Classified on: artifact nature x failure risk x gate strictness.

| Type | Definition | Key Risk | Gate Strictness |
|---|---|---|---|
| **SE-meta** | Agent development tooling (your harness, starter template) | false sense of security | destructively strict |
| **code_app** | Infrastructure / shared services / application codebase | spreads to all families | very strict |
| **SE-product** | End-user-facing product-type repositories | scope-limited | strict |
| **hybrid_pipeline** | Content/Data Pipeline (stories, video, text, signals) | fact / style | moderate |
| **content_app** | Personal/content-centric apps and workspaces | privacy / context drift | selectively strict |
| **template** | Public/Sealed template repos | leakage if sanitize absent | very strict |

## 2. Inheritance Graph

```text
shared
  +-- SE-meta
  +-- code_app
  +-- SE-product
  +-- hybrid_pipeline
  +-- content_app
  +-- template
```

`SE-meta` controls itself, so it inherits `code_app`-level strong gates and adds stricter additional rules on top.

## 3. SE-Meta Self-Stop Condition

> If enforcement in an SE-meta family does not work against itself, stop the project.

- If the hook applied to your own harness does not fire -> stop; workarounds are prohibited
- Rules that cannot be applied to yourself must not be imposed on other families
- 3 failures -> forced structural redesign

This condition is the hardest cut line for SE-meta. Violation -> return to Phase 0.

**Clarification (enforced advisory)**: The "stop the project" statement in this section is currently **advisory**. Automatic `project-halt` code does not yet exist. Until automated, all items in this condition are manually tracked by the operator.

## 4. Dogfooding Priority

1. **Confirm own classification** -- your harness = SE-meta (confirm)
2. **Design + apply SE-meta variant first**
3. **POC = 1 enforcement hook complete** (simultaneous 4-variant design is prohibited)
4. **Dependency order**: shared -> SE-meta -> code_app -> SE-product -> hybrid_pipeline -> content_app -> template

### 4-1. Simultaneous vs Serial Rollout Criteria

For multi-family rollout, use these rules to decide concurrent vs serial:

| Condition | Decision | Reason |
|---|---|---|
| Same type (e.g., 2 code_app families) | **Concurrent allowed** (conditional) -- only if fleet_observe advisory can observe separately for 1 week | Identical type-level rules; low mutual impact |
| Different types (e.g., code_app + hybrid_pipeline) | **Serial mandatory** | Strictness differences create cross-family pollination risk |
| SE-meta harness itself | Always **single serial** | Self-stop obligation prohibits concurrent changes with other families |
| Security patch (security-baseline.md 5 surfaces) | Forced concurrent sync | Prevent security gap exposure -- type-independent |
| Family with revert in progress | Block other family rollouts (serial) | Pre-empt cross-family impact of the revert cause |

## 5. Fleet Rollout Matrix

The table below references 4 fields from `config/repos/*.json`: `family_type`, `repository_type`, `rollout_class`, `status`. If this table conflicts with the schema, the schema is the source of truth.

**Populate this table with your own fleet.** The example below shows one representative entry per family_type:

| Family (example) | family_type | repository_type | rollout_class | status | External apply |
|---|---|---|---|---|---|
| your-harness | SE-meta | meta_harness | immediate_migrate | active | self (dogfooding) |
| your-template | SE-meta | template_transitional | partial_migrate | active | public sync |
| example-infra | code_app | infra_runtime | bootstrap_only | active | applied |
| example-app | code_app | code_app | immediate_migrate | active | applied |
| example-pipeline | hybrid_pipeline | hybrid_pipeline | partial_migrate | active | applied |
| example-brand | content_app | code_app | bootstrap_only | active | greenfield (in progress) |

**Valid `rollout_class` values**: `bootstrap_only` / `partial_migrate` / `immediate_migrate` / `skip_migrate_codex_active` / `supersede`.

**Sealed families policy**: Some families may be designated sealed (no external git push). List sealed families by their config key, not by disk path. Sealed designation is separate from `status: sealed` in config (which means "no new active work"). Document the distinction in your fleet README.

**skip_migrate_codex_active with codex-final-reviewer**: A family with `rollout_class: skip_migrate_codex_active` means the Codex execution lane (code writing) is not applied. `codex-final-reviewer` is a read-only review lane and can still be active. No contradiction.

**bootstrap_only with full agent catalog**: In greenfield phase, the default catalog is inherited. Without `enabled_phases` set, agents are advisory only -- hooks do not fire. Enforced only after user explicitly opts in via `enabled_phases`.

## 6. Porting Procedure (8 steps)

Procedure for onboarding one new family.

1. **survey** -- investigate current family code, rules, and memory (use `tools/fleet_observe/`)
2. **classify** -- assign one of the 6 types in section 1
3. **profile** -- write `config/repos/<name>.json` (rollout_class, claude_role, codex_role, review_scope, tdd_scope)
4. **bootstrap** -- `bootstrap.py registry_entry` auto-estimate + operator confirmation
5. **dry-run** -- `scripts/verify_repo_agent_management.py` advisory pass
6. **migrate** -- apply actual hooks and rules (values from Phases 2-3)
7. **observe** -- 1-week fleet_observe advisory observation
8. **gate** -- check per-family cut line the same way as SE-meta self-stop

## 7. Strictness Differential

Phase rules adjusted by family type.

| Phase Rule | SE-meta | code_app | SE-product | hybrid_pipeline | content_app |
|---|---|---|---|---|---|
| pre-edit hook (code path) | enforced | enforced | enforced | warn | off |
| TDD ledger | enforced | enforced | warn | off | off |
| pre-commit lint/test | enforced | enforced | enforced | warn | off |
| Worker Isolation | enforced | enforced | warn | warn | off |
| sliding window | enforced | enforced | enforced | enforced | enforced |
| `/compact` cadence | enforced | enforced | enforced | enforced | enforced |

hybrid_pipeline and content_app have weak code enforcement but identical memory/context enforcement.

## 8. Cross-pollination

Cross-family asset sharing catalog.

- Shared skills -> global `~/.claude/skills/` (Karpathy pattern)
- Shared agents -> `config/repo-agent-management.json` external agents
- Family-specific add_specialists / skill_overrides -> per-family JSON
- On change, fleet_observe checks catalog consistency

[Phase 8 GC](phase-8-garbage-collection.md) detects unused cross-pollinated assets.

## 9. Public Template Sync

Sync with public template repos.

- User-initiated only (automatic sync prohibited)
- Sanitize required: Korean -> English, family-specific -> generic language, LICENSE unchanged
- `scripts/verify_codex_sync.py` verification
- template-sync-validator subagent dry-run

## 10. Prohibitions

- Simultaneous 4-variant design
- SE-meta self-stop evasion
- Accepting new family without classification
- Copy-pasting hooks without profile
- Imposing your own SoT on external families

## 11. Application Status

| Item | Status | Location |
|---|---|---|
| 6-Type classification | landed | `family_type` schema + family configs populated |
| Inheritance graph | not yet implemented | flat catalog only |
| SE-meta self-stop | partial | `enabled_phases` verifier + `verify_self_stop.py` advisory path landed; stronger halt enforcement pending |
| Dogfooding priority | landed | Self-harness prioritized |
| N-family rollout | landed | `config/repos/*.json` |
| 8-step porting procedure | landed | survey / classify / migrate / observe |
| Strictness differential | partial | Per-family JSON hooks settings |
| Cross-pollination | landed | external agents/skills catalog |
| Public template sync | landed | claude-codex-harness operations |

**Gaps**: Inheritance graph introduction + stronger self-stop enforcement + 1 new family "1-week advisory-clean" measurement.

## 12. Exit Criterion

SE-meta dogfooding 1 pass complete (all Phase 0-6 values applied to your harness with zero self-stop condition violations). 1 new family completes the 8-step porting procedure + fleet_observe advisory 1-week clean.

## 13. Next Step

[Phase 8 -- Garbage Collection](phase-8-garbage-collection.md)
