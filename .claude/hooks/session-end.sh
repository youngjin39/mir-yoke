#!/bin/bash
# session-end.sh
# Save a one-line snapshot to tasks/sessions/<timestamp>.md so the next
# session can pick up where this one left off.

set -u

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$PWD}"
SESSIONS_DIR="$PROJECT_DIR/tasks/sessions"
mkdir -p "$SESSIONS_DIR" 2>/dev/null || exit 0

TS="$(date -u +%Y%m%d-%H%M%S)"
SNAPSHOT="$SESSIONS_DIR/$TS.md"

{
  echo "# Session snapshot — $TS UTC"
  echo
  echo "## What worked"
  echo "(fill on demand)"
  echo
  echo "## What did not work"
  echo "(fill on demand)"
  echo
  echo "## Decisions"
  echo "(fill on demand)"
  echo
  echo "## Next step"
  echo "(fill on demand)"
} > "$SNAPSHOT"

echo "[SessionEnd] snapshot saved: $SNAPSHOT" >&2
exit 0
