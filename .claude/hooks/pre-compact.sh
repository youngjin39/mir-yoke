#!/bin/bash
export UV_OFFLINE=1
_MIR_PYTHON_LAUNCHER="${MIR_COMPACT_PYTHON_LAUNCHER:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/_lib/run-python.sh}"
# PreCompact hook: refresh the one canonical handoff before compaction.

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
HANDOFF_DIR="$PROJECT_DIR/tasks/handoffs"
HANDOFF_FILE="$HANDOFF_DIR/session-handoff-LATEST.md"
_MIR_INVOCATION_LOG_HELPER="$(dirname "$0")/_lib/invocation_log.sh"
# shellcheck source=./_lib/invocation_log.sh
[ -f "$_MIR_INVOCATION_LOG_HELPER" ] && . "$_MIR_INVOCATION_LOG_HELPER"
if command -v mir_invocation_log_enable >/dev/null 2>&1; then
  mir_invocation_log_enable "pre-compact" "$PROJECT_DIR"
fi

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
_mir_pre_compact_on_exit() {
  local exit_code=$?
  rm -f "$SNAPSHOT_FILE"
  if command -v mir_invocation_log_flush >/dev/null 2>&1; then
    mir_invocation_log_flush "$exit_code"
  fi
}
trap _mir_pre_compact_on_exit EXIT

{
  echo "<!-- mir:runtime-snapshot:begin -->"
  echo "## Runtime Snapshot (Generated)"
  echo ""
  echo "### Active Plan Items"
  if [ -f "$PROJECT_DIR/tasks/plan.md" ]; then
    PLAN_ITEMS=$(grep -Ei '^- \[ \]|^Step [0-9]+:[[:space:]]*(in[[:space:]_-]*progress|pending|blocked|active|running|todo)([[:space:]]|$)' "$PROJECT_DIR/tasks/plan.md" 2>/dev/null | head -10 | sed 's/^- \[ \] /- /; s/^Step /- Step /')
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
    "$_MIR_PYTHON_LAUNCHER" - "$LATEST_DISPATCH_BRIEF" <<'PY'
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

if ! "$_MIR_PYTHON_LAUNCHER" - "$HANDOFF_FILE" "$SNAPSHOT_FILE" <<'PY'
import os
from pathlib import Path
import sys
import tempfile

handoff_path = Path(sys.argv[1])
snapshot_path = Path(sys.argv[2])
begin = "<!-- mir:runtime-snapshot:begin -->"
end = "<!-- mir:runtime-snapshot:end -->"
body = handoff_path.read_text(encoding="utf-8")
snapshot = snapshot_path.read_text(encoding="utf-8").strip()
begin_count = body.count(begin)
end_count = body.count(end)
if begin_count != end_count:
    raise ValueError("runtime snapshot markers are unbalanced")

if begin_count:
    chunks = []
    cursor = 0
    inserted = False
    for _ in range(begin_count):
        begin_at = body.find(begin, cursor)
        end_at = body.find(end, begin_at + len(begin))
        if begin_at < 0 or end_at < 0:
            raise ValueError("runtime snapshot markers are malformed")
        chunks.append(body[cursor:begin_at])
        if not inserted:
            chunks.append(snapshot)
            inserted = True
        cursor = end_at + len(end)
    chunks.append(body[cursor:])
    rendered = "".join(chunks)
else:
    separator = "" if body.endswith("\n\n") else "\n" if body.endswith("\n") else "\n\n"
    rendered = body + separator + snapshot + "\n"

descriptor, temp_name = tempfile.mkstemp(
    prefix=f".{handoff_path.name}.", dir=handoff_path.parent
)
try:
    os.close(descriptor)
    temp_path = Path(temp_name)
    temp_path.write_text(rendered, encoding="utf-8")
    os.replace(temp_path, handoff_path)
finally:
    Path(temp_name).unlink(missing_ok=True)
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
