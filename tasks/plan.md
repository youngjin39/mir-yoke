# Plan

## Current status — completed and published (2026-09-06)

- Authority: `tasks/intent.json` records the current Yoke purpose and management alignment. Parent
  Harness cursor `tasks/plan.md` run `harness-managed-central-provider-mandate-2026-09-06` is the
  overall design authority.
- [x] Preserve the published central capability implementation and its 987-test clean-candidate
  evidence at `0d5501fb765e7a829d3aec7ff64fa591f226f0d9`.
- [x] Record the superseding Yoke intent and preserve the previous cursor in the evidence archive.
- [x] Amend the current purpose/authority sources and maintain public-template distribution,
  supported-channel, and consumer-ownership boundaries.
- [x] Regenerate canonical derivatives and adopter payload after documentation stabilizes, then pass
  focused purpose, authority, adopter-boundary, asset, and parity verification: 52 tests passed;
  Codex derivative, asset classification, Ruff, and diff checks passed. The current and legacy
  Yoke contract titles both remain provider-identity markers. Log:
  `/tmp/mir-yoke-purpose-alignment-postdocs.log`.

Published implementation `f6d3f9a4949cfe19785d37ab952bf8f699d51802` has verified local/origin main parity.

## Current boundaries

- Retain the three role packages and one exact lifecycle package (14 skills total). Agents/commands remain separately delivered, and project policy/hooks/MCP remain target-owned.
- Source/config/path/digest/runtime checks remain fail-closed. Removed peer-required plugin names are a compatibility rejection, not an automatic migration.
- No live provider update/install, user trust change, capability-driven peer write, PR, workflow, tag or release was part of this repository repair.
- macOS remains the executed lane. WSL/native Windows and live model/hook execution are not claimed by these tests.

Before new work, compare `git rev-parse HEAD` with `git ls-remote origin refs/heads/main` and inspect the working tree.
