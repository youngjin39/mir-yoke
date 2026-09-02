---
status: superseded
date: 2026-05-23
updated: 2026-09-02
scope: historical template versioning policy pointer
---

# Template Versioning Runbook — Historical Pointer

The former document set the template's versioning policy under a maintainer charter that is now archived. It named three release artifacts and their update triggers, semantic-version decision rules with edge cases for phase and schema changes and two pre-release suffixes, then a seven-step manual bump procedure: diff the log since the recorded version, write the version file, add a changelog entry in the standard format, add a migration section for a major, commit and tag and push, write the new version back into a central state file held by the control plane, and notify the receiving repositories — by digest for a minor and by priority alert for a major. It closed with a changelog writing guide, a status table recording which of the three artifacts were then missing or malformed, and a correction noting an earlier claim in that table had been made without checking.

Versioning here is ordinary repository practice against the version file and changelog in this tree, with no state file to update, no downstream notification and no per-consumer adopted-version bookkeeping; the artifact measurements the original reported are pinned to a long-superseded revision. Current authority is ADR-83 (the four-file starter, the Project Agent Kit recipe and the optional installed CLI are the only adoption layers), ADR-84 (upgrade guidance; it already classifies this whole directory as history), ADR-85 (agent contracts), ADR-86 (Mir Harness maintains this repository) and ADR-81 (the Starter). Fleet rollout, hash conformance, direct deployment, drift enforcement and notification behaviour are cancelled and named only to forbid their return. The current replacement guide is `docs/operations/harness-engineering-upgrade.md`.

A new session must not execute the historical procedure. The complete original is preserved in [the archive](../../../_archive/harness-engineering/applications/template-repo/versioning-2026-05-23-historical.md).
