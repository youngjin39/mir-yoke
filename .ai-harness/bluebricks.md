# Bluebricks

Bluebricks describes bounded modules for work in this public template repository. Mir Yoke has no
provider runtime; consumer-side CLIs and hooks remain inert until explicitly invoked or adopted.

## Current Product Bluebricks

### Contract

Defines public-template identity, authority, non-goals, and adoption semantics.
Full brick: `docs/bluebricks/contract.md`.

### Adoption

Separates manual core adoption, preservation-first composition, and retained legacy bootstrap.
Full brick: `docs/bluebricks/adoption.md`.

### Distribution

Builds deterministic core and capability-pack archives with manifest, checksums, and provenance.
Full brick: `docs/bluebricks/distribution.md`.

### Composition

Resolves advisory profiles, plans without mutation, applies only conflict-free new files, and pins
content-addressed providers. Full brick: `docs/bluebricks/composition.md`.

### Retained Capability Provenance

Provides explicit local status, check, sync, update, attestation, and finalization with
integrity-only hashes. Full brick: `docs/bluebricks/capability.md`.

### Maintenance

Classifies, validates, sanitizes, and prepares Mir Yoke release candidates.
Full brick: `docs/bluebricks/maintenance.md`.

### History

Separates current decision authority from retrievable centralization-era evidence.
Full brick: `docs/bluebricks/history.md`.

## Proportional Validation Rule

For non-trivial changes, identify the affected bluebrick and run the smallest check that can fail.
Use `tasks/tdd.json` for broad, high-risk, restartable, release, or explicitly ledger-driven work.

## Agent Rule

Before changing a bluebrick, identify its purpose, public interface, hazards, dependencies,
downstream users, composition, orchestration, and validation method.
