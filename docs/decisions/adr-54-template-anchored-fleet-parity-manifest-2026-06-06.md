---
adr: 54
status: accepted
date: 2026-06-06
amended: 2026-07-15
source: sanitized-template-summary
amended_by: [adr-73]
---

# ADR-54 — Template-Anchored Parity Manifest

## Current Decision

`config/parity-manifest.json` is a generated, read-only comparison artifact anchored to a known
Mir Yoke release. It reports drift on portable template-owned surfaces after the declared
normalization. It does not select repositories, authorize writes, or require family-owned files to
match the template.

The manifest is refreshed from the public template source after a release commit. A stale base
makes parity findings advisory until the manifest is regenerated. Scans are user-directed; this ADR
does not install a weekly scheduler or mutation step.

## ADR-73 Precedence

Repair only deterministic portable drift. Repository-specific behavior and optional surfaces remain
profile-owned and are not overwritten merely to make a hash pass.
