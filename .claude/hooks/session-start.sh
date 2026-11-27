#!/usr/bin/env bash
# Render read-only startup context and its output budget in the native handler.
# Match the project-hook renderer's native availability and failed-launch policy.
project_root="${CLAUDE_PROJECT_DIR:-.}"
unavailable() {
  printf '%s\n' '[SessionStart] native context unavailable; inspect repository-local instructions before mutation.' >&2
  printf '%s\n' '=== SESSION CONTEXT ==='
  local gate state=unknown
  gate="$(dirname -- "${BASH_SOURCE[0]}")/_lib/bootstrap-gate.sh"
  if [ -f "$gate" ]; then
    . "$gate"
    if state="$(mir_bootstrap_gate_state "$project_root")"; then
      printf 'bootstrap_gate: ready (state=%s)\n' "$state"
    else
      mir_bootstrap_gate_instructions "$state" "$project_root"
    fi
  else
    printf '%s\n' 'bootstrap_gate: unknown; verify bootstrap before mutation'
  fi
  printf '%s\n' 'native_repair_command: scripts/mir.sh project-hooks install --project-root .'
  printf '%s\n' 'mandatory_safety: inspect repository-local instructions before mutation'
  # Read declarations only, never secret files. Show the complete profile so
  # quoted keys and multiline safety arrays need no second TOML parser.
  local profile="$project_root/.mir/repo-profile.toml" profile_bytes
  if [ -L "$project_root/.mir" ] || [ -L "$profile" ]; then
    printf '%s\n' 'repository_safety_declarations: unavailable (linked profile path)'
  elif [ ! -f "$profile" ] || [ ! -r "$profile" ]; then
    printf '%s\n' 'repository_safety_declarations: unavailable (expected a readable regular profile)'
  elif profile_bytes="$(wc -c 2>/dev/null <"$profile")" && [ "$profile_bytes" -le 65536 ]; then
    printf '%s\n' 'repository_safety_declarations (TOML):'
    cat -- "$profile"
  else
    printf '%s\n' 'repository_safety_declarations: unavailable (profile size unavailable or exceeds 65536 bytes)'
  fi
  exit 0
}
[ "${MIR_NATIVE_HOOKS:-1}" != 0 ] || unavailable
native="$project_root/.mir/bin/project-hooks"
if [ -f "$native" ] && [ -x "$native" ] && [ ! -L "$native" ] && \
   [ ! -L "$project_root/.mir" ] && [ ! -L "$project_root/.mir/bin" ] && \
   "$native" --mir-warmup </dev/null >/dev/null 2>&1 && \
   capabilities="$("$native" capabilities </dev/null 2>/dev/null)" && \
   printf '%s\n' "$capabilities" | grep -qx 'mir-project-hooks-session-start-v2'; then
  CLAUDE_PROJECT_DIR="$project_root" "$native" session-start
  result=$?
  case "$result" in
    64|126|127) unavailable ;;
    *) exit "$result" ;;
  esac
else
  unavailable
fi
