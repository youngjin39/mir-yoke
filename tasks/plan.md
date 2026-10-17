# Plan

## Active task: repository maintenance re-verification (2026-10-17)

Authority: owner Discord 1560953913631318118 (2026-10-17), relayed by Mir Harness Main;
parent-supplied directive `tasks/directives/repo-maintenance-fleet-2026-10-17.md`
in Mir Harness. This cursor is the intent and bounded design authority.

Re-verify all 22 `mir-core:repo-maintenance` items against evidence observed now,
then make the smallest useful improvement. Prior verdicts are a baseline only.
Preserve accepted ADRs, owner decisions and unrelated work. No commit, delivery,
restart, secret read, consumer write, live DB write or generated `.codex/**` write.
Existing dirty `tasks/handoffs/session-handoff-LATEST.md` is excluded from edits.

### Bounded design and evaluation

Inspect declared surfaces, take a WAL-inclusive scratch snapshot for memory checks,
use synthetic hooks plus explicitly parent-supplied fresh-session evidence, and
record 22 dated matrix rows in `tasks/change_log.md#matrix-pass-2026-10-17`.
Use existing checks first; any behavior fix requires observed fail-first coverage.
Documentation-only continuity corrections need direct consistency checks.
Run the full pytest/Ruff gate, read-only parity checks and ontology mapping/impact.
Main owns forbidden generated writes, host-only probes and final acceptance/commit.

### Current acceptance

22/22 evaluated; 19/22 closed. Full pytest: 2064 passed, no failures.
Items 13, 19 and 21 need Main: curate the preserved dirty handoff and confirm
actual runtime/base-hook trust in fresh sessions. Current status projection:
`tasks/checklist.md`; sole evidence log: `tasks/change_log.md`; existing resume
pointer: `tasks/handoffs/session-handoff-LATEST.md` (preserved for Main).
D1 is contained in v0.13.3 by patch equivalence: both branch-only commits are
reported by git cherry with '-'; the branch itself is not an ancestor. No owner
choice remains. Current gate results and all 22 rows are in the evidence log.
Prior cursor, intent and checklist are preserved verbatim in
`tasks/change_log.md#superseded-continuity-before-matrix-pass-2026-10-17`.
