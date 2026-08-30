# Plan

## Current status — ADR-86 CLOSED (2026-08-30)

- [x] Designate Mir Harness as Mir Yoke's repository-maintenance manager in ADR-86 and root policy.
- [x] Track the portable maintainer Profile and remove `.mir/capability-lock.json` from its
  protected paths without changing adopter-generated Profile protection.
- [x] Set the maintainer registry to `harness-managed` while preserving non-runtime and consumer
  non-authority contracts.
- [x] Regenerate derivatives and adopter payload; pass the full 803-test suite.

Scope is Mir Yoke maintenance governance only. This instruction authorizes the scoped commit and
`origin/main` push; tags, releases, and consumer-repository changes remain unauthorized.

No active implementation action remains.

## Deferred owner work

When the owner supplies a target, run the published prompt once with Claude and once with Codex in
separate empty repositories. This is post-release acceptance, not an open repository task or a
`v0.9.0` claim.
