#!/usr/bin/env bash
# Render read-only startup context and its output budget in the native handler.
# Match the project-hook renderer's native availability and failed-launch policy.
project_root="${CLAUDE_PROJECT_DIR:-.}"
unavailable() {
  printf '%s\n' 'project-hooks: native unavailable' >&2
  exit 0
}
[ "${MIR_NATIVE_HOOKS:-1}" != 0 ] || unavailable
native="$project_root/.mir/bin/project-hooks"
if [ -f "$native" ] && [ -x "$native" ] && [ ! -L "$native" ] && \
   [ ! -L "$project_root/.mir" ] && [ ! -L "$project_root/.mir/bin" ] && \
   "$native" --mir-warmup </dev/null >/dev/null 2>&1; then
  CLAUDE_PROJECT_DIR="$project_root" "$native" session-start
  result=$?
  case "$result" in
    64|126|127) unavailable ;;
    *) exit "$result" ;;
  esac
else
  unavailable
fi
