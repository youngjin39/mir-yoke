---
status: superseded
date: 2026-05-23
updated: 2026-09-02
scope: historical observability scheduling runbook pointer
---

# Daily Observability Cron Runbook — Historical Pointer

This runbook told a single operator how to activate three daily observability jobs as per-user scheduled tasks on the maintainer's own
machine: it listed each job label, its local and UTC run time, its temporary-directory output and log files, a chained template
verifier, install and uninstall scripts, and a troubleshooting table. The scheduler payloads, `template_health.py`, `harness_drift.py`
and `render_families_overview.py` do not exist here, and nothing in this repository installs a scheduled job.

Current authority is ADR-83 (the four-file Starter, the Project Agent Kit recipe and the optional installed CLI are the only adoption
layers), ADR-84, which already classifies this whole directory as history, ADR-85 (agent contracts), ADR-86 (Mir Harness maintains this
repository) and ADR-81 (the Starter). Fleet rollout, hash conformance, direct deployment, drift enforcement and notification behaviour are
cancelled and named only to forbid their return; the current replacement guide is `docs/operations/harness-engineering-upgrade.md`.

A new session must not execute the historical procedure. The complete original is preserved in
[the archive](../../../_archive/harness-engineering/applications/example-harness/cron-runbook-2026-05-23-historical.md).
