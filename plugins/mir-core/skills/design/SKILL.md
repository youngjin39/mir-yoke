---
name: design
description: "Proportional design guidance (brainstorming, planning, design analysis, design review, multi-role pipeline). Tiny bounded work may proceed directly.\n\nTrigger: design, brainstorming, plan, implementation plan, architecture, audit design, develop from design, role-split, interview, grill me, stress-test a plan\n\nAbsorbs: brainstorming, writing-plans, analyze-design, audit-design-fit, develop-from-design, role-split-pipeline, deep-interview"
---

# Design

Architecture precedence: existing, as-built architecture analysis → bluebricks; unresolved architecture choices and new design → design.

## Use When
- Before consequential or ambiguous architecture work.
- When requirements are ambiguous or multiple approaches exist.
- When a plan or implementation steps are needed.
- When unresolved architecture choices or a new design need audit or analysis.
- When a multi-role pipeline review is required.
- When harness, ADR, template, fleet, policy, or generated-surface work contains a material choice or broad rollout boundary.
- When a material decision exists. A known tiny or bounded development change may proceed directly.

## Absorbed legacy skills
- brainstorming — Resolve uncertainty before consequential coding.
- writing-plans — Concrete implementation plan. Bite-sized steps.
- analyze-design — Analyze and iterate design across sub-agents.
- audit-design-fit — Audit design fit against original purpose.
- develop-from-design — Design-driven harness development loop.
- role-split-pipeline — role-separated stages: design → independent review → delegated execution → independent evaluation, using whatever agents the host provides.
- deep-interview — Requirements clarification. Ambiguity gating.

## Workflow

When installed, follow the method order in the `mir-lifecycle-hooks:runtime-continuity` skill's `references/default-work-method.md`, applying each step proportionally. If `mir-lifecycle-hooks` is not installed, follow the repository's own documented method, or else the order in this skill.

When identity, relation or status meaning affects the task, apply `mir-core:ontology` using the project-owned mapping.
1. Identify which absorbed legacy intent applies (design vs. plan vs. interview etc.).
2. Understand the real flow and stop at the first sufficient Ponytail rung: remove unnecessary work, reuse project code, use built-ins, justify a dependency, and write minimum custom code last.
3. Use only the design, parallel analysis, or independent review needed to resolve consequential uncertainty.
4. For a persisted harness design, include only relevant fields:
   - phase ownership / rollout binding
   - source-of-truth edit surfaces
   - generated-surface regeneration and verifier path
   - verification gate
   - evidence sink
   - template/fleet claim boundary when public or cross-repo wording is involved
5. If a bounded task has an obvious verification path, skip the separate design artifact and execute directly.

## Intent Extraction

An advisory design-skill discipline (no runtime hook): extract the user's real intent before designing.

1. **Materials** — Treat inputs as material, not ground truth. Classify each as `confirmed`, `derived`, `observed`, `assumed`, `conflict`, `open`, or `tunable` before it informs the design.
2. **Decision Surface** — Internally enumerate load-bearing decisions across `goal_boundary`, `actors`, `data_state`, `behavior`, `safety_policy`, `compatibility_ops`, and `verification`. Each carries a state of `confirmed`, `derived`, `assumed`, `open`, `conflict`, or `tunable`. Surface only genuinely open, high-cost decisions.
   For an owner-invoked grill or frontier interview, override the high-cost filter and tuning defaults: ask every unresolved human decision, derive facts first, and leave nothing load-bearing silently assumed.
3. **Grill-style elicit** — Ask only open, high-cost questions, giving options, a recommendation, and rationale. Never re-ask answered items or code-verifiable facts. Ask domain policy; propose technical choices; default tuning choices and mark them tunable. In remote channels, use numbered text lists rather than interactive pickers.
4. **Authority separation** — Code is reality-material, not intent-authority. Keep spec-versus-code disagreement explicit until resolved; memory and prior decisions provide context but do not automatically override the current request.

5. **Freeze exit** — Before a design or spec is frozen, no load-bearing decision remains `assumed`. Resolve from available evidence first; ask the owner about open domain and policy decisions, present technical decisions with a recommendation, and mark tuning values `tunable`. Close assumptions under the existing high-cost-question rule; do not turn settled decisions into extra questions.

Second-pass reinforcements (dryforge; central directive 2026-07-25):

- **Derive-first elicit** — Before surfacing any question, first attempt to derive the answer from stated goals, constraints, and code facts; ask only when a specific unresolved decision remains. Question count is not a quality metric.
- **Proposal-as-material** — A user-proposed solution is material serving the stated intent, not automatic specification authority. Confirm the underlying intent and surface a simpler path when one satisfies it; the user's explicit trade-off decision remains binding once made.
- **Specification-over-plan precedence** — The specification (design behavior, constraints, invariants) defines the result; the plan describes how to reach it. When they disagree, the specification governs and the conflict is surfaced, never silently resolved.
- **Non-reconstructible intent** — Handoffs record authority boundaries and intent that a future executor must not re-derive from implementation evidence.

For existing-code onboarding, run a migration interview. Close each policy or behavior item as `code_confirmed`, `user_confirmed`, `derived`, `not_applicable` with a reason, `unresolved`, or `conflict`. Never close `unresolved` or `conflict` by inference. Apply [migration policy confirmation](references/migration-policy-confirmation.md) to separate implementation evidence from owner intent and elicit missing rules.

Apply by triage: **Tiny** skips full extraction (goal, targets, verification, non-goals only); **Normal** classifies materials, enumerates the Decision Surface, and elicits open decisions; **Heavy** adds the migration interview when existing code is involved plus an independent review.

When the repository provides a design schema, record structured output through its optional `materials`, `decision_surface`, `open_decisions`, `authority_notes`, and `migration_closure` fields.

## Status
This skill is the canonical design entry point. Use it proportionally rather than as a universal pre-code gate.

For consequential or owner-requested interviews, extend the existing elicitation rules with [frontier rounds](references/frontier-interview.md).

When Main authorizes independent intent review before specification freeze, use the advisory [pre-spec intent audit](references/pre-spec-intent-audit.md).

For a consequential choice, Main may use the advisory [decision mode](references/consequential-choice.md) even without a stall.

When an interview cannot proceed, use the [text-only degraded brief](references/interview-fallback.md).

For owner-requested product requirements, use the [product-focused PRD recipe](references/product-prd.md).

Inspired by fn-opt/dryforge at f5aa6d7.
