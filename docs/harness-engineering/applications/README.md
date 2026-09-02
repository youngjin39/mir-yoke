---
status: superseded
date: 2026-06-13
updated: 2026-09-02
scope: historical rollout application ledger pointer
---

# Applications — Harness Engineering Execution Ledger — Historical Pointer

This file indexed a fourteen-phase harness rollout ledger: the per-phase application document schema, a dogfooding rule requiring a
private control-plane repository to apply every phase to itself before any external target, a phase-by-target gate table, and an ordered
wave sequence across a private template repository and a roster of private family repositories. Its closing verification step invoked
`scripts/verify_repo_agent_management.py` and `tools/fleet_observe/mir_manage.py`, neither of which exists in this repository.

Current authority is ADR-83 (the four-file Starter, the Project Agent Kit recipe and the optional installed CLI are the only adoption
layers), ADR-84, which already classifies this whole directory as history, ADR-85 (agent contracts), ADR-86 (Mir Harness maintains this
repository) and ADR-81 (the Starter). Fleet rollout, hash conformance, direct deployment, drift enforcement and notification behaviour are
cancelled and named only to forbid their return; the current replacement guide is `docs/operations/harness-engineering-upgrade.md`.

A new session must not execute the historical procedure. The complete original is preserved in
[the archive](../../_archive/harness-engineering/applications/README-2026-06-13-historical.md).
