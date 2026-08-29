# Plan

## Current status — ACTIVE (2026-08-29)

- [x] Confirm global/project precedence and record the boundary in ADR-85.
- [x] Add failing regressions for project-policy inheritance, runtime-neutral agent contracts,
  source-driven read-only roles, Codex unpinned agents, and ADR classification.
- [x] Update canonical generation, agent, bootstrap-validation, and migration guidance sources.
- [x] Regenerate `AGENTS.md`, `.codex/`, and `.codex-sync/manifest.json; refresh the adopter payload
  after the final evidence record.
- [x] Run focused tests, derivative verification, repository governance checks, Ruff, Bash syntax,
  and independent design-vs-code review.
- [ ] Reconcile `.mir/capability-lock.json` after an authorized implementation commit, then rerun
  the lock regression.

Scope is Mir Yoke only. The current request authorizes the approved source and protected-lock
design, but it does not authorize a Git commit or push. The capability lock cannot truthfully bind
uncommitted agent bytes because its regression reads the selected Git commit object.

Do not tag, publish a release, or modify consumer repositories.

## Deferred owner work

When the owner supplies a target, run the published prompt once with Claude and once with Codex in
separate empty repositories. This is post-release acceptance, not an open repository task or a
`v0.9.0` claim.
