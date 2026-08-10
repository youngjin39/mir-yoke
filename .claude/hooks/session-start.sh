#!/bin/bash
_MIR_PYTHON_LAUNCHER="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/_lib/run-python.sh"
_MIR_HOOK_TIER="warn"
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
_MIR_BOOTSTRAP_GATE="$(dirname "$_MIR_PYTHON_LAUNCHER")/bootstrap-gate.sh"
# shellcheck source=./_lib/bootstrap-gate.sh
[ -f "$_MIR_BOOTSTRAP_GATE" ] && . "$_MIR_BOOTSTRAP_GATE"
_MIR_BOOTSTRAP_READY=no
_MIR_BOOTSTRAP_STATE=missing
if command -v mir_bootstrap_gate_state >/dev/null 2>&1; then
  if _MIR_BOOTSTRAP_STATE="$(mir_bootstrap_gate_state "$PROJECT_DIR")"; then
    _MIR_BOOTSTRAP_READY=yes
  fi
fi
_mir_session_body() {
# SessionStart hook: inject startup context into the session
# stdout → Claude's context window
# ADR-53: task-blind startup includes only repository identity, mandatory safety,
# and an on-demand retrieval hint. Task-specific context is pulled after classification.

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"

# SessionStart is read-only. Cursor cleanup is an explicit operator task; startup must
# never mutate tasks/plan.md or create archive files in either main or delegated worktrees.

echo "=== SESSION CONTEXT ==="

if [ "$_MIR_BOOTSTRAP_READY" != yes ]; then
  mir_bootstrap_gate_instructions "$_MIR_BOOTSTRAP_STATE" "$PROJECT_DIR"
  return 0
fi

if [ -f "$PROJECT_DIR/scripts/build_session_upfront_context.py" ]; then
  _UPFRONT=$("$_MIR_PYTHON_LAUNCHER" "$PROJECT_DIR/scripts/build_session_upfront_context.py" "$PROJECT_DIR" 2>/dev/null)
  echo "$_UPFRONT"
  echo ""
else
  echo "repository_profile: unavailable"
  echo "mandatory_safety: inspect repository-local instructions before mutation"
  echo "Context depth on demand: scripts/mir.sh context pull \"<query>\" (--history for archived/expired)"
  echo ""
fi

}

# mir:f3:stdout-cap:begin
# token-efficiency F3 (2026-06-10): template-parity 10,240B stdout cap (UTF-8 safe).
if [ "$_MIR_BOOTSTRAP_READY" != yes ]; then
  _mir_session_body "$@"
else
  _mir_session_body "$@" | "$_MIR_PYTHON_LAUNCHER" -c '
import sys
data = sys.stdin.buffer.read()
limit = 10240
if len(data) <= limit:
    sys.stdout.buffer.write(data)
else:
    cut = data[: limit - 64].decode("utf-8", errors="ignore")
    sys.stdout.write(cut + "\n[mir] session-start context truncated at 10KB (F3 cap)\n")
'
fi
# mir:f3:stdout-cap:end
