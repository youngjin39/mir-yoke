---
status: consolidated-v1
date: 2026-05-22
source: 16 raw documents, ~213KB
audience: harness operators + future migrators
---

# Harness Engineering — Phase Consolidated Docs

## 1. Purpose

This directory compresses accumulated learning notes, external critiques, alternative designs, blueprints, and engineering references (~16 files, ~213KB) into **a single phase flow**. Original sources are preserved in the `참고 문서/` directory. This directory separates "decided" from "archived" items and provides the consolidated reference.

## 2. Reading Order

Each phase assumes the prior phase is complete. For a new family being onboarded, apply Phase 0 → Phase 8 sequentially.

| # | Phase | One-line definition | Entry condition |
|---|---|---|---|
| 0 | [Foundations](phase-0-foundations.md) | Philosophy · principles · terminology | (start) |
| 1 | [Start Harness](phase-1-start-harness.md) | Task classification · routing · 5-element declaration | Phase 0 agreement |
| 2 | [Enforcement](phase-2-enforcement.md) | hook/script/validator + strength levels | Phase 1 routing working |
| 3 | [Memory & Context](phase-3-memory-context.md) | SoT + selective injection + lifetime fields | Phase 1 read procedure established |
| 4 | [State Machine](phase-4-state-machine.md) | 13-state SM + 5 JSON schemas + retry budget | Phase 2 enforcement active |
| 5 | [Subagents](phase-5-subagents.md) | Worker Isolation + Claude+Codex 4-step | Phase 4 state tracking available |
| 6 | [Observability](phase-6-observability.md) | 8 metrics + autonomous reply loop | Phase 4 event logging |
| 7 | [Fleet Expansion](phase-7-fleet-expansion.md) | 6-Type classification + dogfooding + fleet families | Phase 0-6 self-harness verified |
| 8 | [Garbage Collection](phase-8-garbage-collection.md) | Unused detect + diet cadence | Phase 7 fleet stable |
| 9 | [Fleet Catalog](phase-9-fleet-catalog.md) | Family × phase-0..12 adoption matrix + drift + share catalog (non-forced, excluding phase-13 closure lane) | Phase 7 family_type labeled |
| 10 | [Rollout / Share Pipeline](phase-10-rollout-pipeline.md) | 3-stage your-harness→template→fleet (opt-in) + greenfield bootstrap | Phase 9 catalog + Phase 7 |
| 11 | [Back-Propagation](phase-11-back-propagation.md) | Family innovation → your-harness catalog → other families opt-in share (non-forced) | Phase 9 + Phase 10 |
| 12 | [Template Lifecycle](phase-12-template-lifecycle.md) | Template version-lag + upgrade migration + sunset / hand-off | Phase 9-11 + your-harness-roles.md |
| 13 | [Applied-State Closure](phase-13-applied-state-closure.md) | Public template applied-state verdict and catalog/snapshot/verifier truth-source closure | Phase 9-12 + example-harness ledger + ADR-39/42 |
| 14 | [Completion Consistency](phase-14-completion-consistency.md) | Stronger consistency closure between your-harness backlog and template completion claims | Phase 13 + example-harness ledger + template applied verdict |
| 15 (potential) | Security & Compliance (not yet created) | 5-surface integration + CWE pattern detection + audit trail | Phase separation decision pending — ADR candidate 32 |

### Supplementary — Harness Roles

- [`your-harness-roles.md`](mir-roles.md) — Dual-role (Role A Per-Family Tracker / Role B Template Maintainer) separation + identity disambiguation + SoT reconciliation rule.

**R9 update (2026-05-23)**: This consolidated doc expanded from 9 phases to 12 rollout phases. Three new phases (9 Fleet Catalog / 10 Rollout Share Pipeline / 11 Back-Propagation) are the core of **Axis III (Fleet Central Management)** — the three-axis fleet-wide application path.

**R30 update (2026-05-25)**: Added `phase-13` as a dedicated Applied-State Closure lane to resolve truth-alignment between the self-harness apply-state completion criteria and the public template applied-state verdict. The general family rollout target remains `phase-0..12`.

**R30 decision** (Applied-State Closure phase): The harness self-baseline has 0 `done` phases by ledger standards, while the public template has applied-state verdict conflicts between catalog rows and physical artifacts. Phase-13 binds these two completion criteria and measurement standards into a single closure lane.
- Self-harness goal: close `pending/partial` entries in the self ledger (`applications/example-harness/README.md` §2 ledger) to `done` or `blocked` with actual verification evidence
- Template goal: align the verdict from ADR-39 applied-state charter, ADR-42 verifier, catalog row, and physical template repo snapshot to a consistent standard
- External families are not direct rollout targets for this phase and are tracked as `n_a` in the catalog

**R31 update (2026-05-27)**: `phase-14` is not another rollout phase. After `phase-13` closes the template applied-state verdict in a truth-aligned state, `phase-14` checks that the stronger verdict remains non-conflicting with the actual self-harness backlog description. Total conceptual phases are now 15, but per-family rollout still only covers `phase-0..12`.

**R31 decision** (Completion Consistency phase): The template can now claim `applied` by verifier standards, but the self-harness backlog remains. Phase-14 does not force both into the same completion state; instead it manages two different meanings of "completion" claim so they coexist without contradiction in public docs and ledger.
- Self-harness goal: continue exposing self backlog and remaining work; prevent phase-13 completion from implying phase-0..12 completion
- Template goal: fix the claim boundary so the public template `applied` verdict is not read as a proxy metric for self-harness completion
- External families are not direct rollout targets for this phase; they only consume the closure outcome as an interpretation rule

**R7-C-I3 decision** (Security phase): The security domain is currently spread across 4 locations: phase-2 §3-4 (Prompt Injection), `applications/security-baseline.md` (5 surfaces), `cwe-auditor` agent, and memory-poisoning defense (phase-3). Phase separation is pending the following triggers:
- At least 1 measured security incident (currently 0)
- All external families complete rollout with diverse security surfaces
- Explicit user instruction

Until those triggers are met: Security phase creation deferred, current 4-location distributed operation maintained.

## 2-rollback. Phase failure rollback / incident path

This phase-0~8 body covers the "normal flow" only. When a phase fails or autonomous behavior causes an incident, follow these cross-reference paths:

| Situation | Primary path | Secondary path |
|---|---|---|
| Validation failure during phase application | [`applications/incident-response.md`](applications/incident-response.md) §2 4-phase Response | Record `blocked` in the phase's "Apply State" table + update [`applications/example-harness/README.md`](applications/example-harness/README.md) §2 ledger |
| Autonomous operation 6-trigger fires | [`applications/autonomous-execution.md`](applications/autonomous-execution.md) §6 triggers → user intervention | [`applications/incident-response.md`](applications/incident-response.md) DETECT pre-condition |
| Problem within 1 week after external family rollout | [`applications/exceptions.md`](applications/exceptions.md) §6 Revert procedure | example-harness ledger row `reverted` status code |
| Security surface 5-type fires | [`applications/security-baseline.md`](applications/security-baseline.md) | [`applications/incident-response.md`](applications/incident-response.md) §2 CONTAIN |
| General phase body rollback | [Phase 4 §7 interrupt atomicity 4 methods](phase-4-state-machine.md) (CANCELLING → ROLLBACK → INTERRUPTED) | git worktree recovery |

The phase body text does not contain "rollback / incident / revert" keywords; this §2-rollback is the single entry point.

## 2a. Feature-based quick entry

When feature-based entry is needed rather than phase-by-phase:

- **[`applications/feature-matrix.md`](applications/feature-matrix.md)** — 14 features × 9 phases integrated matrix + dependency graph + apply state + depth evaluation. Read this matrix first when "where to find what" is unclear.

## 3. Supporting materials

- [Appendix A — Original mapping · archived items · conflict resolution](appendix-a-sources.md): Tracks which of the 16 original documents was absorbed into which phase section, which ideas were archived, and how conflicting standards were resolved.
- [`applications/feature-matrix.md`](applications/feature-matrix.md) — 14-feature SoT mapping (see §2a above).

## 4. Document authoring principles

1. **Compression**: Do not repeat the same idea across multiple phases. Use cross-references (`[[phase-N#section]]`) only.
2. **Decisions only**: Remove archived and undecided items from the body; organize them in Appendix A.
3. **Apply state mapping**: Each phase ends with an "Apply State" table — already landed / partially landed / unimplemented gap.
4. **Enforcement-first**: Rules without a forcing mechanism must explicitly state that fact (mark as advisory).
5. **No external references**: Body is self-contained. External citations go only in Appendix A's source table.

## 5. Relationship to the main harness

- This directory is **a consolidated reference**. ADRs and actual operational decisions live in `docs/decisions/`.
- Phase definitions here do not map 1:1 to `tasks/phase.json` phase numbers. Phases here are **harness engineering conceptual stages**; `tasks/phase.json` phases are **implementation stages**. The two axes are mapped in [Appendix A §3](appendix-a-sources.md).
- `CLAUDE.md` / `AGENTS.md` is the source of truth. This document is supplementary context.

## 6. Update policy

- Update only when a new ADR changes a phase's decision values.
- When new source documents are added, update only Appendix A's mapping; changes to phase body require a separate decision.
- On update, add `date` to frontmatter and reason to this README §Change History.

## 7. Change history

- 2026-05-22: Initial consolidated doc created. 16 reference documents → 9 phases + 1 appendix.
- 2026-05-22 R1 (post codex-final-reviewer verification): Added archived item #9 UI/Workflow Layer, improved rewrite-classification mapping, added ADR candidates 12-14, fixed phase-1 §10 location error, removed phase-4 §6 retry_budget duplication, added Exit Criterion section to all 9 phases.
- 2026-05-23 R9 (Slice A~D cold-context audit 64 findings + user 3-axis goal refinement): (a) Slice B alignment fix — 9→13 state SM bulk replace (5 files), task_subtype enum split (phase-3 §8-1), autonomous-execution trigger 6 catalog alignment. (b) Added §0.5 "Design Goals" anchor to all 9 existing phases — 3 axes (Axis I self-harness / II template sync / III fleet share) + Inter-phase contract. (c) Added 3 new phases (9 Fleet Catalog / 10 Rollout Share Pipeline / 11 Back-Propagation) — reflecting user refinement "your-harness = central management, non-forced, opt-in share". (d) Strengthened `design` skill — `design_goals` 5-field capture mandatory (R9-T11). (e) Added `applications/design-process.md` §0 — design goal capture registered as harness engineering item → inherited by other agents via template.
- 2026-05-25 R30: Added new phase-13 `Applied-State Closure`. Purpose is to resolve SoT/cross-check conflicts between self-apply completion criteria and public template applied-state verdict in a separate closure lane.
- 2026-05-27 R31: Added new phase-14 `Completion Consistency`. Purpose is to fix completion claim boundary so the template `applied` claim and the self-harness backlog description do not imply the same meaning.
