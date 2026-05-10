#!/bin/bash
# session-start.sh
# Auto-load the working ledger so the agent starts with the right context.
# Output is written to stdout — Claude Code shows it as session-start context.

set -u

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$PWD}"

emit_block() {
  local label="$1"
  local path="$2"
  if [ -f "$path" ]; then
    echo "--- $label ($path) ---"
    cat "$path"
    echo
  fi
}

echo "=== SESSION CONTEXT ==="
emit_block "plan.md"      "$PROJECT_DIR/tasks/plan.md"
emit_block "lessons.md"   "$PROJECT_DIR/tasks/lessons.md"
emit_block "memory-map"   "$PROJECT_DIR/docs/memory-map.md"

# Most recent session snapshot, if any.
LATEST=$(ls -1 "$PROJECT_DIR/tasks/sessions"/*.md 2>/dev/null | tail -1)
if [ -n "${LATEST:-}" ]; then
  emit_block "latest-session-snapshot" "$LATEST"
fi

# Latest auto-handoff, if any.
LATEST_HANDOFF=$(ls -1 "$PROJECT_DIR/tasks/handoffs"/auto-*.md 2>/dev/null | tail -1)
if [ -n "${LATEST_HANDOFF:-}" ]; then
  emit_block "latest-auto-handoff" "$LATEST_HANDOFF"
fi

echo "=== END SESSION CONTEXT ==="
exit 0
