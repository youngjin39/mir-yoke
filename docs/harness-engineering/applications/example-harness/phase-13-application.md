---
status: superseded
date: 2026-06-13
updated: 2026-09-02
scope: historical applied-state closure application pointer
---

# Phase 13 — Applied-State Closure Application — Historical Pointer

The former document was a per-phase application ledger entry that declared the applied-state closure problem closed for a reference harness family: it reconciled a self-baseline done/block verdict, a control-plane state file, a public template snapshot and a dedicated closure verifier so that all four reported one identical verdict, and it recorded that external families never rolled this phase out directly. None of that machinery exists here — the blueprint, the state file and the closure and self-stop verifier scripts are absent, and the applied-state verifier ADR it depended on is itself archived.

Nothing now tracks per-phase applied state for anyone but this repository, and no ledger row grants a verdict over another repository. Current authority is ADR-83 (the four-file starter, the Project Agent Kit recipe and the optional installed CLI are the only adoption layers), ADR-84 (upgrade guidance; it already classifies this whole directory as history), ADR-85 (agent contracts), ADR-86 (Mir Harness maintains this repository) and ADR-81 (the Starter). Fleet rollout, hash conformance, direct deployment, drift enforcement and notification behaviour are cancelled and named only to forbid their return. The current replacement guide is `docs/operations/harness-engineering-upgrade.md`.

A new session must not execute the historical procedure. The complete original is preserved in [the archive](../../../_archive/harness-engineering/applications/example-harness/phase-13-application-2026-06-13-historical.md).
