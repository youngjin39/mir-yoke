# Plan

## Active task: 0.13.9 release preparation (2026-10-19)

Intent authority: owner Discord 1561414827409281077 (release the 32 KiB mapping
budget), parent-supplied by Mir Harness Main. This cursor owns the bounded design.
Follow preparation commit c1b6ba6 and its tasks/change_log.md evidence for release
change 10aaea9: bump package and plugin metadata, version assertions, changelog and
migration note; refresh the lifecycle-hooks digest acknowledgement; regenerate the
adopter payload as the final artifact mutation. Archive the prior cursor verbatim.

Request matrix: (1) version metadata and assertions; (2) dated changelog and patch
migration note; (3) digest acknowledgement; (4) cursor preservation and evidence;
(5) final adopter payload and required verification. Status: 5/5 preparation cells
checked with the explicitly accepted Main-owned lock-binding exception.
Use the existing release assertions for fail-first and the full suite for evaluation;
no new behavior, architecture or database migration is introduced. No TDD ledger
change is needed for this metadata-only preparation, matching c1b6ba6's scope.

Acceptance evidence: package fail-first 2 failed, 13 passed; after bump 15 passed.
Initial offline full suite: 5 failed, 2136 passed in 233.51s. After adopter payload
refresh and local cached dependency wheel provisioning, final offline full suite:
1 failed, 2140 passed in 229.00s. Only remaining failure:
test_repository_lock_is_portable_and_matches_managed_trees. Ruff and diff checks
passed; public-surface tests: 3 passed; ontology mapping: 0 errors/0 warnings;
strict impact: no stale refs. Final records precede final adopter regeneration and
read-only checks. Evidence: tasks/change_log.md#0139-release-preparation-2026-10-19.
Full-suite green and delivery remain pending Main's authorized release work.

Semantic evidence: .mir/ontology-map.json#/contract declares mir.common-semantics@1.1.0;
/concepts/Task maps this active cursor. Verified map SHA256:
516c5b160c0fa49de51e4a0dc6f14c6e6a955d1baf72cc75dc2c93de7ea23e79.
No contract-distribution change, DB migration, memory re-ingestion or automatic
consumer update. Network, commits, tags, pushes, mir capability commands,
capability-lock, .codex/** and consumer writes are forbidden. Main owns lock binding,
tag, push, provider update and attestation; consumer map checks remain outside this
preparation. Previous cursor: tasks/change_log.md#superseded-cursor-before-0139-release-preparation-2026-10-19.
