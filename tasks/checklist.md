# Checklist

Historical completion detail remains in `tasks/tdd.json` and `tasks/change_log.md`.

## Current

- [x] **Protected:** Obtain explicit authorization to reconcile
  `.mir/capability-lock.json` against the implementation commit.
- [ ] **Publication:** After lock authorization, commit implementation, update and verify the lock,
  commit the state reconciliation, and push `main`.

## Recent Completed

- [x] Replaced stale reviewer contracts and regenerated host-neutral Codex mirrors (2026-08-30).
- [x] Added exact, batch fail-closed read-only metadata derivation and regression coverage
  (2026-08-30).
- [x] Refreshed adopter payload and TDD evidence; passed full lock-excluded and independent review
  (2026-08-30).
