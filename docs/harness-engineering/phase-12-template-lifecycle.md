---
status: superseded
date: 2026-05-23
updated: 2026-09-02
scope: historical template lifecycle pointer
---

# Phase 12 — Template Lifecycle (Template Sunset + Upgrade Migration) — Historical Pointer

This phase specified the maintainer lane for the public template across create, maintain, deprecate and sunset stages, with a ninety-day deprecation grace period and archive, replace, rename and fork sunset procedures each carrying an impact assessment and migration path. It added a version-lag detector that compared each managed repository's adopted version against the current one and graded the gap as patch, minor, major or unknown; per-bump migration runbooks in which patch upgrades auto-applied on a thirty-day timeout and breaking changes ran on a six-month grace period; a hand-off protocol built on a declared-stable schema and enum interface; and required continuous-integration workflows, hooks and self-tests. The version-lag tooling, health checker and notification digests it named do not exist here.

Authority for this repository now sits with ADR-83 (the product boundary: the four-file starter, the Project Agent Kit recipe, and the optional installed CLI are the only adoption layers), ADR-84 (upgrade guidance, which already classifies this whole directory as history), ADR-85 (agent contracts), ADR-86 (Mir Harness maintains this repository), and ADR-81 (the Starter). Fleet rollout, drift enforcement, central direct-apply, daemons and notifications are cancelled and are named here only to forbid their return. The current replacement guide is `docs/operations/harness-engineering-upgrade.md`.

A new session must not execute the historical procedure. The complete original is preserved in [the archive](../_archive/harness-engineering/phase-12-template-lifecycle-2026-05-23-historical.md).
