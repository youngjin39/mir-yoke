---
status: superseded
date: 2026-05-28
updated: 2026-09-02
scope: historical rollout report contract pointer
---

# Fleet Rollout Report Contract — Historical Pointer

The former document made a per-repository rollout report mandatory after every direct-apply cycle into another repository, and said so in those terms: the report was not optional and was the user-facing management surface for the target's state. It fixed fourteen required fields including the target's slug and working path, the surfaces found before the write, the applied patch summary, the verification commands and results, a readiness score and a rollback note; a suggested text shape; a storage path under a task-report tree; an indirect linkage back to a central state file; and an exit rule that a direct-apply wave stayed incomplete for a repository until its report existed. The decision record that authorised that direct-apply model is itself archived.

Direct apply into another repository is cancelled, so there is no wave to report on, no target state to summarise and no score to publish for a consumer. Current authority is ADR-83 (the four-file starter, the Project Agent Kit recipe and the optional installed CLI are the only adoption layers), ADR-84 (upgrade guidance; it already classifies this whole directory as history), ADR-85 (agent contracts), ADR-86 (Mir Harness maintains this repository) and ADR-81 (the Starter). Fleet rollout, hash conformance, direct deployment, drift enforcement and notification behaviour are cancelled and named only to forbid their return. The current replacement guide is `docs/operations/harness-engineering-upgrade.md`.

A new session must not execute the historical procedure. The complete original is preserved in [the archive](../../_archive/harness-engineering/applications/fleet-rollout-report-contract-2026-05-28-historical.md).
