#!/bin/bash
# PreCompact hook: refresh the one canonical handoff before compaction.

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
HANDOFF_DIR="$PROJECT_DIR/tasks/handoffs"
HANDOFF_FILE="$HANDOFF_DIR/session-handoff-LATEST.md"

latest_active_runner() {
  find "$PROJECT_DIR/tasks/runner" -name "*.md" -type f 2>/dev/null \
    | sort -r \
    | while IFS= read -r candidate; do
        if grep -Eiq '^- status:[[:space:]]*`?(active|running|in_progress)`?[[:space:]]*$' "$candidate"; then
          printf '%s\n' "$candidate"
          break
        fi
      done
}

LATEST_RUNNER=$(latest_active_runner)
LATEST_DISPATCH_BRIEF=""
if [ -n "$LATEST_RUNNER" ]; then
  LATEST_DISPATCH_BRIEF=$(find "$PROJECT_DIR/tasks/dispatch" -name "*.json" -type f 2>/dev/null | sort -r | head -1)
fi
RUNNER_REL="${LATEST_RUNNER#"$PROJECT_DIR"/}"
DISPATCH_REL="${LATEST_DISPATCH_BRIEF#"$PROJECT_DIR"/}"

mkdir -p "$HANDOFF_DIR" || {
  echo "[PreCompact] ERROR: Cannot create $HANDOFF_DIR"
  exit 0
}

if [ ! -f "$HANDOFF_FILE" ]; then
  cat > "$HANDOFF_FILE" <<'EOF'
# Session Handoff — Current

## Completed Work
- Add only completed outcomes useful to the next session.

## Decisions
- Add only durable decisions needed by the next session.

## Unresolved Issues
- Add only unresolved work or blockers.

## Next Actions
- Add only the next actions needed to resume.

## Modified Files
- Add only files or groups needed to understand the handoff.

## Verification Results
- Add the checks run and their observed results.

## Key Risks
- Add only risks that remain relevant to the next session.
EOF
fi

WORKTREE_STATUS_COUNT=""
if git -C "$PROJECT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  WORKTREE_STATUS_COUNT=$(git -C "$PROJECT_DIR" status --short --untracked-files=all 2>/dev/null | wc -l | tr -d '[:space:]')
fi

SNAPSHOT_FILE=$(mktemp "$HANDOFF_DIR/.runtime-snapshot.XXXXXX") || {
  echo "[PreCompact] ERROR: Cannot create runtime snapshot."
  exit 0
}
trap 'rm -f "$SNAPSHOT_FILE"' EXIT

{
  echo "<!-- mir:runtime-snapshot:begin -->"
  echo "## Runtime Snapshot (Generated)"
  echo ""
  echo "### Active Plan Items"
  if [ -f "$PROJECT_DIR/tasks/plan.md" ]; then
    PLAN_ITEMS=$(grep -E '^- \[ \]' "$PROJECT_DIR/tasks/plan.md" 2>/dev/null | head -10 | sed 's/^- \[ \] /- /')
    if [ -n "$PLAN_ITEMS" ]; then
      printf '%s\n' "$PLAN_ITEMS"
    else
      echo "- No open plan items."
    fi
  else
    echo "- No active plan cursor."
  fi
  echo ""
  echo "### Working Tree"
  if [ -n "$WORKTREE_STATUS_COUNT" ]; then
    if [ "$WORKTREE_STATUS_COUNT" -gt 0 ]; then
      echo "- Working tree dirty ($WORKTREE_STATUS_COUNT paths; inspect git status --short)."
    else
      echo "- Working tree clean."
    fi
  else
    echo "- Git status unavailable."
  fi
  if [ -n "$LATEST_RUNNER" ] && [ -f "$LATEST_RUNNER" ]; then
    echo ""
    echo "### Runner State"
    echo "- Ledger: $RUNNER_REL"
    grep -E '^- (stage|status|last_checked_at|resume_command):' "$LATEST_RUNNER" 2>/dev/null
  fi
  if [ -n "$LATEST_DISPATCH_BRIEF" ] && [ -f "$LATEST_DISPATCH_BRIEF" ]; then
    echo ""
    echo "### Dispatch Brief"
    echo "- Brief: $DISPATCH_REL"
    python3 - "$LATEST_DISPATCH_BRIEF" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
print(f"- task_id: `{data.get('task_id', 'unknown')}`")
print(f"- slice_id: `{data.get('slice_id', 'unknown')}`")
print(f"- target_agent: `{data.get('target_agent', 'unknown')}`")
print(f"- resume_state_ref: `{data.get('resume_state_ref', 'unknown')}`")
PY
  fi
  echo "<!-- mir:runtime-snapshot:end -->"
} > "$SNAPSHOT_FILE"

if ! python3 - "$HANDOFF_FILE" "$SNAPSHOT_FILE" <<'PY'
from pathlib import Path
import sys

handoff_path = Path(sys.argv[1])
snapshot_path = Path(sys.argv[2])
begin = "<!-- mir:runtime-snapshot:begin -->"
end = "<!-- mir:runtime-snapshot:end -->"
body = handoff_path.read_text(encoding="utf-8")
while begin in body:
    prefix, remainder = body.split(begin, 1)
    if end not in remainder:
        body = prefix
        break
    _, suffix = remainder.split(end, 1)
    body = prefix.rstrip() + "\n\n" + suffix.lstrip()
snapshot = snapshot_path.read_text(encoding="utf-8").strip()
handoff_path.write_text(body.rstrip() + "\n\n" + snapshot + "\n", encoding="utf-8")
PY
then
  echo "[PreCompact] ERROR: Failed to refresh canonical handoff."
  exit 0
fi

if [ -f "$HANDOFF_FILE" ]; then
  echo "[PreCompact] Canonical handoff updated: $HANDOFF_FILE"
else
  echo "[PreCompact] ERROR: Failed to write canonical handoff."
fi
