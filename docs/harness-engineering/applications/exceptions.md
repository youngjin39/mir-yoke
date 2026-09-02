---
status: superseded
date: 2026-05-22
updated: 2026-09-02
scope: historical enforcement exception matrix pointer
---

# Exceptions — Cross-Family Enforcement Exception Matrix — Historical Pointer

The former document was a cross-repository enforcement exception catalog. It set a per-phase, per-repository-class strictness matrix over four levels — enforced, doc-strict, warn and off — then defined a six-step procedure for granting a justified, time-bounded exemption, an opt-in schema block written into a per-repository config file, a revert path, a conflict-resolution table, cross-pollination safeguards against an exception spreading by similarity, and a rule that sealed repositories carried blanket pre-granted exemptions. Every mechanism it relied on is absent here: the per-repository config files, the central state file that alone made an exception live, and the verifier that was to read and report active exceptions.

Because this repository asserts no enforcement level over any consumer, there is nothing left to be excepted from; a consumer's own profile owns its rules and its exemptions. Current authority is ADR-83 (the four-file starter, the Project Agent Kit recipe and the optional installed CLI are the only adoption layers), ADR-84 (upgrade guidance; it already classifies this whole directory as history), ADR-85 (agent contracts), ADR-86 (Mir Harness maintains this repository) and ADR-81 (the Starter). Fleet rollout, hash conformance, direct deployment, drift enforcement and notification behaviour are cancelled and named only to forbid their return. The current replacement guide is `docs/operations/harness-engineering-upgrade.md`.

A new session must not execute the historical procedure. The complete original is preserved in [the archive](../../_archive/harness-engineering/applications/exceptions-2026-05-22-historical.md).
