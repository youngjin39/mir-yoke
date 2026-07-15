#!/bin/bash
_MIR_HOOK_TIER="warn"
_mir_session_body() {
# SessionStart hook: inject startup context into the session
# stdout → Claude's context window
# ADR-53: task-blind startup includes only repository identity, mandatory safety,
# and an on-demand retrieval hint. Task-specific context is pulled after classification.

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"

# SessionStart is read-only. Cursor cleanup is an explicit operator task; startup must
# never mutate tasks/plan.md or create archive files in either main or delegated worktrees.

echo "=== SESSION CONTEXT ==="

if [ -f "$PROJECT_DIR/scripts/build_session_upfront_context.py" ]; then
  _UPFRONT=$(python3 "$PROJECT_DIR/scripts/build_session_upfront_context.py" "$PROJECT_DIR" 2>/dev/null)
  echo "$_UPFRONT"
  echo ""
else
  echo "repository_profile: unavailable"
  echo "mandatory_safety: inspect repository-local instructions before mutation"
  echo "Context depth on demand: uv run mir context pull \"<query>\" (--history for archived/expired)"
  echo ""
fi

}

# mir:f3:stdout-cap:begin
# token-efficiency F3 (2026-06-10): template-parity 10,240B stdout cap (UTF-8 safe).
_mir_session_body "$@" | python3 -c '
import sys
data = sys.stdin.buffer.read()
limit = 10240
if len(data) <= limit:
    sys.stdout.buffer.write(data)
else:
    cut = data[: limit - 64].decode("utf-8", errors="ignore")
    sys.stdout.write(cut + "\n[mir] session-start context truncated at 10KB (F3 cap)\n")
'
# mir:f3:stdout-cap:end
