# Mir Yoke Public Template Architecture

## Product Boundary

Mir Yoke is a public template and reference repository made of versioned files. It has no provider
runtime and no standing authority over consumer repositories. A maintainer command validates this
checkout; a consumer command runs only after explicit invocation for one declared local root.

## Modules

- **Contract** — `README.md`, `CLAUDE.md`, ADR-78, and this file define product identity,
  authority, non-goals, and adoption semantics.
- **Adoption** — `mir bootstrap` owns greenfield creation; `mir bootstrap-adoption` owns read-only
  existing-repository assessment and receipt-only explicit apply.
- **Capability provenance** — `mir capability` verifies one configured Git source and local locks.
  Hashes prove integrity, never adoption or conformance.
- **Maintenance** — asset classification, tests, generated-surface checks, sanitization, and release
  readiness validate Mir Yoke itself.
- **History** — the decision index exposes current authority and routes centralization-era material
  through `docs/history/centralization/`.

Dependencies point toward Contract. Adoption and Capability are independent consumer boundaries;
Maintenance validates all modules; History never grants executable authority.

## Runtime and Deployment Views

Provider runtime topology is empty: no agent host, daemon, target scanner, scheduler, fleet
notification, or background service. The Python CLI and shipped hooks are optional consumer tools,
not processes started by Mir Yoke.

Deployment means publishing an immutable Git tree. Adoption is a later consumer-owned choice.
Template version lag is not drift, and a release never selects or mutates consumer repositories.

## Data and Transaction Boundaries

Mir Yoke owns release metadata and the asset manifest. Consumer profiles, memory databases, locks,
and receipts remain repository- or machine-local. Existing-repository assessment is read-only;
successful explicit apply atomically replaces only the local receipt. Capability apply preserves
the prior provider and local agents on failure.

## Verification

`scripts/verify_release_readiness.py` composes identity, classification, history, sanitization,
derivative, behavior, full-test, and lint evidence from a clean materialized candidate tree.
