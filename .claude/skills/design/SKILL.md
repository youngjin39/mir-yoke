---
name: design
description: "Pre-coding design enforcement (brainstorming, planning, design analysis, design review, multi-role pipeline). Hard gate before code.\n\nTrigger: design, brainstorming, plan, implementation plan, architecture, audit design, develop from design, role-split, interview\n\nAbsorbs: brainstorming, writing-plans, analyze-design, audit-design-fit, develop-from-design, role-split-pipeline, deep-interview"
---

# Design

## Use When
- Before writing any new code or modifying existing architecture.
- When requirements are ambiguous or multiple approaches exist.
- When a plan or implementation steps are needed.
- When a design or architecture needs audit or analysis.
- When a multi-role pipeline review is required.
- When the request touches harness docs, phases, ADRs, skills, agents, template sync, fleet rollout/share, repo-wide policy, or generated surfaces.
- By default for development-changing requests, unless the task is truly docs-only or a trivial non-development action.

## Absorbed legacy skills
- brainstorming — Design enforcement. Hard gate before coding.
- writing-plans — Concrete implementation plan. Bite-sized steps.
- analyze-design — Analyze and iterate design across sub-agents.
- audit-design-fit — Audit design fit against original purpose.
- develop-from-design — Design-driven harness development loop.
- role-split-pipeline — Claude design → Codex review → executor dev → Codex eval 4-stage pipeline.
- deep-interview — Requirements clarification. Ambiguity gating.

## Workflow
1. Identify which absorbed legacy intent applies (design vs. plan vs. interview etc.).
2. Keep the harness structure by default: first-pass design, parallel analysis, integration, independent review, and revision.
3. For harness-structured design outputs, explicitly include:
   - phase ownership / rollout binding
   - source-of-truth edit surfaces
   - generated-surface regeneration and verifier path
   - verification gate
   - evidence sink
   - template/fleet claim boundary when public or cross-repo wording is involved
4. If the request is a bounded development task, a short design pass is still required; shorten the output, not the structure.

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
This skill is the canonical entry point. Legacy slugs remain dispatchable until P15-I archive completes. Harness-structured design is the default for development-changing requests.
