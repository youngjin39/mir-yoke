---
status: consolidated-v1
date: 2026-05-22
source: reference documents (16 raw documents, ~213KB)
audience: your-harness operators + future migrators
---

# Harness Engineering — Phase Consolidated Document

## 1. Purpose of This Document

Compress the accumulated learning notes, external critiques, GPT alternative designs, English master blueprint, classification rewrites, and numbered policy 9-parts (total 16 files, ~213KB) from the `reference documents/` directory into **a single phase flow**. Source files are not sunset — they remain in `reference documents/`. This directory is a consolidated document that separates "already decided" from "sunset (dead-storage)" items.

## 2. Reading Order (proceed sequentially)

Each phase assumes the completion of the previous phase. If introducing a new family, apply sequentially from Phase 0 → Phase 8.

| # | Phase | One-line definition | Entry Condition |
|---|---|---|---|
| 0 | [Foundations](phase-0-foundations.md) | Philosophy·principles·terminology fixed | (start) |
| 1 | [Start Harness](phase-1-start-harness.md) | Task classification·routing·5-element declaration | Phase 0 consensus |
| 2 | [Enforcement](phase-2-enforcement.md) | hook/script/validator + intensity levels | Phase 1 routing operational |
| 3 | [Memory & Context](phase-3-memory-context.md) | SoT + selective injection + lifetime fields | Phase 1 read procedure established |
| 4 | [State Machine](phase-4-state-machine.md) | 13-state SM + 5 JSON schemas + retry budget | Phase 2 enforcement active |
| 5 | [Subagents](phase-5-subagents.md) | Worker Isolation + Claude+Codex 4-step | Phase 4 state tracking possible |
| 6 | [Observability](phase-6-observability.md) | 8 metrics + autonomous reply loop | Phase 4 event logging |
| 7 | [Fleet Expansion](phase-7-fleet-expansion.md) | 6-Type classification + dogfooding + N families | Phase 0~6 self-harness verified |
| 8 | [Garbage Collection](phase-8-garbage-collection.md) | Unused detect + diet cadence | Phase 7 fleet stable |
| 9 (R9 newly added) | [Fleet Catalog](phase-9-fleet-catalog.md) | N family × phase-0..12 adoption matrix + drift + share catalog (enforcement: X, phase-13 closure lane excluded) | Phase 7 family_type labeling |
| 10 (R9 newly added) | [Rollout / Share Pipeline](phase-10-rollout-pipeline.md) | 3-stage your-harness→template→fleet (opt-in) + greenfield bootstrap | Phase 9 catalog + Phase 7 |
| 11 (R9 newly added) | [Back-Propagation](phase-11-back-propagation.md) | family innovation → your-harness catalog → other family autonomous share (enforcement: X) | Phase 9 + Phase 10 |
| 12 (R10 newly added) | [Template Lifecycle](phase-12-template-lifecycle.md) | template version-lag + upgrade migration + sunset / hand-off | Phase 9~11 + harness-roles.md |
| 13 (R30 newly added) | [Applied-State Closure](phase-13-applied-state-closure.md) | public template applied-state verdict and catalog/snapshot/verifier truth source closure | Phase 9~12 + example-harness ledger + ADR-39/42 |
| 14 (R31 newly added) | [Completion Consistency](phase-14-completion-consistency.md) | `your-harness` backlog and template completion claim stronger consistency closure | Phase 13 + example-harness ledger + template applied verdict |
| 15 (potential, R7-C-I3) | Security & Compliance (not yet created) | 5 surface integration + CWE pattern detection + audit trail | Phase separation obligation evaluation — ADR candidate 32 |

### Appendix — Harness Roles (R10 newly added)

- [`harness-roles.md`](mir-roles.md) — Dual-role (Role A Per-Family Tracker / Role B Template Maintainer) separation + identity disambiguation + SoT reconciliation rule.

**R9 update (2026-05-23)**: This consolidated document expanded from 9 phases → 12 rollout phases. R9's 3 newly added phases (9 Fleet Catalog / 10 Rollout Share Pipeline / 11 Back-Propagation) are the core of **Axis III (Fleet Central Management·Back-Propagation)** — the 3-axis goal fleet-wide application path. The `§0.5 "Design Goals"` anchor in all phases aligns with the [`design` skill](../../.claude/skills/design/SKILL.md) R9-T11 mandate.

**R30 update (2026-05-25)**: Rather than directly adding `phase-13` to the per-family rollout system, a separate closure lane was introduced for `your-harness`/template verdict truth-alignment. Therefore the total conceptual phases are 14, but the general family rollout target continues to be `phase-0..12`.

**R30 decision** (Applied-State Closure phase): `your-harness` is the self-baseline, but by ledger standards still has 0 `done` phases, and the public template `mir-yoke` has remaining applied-state verdict conflicts between catalog rows and physical artifacts. This R30 phase-13 bundles **the completion criteria and measurement criteria for both into a single closure lane**.
- `your-harness` side goal: close the self ledger (`applications/example-harness/README.md`) `pending/partial` to `done` or `blocked` honestly with actual verification evidence
- Template side goal: align the verdict for ADR-39 applied-state charter, ADR-42 verifier, catalog row, and physical template repo snapshot to the same standard
- External families are not direct rollout targets for this phase and are tracked as `n_a` in catalog

**R31 update (2026-05-27)**: `phase-14` is not another rollout phase. After `phase-13` closes the template applied-state verdict itself in a truth-aligned state, `phase-14` is a subsequent consistency lane that checks whether that stronger verdict is maintained without conflict with `your-harness`'s actual backlog description. Therefore the total conceptual phases became 15, but the per-family rollout system is still only `phase-0..12`.

**R31 decision** (Completion Consistency phase): The template can now claim `applied` by verifier standards, but the `your-harness` own backlog still remains. This R31 phase-14 does not forcibly put them in the same completion state, but manages so that the two different meanings of "completion" claims can coexist without contradiction in public documents and the ledger.
- `your-harness` side goal: continue exposing self backlog and remaining work, and prevent phase-13 completion from implying phase-0..12 completion
- Template side goal: fix claim boundary so the public template `applied` verdict is not read as a proxy metric for your-harness self-completion
- External families are not direct rollout targets for this phase, and only consume the closure outcome as an interpretation rule

**R7-C-I3 decision** (Security phase): The Security domain is currently distributed across 4 locations: phase-2 §3-4 (Prompt Injection) + applications/security-baseline.md (5 surfaces) + `cwe-auditor` agent + memory-poisoning defense (phase-3). This phase separation will be decided after the following triggers:
- 1+ security incident measured (currently 0)
- All external families completed rollout and security surface diversified (currently some families in rollout)
- Explicit user instruction

Until those triggers are met → Security phase creation on hold, continuing distributed operation across 4 locations.

## 2-rollback. Rollback / incident path on phase failure (R7-A-I1 newly added)

The main body of phase-0~8 covers only the "normal progress" flow. If a phase fails or autonomous behavior causes an incident, follow these cross-reference paths.

| Situation | Primary path | Secondary path |
|---|---|---|
| Verification failure during phase application | [`applications/incident-response.md`](applications/incident-response.md) §2 4-phase Response | Record `blocked` in the relevant phase's §"Application Status" table + update [`applications/example-harness/README.md`](applications/example-harness/README.md) §2 ledger |
| 6 triggers fire during autonomous operation (R8 reinforced) | [`applications/autonomous-execution.md`](applications/autonomous-execution.md) §6 6 triggers → user intervention | [`applications/incident-response.md`](applications/incident-response.md) DETECT pre-condition |
| Problems within 1 week of external family rollout | [`applications/exceptions.md`](applications/exceptions.md) §6 Revert procedure | example-harness ledger row `reverted` status code |
| 5 security surfaces fire | [`applications/security-baseline.md`](applications/security-baseline.md) | [`applications/incident-response.md`](applications/incident-response.md) §2 CONTAIN |
| General phase rollback | [Phase 4 §7 interrupt atomicity 4 means](phase-4-state-machine.md) (CANCELLING → ROLLBACK → INTERRUPTED) | git worktree recovery |

The keywords "rollback / incident / revert" are not recorded in the phase body, but this §2-rollback is the single entry point.

## 2a. Feature-based fast entry (R6 newly added)

When **feature-based** entry is needed rather than phase-based:

- **[`applications/feature-matrix.md`](applications/feature-matrix.md)** — User 14 features × 9 phase integrated matrix + dependency graph + land status + depth evaluation. If "where to find what" is unclear, read this matrix first.

## 3. Supporting Materials

- [Appendix A — Source Mapping·Sunset Items·Conflict Resolution](appendix-a-sources.md): Track which section of each conceptual phase the original 16 documents were absorbed into, what ideas were sunset, and how conflicting criteria were resolved.
- [`applications/feature-matrix.md`](applications/feature-matrix.md) — 14 feature SoT mapping (see §2a above).

## 4. Document Writing Principles

1. **Compression**: Don't repeat the same idea across multiple phases. Only place cross-references (`[[phase-N#section]]`).
2. **Decision values only**: Exclude sunset and pending items from the body and organize them in Appendix A.
3. **Current state mapping**: At the end of each phase, an "Application Status" table — already landed / partial land / unimplemented gaps.
4. **Enforcement-first**: Rules without enforcement mechanisms must explicitly state that fact (mark as advisory).
5. **Block external references**: The body is self-contained. External video/blog citations are only in the source table of Appendix A.

## 5. Relationship with the Harness Codebase

- This directory is a **consolidated reference**. ADRs / actual operational decisions are placed in `docs/decisions/`.
- Phase definitions do not correspond 1:1 to the phase numbers in `tasks/phase.json`. The phases in this document are **harness engineering conceptual stages**, and P0-F~P14 in `tasks/phase.json` are **harness implementation stages**. The two axes are mapped in [Appendix A §3](appendix-a-sources.md).
- `.mir/repo-profile.toml` owns detailed boundaries and `CLAUDE.md` owns shared startup
  invariants. `AGENTS.md` is generated; this directory is supplementary context.

## 6. Update Policy

- Update only when a new ADR changes the decision values in this phase.
- If source `reference documents/` material is added, only update the mapping in Appendix A; phase body changes go through a separate decision process.
- When updating, add the date and reason to this README §Change History in the frontmatter.

## 7. Change History

- 2026-05-22: Initial consolidated document created. 16 reference documents → 9 phases + 1 appendix compressed.
- 2026-05-22 R1 (after codex-final-reviewer verification): Added UI/Workflow Layer sunset item #9, accurized rewrite-classification mapping, added ADR candidates 12~14, corrected phase-1 §10 location error, removed duplicate phase-4 §6 retry_budget, added Exit Criterion sections to all 9 phases.
- 2026-05-23 R9 (Slice A~D cold-context audit 64 findings + user 3-axis goal refinement): (a) Slice B consistency fix — 9→13 state SM bulk replace (5 files), task_subtype enum separation (phase-3 §8-1), autonomous-execution trigger 6 catalog consistency. (b) Added `§0.5 "Design Goals"` anchor to all 9 existing phases — 3 axes (Axis I self-harness / II template sync / III fleet share) + Inter-phase contract. (c) Added 3 new phases (9 Fleet Catalog / 10 Rollout Share Pipeline / 11 Back-Propagation) — reflecting user refinement "your-harness = central management, enforcement: X, opt-in share". (d) Enhanced `design` skill — mandatory capture of `design_goals` 5 fields (R9-T11). (e) Added `applications/design-process.md` §0 — design goals capture registered as harness engineering item → autonomously inherited by other agents through template.
- 2026-05-25 R30: Added new phase-13 `Applied-State Closure`. Purpose is to organize the completion criteria conflict between `your-harness` self-apply completion standard and public template applied-state verdict SoT/cross-check in a separate closure lane.
- 2026-05-27 R31: Added new phase-14 `Completion Consistency`. Purpose is to fix the subsequent consistency lane so that the template `applied` claim and the `your-harness` backlog description don't confuse different meanings of "completion".
