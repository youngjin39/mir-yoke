#!/bin/bash
# tdd-guard.sh
# Block edits to implementation files (src/, app/, lib/ + recognized
# source extensions) unless tasks/tdd.json has a `change` entry whose
# `targets` array contains the path. Called by pre-tool-use.sh.

set -u

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$PWD}"
LEDGER="$PROJECT_DIR/tasks/tdd.json"
TARGET="${1:-}"

[ -n "$TARGET" ] || exit 0

# Only guard real implementation paths.
case "$TARGET" in
  src/*|app/*|lib/*) ;;
  *) exit 0 ;;
esac
case "$TARGET" in
  *.py|*.js|*.ts|*.jsx|*.tsx|*.mjs|*.cjs|*.go|*.rs|*.rb|*.kt|*.swift|*.c|*.cc|*.cpp|*.h|*.hpp|*.sql|*.java) ;;
  *) exit 0 ;;
esac

if [ ! -f "$LEDGER" ]; then
  echo "[TddGuard BLOCK] $TARGET edit requires tasks/tdd.json. Create the composite ledger and add an entry whose targets list this path." >&2
  exit 2
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "[TddGuard WARN] jq not available — ledger check skipped" >&2
  exit 0
fi

# Look for a `change` entry whose `targets` includes the path (relative or
# absolute against PROJECT_DIR).
REL="$TARGET"
case "$REL" in
  "$PROJECT_DIR"/*) REL="${REL#$PROJECT_DIR/}" ;;
esac

MATCH=$(jq -r --arg t "$REL" '.changes[]? | select((.targets // []) | index($t)) | .id' "$LEDGER" 2>/dev/null | head -1)

if [ -z "$MATCH" ]; then
  echo "[TddGuard BLOCK] No tasks/tdd.json change entry covers $REL." >&2
  echo "  Add an entry with: \"targets\": [\"$REL\"] and the 12-category matrix." >&2
  exit 2
fi

exit 0
