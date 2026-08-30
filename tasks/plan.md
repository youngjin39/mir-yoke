# Plan

## Current status — CLOSED (2026-08-30)

- [x] Confirm global/project precedence and record the boundary in ADR-85.
- [x] Replace the remaining host-specific reviewer contracts with ADR-85 runtime-neutral wording.
  This wording supersedes the host-specific contract without changing Claude model pins.
- [x] Require exact comma-delimited `Write` and `Edit` tokens for generated read-only sandboxes.
- [x] Fail closed before agent generation when patterned frontmatter fields are invalid.
- [x] Add regressions for near-match tool names and stale contracts across all generated agents.
- [x] Regenerate `.codex/` and `.codex-sync/manifest.json`, refresh the adopter payload, and run
  focused and broad verification.
- [x] After authorization and an implementation commit, reconcile and retest the protected lock.

Scope is Mir Yoke only. The owner authorized the implementation commit, protected capability-lock
reconciliation, final state commit, and push to `origin/main`. Do not tag, publish a release, or
modify consumer repositories. The lock must bind the implementation commit object.

Implementation commit `3018f5c` is lock-bound and the full suite passes. No active repository action
remains after the final state commit and authorized `origin/main` push.

## Deferred owner work

When the owner supplies a target, run the published prompt once with Claude and once with Codex in
separate empty repositories. This is post-release acceptance, not an open repository task or a
`v0.9.0` claim.
