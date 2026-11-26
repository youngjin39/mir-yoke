#!/bin/bash
# Optional TDD advisory: report missing composite TDD evidence without blocking edits.
# tier: warn — invoke directly when ledger guidance is useful.
_MIR_HOOK_TIER="warn"

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
TARGET_PATH="${1:-}"
native="$PROJECT_DIR/.mir/bin/project-hooks"

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
    src/*|app/*|apps/*|packages/*|pipelines/*|infra/*|content/*|lib/*)
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
  if [ "${MIR_NATIVE_HOOKS:-1}" != 0 ] && \
     [ -f "$native" ] && [ -x "$native" ] && [ ! -L "$native" ] && \
     [ ! -L "$PROJECT_DIR/.mir" ] && [ ! -L "$PROJECT_DIR/.mir/bin" ] && \
     "$native" --mir-warmup </dev/null >/dev/null 2>&1 && \
     capabilities="$("$native" capabilities </dev/null 2>/dev/null)" && \
     printf '%s\n' "$capabilities" | grep -qx 'mir-project-hooks-tdd-v1'; then
    if ! "$native" tdd-matrix prewrite "$PROJECT_DIR" "$rel" >/dev/null 2>&1; then
      echo "[TddGuard WARN] composite TDD evidence is incomplete for $rel (advisory only)" >&2
    fi
  else
    echo "[TddGuard WARN] Native TDD validation unavailable (advisory only)" >&2
  fi
  exit 0
}

main "$@"
