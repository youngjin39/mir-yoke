#!/usr/bin/env bash
# Startup gate shared by SessionStart and mutation hooks.

mir_bootstrap_gate_state() {
  local project_dir="${1:-${CLAUDE_PROJECT_DIR:-.}}"
  local profile="$project_dir/.mir/repo-profile.toml"
  local receipt="$project_dir/.mir/bootstrap-receipt.json"

  if [ -f "$profile" ] && grep -Eq '^[[:space:]]*repository_type[[:space:]]*=[[:space:]]*"public_harness_template"' "$profile"; then
    printf 'template_maintainer\n'
    return 0
  fi
  if [ ! -f "$receipt" ]; then
    printf 'missing\n'
    return 1
  fi
  if ! command -v jq >/dev/null 2>&1; then
    printf 'invalid\n'
    return 1
  fi
  local status
  status="$(jq -r '.status // "invalid"' "$receipt" 2>/dev/null || printf 'invalid')"
  printf '%s\n' "$status"
  [ "$status" = "ready" ]
}

mir_bootstrap_gate_instructions() {
  local state="$1"
  local project_dir="${2:-${CLAUDE_PROJECT_DIR:-.}}"
  printf 'bootstrap_gate: required (state=%s)\n' "$state"
  printf 'normal_mutation: blocked until .mir/bootstrap-receipt.json has status=ready\n'
  if [ -f "$project_dir/config/bootstrap-adoption.json" ]; then
    printf 'existing_repository: complete tracked adoption evidence, then run uv run mir bootstrap-adoption --apply\n'
  else
    printf 'phase_1: run setup.sh/setup.ps1 with --profile, --purpose, and --stack\n'
    printf 'phase_2: restart, run mir-core:design then mir-core:spec-architect, write coverage/gap evidence, and finalize\n'
  fi
}

_mir_bootstrap_allowed_path() {
  local normalized="${1//\\//}"
  local project_dir="${2:-${CLAUDE_PROJECT_DIR:-.}}"
  local project_normalized="${project_dir//\\//}"
  normalized="${normalized#./}"
  if [ "${normalized#"$project_normalized"/}" != "$normalized" ]; then
    normalized="${normalized#"$project_normalized"/}"
  fi
  case "$normalized" in
    spec/*|*/spec/*|config/bootstrap-adoption.json|config/content-onboarding.json)
      return 0
      ;;
  esac
  local manifest="$project_dir/config/bootstrap-adoption.json"
  if [ -f "$manifest" ] && command -v jq >/dev/null 2>&1; then
    jq -e --arg path "$normalized" '[.surfaces[]?.evidence_paths[]?] | index($path) != null' "$manifest" >/dev/null 2>&1 && return 0
  fi
  return 1
}

_mir_bootstrap_patch_paths_allowed() {
  local patch="$1"
  local project_dir="${2:-${CLAUDE_PROJECT_DIR:-.}}"
  local paths found_path path
  paths="$(printf '%s\n' "$patch" | sed -nE 's/^\*\*\* (Add|Update|Delete) File: (.*)$/\2/p')"
  [ -n "$paths" ] || return 1
  found_path=no
  while IFS= read -r path; do
    [ -n "$path" ] || continue
    found_path=yes
    _mir_bootstrap_allowed_path "$path" "$project_dir" || return 1
  done <<EOF
$paths
EOF
  [ "$found_path" = yes ]
}

mir_bootstrap_gate_enforce() {
  local payload="$1"
  local project_dir="${2:-${CLAUDE_PROJECT_DIR:-.}}"
  local state
  state="$(mir_bootstrap_gate_state "$project_dir")" && return 0

  command -v jq >/dev/null 2>&1 || {
    printf '[BootstrapGate BLOCK] jq is required to inspect an incomplete bootstrap\n' >&2
    return 2
  }
  local tool_name
  tool_name="$(printf '%s' "$payload" | jq -r '.tool_name // ""' 2>/dev/null)"
  case "$tool_name" in
    Bash)
      local command
      command="$(printf '%s' "$payload" | jq -r '.tool_input.command // ""')"
      if printf '%s\n' "$command" | grep -Eq '(^|[;&|][[:space:]]*)apply_patch[[:space:]]*<<'; then
        _mir_bootstrap_patch_paths_allowed "$command" "$project_dir" && return 0
      elif printf '%s' "$command" | grep -Eq '(^|[[:space:]])(\./setup\.sh|\.\\setup\.ps1|uv[[:space:]]+run.*[[:space:]](mir[[:space:]]+(bootstrap-adoption|bootstrap|memory|context|capability)|pytest|ruff)|git[[:space:]]+(status|diff)|rg([[:space:]]|$)|find[[:space:]]|ls([[:space:]]|$)|pwd([[:space:]]|$)|sed[[:space:]]|head[[:space:]]|tail[[:space:]]|jq[[:space:]])'; then
        return 0
      fi
      ;;
    Write|Edit)
      local path
      path="$(printf '%s' "$payload" | jq -r '.tool_input.file_path // .tool_input.path // ""')"
      _mir_bootstrap_allowed_path "$path" "$project_dir" && return 0
      ;;
    apply_patch|ApplyPatch)
      local patch
      patch="$(printf '%s' "$payload" | jq -r '.tool_input.input // .tool_input.patch // .tool_input.content // ""')"
      _mir_bootstrap_patch_paths_allowed "$patch" "$project_dir" && return 0
      ;;
  esac
  printf '[BootstrapGate BLOCK] bootstrap is %s; normal work must wait for Phase 2 ready receipt\n' "$state" >&2
  printf '[BootstrapGate BLOCK] only setup/adoption, memory/spec verification, and declared evidence edits are allowed\n' >&2
  return 2
}
