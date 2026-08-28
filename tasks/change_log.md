# Change log

One bullet per non-trivial change. Newest at the top.

- 2026-08-29: migrated generated Codex permission ownership to operator-selected profiles, rejected
  legacy/profile mixing, bound vector writes to a persisted encoder fingerprint, preserved fact
  subject/provenance, quarantined credential-shaped facts, and passed clean-candidate readiness
  with 797 tests; published the implementation to `origin/main` at `d3693b8`.
- 2026-08-28: added ADR-84 and the current harness engineering upgrade guide without expanding the
  Starter, Project Agent Kit, optional CLI, plugin, or consumer-authority boundaries.
- 2026-08-28: corrected current-only fact/document retrieval, semantic history classification,
  explicit resumable missing-vector backfill, and the public 1024-dimension vector contract.
- 2026-08-28: fixed current Codex patch hook input, secret-value redaction, instruction-like memory
  quarantine, least-privilege generated Codex defaults, bounded SessionEnd parity, and hook-trust
  guidance; clean-candidate readiness passed with 793 tests.
- 2026-08-28: published the portable compact lifecycle and Project Agent Kit common-harness parity
  on `main`; owner-run Claude/Codex example repositories remain optional post-release acceptance.
- 2026-08-28: refreshed the protected capability lock against implementation commit `a0768ce` and
  reconciled the canonical intent, plan, checklist, TDD evidence, profile, and handoff.
- 2026-08-11: closed the active repository plan, reconciled canonical state, and removed merged
  local and remote agent branches so `main` is the only branch.
- 2026-08-11: clarified the canonical Project Agent Kit prompt in `409d09e`; concrete project
  purpose and goals are required before repository writes.
- 2026-08-11: published the restored harness engineering surface as GitHub Release `v0.9.0`; the
  immutable tag points to release commit `1d17358`.
