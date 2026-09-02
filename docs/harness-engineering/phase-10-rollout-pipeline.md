---
status: superseded
date: 2026-05-23
updated: 2026-09-02
scope: historical rollout share pipeline pointer
---

# Phase 10 — Rollout / Share Pipeline — Historical Pointer

This phase specified a three-stage promotion pipeline with per-stage exit criteria: land a change in a maintainer harness and hold it through one to three audit rounds, then sanitize and version-bump the public template behind a merged pull request, then have a central harness inspect, patch, verify and report directly into actively managed repositories without waiting for owner opt-in. It added a greenfield clone-and-bootstrap path with default enabled phase sets per repository class, a table of which stage transitions ran automatically, and a propagation rule shipping advisory triage defaults publicly while stricter strictness stayed in maintainer workspaces. The sanitizer, bootstrap script and share dispatcher it invoked are absent here.

Authority for this repository now sits with ADR-83 (the product boundary: the four-file starter, the Project Agent Kit recipe, and the optional installed CLI are the only adoption layers), ADR-84 (upgrade guidance, which already classifies this whole directory as history), ADR-85 (agent contracts), ADR-86 (Mir Harness maintains this repository), and ADR-81 (the Starter). Fleet rollout, drift enforcement, central direct-apply, daemons and notifications are cancelled and are named here only to forbid their return. The current replacement guide is `docs/operations/harness-engineering-upgrade.md`.

A new session must not execute the historical procedure. The complete original is preserved in [the archive](../_archive/harness-engineering/phase-10-rollout-pipeline-2026-05-23-historical.md).
