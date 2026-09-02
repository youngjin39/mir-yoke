---
status: superseded
date: 2026-06-13
updated: 2026-09-02
scope: historical foundations phase pointer
---

# Phase 0 — Foundations — Historical Pointer

This phase fixed the shared vocabulary before any code was written: four governing variables, four pillars, a five-layer responsibility split with an explicit list of what must not live in each layer, the HOW NOT question ordering, four task classifications, a core prohibition list, and a decisions-versus-sunset table pinning language, memory infrastructure, execution lanes and directory roots. Its exit criterion was a consensus pass followed by creating a per-repository profile JSON, which made it the entry gate that stopped a repository progressing into later phases of a fleet programme this repository does not run.

Authority for this repository now sits with ADR-83 (the product boundary: the four-file starter, the Project Agent Kit recipe, and the optional installed CLI are the only adoption layers), ADR-84 (upgrade guidance, which already classifies this whole directory as history), ADR-85 (agent contracts), ADR-86 (Mir Harness maintains this repository), and ADR-81 (the Starter). Fleet rollout, drift enforcement, central direct-apply, daemons and notifications are cancelled and are named here only to forbid their return. The current replacement guide is `docs/operations/harness-engineering-upgrade.md`.

A new session must not execute the historical procedure. The complete original is preserved in [the archive](../_archive/harness-engineering/phase-0-foundations-2026-06-13-historical.md).
