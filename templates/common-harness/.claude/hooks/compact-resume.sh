#!/bin/bash
export UV_OFFLINE=1
_MIR_PYTHON_LAUNCHER="${MIR_COMPACT_PYTHON_LAUNCHER:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/_lib/run-python.sh}"
# SessionStart(source=compact) injects the bounded canonical recovery context.

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
HANDOFF_FILE="$PROJECT_DIR/tasks/handoffs/session-handoff-LATEST.md"
MAX_CONTEXT_BYTES=8192
INPUT=$(cat 2>/dev/null || true)
SOURCE=$(printf '%s' "$INPUT" | "$_MIR_PYTHON_LAUNCHER" -c '
import json
import sys

try:
    payload = json.load(sys.stdin)
except (json.JSONDecodeError, TypeError):
    raise SystemExit(0)
source = payload.get("source")
if isinstance(source, str):
    print(source)
' 2>/dev/null)

[ "$SOURCE" = "compact" ] || exit 0

_MIR_INVOCATION_LOG_HELPER="$(dirname "$0")/_lib/invocation_log.sh"
# shellcheck source=./_lib/invocation_log.sh
[ -f "$_MIR_INVOCATION_LOG_HELPER" ] && . "$_MIR_INVOCATION_LOG_HELPER"
if command -v mir_invocation_log_enable >/dev/null 2>&1; then
  mir_invocation_log_enable "compact-resume" "$PROJECT_DIR"
fi

if ! "$_MIR_PYTHON_LAUNCHER" - "$HANDOFF_FILE" "$MAX_CONTEXT_BYTES" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
limit = int(sys.argv[2])
header = "=== MIR COMPACTION RECOVERY CONTEXT ===\ncanonical_source: tasks/handoffs/session-handoff-LATEST.md\n\n"
footer = "\n=== END MIR COMPACTION RECOVERY CONTEXT ===\n"
truncation = "\n[mir] recovery context truncated at 8192 bytes\n"

try:
    body = path.read_text(encoding="utf-8").strip()
except FileNotFoundError:
    body = "[mir] canonical handoff is missing; inspect repository state before continuing."
except (OSError, UnicodeError) as exc:
    body = f"[mir] canonical handoff is unreadable ({type(exc).__name__}); inspect repository state before continuing."

full = (header + body + footer).encode("utf-8")
if len(full) <= limit:
    sys.stdout.buffer.write(full)
    raise SystemExit(0)

fixed_size = len((header + truncation + footer).encode("utf-8"))
available = max(limit - fixed_size, 0)
clipped = body.encode("utf-8")[:available].decode("utf-8", errors="ignore")
payload = (header + clipped + truncation + footer).encode("utf-8")
sys.stdout.buffer.write(payload[:limit])
PY
then
  printf '%s\n' \
    '=== MIR COMPACTION RECOVERY CONTEXT ===' \
    '[mir] canonical handoff recovery failed; inspect repository state before continuing.' \
    '=== END MIR COMPACTION RECOVERY CONTEXT ==='
fi

exit 0
