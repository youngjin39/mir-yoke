# Plan

## Current status — CLOSED (2026-08-29)

- [x] Audit the current Starter, Project Agent Kit, optional CLI, plugins, agents, skills, hooks,
  context retrieval, memory, embeddings, generated parity, governance, and release checks.
- [x] Record the bounded design in ADR-84 without expanding the three-layer product boundary.
- [x] Add the current harness-upgrade guide and correct product navigation and asset-class wording.
- [x] Correct current-only context, bounded active-fact retrieval, semantic history classification,
  explicit missing-vector backfill, and unsupported embedding dimension handling.
- [x] Normalize current Codex `apply_patch` hook input, keep project configuration from overriding
  operator permission profiles, remove deprecated generated keys, and add bounded Codex
  `SessionEnd` parity.
- [x] Bind vector writes and resumable backfill to one persisted encoder fingerprint; preserve fact
  subject/provenance and quarantine instruction-like or credential-shaped values.
- [x] Regenerate derivatives, run focused and full verification, complete independent review, and
  reconcile final repository state.
- [x] Commit the verified change to `main` and push it to `origin/main`.

Scope is Mir Yoke only. The owner authorized commit and push after verification. Do not edit the
protected capability lock, tag, publish a release, or modify consumer repositories.

No active repository implementation or publication action remains. The final clean-candidate
readiness gate passed with 797 tests and all static checks; local `main` and `origin/main` are
synchronized.

## Deferred owner work

When the owner supplies a target, run the published prompt once with Claude and once with Codex in
separate empty repositories. This is post-release acceptance, not an open repository task or a
`v0.9.0` claim.
