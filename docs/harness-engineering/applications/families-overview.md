---
status: superseded
date: 2026-05-25
updated: 2026-09-02
scope: historical repository roster catalog pointer
---

# Fleet Families Overview — Historical Pointer

The former document was a generated roster of every repository managed by one control plane, one card per repository, each card carrying a slug, a class label, a seal flag, a filesystem path, an adopted-phase range, a readiness baseline and a purpose line. It closed with a seal table giving a date and reason per sealed repository, notes on a standalone specialist agent and a reference implementation, and a clustering table that decided which repositories were considered compatible enough to receive each other's changes. It declared a central state file its source of truth, and that file, the generator and the inventory itself are all outside this repository.

There is no fleet and no roster now: this repository publishes adoption layers, not a list of the repositories that took them, and the cross-repository recommendation affinity died with the catalog that computed it. Current authority is ADR-83 (the four-file starter, the Project Agent Kit recipe and the optional installed CLI are the only adoption layers), ADR-84 (upgrade guidance; it already classifies this whole directory as history), ADR-85 (agent contracts), ADR-86 (Mir Harness maintains this repository) and ADR-81 (the Starter). Fleet rollout, hash conformance, direct deployment, drift enforcement and notification behaviour are cancelled and named only to forbid their return. The current replacement guide is `docs/operations/harness-engineering-upgrade.md`.

A new session must not execute the historical procedure. The complete original is preserved in [the archive](../../_archive/harness-engineering/applications/families-overview-2026-05-25-historical.md).
