---
status: superseded
date: 2026-05-23
updated: 2026-09-02
scope: historical dual-role charter pointer
---

# Harness Roles — Dual-Role Charter + Identity Disambiguation — Historical Pointer

This charter split one agent into two standing lanes and gave each its own service level, signals and failure modes: a per-repository tracker running a daily read-only scan with drift-detection latency and catalog-availability targets, and a template maintainer owning versioning, daily health checks, dependency and security patching, deprecation and release notes. It disambiguated the agent identity from its own catalog row and from the repository on disk, made a per-repository ledger the source of truth that a self-stop verifier would enforce before any share, and assigned that work to independent runner processes, a drift detector, a sanitizer and health tooling that this repository does not contain.

Authority for this repository now sits with ADR-83 (the product boundary: the four-file starter, the Project Agent Kit recipe, and the optional installed CLI are the only adoption layers), ADR-84 (upgrade guidance, which already classifies this whole directory as history), ADR-85 (agent contracts), ADR-86 (Mir Harness maintains this repository), and ADR-81 (the Starter). Fleet rollout, drift enforcement, central direct-apply, daemons and notifications are cancelled and are named here only to forbid their return. The current replacement guide is `docs/operations/harness-engineering-upgrade.md`.

A new session must not execute the historical procedure. The complete original is preserved in [the archive](../_archive/harness-engineering/mir-roles-2026-05-23-historical.md).
