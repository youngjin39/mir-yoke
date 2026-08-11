# Plan

## P4 — Project Agent Kit supported flow (2026-08-11) — READY FOR OWNER APPROVAL

Authorization: the owner approved implementation of the revised design in Mir Yoke. Commit, push,
tag, release, provider activation, protected capability-lock mutation, and consumer-repository
writes remain outside this task.

- P4.1 DONE — recorded the Project Agent Kit TDD contract and observed the expected failures.
- P4.2 DONE — selectively reversed the ADR-82 platform/composer expansion while preserving Git
  history, the protected capability lock, and generated-file ownership.
- P4.3 DONE — implemented ADR-83, the short prompt, recipe, portable plugin contract, classification,
  generated parity, and state alignment.
- P4.4 DONE — implemented the recipe-owned target schema plus a two-phase clean-room observer that
  binds purpose and provider revision, statically validates the target before execution, runs real
  checks in a credential-free target-local environment, mutation-probes every foundation/generated
  surface, preserves Git policy, and publishes sanitized content-bound evidence.
- P4.5 DONE — independent re-review found no fix-now blocker; the regenerated candidate passed 741
  tests with only the protected capability-lock test intentionally deselected, plus Ruff, derivative
  parity, diff inspection, asset classification, and actual dual-CLI plugin activation.

Release-time Claude and Codex clean-room runs remain unevaluated until a publishable revision exists;
static tests do not substitute for that evidence.
