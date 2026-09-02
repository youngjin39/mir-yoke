---
status: superseded
date: 2026-06-10
updated: 2026-09-02
scope: historical fleet review criteria pointer
---

# Harness Review & Improvement Criteria — Historical Pointer

The former document was the standing method for a full review sweep spanning a private source repository, the public template and every other repository under one control plane. It specified a per-surface scoring rubric, a before-and-after byte-measurement discipline that banned estimates in final reports, an all-hooks verification standard, a context-injection classification rule, fixed token budgets per repository class, contract-pin awareness, risk tiers gating what could ship in-session, a cross-repository write lane requiring an elevation record before any write, a pre-push checklist with a leak scan and a remote check, a three-pillar execution recipe using parallel sub-agents whose outputs it treated as claims rather than facts, and a deterministic verifier command set. It flags itself that several of those commands belong to the full maintainer harness and are not wired into this repository.

Review here is scoped to this repository's own changed surfaces and its smallest failing check, with no sweep, no cross-repository write lane and no elevation record; the one durable lesson it records is that a push-blocking guard was found to fail open on every invocation and was removed rather than trusted. Current authority is ADR-83 (the four-file starter, the Project Agent Kit recipe and the optional installed CLI are the only adoption layers), ADR-84 (upgrade guidance; it already classifies this whole directory as history), ADR-85 (agent contracts), ADR-86 (Mir Harness maintains this repository) and ADR-81 (the Starter). Fleet rollout, hash conformance, direct deployment, drift enforcement and notification behaviour are cancelled and named only to forbid their return. The current replacement guide is `docs/operations/harness-engineering-upgrade.md`.

A new session must not execute the historical procedure. The complete original is preserved in [the archive](../../_archive/harness-engineering/applications/harness-review-criteria-2026-06-10-historical.md).
