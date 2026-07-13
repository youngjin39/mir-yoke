---
name: design
description: "Proportional design guidance (brainstorming, planning, design analysis, design review, multi-role pipeline). Tiny bounded work may proceed directly.\n\nTrigger: design, brainstorming, plan, implementation plan, architecture, audit design, develop from design, role-split, interview\n\nAbsorbs: brainstorming, writing-plans, analyze-design, audit-design-fit, develop-from-design, role-split-pipeline, deep-interview"
---

# Design

## Use When
- Before consequential or ambiguous architecture work.
- When requirements are ambiguous or multiple approaches exist.
- When a plan or implementation steps are needed.
- When a design or architecture needs audit or analysis.
- When a multi-role pipeline review is required.
- When harness, ADR, template, fleet, policy, or generated-surface work contains a material choice or broad rollout boundary.
- When a material decision exists. A known tiny or bounded development change may proceed directly.

## Absorbed legacy skills
- brainstorming — Resolve uncertainty before consequential coding.
- writing-plans — Concrete implementation plan. Bite-sized steps.
- analyze-design — Analyze and iterate design across sub-agents.
- audit-design-fit — Audit design fit against original purpose.
- develop-from-design — Design-driven harness development loop.
- role-split-pipeline — Claude design → Codex review → executor dev → Codex eval 4-stage pipeline.
- deep-interview — Requirements clarification. Ambiguity gating.

## Workflow
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
3. **Grill-style elicit** — Ask only open, high-cost questions, giving options, a recommendation, and rationale. Never re-ask answered items or code-verifiable facts. Ask domain policy; propose technical choices; default tuning choices and mark them tunable. In remote channels, use numbered text lists rather than interactive pickers.
4. **Authority separation** — Code is reality-material, not intent-authority. Keep spec-versus-code disagreement explicit until resolved; memory and prior decisions provide context but do not automatically override the current request.

For existing-code onboarding, run a migration interview. Close each policy or behavior item as `code_confirmed`, `user_confirmed`, `derived`, `not_applicable` with a reason, `unresolved`, or `conflict`. Never close `unresolved` or `conflict` by inference.

Apply by triage: **Tiny** skips full extraction (goal, targets, verification, non-goals only); **Normal** classifies materials, enumerates the Decision Surface, and elicits open decisions; **Heavy** adds the migration interview when existing code is involved plus an independent review.

Record structured output through the optional `materials`, `decision_surface`, `open_decisions`, `authority_notes`, and `migration_closure` fields in `docs/templates/_schema/design_doc.schema.json`.

## Status
This skill is the canonical design entry point. Use it proportionally rather than as a universal pre-code gate.
