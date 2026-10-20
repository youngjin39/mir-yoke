# Plan

## Active task: 0.13.10 release preparation (2026-10-20)

Intent authority: owner Discord 1562070585855447051, 2026-10-20, approved for
release (parent-supplied by Mir Harness Main). This cursor owns the bounded design.
Qualified target: mir-yoke:release-0.13.10; root: this checkout; verified base HEAD
48219720496a2f827c1c92e579e6aa19463679ca. Mirror preparation commit 3c79805 and its
0.13.9 evidence for release change 4821972. No new behavior.

Request matrix: (1) package/plugin metadata and existing version assertions;
(2) dated changelog and patch migration note; (3) lifecycle-hooks digest
acknowledgement if required; (4) verbatim cursor archive and evidence;
(5) final adopter payload and required verification. Status: 5/5 preparation cells checked
with the explicitly accepted Main-owned lock-binding exception.
Design: fail-first using the existing version assertions, bump metadata, refresh
the affected digest, run focused/full checks, finalize records, then regenerate
adopter payload as the final artifact mutation. Follow with read-only checks.
No separate TDD ledger mutation is needed for this metadata-only preparation,
matching 3c79805. Full-suite lock-binding failure is explicitly accepted.

Semantic evidence: .mir/ontology-map.json#/contract declares
mir.common-semantics@1.1.0; /concepts/Task identifies this cursor. Verified map SHA256:
516c5b160c0fa49de51e4a0dc6f14c6e6a955d1baf72cc75dc2c93de7ea23e79.
Contract source: plugins/mir-core/skills/ontology/references/common-contract.json,
SHA256 b2f1ecd01aaa88d41caac2bc2481e7f4c5a429cff3983aaa85ddfb0fc2f1b93f.

Authority: only requested checkout edits and authorized local checks. No commit,
tag, push, network, capability commands, capability-lock, .codex/**, other
repositories, Memory Keeper or handoff writes. Preserve the existing handoff diff.
Main owns lock binding and delivery; final release/tag/provider pins remain unknown.
Lifecycle: prepared; temporal: current working tree; epistemic: verified-in-repo;
verification: checked with the authorized lock-binding exception. Approval is
parent-supplied; local file and check results are directly observed on 2026-10-20.
Self-check: all required handoff fields and current source/map/contract pins are
present; final delivery pins and post-bind verification remain unknown.
Previous cursor: tasks/change_log.md#superseded-cursor-before-01310-release-preparation-2026-10-20.
Evidence: tasks/change_log.md#01310-release-preparation-2026-10-20.

Acceptance evidence: fail-first package module 2 failed, 13 passed in 0.16s;
after bump 15 passed in 0.13s. Offline full suite: 2146 passed, 1 failed in
243.33s, solely test_repository_lock_is_portable_and_matches_managed_trees.
Isolated installed-CLI test: 1 passed in 2.99s using 45 locally repacked cached
wheels, without downloads. Ruff and diff checks passed; ontology mapping:
0 errors/0 warnings; strict impact: no stale refs. Prior cursor archive matches
HEAD:tasks/plan.md verbatim; the 19 preparation files match 3c79805's file set.
These records precede final adopter regeneration and read-only payload/surface,
Ruff and diff checks. Full-suite green and delivery remain pending Main's work.
