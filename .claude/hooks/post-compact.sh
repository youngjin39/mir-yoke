#!/bin/bash
export UV_OFFLINE=1
_MIR_PYTHON_LAUNCHER="${MIR_COMPACT_PYTHON_LAUNCHER:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/_lib/run-python.sh}"
# PostCompact validates the checkpoint. Its stdout is not recovery context.

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
HANDOFF_FILE="$PROJECT_DIR/tasks/handoffs/session-handoff-LATEST.md"
_MIR_INVOCATION_LOG_HELPER="$(dirname "$0")/_lib/invocation_log.sh"
# shellcheck source=./_lib/invocation_log.sh
[ -f "$_MIR_INVOCATION_LOG_HELPER" ] && . "$_MIR_INVOCATION_LOG_HELPER"
if command -v mir_invocation_log_enable >/dev/null 2>&1; then
  mir_invocation_log_enable "post-compact" "$PROJECT_DIR"
fi

VALIDATION_ERROR=$("$_MIR_PYTHON_LAUNCHER" - "$HANDOFF_FILE" <<'PY' 2>/dev/null
from pathlib import Path
import sys

path = Path(sys.argv[1])
begin = "<!-- mir:runtime-snapshot:begin -->"
end = "<!-- mir:runtime-snapshot:end -->"

try:
    body = path.read_text(encoding="utf-8")
except FileNotFoundError:
    print("canonical handoff is missing")
except (OSError, UnicodeError) as exc:
    print(f"canonical handoff is unreadable: {type(exc).__name__}")
else:
    begin_count = body.count(begin)
    end_count = body.count(end)
    if begin_count != 1 or end_count != 1:
        print(
            "runtime snapshot markers must appear exactly once "
            f"(begin={begin_count}, end={end_count})"
        )
    elif body.index(begin) > body.index(end):
        print("runtime snapshot begin marker must precede the end marker")
PY
)
validation_status=$?

if [ "$validation_status" -ne 0 ] && [ -z "$VALIDATION_ERROR" ]; then
  VALIDATION_ERROR="canonical handoff validation could not run"
fi

if [ -n "$VALIDATION_ERROR" ]; then
  WARNING="[mir] PostCompact degraded: session-handoff-LATEST.md — $VALIDATION_ERROR"
  if ! "$_MIR_PYTHON_LAUNCHER" - "$WARNING" <<'PY'
import json
import sys

print(json.dumps({"continue": True, "systemMessage": sys.argv[1]}, ensure_ascii=False))
PY
  then
    printf '{"continue":true,"systemMessage":"[mir] PostCompact degraded: canonical handoff validation failed"}\n'
  fi
fi

exit 0
