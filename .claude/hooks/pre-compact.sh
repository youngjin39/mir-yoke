#!/bin/bash
# pre-compact.sh
# Auto-write a handoff stub before the agent compacts its context, so the
# next session can resume without losing the in-progress plan.

set -u

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$PWD}"
HANDOFF_DIR="$PROJECT_DIR/tasks/handoffs"
mkdir -p "$HANDOFF_DIR" 2>/dev/null || exit 0

TS="$(date -u +%Y%m%d-%H%M%S)"
HANDOFF="$HANDOFF_DIR/auto-$TS.md"

{
  echo "# Auto-handoff — $TS UTC"
  echo
  echo "## Plan at compact time"
  echo
  if [ -f "$PROJECT_DIR/tasks/plan.md" ]; then
    sed -n '1,40p' "$PROJECT_DIR/tasks/plan.md"
  else
    echo "(tasks/plan.md not present)"
  fi
  echo
  echo "## TDD ledger entries in flight"
  echo
  if [ -f "$PROJECT_DIR/tasks/tdd.json" ] && command -v jq >/dev/null 2>&1; then
    jq -r '.changes[] | select(.categories | to_entries | map(.value.status) | any(. == "planned")) | "- " + .id + " (scope: " + (.scope[:120] // "") + ")"' "$PROJECT_DIR/tasks/tdd.json" 2>/dev/null | head -10
  fi
  echo
  echo "## Reminder"
  echo "When the next session starts, read tasks/plan.md and resume the in-flight ledger entry."
} > "$HANDOFF"

echo "[PreCompact] handoff saved: $HANDOFF" >&2
exit 0
