# Plan

## Active task: 0.13.7 release preparation (2026-10-18)

Intent authority: Mir Harness Main writer brief, continuation of owner Discord
1561203611252297729, parent-supplied. Prepare content for release change `df9f720`
by mirroring the file set and method of preparation commit `5f5574b`. Main owns
commit, lock binding, tag, push and attestation.

Design: update all version surfaces and pinned tests, move the `df9f720` Unreleased
note into a dated `v0.13.7` section, add the migration note, update lifecycle-hooks
acknowledgement only if its package bytes changed, then regenerate adopter payload last.
Preserve the previous cursor verbatim in `tasks/change_log.md`.

Boundaries: content only. No commit, tag, push, `mir capability` commands,
`.mir/capability-lock.json`, repository `.codex/**`, or private absolute paths in tracked
files. Do not set `MIR_CAPABILITY_HOME`; use the supplied UV cache setting. Keep scratch
only in the approved task scratch directory and remove it at task end.

Request matrix: (1) exact release version surfaces and 0.13.6 preparation parity,
(2) changelog and migration notes, (3) generated adopter payload parity,
(4) full `uv run pytest -q -p no:cacheprovider` with only the managed-lock test allowed
to fail, (5) Ruff and `git diff --check`, (6) changed-file and remaining-work report.
Status: 6/6 evaluated and closed. Version surfaces, release notes, package acknowledgement
and generated payload match. Full suite: 2138 passed, 1 expected managed-lock failure.
Ruff and `git diff --check` passed. The managed-lock binding remains Main-owned.
Evidence: tasks/change_log.md#0137-release-preparation-2026-10-18.

Previous cursor: tasks/change_log.md#superseded-cursor-before-0137-release-preparation-2026-10-18.
