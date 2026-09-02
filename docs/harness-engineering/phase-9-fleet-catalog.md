---
status: superseded
date: 2026-05-23
updated: 2026-09-02
scope: historical fleet catalog drift pointer
---

# Phase 9 — Fleet Catalog (Central Management) — Historical Pointer

This document made one central harness the state cache, drift tracker, direct-apply manager, and reporting hub for N other repositories. It separated four storages (a public template blueprint, a central adoption state cache, a per-family drift log, and each family's own local agent files), sketched a state schema carrying per-phase adoption status, `last_sync`, free-text drift strings, and innovation share candidates; defined three drift types (template-ahead, family-ahead, conflict); prescribed a six-step inspect, classify, minimum-patch-plan, direct-apply, verify, report loop across repository boundaries; supplied a source-to-target compatibility matrix for auto-recommending patterns between family types; handled decline with a thirty-day expiry on pending decisions; and listed an update cadence naming a drift detector, a share dispatcher, a full-audit job, and a manual chat-notification path.

Neither the state cache, the drift log, the drift detector, nor the share dispatcher exists in this repository, and cross-repository direct apply is forbidden outright: this repository has no standing write authority over any consumer and never discovers them. The current authority is ADR-83 (product boundary — the four-file starter, the Project Agent Kit recipe, and the optional installed CLI are the only adoption layers), ADR-84 (upgrade guidance, which already classifies this whole directory as history), ADR-85 (agent contracts), ADR-86 (Mir Harness maintains this repository), and ADR-81 (the Starter). Fleet rollout, drift enforcement, central direct-apply, daemons and notifications are cancelled and are named here only to forbid their return; the current replacement guide is `docs/operations/harness-engineering-upgrade.md`.

A new session must not execute the historical procedure. The complete original is preserved in [the archive](../_archive/harness-engineering/phase-9-fleet-catalog-2026-05-23-historical.md).
