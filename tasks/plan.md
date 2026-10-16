# Plan

## Active task: ontology gap development (2026-10-16)

Authority: current owner brief; this single cursor records intent and design.
Preserve prior completed validation evidence in `tasks/change_log.md`.

Outcome: affected invariants select declared checks without execution (G04); the
capability manager supports fixture-only supplier/two-consumer distribution and
rollback (G05); E06/E08 claims match their actual producer/consumer scope.

- [x] Reproduce gaps with isolated fail-first tests and inspect E06/E08 boundaries.
- [x] Implement minimal selection and fixture interface changes; narrow map claims.
- [x] Run focused tests, mapping, strict impact, lint and public-surface checks.
- [x] Record files, commands/counts, canonical runner digest and Main follow-ups.

Limits: one writer; no commits, network, live databases, consumer writes or live
updater. Do not write generated `.codex/**`. Every pytest command deselects
`tests/test_harness_consistency.py`. Use external uv cache and fixture scratch.
Harness owns its separate rehearsal script; release and consumer sync stay with Main.

Implementation and bounded verification are complete. Expanded checks returned 462 passed
and one release-binding failure because the candidate mir-core tree differs from the
existing committed capability lock. Mapping/strict impact, lint, public surface and
read-only generated parity passed. The canonical consumer runner is unchanged.

Evidence and exact digests: `tasks/change_log.md#ontology-gap-development-2026-10-16`.
Main owns the separate rehearsal script, release/lock binding, consumer sync and full host
verification (including the excluded consistency test). No live updater or delivery ran.
