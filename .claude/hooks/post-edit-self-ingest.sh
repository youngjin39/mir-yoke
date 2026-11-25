#!/usr/bin/env bash
# Keep the required local memory index current after durable Markdown edits.
# Match the project-hook renderer's native availability and failed-launch policy.
project_root="${CLAUDE_PROJECT_DIR:-.}"
unavailable() {
  printf '%s\n' '[mir-memory] skipped post-edit-memory-sync: native unavailable or outdated; repair: scripts/mir.sh project-hooks install --project-root .' >&2
  exit 0
}
[ "${MIR_NATIVE_HOOKS:-1}" != 0 ] || unavailable
native="$project_root/.mir/bin/project-hooks"
if [ -f "$native" ] && [ -x "$native" ] && [ ! -L "$native" ] && \
   [ ! -L "$project_root/.mir" ] && [ ! -L "$project_root/.mir/bin" ] && \
   "$native" --mir-warmup </dev/null >/dev/null 2>&1 && \
   capabilities="$("$native" capabilities </dev/null 2>/dev/null)" && \
   printf '%s\n' "$capabilities" | grep -qx 'mir-project-hooks-post-edit-memory-sync-v1'; then
  CLAUDE_PROJECT_DIR="$project_root" "$native" post-edit-memory-sync
  result=$?
  case "$result" in
    64|126|127) unavailable ;;
    *) exit "$result" ;;
  esac
else
  unavailable
fi
