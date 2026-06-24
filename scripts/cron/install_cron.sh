#!/bin/bash
# install_cron.sh — Install your-harness daily cron LaunchAgents
# Usage: bash scripts/cron/install_cron.sh
# Run from the project root: <your-harness-path>
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLIST_DIR="$HOME/Library/LaunchAgents"
mkdir -p "$PLIST_DIR"

for plist in "$SCRIPT_DIR"/com.mir.*.plist; do
    base="$(basename "$plist")"
    dest="$PLIST_DIR/$base"
    name="$(basename "$plist" .plist)"
    cp "$plist" "$dest"
    launchctl unload "$dest" 2>/dev/null || true
    launchctl load "$dest"
    echo "Installed: $name"
done

echo ""
echo "Verification:"
launchctl list | grep com.mir || echo "(no com.mir jobs listed yet — may require a new login session)"
