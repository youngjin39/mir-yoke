#!/bin/bash
# Optional TDD advisory: report missing composite TDD evidence without blocking edits.
# tier: warn — invoke directly when ledger guidance is useful.
_MIR_HOOK_TIER="warn"

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
TARGET_PATH="${1:-}"
TDD_MATRIX_GUARD_SCRIPT="$PROJECT_DIR/.claude/hooks/tdd-matrix-guard.py"

normalize_path() {
  local path="$1"
  path="${path#./}"
  if [[ "$path" == "$PROJECT_DIR/"* ]]; then
    path="${path#"$PROJECT_DIR"/}"
  fi
  printf '%s' "$path"
}

is_implementation_file() {
  local path="$1"
  case "$path" in
    src/*|app/*|lib/*)
      ;;
    *)
      return 1
      ;;
  esac
  case "$path" in
    *.py|*.js|*.ts|*.jsx|*.tsx|*.rb|*.go|*.rs|*.java|*.kt|*.swift|*.c|*.cc|*.cpp|*.h|*.hpp|*.sql)
      return 0
      ;;
  esac
  return 1
}

main() {
  [ -n "$TARGET_PATH" ] || exit 0
  cd "$PROJECT_DIR" || exit 0
  local rel
  rel="$(normalize_path "$TARGET_PATH")"
  if ! is_implementation_file "$rel"; then
    exit 0
  fi
  if [ -f "$TDD_MATRIX_GUARD_SCRIPT" ]; then
    if ! python3 "$TDD_MATRIX_GUARD_SCRIPT" prewrite "$PROJECT_DIR" "$rel" >/dev/null 2>&1; then
      echo "[TddGuard WARN] composite TDD evidence is incomplete for $rel (advisory only)" >&2
    fi
  else
    echo "[TddGuard WARN] Missing helper: $TDD_MATRIX_GUARD_SCRIPT (advisory only)" >&2
  fi
  exit 0
}

main "$@"
