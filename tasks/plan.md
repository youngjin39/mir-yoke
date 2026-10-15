# Plan

## Active task: P4 ontology work path (2026-10-15)

Authority: current P4 owner request in `tasks/intent.json`; this is the single active
cursor and design authority. Prior P2 cursor is preserved in `tasks/change_log.md`.

Outcome: map 1.1.0 validates at 0/0 within 12,288 bytes; pytest runs mapping and strict
Git impact; a thin checkout runner connects optional MK lookup; no planned errors remain.
Design: reuse released scripts unchanged; exercise own-map failures in an independent
committed Git fixture. No generated writes, live MK, databases, commits or delivery.

- [x] Add fail-first runner/gate and missing-config regressions.
- [x] Connect runner, map and instructions within budgets.
- [x] Run full pytest, lint, checker and read-only derivative parity; record evidence.

Completed at the code/test boundary. Final full-suite process exited 0; exact receipts,
scoped error statuses and the separately observed derivative update are in `tasks/change_log.md`.
No live MK or delivery operation is authorized or needed for this bounded task.
