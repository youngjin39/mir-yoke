---
status: superseded
date: 2026-05-20
updated: 2026-09-02
scope: historical autonomous execution model pointer
---

# Autonomous Execution — Historical Pointer

This document specified an autonomous execution model for applying harness phases: five graduated autonomy levels with delegated
execution as the default, a split between an orchestrating main agent and an implementation lane bound to an approved dispatch brief,
six halt-and-escalate intervention triggers, and an unconditional self-stop whenever a change would touch hook enforcement or the
verification contract. The dispatch brief, the halt contract and the `config/fleet-harness-state.json` it read are absent here.

Current authority is ADR-83 (the four-file Starter, the Project Agent Kit recipe and the optional installed CLI are the only adoption
layers), ADR-84, which already classifies this whole directory as history, ADR-85 (agent contracts), ADR-86 (Mir Harness maintains this
repository) and ADR-81 (the Starter). Fleet rollout, hash conformance, direct deployment, drift enforcement and notification behaviour are
cancelled and named only to forbid their return; the current replacement guide is `docs/operations/harness-engineering-upgrade.md`.

A new session must not execute the historical procedure. The complete original is preserved in
[the archive](../../_archive/harness-engineering/applications/autonomous-execution-2026-05-20-historical.md).
