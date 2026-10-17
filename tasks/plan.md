# Plan

## Active task: 0.13.6 release preparation (2026-10-18)

Intent authority: current Mir Harness Main writer brief, owner Discord 1561086355767824457
and earlier delivery direction, parent-supplied. This single active cursor owns the bounded
preparation design; this writer is authorized for content only, without commit or delivery.
Release change `b42ec20`; mirror the 19-file preparation set and method of `5276401`.
Previous cursor: `tasks/change_log.md#superseded-cursor-before-0136-release-preparation-2026-10-18`.

Bounded design: align release versions and lifecycle-hooks acknowledgement, move only the
namespace-fence/Claude user-scope Fixed notes into v0.13.6 dated 2026-10-18, append migration
notes, and regenerate adopter payload after final records using the documented command.
Existing tests cover metadata edits; no new behavior or tests are needed. Use the existing
request matrix here instead of changing the unrelated historical tasks/tdd.json ledger.
No network, commit, tag, push, activation, consumer or live database write. Preserve
`.mir/capability-lock.json` and repository `.codex/**`; Main owns their later handling.

Request matrix: (1) version surfaces and acknowledgement, (2) changelog/migration,
(3) adopter payload parity, (4) full offline suite with only the deferred repository-lock
failure permitted, (5) canonical records and changed-file handoff.
Completion: 5/5 evaluated, 4/5 closed. Full offline suite: 2138 passed, 1 failed in 234.69s;
only `test_repository_lock_is_portable_and_matches_managed_trees` remains open until Main
binds the lock in commit B. Focused checks passed 30 tests; Ruff, Codex parity, context paths
and strict ontology impact passed. Final record hashes are regenerated into adopter payload
and checked exactly after this update. Main owns final repository derivatives, A/B commits,
lock/full-gate verification and subsequent delivery.
Evidence: `tasks/change_log.md#0136-release-preparation-2026-10-18`.
