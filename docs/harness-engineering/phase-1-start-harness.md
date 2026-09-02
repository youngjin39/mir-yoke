---
status: superseded
date: 2026-06-13
updated: 2026-09-02
scope: historical start harness routing pointer
---

# Phase 1 — Start Harness — Historical Pointer

This phase defined a single routing entrypoint that had to emit a five-element declaration — task type, risk level, required reads, required tools and required checks, plus a route and a report contract — before any task began, and treated a missing element as a start failure. It supplied the rules for grading risk as low, medium or high with automatic escalation mid-task, the default flow per classification, the conditions that counted as routing failure, and prompt-cache obligations that froze read order and template shape. The orchestrator surface, verifier script and pytest gate it named as machine verification are not present in this repository.

Authority for this repository now sits with ADR-83 (the product boundary: the four-file starter, the Project Agent Kit recipe, and the optional installed CLI are the only adoption layers), ADR-84 (upgrade guidance, which already classifies this whole directory as history), ADR-85 (agent contracts), ADR-86 (Mir Harness maintains this repository), and ADR-81 (the Starter). Fleet rollout, drift enforcement, central direct-apply, daemons and notifications are cancelled and are named here only to forbid their return. The current replacement guide is `docs/operations/harness-engineering-upgrade.md`.

A new session must not execute the historical procedure. The complete original is preserved in [the archive](../_archive/harness-engineering/phase-1-start-harness-2026-06-13-historical.md).
