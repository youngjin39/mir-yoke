---
status: superseded
date: 2026-05-23
updated: 2026-09-02
scope: historical greenfield bootstrap checklist pointer
---

# Bootstrap Day-0 / Day-1 / Day-7 Checklist — Historical Pointer

The former document was a greenfield onboarding checklist for the first day, the next day and the first week after cloning the template. Day zero ran eight steps: clone, an identity interview fixing a slug, class, purpose, traits, adopted phases and a seal flag, a bootstrap invocation, a verifier run, in-place substitution of the template's placeholder slug followed by regeneration of the derived startup files, registration of a new row in a central state file held by the control plane, a first commit and a push to a new remote, then a verification list. Day one checked that each adopted phase actually fired, started a privately authored capability and optionally wired a chat channel; day seven expected a first recommendation decision, a week-one observability report, a drift field update and an entry in a weekly digest. The bootstrap module, the registration script, the verifier and the state file are all absent here.

Greenfield setup is now the Project Agent Kit recipe run once against the user's own empty target, with target-local initialization and a single commit only when the user's prompt grants that authority, and with no registration or reporting anywhere else. Current authority is ADR-83 (the four-file starter, the Project Agent Kit recipe and the optional installed CLI are the only adoption layers), ADR-84 (upgrade guidance; it already classifies this whole directory as history), ADR-85 (agent contracts), ADR-86 (Mir Harness maintains this repository) and ADR-81 (the Starter). Fleet rollout, hash conformance, direct deployment, drift enforcement and notification behaviour are cancelled and named only to forbid their return. The current replacement guide is `docs/operations/harness-engineering-upgrade.md`.

A new session must not execute the historical procedure. The complete original is preserved in [the archive](../../../_archive/harness-engineering/applications/template-repo/bootstrap-day-0-2026-05-23-historical.md).
