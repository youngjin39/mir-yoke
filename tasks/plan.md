# Plan

## Active task: Covered-label fix (2026-10-16)

Authority: the current owner request recorded in `tasks/intent.json`; this is the single
active cursor and design record. Prior cursor details are preserved in
`tasks/change_log.md#superseded-cursor-domain-relation-audit-before-covered-label-fix-2026-10-16`.

Outcome: E03 and E07 retain `covered` only with symbol-anchored tests that exercise their
error cases, and reasons describing that tested scope. Reuse the owner-suggested existing
tests; no behavior changes or new tests are needed. Keep the map at most 12,288 bytes.

- [x] Confirm supplied map hash, installed 1.1.0 contract definitions and candidate behavior.
- [x] Re-point E03/E07 checks and scope reasons; preserve every unrelated mapping entry.
- [x] Run ontology tests and every mapped check with temporary fixture databases only.
- [x] Pass installed and checkout mapping (0/0) and strict Git impact; record evidence.

Skip `tests/test_harness_consistency.py`, `harness_consistency run`, memory render/sync,
context sync and any gate wrapping them. Run individual allowed gate steps only.
No commits, generated derivatives, live databases, service operations or consumer writes.

Completed: 262 ontology and mapped-check tests passed. Installed and checkout checkers each
reported mapping 0 errors / 0 warnings and strict impact exit 0 with no stale refs; both
contract self-checks returned 0/0. The map is 12,275 bytes. Refs and evidence:
`tasks/change_log.md#covered-label-fix-2026-10-16`.

The dependent adopter inventory is refreshed after bookkeeping and checked separately.
No generated instruction/runtime derivatives need regeneration because their sources did
not change. Full suite and live-memory steps are intentionally excluded by owner scope.
