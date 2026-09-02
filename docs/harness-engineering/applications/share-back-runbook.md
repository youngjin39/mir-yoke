---
status: superseded
date: 2026-05-23
updated: 2026-09-02
scope: historical share-back pipeline pointer
---

# Share-Back Runbook — Historical Pointer

The former document was the end-to-end procedure for lifting an improvement out of one repository, registering it centrally, and pushing it back out to others. It laid out six steps, each with a manual column and a planned scripted column: a daily drift scan or an owner notification, hand-edited state-file snippets to register the item as a candidate, a four-way triage decision of share, absorb, promote or archive, a dispatcher that appended recommendations to a list of named target repositories, a receiving-side decision command with a thirty-day auto-decline, a weekly digest posted to a chat channel, and a final catalog update. It also carried a self-stop check that blocked sharing a phase the control plane had not itself adopted, and two contradiction resolutions covering privately authored capabilities and reverse absorption. Every tool it names lives outside this repository and the self-stop decision record is archived.

There is no hub to share back to: improvements reach this repository through ordinary contribution, and nothing is dispatched to a consumer, decided on their behalf, or auto-declined by a timer. Current authority is ADR-83 (the four-file starter, the Project Agent Kit recipe and the optional installed CLI are the only adoption layers), ADR-84 (upgrade guidance; it already classifies this whole directory as history), ADR-85 (agent contracts), ADR-86 (Mir Harness maintains this repository) and ADR-81 (the Starter). Fleet rollout, hash conformance, direct deployment, drift enforcement and notification behaviour are cancelled and named only to forbid their return. The current replacement guide is `docs/operations/harness-engineering-upgrade.md`.

A new session must not execute the historical procedure. The complete original is preserved in [the archive](../../_archive/harness-engineering/applications/share-back-runbook-2026-05-23-historical.md).
