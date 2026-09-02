---
status: superseded
date: 2026-06-03
updated: 2026-09-02
scope: historical context surface reduction pointer
---

# Context-Surface Reduction — Fleet-Application Design — Historical Pointer

This design specified how to shrink the always-on per-session context surface across a managed fleet: deduplicate the eagerly loaded instruction prose, regenerate the agent-facing mirror rather than hand-editing it, trim the session-start injection slices, and split each agent memory index into an injected hot tier and an archived cold tier without losing an entry. It set a per-repository measure, apply and verify rollout order against a full-suite baseline, warned that test-pinned injections block the largest cuts and must not be weakened, and listed automation, revert and archive items as explicitly non-portable.

Authority for this repository now sits with ADR-83 (the product boundary: the four-file starter, the Project Agent Kit recipe, and the optional installed CLI are the only adoption layers), ADR-84 (upgrade guidance, which already classifies this whole directory as history), ADR-85 (agent contracts), ADR-86 (Mir Harness maintains this repository), and ADR-81 (the Starter). Fleet rollout, drift enforcement, central direct-apply, daemons and notifications are cancelled and are named here only to forbid their return. The current replacement guide is `docs/operations/harness-engineering-upgrade.md`.

A new session must not execute the historical procedure. The complete original is preserved in [the archive](../_archive/harness-engineering/context-surface-reduction-fleet-design-2026-06-03-historical.md).
