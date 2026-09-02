---
status: superseded
date: 2026-05-25
updated: 2026-09-02
scope: historical applied-state closure pointer
---

# Phase 13 — Applied-State Closure — Historical Pointer

This phase bundled the completion verdict for a maintainer harness and for the public template into one closure lane, to catch the case where a catalog claimed a phase was applied but the repository did not reflect it. It defined a three-axis self-check over catalog freshness, a repository verifier and an agent self-health file; a five-axis template check over phase coverage, schema validity, hook executability, a sanitization grep and role-policy parity; and a six-step inspection sequence of snapshot, physical scan, verifier run, template gate, reconcile and verdict producing a single composite pass, fail or partial result, recorded as passing on its 2026-05-25 baseline. The catalog, self-health and drift inputs those steps read are absent here.

Authority for this repository now sits with ADR-83 (the product boundary: the four-file starter, the Project Agent Kit recipe, and the optional installed CLI are the only adoption layers), ADR-84 (upgrade guidance, which already classifies this whole directory as history), ADR-85 (agent contracts), ADR-86 (Mir Harness maintains this repository), and ADR-81 (the Starter). Fleet rollout, drift enforcement, central direct-apply, daemons and notifications are cancelled and are named here only to forbid their return. The current replacement guide is `docs/operations/harness-engineering-upgrade.md`.

A new session must not execute the historical procedure. The complete original is preserved in [the archive](../_archive/harness-engineering/phase-13-applied-state-closure-2026-05-25-historical.md).
