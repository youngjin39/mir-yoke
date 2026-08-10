# Mir Yoke Public Template Architecture

## Product Boundary

Mir Yoke is an agent-guided public harness-engineering template and reference repository made of
versioned files. It has no provider runtime and no standing authority over consumer repositories.
The active agent interprets the baseline against the target's current state and local contract. A
maintainer command validates this checkout; a consumer command runs only after explicit invocation
for one declared local root.
It is not a universal installer: automated greenfield mutation is limited to macOS, Linux, and WSL.

## Modules

- **Contract** — `README.md`, `CLAUDE.md`, ADR-78, ADR-79, ADR-80, and this file define product identity,
  authority, non-goals, and adoption semantics.
- **Adoption** — `mir bootstrap` owns supported macOS, Linux, and WSL greenfield creation;
  `mir bootstrap-adoption` owns read-only existing-repository assessment and receipt-only explicit
  apply. Greenfield setup rejects a provider push remote before mutation and installs the exact
  committed CLI into a project-specific external runtime whose installed-file manifest is bound to
  the receipt and startup gate. Native Windows stops before mutation and provides WSL or
  reference-adaptation guidance.
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

Deployment means publishing an immutable Git tree. Adoption is a later consumer-owned choice made
with agent judgment. Template version lag is not drift, and a release never selects or mutates
consumer repositories.

## Data and Transaction Boundaries

Mir Yoke owns release metadata and the asset manifest. Consumer profiles, memory databases, locks,
and receipts remain repository- or machine-local. Existing-repository assessment is read-only;
successful explicit apply atomically replaces only the local receipt. Capability apply preserves
the prior provider and local agents on failure. A product's inherited Git history remains
provenance, but its effective push URLs must not target the Mir Yoke provider.

## Verification

`scripts/verify_release_readiness.py` composes identity, classification, history, sanitization,
derivative, behavior, full-test, and lint evidence from a clean materialized candidate tree.
