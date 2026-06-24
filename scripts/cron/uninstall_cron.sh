#!/bin/bash
# uninstall_cron.sh — Uninstall your-harness daily cron LaunchAgents
# Usage: bash scripts/cron/uninstall_cron.sh
# Run from the project root: <your-harness-path>
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLIST_DIR="$HOME/Library/LaunchAgents"

for plist in "$SCRIPT_DIR"/com.mir.*.plist; do
    base="$(basename "$plist")"
    dest="$PLIST_DIR/$base"
    name="$(basename "$plist" .plist)"
    launchctl unload "$dest" 2>/dev/null || true
    rm -f "$dest"
    echo "Uninstalled: $name"
done

echo ""
echo "Verification:"
launchctl list | grep com.mir && echo "WARNING: some jobs still listed" || echo "All com.mir jobs removed"
