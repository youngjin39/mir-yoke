# Plan

## Active task: inline SessionStart handoff fields (2026-10-19)

Intent authority: owner Discord 1561401861251268689 item 3, relayed by Mir Harness
Main in a parent-supplied feature-only brief. This single cursor owns the design.
Main owns commit, release preparation, lock binding, tag, push and attestation.

Scope: mirror df9f720's eight files. Feature only; no version bump, release heading,
lock write, capability command, commit, tag, push, consumer or generated Codex write.

Design: inline all six fields from plugins/mir-core/skills/ontology/SKILL.md#Handoff,
including four status axes, current pins and a missing-field/pin self-check.
Preserve owner-authority wording; compress only the replacement clause to keep
stdout <800 bytes and handler <=1024 bytes. Match the reviewed-byte mirror and
refresh the digest acknowledgement. Archive the old cursor verbatim in the log.
Semantic evidence: .mir/ontology-map.json#/contract declares
mir.common-semantics@1.1.0; verified map SHA256 is
516c5b160c0fa49de51e4a0dc6f14c6e6a955d1baf72cc75dc2c93de7ea23e79.

Request matrix: (1) exact-output fail-first; (2) six fields, unchanged authority,
byte bounds, exact mirror and digest; (3) Unreleased note, archived cursor,
evidence and final adopter payload; (4) full pytest, Ruff and diff checks.
Status: 4/4 feature cells complete. Fail-first: 1 failed in 0.12s; package module:
15 passed in 0.15s. Full pytest: 1 failed, 2139 passed in 240.50s (0:04:00).
Only failure: test_repository_lock_is_portable_and_matches_managed_trees,
the explicitly accepted Main-owned lock binding. Ruff passed; diff check passed;
ontology mapping passed with 0 errors/0 warnings and strict impact has no stale refs.
Stdout is 799 bytes including newline; handler is 1014 bytes. Final payload is
regenerated after these records. Main retains release preparation and delivery.

Evidence: tasks/change_log.md#inline-sessionstart-handoff-fields-2026-10-19.
Previous cursor: tasks/change_log.md#superseded-cursor-before-inline-handoff-fields-2026-10-19.
