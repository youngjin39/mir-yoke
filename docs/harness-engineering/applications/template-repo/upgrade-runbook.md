---
status: superseded
date: 2026-05-23
updated: 2026-09-02
scope: historical template upgrade runbook pointer
---

# Template Upgrade Runbook — Historical Pointer

The former document was the receiving side's procedure for taking a template version bump, split by patch, minor and major release. It gave a decision flow ending in adopted, declined, pending or superseded, with a notification body for each tier: a patch that auto-upgraded after thirty days unless the recipient replied to opt out, a minor that stayed pending by default and expected a selection pass before adoption, and a major announced ninety days in advance with a six-month migration grace, after which the recipient stopped receiving recommendations and its catalog row was archived. It added a conflict-resolution matrix across the three tiers, special handling that defaulted sealed repositories to decline, and a self-stop check firing before any capability was recommended at all. The decision command, the notification renderer and the schedulers were never built, and the self-stop decision record is archived.

Nothing auto-upgrades a consumer, no grace period is counted against them and no adopted version is tracked on their behalf: upgrading is the user's own read-and-decide step in their own tree. Current authority is ADR-83 (the four-file starter, the Project Agent Kit recipe and the optional installed CLI are the only adoption layers), ADR-84 (upgrade guidance; it already classifies this whole directory as history), ADR-85 (agent contracts), ADR-86 (Mir Harness maintains this repository) and ADR-81 (the Starter). Fleet rollout, hash conformance, direct deployment, drift enforcement and notification behaviour are cancelled and named only to forbid their return. The current replacement guide is `docs/operations/harness-engineering-upgrade.md`.

A new session must not execute the historical procedure. The complete original is preserved in [the archive](../../../_archive/harness-engineering/applications/template-repo/upgrade-runbook-2026-05-23-historical.md).
