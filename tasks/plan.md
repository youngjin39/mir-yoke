# Plan

## Active task: 0.13.5 release preparation (2026-10-18)

Intent authority: current Mir Harness Main writer brief, owner Discord 1561054690681032776
(2026-10-18) and directive `ontology-engineering-settlement-2026-10-17`, parent-supplied.
This single active cursor is the bounded design authority for commit A content preparation.
Release the ontology handoff-packet change `f25e508`; mirror preparation commit `8a9fa95`.
Previous cursor: `tasks/change_log.md#superseded-cursor-before-0135-release-preparation-2026-10-18`.

Bounded design: align the same release/version surfaces, move only the handoff note into
v0.13.5, follow the migration-entry pattern, refresh the lifecycle acknowledgement from a
cache-free copy, regenerate adopter payload after final records, and generate Codex derivatives
in external scratch. Do not write repository `.codex/**` or `.mir/capability-lock.json`.
No commits, tags, pushes, publishing, activation, consumer writes or live database writes.
Existing package/release checks cover these metadata-only edits; no new logic tests are needed.

Request matrix: (1) version surfaces and acknowledgement, (2) changelog/migration,
(3) adopter generation and scratch Codex parity, (4) required verification with only the
repository lock failure expected until B, (5) records and Main handoff.
Completion: 5/5 evaluated, 4/5 closed. Full pytest: 2092 passed, 1 expected lock failure
until B. Ruff, scratch Codex generation/parity, context paths, public surface and focused
release/package checks passed. Final records are included in regenerated adopter hashes.
Evidence: `tasks/change_log.md#0135-release-preparation-2026-10-18`.

Main remaining: review/regenerate repository derivatives, commit A, bind the lock in separate
commit B, verify the final lock and full gate, tag/push/publish, capability update/attest/finalize.
