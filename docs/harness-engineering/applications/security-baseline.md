---
status: superseded
date: 2026-05-23
updated: 2026-09-02
scope: historical cross-cutting security baseline pointer
---

# Security Baseline — Cross-cutting 5 Security Surfaces — Historical Pointer

The former document consolidated five security surfaces — prompt injection, tool sandboxing, supply chain, memory poisoning and inter-agent trust — into one cross-cutting baseline. It gave an injection application matrix per input surface that deliberately exempted the maintainer's own command channel and explained why, a tool permission table and sandbox-intensity ladder, a per-call permission-scope sketch left as a candidate decision, supply-chain categories with verification obligations including a borrowed-code annotation and a dependency audit cadence, a memory-poisoning threat model with source annotation and a lifetime default for external material, an inter-agent trust table with a handoff contract requiring low-trust input to be wrapped rather than obeyed, and a propagation matrix setting an enforcement level per repository class. Its validators were advisory scripts in a harness this repository does not ship, and the exception catalog it drew its matrix from is archived beside it.

Security posture is the consumer's own decision here; this repository ships no enforced baseline and asserts no enforcement level over any target, though the surfaces it enumerated remain a reasonable checklist for a reader to apply themselves. Current authority is ADR-83 (the four-file starter, the Project Agent Kit recipe and the optional installed CLI are the only adoption layers), ADR-84 (upgrade guidance; it already classifies this whole directory as history), ADR-85 (agent contracts), ADR-86 (Mir Harness maintains this repository) and ADR-81 (the Starter). Fleet rollout, hash conformance, direct deployment, drift enforcement and notification behaviour are cancelled and named only to forbid their return. The current replacement guide is `docs/operations/harness-engineering-upgrade.md`.

A new session must not execute the historical procedure. The complete original is preserved in [the archive](../../_archive/harness-engineering/applications/security-baseline-2026-05-23-historical.md).
