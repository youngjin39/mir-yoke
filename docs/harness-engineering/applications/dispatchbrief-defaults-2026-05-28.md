---
title: DispatchBrief Defaults
created: 2026-05-28
status: applied
type: guide
---

# DispatchBrief Defaults

## Purpose

Keep the public template aligned with the source repo's deeper rollout baseline without forcing every clone into heavyweight planning for tiny maintenance work.

## Default Triage

- `tiny`: one bounded change with one obvious verifier; a formal phase or slice is optional.
- `normal`: multiple edits or one non-trivial code path; prefer a bounded slice and explicit verification plan.
- `heavy`: delegated, restartable, multi-session, or 3+ step work; require phases, handoff memory, and a persisted `DispatchBrief` or equivalent execution brief.

## DispatchBrief Default

- Prefer a persisted execution brief whenever work is delegated to Codex, resumed later, or likely to compact.
- The brief should at minimum capture user intent, expanded execution goal, owned scope, verification, and stop conditions.
- Tiny local maintenance may skip a formal brief when `CLAUDE.md`, `tasks/plan.md`, and the final verification command already make the ownership obvious.

## Template Boundary

- This template ships the policy as a baseline guide, not a family-specific runtime mandate.
- Active managed repositories may tighten the policy in their own `CLAUDE.md`, reports, or local runtime docs.
