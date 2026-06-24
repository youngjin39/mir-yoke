# your-harness Stall Watchdog — launchd installation

ADR-06 §2.2.7. macOS-only. Single-deploy daemon covers all 15 family workspaces
via the unified `~/.claude/projects/` pool.

## Why launchd and not a your-harness agent

- The daemon must outlive Claude / Codex sessions and survive crashes.
- launchd `KeepAlive=true` is your-harness's chosen mitigation for the "watcher itself
  stalls" meta-stall case.
- The plist is installed once per-host by the user — your-harness agent does not invoke
  `launchctl load` (destructive system change).

## Install

```bash
# 1. Copy the template, then edit placeholders.
cp tools/stall_watchdog/launchd/com.mir.stall_watchdog.plist.template \
   /tmp/com.mir.stall_watchdog.plist

# 2. Set per-family webhook URLs in the EnvironmentVariables dict. Example:
#       <key>MIR_STALL_WATCHDOG_WEBHOOK_WRITE_SCORE</key>
#       <string>https://discord.com/api/webhooks/.../secret-token</string>
#    Never commit real webhook URLs back to this repo.

# 3. Install + load.
cp /tmp/com.mir.stall_watchdog.plist \
   <your-home>/Library/LaunchAgents/com.mir.stall_watchdog.plist
launchctl load -w <your-home>/Library/LaunchAgents/com.mir.stall_watchdog.plist
```

## Smoke

```bash
# Doctor — environment diagnosis without scanning.
uv run python -m tools.stall_watchdog.cli doctor

# One-shot scan (dry-run, no Discord push).
uv run python -m tools.stall_watchdog.cli scan --dry-run --json

# Tail logs after launchd load.
tail -f <your-home>/Library/Logs/com.mir.stall_watchdog.out.log
tail -f <your-home>/Library/Logs/com.mir.stall_watchdog.err.log
```

## Uninstall

```bash
launchctl unload <your-home>/Library/LaunchAgents/com.mir.stall_watchdog.plist
rm <your-home>/Library/LaunchAgents/com.mir.stall_watchdog.plist
```

## Notes

- The plist uses `HOME=<your-home>` (real user HOME, not your-harness sandbox HOME).
  See `project_sandbox_home_trap` auto-memory for why.
- `WorkingDirectory=<your-home>` avoids the `T7 Shield` space-in-path
  pitfall during subprocess invocation.
- `LANG=en_US.UTF-8` ensures Korean family display names render correctly in
  Discord webhook payloads.
