#!/bin/bash
_MIR_PYTHON_LAUNCHER="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/_lib/run-python.sh"
# mir-stop.sh
# Claude Stop hook: write audit log entry to tasks/sessions/stop-<ISO8601>-<pid>-<rand>.log.
# ADR: docs/decisions/p0j2-claude-stop-hook-2026-05-09.md (Alternative C, MVP audit-only).
# NEVER exits non-zero — Stop hook must never block session termination.

set -u

SESSIONS_DIR="${CLAUDE_PROJECT_DIR:-.}/tasks/sessions"

# W1 fix: read stdin into variable, then pipe to "$_MIR_PYTHON_LAUNCHER" via stdin (avoids ARG_MAX limit).
STDIN_DATA=$(cat)

# Write the python helper to a temp file so we can both pipe STDIN_DATA and run python code.
# This avoids the bash limitation where heredoc and pipe both claim stdin.
_PY_TMP=$(mktemp /tmp/mir-stop-XXXXXX.py)
cat > "$_PY_TMP" <<'PYEOF'
import json
import os
import pathlib
import sys
import datetime

sessions_dir = pathlib.Path(sys.argv[1])

# W1 fix: read JSON from stdin (piped), not argv[2].
raw = sys.stdin.read()

try:
    event = json.loads(raw) if raw.strip() else {}
    parse_ok = True
    parse_error = ""
except Exception as exc:
    event = {}
    parse_ok = False
    parse_error = str(exc)

# I1 fix: single timestamp at top, reused for filename and content.
ts_dt = datetime.datetime.now(datetime.timezone.utc)
ts = ts_dt.strftime("%Y%m%dT%H%M%SZ")
ts_iso = ts_dt.isoformat()

# W2 fix: include PID and 6-char random hex to prevent same-second filename collision.
pid = os.getpid()
rand_hex = os.urandom(3).hex()
log_filename = f"stop-{ts}-{pid}-{rand_hex}.log"

sessions_dir.mkdir(parents=True, exist_ok=True)
log_path = sessions_dir / log_filename

stop_hook_active = event.get("stop_hook_active", "")
last_msg = str(event.get("last_assistant_message", ""))[:500]
cwd = event.get("cwd", os.environ.get("CLAUDE_PROJECT_DIR", ""))
hook_event_name = event.get("hook_event_name", "Stop")

if parse_ok:
    lines = [
        f"timestamp: {ts_iso}",
        f"stop_hook_active: {stop_hook_active!r}",
        f"last_assistant_message_snippet: {last_msg!r}",
        f"cwd: {cwd!r}",
        f"hook_event_name: {hook_event_name!r}",
    ]
else:
    lines = [
        f"timestamp: {ts_iso}",
        f"parse_error: {parse_error!r}",
        "stop_hook_active: parse-failure",
    ]

# I2 fix: wrap write_text in try/except OSError to avoid traceback on read-only dirs.
try:
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
except OSError as e:
    print(f"mir-stop: warning: could not write audit log: {e}", file=sys.stderr)
PYEOF

if ! printf '%s' "$STDIN_DATA" | "$_MIR_PYTHON_LAUNCHER" "$_PY_TMP" "$SESSIONS_DIR"; then
    : # "$_MIR_PYTHON_LAUNCHER" failed — log nothing, still exit 0
fi

rm -f "$_PY_TMP"

# P2.5: optional review gate — gated by MIR_REVIEW_GATE env var.
# ADR: docs/decisions/p2-5-l5-review-gate-2026-05-10.md (Alternative B).
# NEVER blocks exit 0 — all executor errors are silenced with || true.
if [ "${MIR_REVIEW_GATE:-0}" = "1" ]; then
    _REVIEW_TS="$(date -u +%Y%m%dT%H%M%SZ 2>/dev/null || printf 'ts')"
    _LAST_MSG_HASH="$(printf '%s' "${STDIN_DATA}" | shasum 2>/dev/null | cut -c1-12 || printf 'nohash')"
    "$_MIR_PYTHON_LAUNCHER" -m tools.mir_executor execute \
        --background \
        --change-id "auto-review-${_REVIEW_TS}-${_LAST_MSG_HASH}" \
        --category review \
        --codex-args "exec --review" \
        --family your-harness \
        2>/dev/null || true
fi

exit 0
