# Checklist

Historical completion detail remains in `tasks/tdd.json` and `tasks/change_log.md`.

## Current

The 2026-09-06 central capability operations repair is ready for final repository verification and
authorized delivery. It makes provider health, consumer enrollment, pending local integration,
legacy fallback, receipt-bound catch-up, and rollback explicit. Runtime status verifies provider
installation and activation; fresh per-consumer hook execution and trust still require explicit
attestation evidence.

## Recent Completed

- [x] Bound the protected capability lock to implementation commit `3018f5c` and passed all 803
  repository tests (2026-08-30).
- [x] Designated Mir Harness as the Yoke maintenance manager and unprotected only the maintainer
  capability lock (2026-08-30).
- [x] Preserved adopter lock protection and passed all 803 repository tests (2026-08-30).
