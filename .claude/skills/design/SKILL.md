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

## Status
This skill is the canonical entry point. Legacy slugs remain dispatchable until P15-I archive completes. Harness-structured design is the default for development-changing requests.
