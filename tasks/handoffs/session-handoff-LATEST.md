# Session Handoff — ADR-85 Agent Contract Publication Complete

- Date: 2026-08-30
- Status: implementation commit `3018f5c` is protected-lock bound and fully verified; final state is
  prepared for the authorized `origin/main` push.
- Branch: local and remote `main` only. The candidate was based on synchronized commit `e65be8e`.

## Completed Work

- Replaced the remaining host-specific reviewer and pipeline-validator dispatch contracts with
  ADR-85 runtime-neutral wording and regenerated their Codex mirrors.
- Required exact comma-delimited `Write` and `Edit` tokens for generated read-only sandboxes.
- Added batch fail-closed validation for patterned `name` and `disallowedTools` metadata before
  any derivative output is created or replaced; invalid later sources cannot leave partial TOMLs.
- Expanded regressions for valid quoted/reversed/extra-token forms, invalid metadata, near matches,
  stale contracts, and preserved output on failure.
- Made TDD E2E evidence run the exact adopter-payload comparison and refreshed the payload.
- Bound `.mir/capability-lock.json` to implementation commit `3018f5c` and passed the full suite.

## Current Decisions

- Claude model frontmatter remains unchanged; generated Codex agents stay dynamically routed.
- The protected capability lock must bind a committed Git object. It is not updated from an
  uncommitted worktree.
- No tag, release, consumer mutation, or external rollout is part of this maintenance change.

## Unresolved Issues and Next Actions

1. No repository-side blocker remains after the final state commit and authorized push.
2. Owner-run Claude/Codex empty-target acceptance and real sqlite-vec acceptance remain optional and
   unevaluated; run them only with an explicit target or suitable environment.

## Verification Results

- Full suite with the protected lock: `803 passed`.
- Final generator and exact-payload focused suite: `10 passed`.
- Generated parity, 692/692 asset classification, adopter-payload equality, Ruff, Bash syntax, JSON,
  and `git diff --check`: passed.
- Independent post-fix review: `READY`, blocking findings = 0.
- Capability lock SHA-256 is
  `1c980f2ab5ed64f3188688261b510ec39c2681d2817bbb4391549c9512acdf35`.

## Risks and Manual Boundaries

- The lock binds committed bytes rather than uncommitted worktree content.
- The authorized protected lock changed; no secret, consumer repository, tag, or release changed.

<!-- mir:runtime-snapshot:begin -->
## Runtime Snapshot (Generated)

### Active Plan Items
- No open plan items.

### Working Tree
- Working tree clean.
<!-- mir:runtime-snapshot:end -->
