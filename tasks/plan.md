# Plan

## Active task: 0.13.1 release preparation (2026-10-16)

Authority: the current owner release brief recorded in `tasks/intent.json`.
This is the single active cursor and design record. Prior completed cursor details
remain in `tasks/change_log.md#superseded-cursor-ontology-gaps-before-0131-preparation-2026-10-16`.

Outcome: consistent 0.13.1 version metadata, focused release notes with the carried
Unreleased backlog preserved, consumer migration guidance and regenerated adopter hashes.
No implementation or common-contract version changes are authorized.

- [x] Compare HEAD checks and mirror the 06ca2f9 version surfaces.
- [x] Update release notes, migration guidance and lifecycle-hooks digest acknowledgement.
- [x] Generate adopter payload; run allowed full tests, lint, generated parity and ontology checks.
- [x] Record results and exact remaining Main delivery steps.

Limits: no commits, tags, pushes, publishing, capability update/attest/finalize,
consumer or user-runtime writes, live databases, memory/context synchronization,
or generated `.codex/**` writes. Exclude `tests/test_harness_consistency.py`.
Use the owner-specified external uv cache and external fixture scratch.
Main owns commit, lock binding, derivative regeneration if needed, tagging and delivery.

Preparation is complete; release delivery remains with Main. HEAD and the prepared tree
both returned 2,058 passed and one capability-lock binding failure. No new failure appeared.
Lint, generated parity, sanitization, links, schemas, mapping 0/0 and strict impact passed.
The Unreleased backlog is byte-identical to eb5aeaa and the 21-file change set matches 06ca2f9.
Evidence and remaining Main steps: `tasks/change_log.md#0131-release-preparation-2026-10-16`.
