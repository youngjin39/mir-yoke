#!/bin/bash
# mir-stop.sh
# Claude Stop hook: write audit log entry to tasks/sessions/stop-<ISO8601>-<pid>-<rand>.log.
# Optional Stop hook — implement per your harness. Alternative C: MVP audit-only mode.
# NEVER exits non-zero — Stop hook must never block session termination.

set -u

SESSIONS_DIR="${CLAUDE_PROJECT_DIR:-.}/tasks/sessions"

# W1 fix: read stdin into variable, then pipe to python3 via stdin (avoids ARG_MAX limit).
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

if ! printf '%s' "$STDIN_DATA" | python3 "$_PY_TMP" "$SESSIONS_DIR"; then
    : # python3 failed — log nothing, still exit 0
fi

rm -f "$_PY_TMP"

# Optional: implement your own review gate here.
# Example: if [ "${HARNESS_REVIEW_GATE:-0}" = "1" ]; then
#   <invoke your review tool or script>
# fi

exit 0
