---
status: superseded
date: 2026-05-25
updated: 2026-09-02
scope: historical fleet adoption matrix pointer
---

# Fleet Catalog — Adoption Matrix — Historical Pointer

The former document rendered a repository-by-phase adoption grid for every repository under one control plane so that laggards could be spotted and pushed a next phase. Alongside it sat a clustering table for recommendation affinity, a reconciliation snippet declaring a central state file authoritative over the table itself, a seal policy listing each sealed repository with a reason and a re-activation condition, registers of pending improvements and of recommendations already dispatched to named targets with decision deadlines, an update cadence including a weekly digest and a monthly review, and a command to regenerate the table from the state file. Neither that state file nor the rendering tool exists here.

Nothing in this repository tracks adoption for a third party, ranks anyone against a phase list, or dispatches a recommendation to a target. Current authority is ADR-83 (the four-file starter, the Project Agent Kit recipe and the optional installed CLI are the only adoption layers), ADR-84 (upgrade guidance; it already classifies this whole directory as history), ADR-85 (agent contracts), ADR-86 (Mir Harness maintains this repository) and ADR-81 (the Starter). Fleet rollout, hash conformance, direct deployment, drift enforcement and notification behaviour are cancelled and named only to forbid their return. The current replacement guide is `docs/operations/harness-engineering-upgrade.md`.

A new session must not execute the historical procedure. The complete original is preserved in [the archive](../../_archive/harness-engineering/applications/fleet-catalog-2026-05-25-historical.md).
