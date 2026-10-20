# Plan

## Active task: Mapping handoff pins (2026-10-20)

Intent authority: Mir Harness owner Discord 1562070585855447051, 2026-10-20,
approving the bounded experiment after fleet-reverify-2026-10-20 (parent-supplied).
This single active cursor is the design authority. Work only in this Yoke checkout;
base HEAD d67b9638d37c88705583ffdef34ce315ba7a0623. The previous cursor is archived
verbatim in tasks/change_log.md#superseded-cursor-before-mapping-handoff-pins-2026-10-20.

Design: extend only the mapping report with repository-relative mapping_path,
mapping_sha256, contract_id and contract_sha256 beside existing versions; hash the
loaded file bytes without shortening digests. Preserve existing fields, validation,
exit behavior and absent-file handling. Add one short Handoff sentence and an
Unreleased changelog entry. Tests precede implementation.

Request matrix: (1) JSON and text pins with byte-exact SHA-256 and explicit contract
selection; (2) missing files preserve IO exits and nullable pins; (3) one-sentence
skill guidance within budget; (4) cursor archive and changelog; (5) focused and full
pytest, Ruff, diff checks and required adopter inventory parity. Status: 5/5 checked;
the owner-accepted repository-lock mismatch remains deferred to release binding.

Semantic evidence: .mir/ontology-map.json#/contract identifies
mir.common-semantics@1.1.0; /concepts/Task identifies this cursor. Map SHA-256:
516c5b160c0fa49de51e4a0dc6f14c6e6a955d1baf72cc75dc2c93de7ea23e79.
Loaded source contract: plugins/mir-core/skills/ontology/references/common-contract.json,
SHA-256 b2f1ecd01aaa88d41caac2bc2481e7f4c5a429cff3983aaa85ddfb0fc2f1b93f
(verified-in-repo). Harness observed 8/8 incomplete handoff pins; evidence and
approval are parent-supplied. Cause and later agent behavior remain unknown.

Authority: edit only task-required checkout files and run owner-authorized checks;
refresh adopter payload last if public-surface tests require it. No commit, release,
version bump, lock, generated Codex, installed runtime, handoff, network, memory or
other-repository writes. Preserve the existing handoff modification.

Acceptance: fail-first 7 failed / 293 deselected; focused checks 324 passed;
full suite 2146 passed / 1 failed, solely the owner-accepted repository-lock test.
Ruff and diff checks passed. Final records precede the last adopter regeneration
and read-only inventory check. Evidence and commands:
tasks/change_log.md#mapping-handoff-pins-2026-10-20.
No agent-behavior improvement is established; Harness measures that separately.
