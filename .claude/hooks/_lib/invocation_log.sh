#!/bin/bash
_MIR_PYTHON_LAUNCHER="${_MIR_PYTHON_LAUNCHER:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/run-python.sh}"
# Best-effort hook invocation log writer for phase-6 usage telemetry.

_mir_invocation_log_now_ms() {
  "$_MIR_PYTHON_LAUNCHER" - <<'PY' 2>/dev/null || return 1
import time

print(int(time.time() * 1000))
PY
}

mir_invocation_log_enable() {
  [ $# -ge 2 ] || return 0
  MIR_INVOCATION_LOG_HOOK_NAME="$1"
  MIR_INVOCATION_LOG_PROJECT_DIR="$2"
  MIR_INVOCATION_LOG_STARTED_AT_MS="$(_mir_invocation_log_now_ms 2>/dev/null || true)"
  trap 'mir_invocation_log_flush "$?"' EXIT
}

mir_invocation_log_flush() {
  local exit_code="${1:-0}"
  [ -n "${MIR_INVOCATION_LOG_HOOK_NAME:-}" ] || return 0

  local project_dir="${MIR_INVOCATION_LOG_PROJECT_DIR:-.}"
  local log_dir="$project_dir/.claude/hooks/state"
  mkdir -p "$log_dir" 2>/dev/null || return 0

  MIR_INVOCATION_LOG_PATH="$log_dir/invocations.jsonl" \
  MIR_INVOCATION_LOG_HOOK_NAME="$MIR_INVOCATION_LOG_HOOK_NAME" \
  MIR_INVOCATION_LOG_EXIT_CODE="$exit_code" \
  MIR_INVOCATION_LOG_STARTED_AT_MS="${MIR_INVOCATION_LOG_STARTED_AT_MS:-}" \
  "$_MIR_PYTHON_LAUNCHER" - <<'PY' >/dev/null 2>&1 || true
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time


def _int_env(name: str) -> int | None:
    raw = os.environ.get(name, "")
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


path = Path(os.environ["MIR_INVOCATION_LOG_PATH"])
started_ms = _int_env("MIR_INVOCATION_LOG_STARTED_AT_MS")
now_ms = int(time.time() * 1000)
if started_ms is None or started_ms > now_ms:
    started_ms = now_ms

record = {
    "ts": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    "kind": "hook",
    "name": os.environ["MIR_INVOCATION_LOG_HOOK_NAME"],
    "exit_code": _int_env("MIR_INVOCATION_LOG_EXIT_CODE") or 0,
    "duration_ms": max(now_ms - started_ms, 0),
}

with path.open("a", encoding="utf-8") as handle:
    json.dump(record, handle, separators=(",", ":"))
    handle.write("\n")
PY
}
