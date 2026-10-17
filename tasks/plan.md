# Plan

## Active task: 0.13.4 release preparation (2026-10-17)

Authority: owner Discord 1561020393568079954 (2026-10-17), via Mir Harness Main, and directive `ontology-engineering-settlement-2026-10-17` (parent-supplied). This cursor is the intent and bounded design authority for commit A content only. The release brief supersedes the previous no-version-change restriction. Previous cursor: `tasks/change_log.md#superseded-cursor-before-0134-release-preparation-2026-10-17`.

Mirror e20d6fa release surfaces at 0.13.4. Move only the ontology-reachability note from Unreleased, follow the migration-entry pattern, refresh the lifecycle acknowledgement from a cache-free copy, and regenerate the adopter payload. Generate Codex derivatives in external scratch; repository `.codex/**` writes remain Main-owned. No capability-lock changes, commits, tags, pushes, publishing or activation here.

Request matrix: (1) version surfaces and cache-free acknowledgement, (2) release and migration notes, (3) adopter generation and scratch Codex parity, (4) required verification with only the repository lock failure expected, (5) records and Main handoff. Existing release/package checks cover these metadata-only edits; no new implementation tests or tasks/tdd.json changes are needed.

Main remaining: review and regenerate repository Codex derivatives, commit A, bind `.mir/capability-lock.json` to A in separate commit B, then rerun the lock check and perform authorized tag, push, publish, capability update/attest/finalize.

Evidence: `tasks/change_log.md#0134-release-preparation-2026-10-17`. All five request-matrix cells were evaluated; 4/5 are closed. The full-gate cell remains open only for Main to bind the release lock in B. Full pytest: 2080 passed, 1 expected repository-lock failure in 240.27s. Ruff, scratch Codex generation/parity, context paths (77) and Korean-text checks (5) passed. Final record-dependent adopter hashes are regenerated and checked separately. No repository Codex files or capability lock were changed.
