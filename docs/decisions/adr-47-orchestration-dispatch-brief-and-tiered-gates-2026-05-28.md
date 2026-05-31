# ADR-47 — Orchestration DispatchBrief and Tiered Gates

## Decision

The public template adopts the DispatchBrief pattern and tiny/normal/heavy task triage as the default orchestration baseline for development-changing work.

- Main-agent design and orchestration happen before delegated execution starts.
- Delegated, restartable, or 3+ step execution should persist a DispatchBrief or equivalent handoff artifact.
- Gate strictness depends on task weight:
  - `tiny`: minimal overhead, explicit verification still required
  - `normal`: bounded slices preferred
  - `heavy`: explicit phases or bounded slices required

## Why

This keeps the template aligned with the current Mir orchestration baseline while remaining public-template safe.

## Consequence

Template consumers inherit:
- design-first orchestration
- persisted execution handoff for heavier work
- tiered gate wording that does not depend on whether Claude or Codex opened the session
