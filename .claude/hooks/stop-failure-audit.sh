#!/bin/bash
_MIR_PYTHON_LAUNCHER="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/_lib/run-python.sh"
# stop-failure-audit.sh
# ADR-06 Phase 6D: Claude StopFailure hook. Records turn-level API errors
# (rate_limit / server_error / authentication_failed / etc.) to
# tasks/sessions/stop-failure-<ISO8601>-<pid>-<rand>.log.
# NEVER exits non-zero — StopFailure hook output is ignored per code.claude.com/docs.
# Stall detection itself is owned by tools/stall_watchdog/ (ADR-06 §2).

set -u

SESSIONS_DIR="${CLAUDE_PROJECT_DIR:-.}/tasks/sessions"

STDIN_DATA=$(cat)

_PY_TMP=$(mktemp /tmp/mir-stopfailure-XXXXXX.py)
cat > "$_PY_TMP" <<'PYEOF'
import json
import os
import pathlib
import sys
import datetime

sessions_dir = pathlib.Path(sys.argv[1])
raw = sys.stdin.read()

try:
    event = json.loads(raw) if raw.strip() else {}
    parse_ok = True
    parse_error = ""
except Exception as exc:
    event = {}
    parse_ok = False
    parse_error = str(exc)

ts_dt = datetime.datetime.now(datetime.timezone.utc)
ts = ts_dt.strftime("%Y%m%dT%H%M%SZ")
ts_iso = ts_dt.isoformat()

pid = os.getpid()
rand_hex = os.urandom(3).hex()
log_filename = f"stop-failure-{ts}-{pid}-{rand_hex}.log"

try:
    sessions_dir.mkdir(parents=True, exist_ok=True)
except OSError as exc:
    sys.stderr.write(f"[mir stop-failure-audit] cannot create dir: {exc}\n")
    sys.exit(0)

log_path = sessions_dir / log_filename

payload = {
    "hook": "StopFailure",
    "ts": ts_iso,
    "parse_ok": parse_ok,
    "parse_error": parse_error,
    "session_id": event.get("session_id"),
    "error_type": event.get("error_type"),
    "hook_event_name": event.get("hook_event_name"),
    "cwd": event.get("cwd"),
    "transcript_path": event.get("transcript_path"),
    "raw_keys": sorted(event.keys()) if isinstance(event, dict) else [],
}

try:
    log_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
except OSError as exc:
    sys.stderr.write(f"[mir stop-failure-audit] cannot write log: {exc}\n")

# Always exit 0 — StopFailure hook output is ignored by Claude Code per docs.
sys.exit(0)
PYEOF

printf '%s' "$STDIN_DATA" | "$_MIR_PYTHON_LAUNCHER" "$_PY_TMP" "$SESSIONS_DIR" || true
rm -f "$_PY_TMP"
exit 0
