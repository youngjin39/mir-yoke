---
title: "your-harness Daily Observability Cron Runbook"
keywords: [cron, launchd, launchagent, observability, daily-jobs, template-health, harness-drift, fleet-observe, macos, install]
created: "2026-05-23"
last_used: "2026-06-07"
type: runbook
---
# cron-runbook.md — your-harness Daily Observability Cron

**Purpose**: Operational runbook for activating and managing the three daily observability jobs via macOS launchd LaunchAgents.

**Audience**: your-harness operator (user running `bash scripts/cron/install_cron.sh` manually).

**Prerequisites**:
- macOS with launchd (any modern macOS)
- Project venv at `<your-harness-path>/.venv/bin/python`
- R11 tools landed (`tools/fleet_observe/harness_drift.py`, `template_health.py`, `render_families_overview.py`)
- Template repo at `<template-repo-path>`
- Fleet state at `config/fleet-harness-state.json`

---

## §1 Overview

Three daily jobs run via macOS launchd LaunchAgents (per-user, no root required):

| Job Label | Tool | KST (local) | UTC | Output |
|---|---|---|---|---|
| `com.your-harness.template_health` | `tools/fleet_observe/template_health.py` | 13:00 | 04:00 | `/tmp/your-harness-template-health-daily.json` |
| `com.your-harness.harness_drift` | `tools/fleet_observe/harness_drift.py` | 13:30 | 04:30 | `/tmp/your-harness-harness-drift-daily.json` |
| `com.your-harness.render_families_overview` | `tools/fleet_observe/render_families_overview.py` | 14:00 | 05:00 | `/tmp/your-harness-families-overview-daily.md` |

**Time zone note**: launchd `StartCalendarInterval` hours are in local system time. The plist files are set to KST (UTC+9) values. If your system clock is not KST, update the `Hour` keys accordingly.

**Chain**: `template_health` (04:00 UTC) runs first and chains to `scripts/verify_template_applied_state.py` via its `--chain` flag. `harness_drift` (04:30 UTC) runs independently 30 minutes later. `render_families_overview` (05:00 UTC) produces the daily families overview markdown.

---

## §2 Installation

Activation is a **manual user step** — the harness does not auto-install cron.

From the project root:

```bash
bash scripts/cron/install_cron.sh
```

The script:
1. Copies all `scripts/cron/com.your-harness.*.plist` to `~/Library/LaunchAgents/`
2. Runs `launchctl unload` (idempotent) then `launchctl load` for each plist
3. Prints installed job names and runs a verification list

Expected output:
```
Installed: com.your-harness.template_health
Installed: com.your-harness.harness_drift
Installed: com.your-harness.render_families_overview

Verification:
-	0	com.your-harness.harness_drift
-	0	com.your-harness.render_families_overview
-	0	com.your-harness.template_health
```

---

## §3 Verification

Check that jobs are registered with launchd:

```bash
launchctl list | grep com.your-harness
```

Expected output (one line per job, PID `-` = not running, exit code `0`):
```
-	0	com.your-harness.harness_drift
-	0	com.your-harness.render_families_overview
-	0	com.your-harness.template_health
```

Check that the plist files are in place:
```bash
ls ~/Library/LaunchAgents/com.your-harness.*.plist
```

Manually trigger a job for smoke test (runs immediately, ignores schedule):
```bash
launchctl start com.your-harness.template_health
# wait ~5s
cat /tmp/your-harness-template-health.log
cat /tmp/your-harness-template-health-daily.json
```

---

## §4 Uninstall

```bash
bash scripts/cron/uninstall_cron.sh
```

The script unloads and removes all `com.your-harness.*` plist files from `~/Library/LaunchAgents/`.

---

## §5 Troubleshooting

**Logs are in `/tmp/`**:
- `harness_drift`: `/tmp/your-harness-harness-drift.log` / `.err`
- `template_health`: `/tmp/your-harness-template-health.log` / `.err`
- `render_families_overview`: `/tmp/your-harness-render-families-overview.log` / `.err`

**Common issues**:

| Symptom | Cause | Fix |
|---|---|---|
| `launchctl: Error` on load | Plist XML invalid | Run `/usr/bin/plutil -lint scripts/cron/com.your-harness.*.plist` |
| Job not in `launchctl list` | Not loaded / login session needed | Re-run `install_cron.sh`, restart Terminal |
| Exit code non-zero in `launchctl list` | Python error at runtime | Check `.err` log file in `/tmp/` |
| `ModuleNotFoundError` | venv path wrong | Verify `.venv/bin/python` exists; re-run `setup.sh` |
| `FileNotFoundError: fleet-harness-state.json` | Config path wrong | Check `config/fleet-harness-state.json` exists |
| Template path error | Public template repo missing | Clone `github.com/<your-org>/mir-yoke` to `<template-repo-path>` |

**Re-install after plist edits**:
```bash
bash scripts/cron/uninstall_cron.sh
# edit scripts/cron/com.your-harness.*.plist
bash scripts/cron/install_cron.sh
```

---

## §6 Discord Notification Integration

Out of scope for this task. Planned as a separate R14 step. When implemented, each tool will post a summary to the harness Discord channel on completion. Until then, check `/tmp/your-harness-*.log` manually or via `launchctl start` smoke test.

---

## §7 Exit Criterion

Cron activation is complete when:
- `launchctl list | grep com.your-harness` shows 3 jobs with exit code `0`
- At least one manual `launchctl start` smoke test completes without error
- `/tmp/your-harness-*-daily.*` output files exist and are non-empty

This constitutes the **cron-active** state required by phase-6 (Observability), phase-11 (Drift Detection), and phase-12 (Template Health) adoption rows in `docs/harness-engineering/applications/example-harness/README.md`. Once cron-active is confirmed, those phases may be promoted from `partial` to `done`.
