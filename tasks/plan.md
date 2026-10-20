# Plan

## Active task: 0.13.11 release preparation (2026-10-21)

Intent authority: owner Discord 1562120317504061453, 2026-10-20, approved for
release (parent-supplied by Mir Harness Main). This cursor owns the bounded design.
Qualified target: mir-yoke:release-0.13.11 (patch), for release change 7d32416.
Root: this checkout; verified base HEAD 7d32416. Mirror preparation commit 43b60d5
and the 0.13.10 release preparation record for this release. No new behavior.

Request matrix: (1) package/plugin metadata and existing version assertions;
(2) dated changelog and matching patch migration note; (3) lifecycle-hooks digest
acknowledgement if required; (4) verbatim cursor archive and evidence; (5) final
adopter payload and requested verification. Status: 5/5 checked; the unchanged Main-owned lock is the only open verification item.
Design: fail-first on the existing version assertions, bump metadata, refresh the
affected digest if required, run focused/full checks, finalize records, then
regenerate adopter payload as the final artifact mutation. Follow with read-only
checks. No separate TDD ledger mutation is needed for this metadata-only preparation,
matching 43b60d5. The expected Main-owned lock-binding failure is accepted.

Semantic evidence: .mir/ontology-map.json#/contract declares
mir.common-semantics@1.1.0; /concepts/Task identifies this cursor. Verified map SHA256:
516c5b160c0fa49de51e4a0dc6f14c6e6a955d1baf72cc75dc2c93de7ea23e79.
Contract source: plugins/mir-core/skills/ontology/references/common-contract.json.

Authority: requested checkout edits and authorized local checks only. No commit,
tag, push, network, capability commands, capability-lock, .codex/**, other
repositories, Memory Keeper or handoff writes. Preserve the existing handoff diff.
Main owns lock binding and delivery; final release/tag/provider pins remain unknown.
Lifecycle: prepared for release; temporal: current working tree; epistemic: verified
locally; verification: checked with the explicitly accepted Main-owned lock exception. Approval is parent-supplied; local pins are observed.
Observation date: 2026-10-21. Previous cursor is archived verbatim in
 tasks/change_log.md#superseded-cursor-before-01311-release-preparation-2026-10-21.

Current evidence: fail-first package module had
2 expected version failures and 13 passes (0.17s); after metadata bump, 15 passed
(0.14s). Package plus lifecycle-hooks digest check: 16 passed (0.15s). The changed
hook tree digest required acknowledgement d4ebd7a654e73a40592dad4aef0ac55062ec3c3245b8d4e19c7525cc7e94a6b6.
Full suite before final payload regeneration: 4 failed, 2157 passed (248.34s).
Three failures are stale adopter payload checks expected to resolve after the requested
final regeneration; one is test_repository_lock_is_portable_and_matches_managed_trees,
whose Main-owned lock remains unchanged pending Main binding. Ruff passed. After final adopter regeneration, targeted adopter-payload modules plus lifecycle digest
and package tests passed: 34 passed in 11.18s. Ruff and git diff --check passed after
regeneration. The full suite is not claimed after regeneration; its only known remaining
failure is the explicitly accepted unchanged Main-owned lock-binding test.
