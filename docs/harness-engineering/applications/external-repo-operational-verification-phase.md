---
status: superseded
date: 2026-05-25
updated: 2026-09-02
scope: historical external repository verification pointer
---

# External Repo Operational Verification Phase — Historical Pointer

The former document was the preparation layer for verifying a roster of other repositories one at a time from a single control plane. It ordered the targets into four waves by blast radius, gave each a class label, a readiness baseline, a gate surface and a caution note, fixed a pre-check that resolved every target's working path out of a central config file and captured a score from a central state file, listed abort rules for unresolvable paths, overlapping working-tree dirt and fixes that would widen beyond harness verification, and prescribed a nine-item review record ending in a post-fix score delta. The roster, the per-target paths and the score snapshot it read were private control-plane material and are not reproduced in this pointer.

This repository never discovers, enumerates or scores consumer repositories, so there is no queue, no wave and no baseline to improve on anyone's behalf; a consumer runs its own checks in its own tree. Current authority is ADR-83 (the four-file starter, the Project Agent Kit recipe and the optional installed CLI are the only adoption layers), ADR-84 (upgrade guidance; it already classifies this whole directory as history), ADR-85 (agent contracts), ADR-86 (Mir Harness maintains this repository) and ADR-81 (the Starter). Fleet rollout, hash conformance, direct deployment, drift enforcement and notification behaviour are cancelled and named only to forbid their return. The current replacement guide is `docs/operations/harness-engineering-upgrade.md`.

A new session must not execute the historical procedure. The complete original is preserved in [the archive](../../_archive/harness-engineering/applications/external-repo-operational-verification-phase-2026-05-25-historical.md).
