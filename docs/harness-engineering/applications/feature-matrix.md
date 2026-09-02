---
status: superseded
date: 2026-05-25
updated: 2026-09-02
scope: historical feature integration matrix pointer
---

# Feature Matrix — 16-Feature Integration SoT — Historical Pointer

The former document declared itself the single source of truth for which of sixteen harness features each phase implemented and to what depth, and required updating before any phase shipped or widened its coverage. It carried the feature-by-phase grid, a dependency graph, an extended table naming specific scripts and decision records behind each capability, a self-coverage score, a gap analysis that queued a scheduled notification job and the promotion of an advisory security check into an enforced one, a per-class applicability table, a pointer to the ledgers holding the evidence, and a change policy. The ledgers, the scripts and the release numbering it used to sequence the work all belong to a control plane this repository does not host.

No matrix now claims feature coverage on anyone's behalf; the supported surfaces are described by their own contracts and proven by the checks in this repository. Current authority is ADR-83 (the four-file starter, the Project Agent Kit recipe and the optional installed CLI are the only adoption layers), ADR-84 (upgrade guidance; it already classifies this whole directory as history), ADR-85 (agent contracts), ADR-86 (Mir Harness maintains this repository) and ADR-81 (the Starter). Fleet rollout, hash conformance, direct deployment, drift enforcement and notification behaviour are cancelled and named only to forbid their return. The current replacement guide is `docs/operations/harness-engineering-upgrade.md`.

A new session must not execute the historical procedure. The complete original is preserved in [the archive](../../_archive/harness-engineering/applications/feature-matrix-2026-05-25-historical.md).
