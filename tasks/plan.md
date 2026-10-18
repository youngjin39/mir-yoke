# Plan

## Active task: 0.13.8 release preparation (2026-10-19)

Intent authority: owner Discord 1561401861251268689 item 3 (release Yoke 0.13.8),
parent-supplied by Mir Harness Main. This single active cursor owns the bounded design.
Verified release HEAD: 1297279307f7bbc854bef926c72898abcd77fc70.
Predecessor: preparation commit 94500c4 and its evidence in tasks/change_log.md.

Scope: mirror the predecessor's 19 files. No commit, tag, push, network, capability
command, capability-lock, consumer or repository .codex/** write. Main owns lock
binding, tag, push, provider update and attestation.

Design: bump package, lock, marketplace and all eight plugin manifest versions;
update existing version assertions; date the Unreleased note; add the patch migration
note; refresh the lifecycle-hooks digest acknowledgement; archive the superseded
cursor verbatim; record verification; regenerate adopter payload last. Existing
version assertions supply fail-first coverage. No behavior change is needed.
The historical TDD ledger is unchanged; this cursor and log own the release matrix.
Semantic evidence: .mir/ontology-map.json#/contract declares
mir.common-semantics@1.1.0; verified map SHA256 is
516c5b160c0fa49de51e4a0dc6f14c6e6a955d1baf72cc75dc2c93de7ea23e79.

Request matrix: (1) package/manifest/version-test parity; (2) changelog and migration;
(3) lifecycle digest acknowledgement; (4) cursor archive, evidence and final adopter
payload; (5) full pytest, Ruff and diff checks, with only the Main-owned repository
lock-binding failure accepted.
Status: 5/5 preparation cells complete, using the explicitly accepted Main-owned
lock-binding exception. Fail-first: 2 failed in 0.06s; package module: 15 passed in
0.14s. Initial offline full suite: 2 failed, 2138 passed in 232.99s; the additional
installed-CLI failure came from its empty isolated dependency cache. Repacked existing
cached dependencies into a temporary local wheel directory without downloads or test
changes; installed-CLI retry: 1 passed in 2.80s. Final offline full suite: 1 failed,
2139 passed in 241.75s. Only remaining failure:
test_repository_lock_is_portable_and_matches_managed_trees.
Ruff and diff checks passed; ontology mapping has 0 errors/0 warnings and strict
impact has no stale refs. Final records precede adopter payload regeneration.
Full-suite green remains pending Main's lock binding; delivery is not performed.

Evidence: tasks/change_log.md#0138-release-preparation-2026-10-19.
Previous cursor: tasks/change_log.md#superseded-cursor-before-0138-release-preparation-2026-10-19.
