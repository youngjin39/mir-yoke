---
status: superseded
date: 2026-05-25
updated: 2026-09-02
scope: historical per-class adoption runbook pointer
---

# Family-Type Adoption Runbooks — Historical Pointer

The former document held one condensed adoption runbook per repository class — self-referential control plane, application code, product workspace, mixed content pipeline and a narrower personal-autonomy variant — each with a phase ordering and rationale, mandatory gates, class-specific cautions, and a named list of live member repositories. Around them it added a cross-class compatibility matrix that auto-dispatched an improvement from one class to another, a doubled containment window for pipeline work, personal-domain rules forbidding automatic escalation, a parity-verification queue naming each member in scan order, and a self-status table. Its stated premise was that recommendations generated from these runbooks were auto-applied across every managed repository.

Adoption is now a single documented recipe a user runs against their own target: no class taxonomy, no auto-dispatch, no standing membership list and no advice pushed anywhere. Current authority is ADR-83 (the four-file starter, the Project Agent Kit recipe and the optional installed CLI are the only adoption layers), ADR-84 (upgrade guidance; it already classifies this whole directory as history), ADR-85 (agent contracts), ADR-86 (Mir Harness maintains this repository) and ADR-81 (the Starter). Fleet rollout, hash conformance, direct deployment, drift enforcement and notification behaviour are cancelled and named only to forbid their return. The current replacement guide is `docs/operations/harness-engineering-upgrade.md`.

A new session must not execute the historical procedure. The complete original is preserved in [the archive](../../_archive/harness-engineering/applications/family-type-adoption-runbooks-2026-05-25-historical.md).
