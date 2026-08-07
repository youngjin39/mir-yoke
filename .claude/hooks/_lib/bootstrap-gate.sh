#!/usr/bin/env bash
# Startup gate shared by SessionStart and mutation hooks.

_mir_bootstrap_sha256() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    return 1
  fi
}

mir_bootstrap_gate_state() {
  local project_dir="${1:-${CLAUDE_PROJECT_DIR:-.}}"
  local profile="$project_dir/.mir/repo-profile.toml"
  local receipt="$project_dir/.mir/bootstrap-receipt.json"

  if [ -f "$profile" ] && [ ! -L "$profile" ] && \
     grep -Eq '^[[:space:]]*slug[[:space:]]*=[[:space:]]*"mir-yoke"' "$profile" && \
     grep -Eq '^[[:space:]]*repository_type[[:space:]]*=[[:space:]]*"public_harness_template"' "$profile"; then
    local template_origin
    template_origin="$(git -C "$project_dir" remote get-url origin 2>/dev/null || true)"
    case "$template_origin" in
      https://github.com/youngjin39/mir-yoke.git|git@github.com:youngjin39/mir-yoke.git)
        printf 'template_maintainer\n'
        return 0
        ;;
    esac
  fi
  if [ ! -f "$receipt" ]; then
    printf 'missing\n'
    return 1
  fi
  if [ -L "$receipt" ]; then
    printf 'invalid\n'
    return 1
  fi
  if ! command -v jq >/dev/null 2>&1; then
    printf 'invalid\n'
    return 1
  fi
  local status
  status="$(jq -r '.status // "invalid"' "$receipt" 2>/dev/null || printf 'invalid')"
  local receipt_mode
  receipt_mode="$(jq -r '.mode // ""' "$receipt" 2>/dev/null)"
  if [ "$status" = "ready" ] && { [ "$receipt_mode" = "existing_repository_adoption" ] || [ -e "$project_dir/config/bootstrap-adoption.json" ]; }; then
    local manifest="$project_dir/config/bootstrap-adoption.json"
    local manifest_hash receipt_hash manifest_source receipt_source
    [ -f "$manifest" ] && [ ! -L "$manifest" ] || status=invalid
    manifest_hash="$(_mir_bootstrap_sha256 "$manifest")" || status=invalid
    receipt_hash="$(jq -r '.manifest.sha256 // ""' "$receipt" 2>/dev/null)"
    manifest_source="$(jq -r '.mir_yoke_source_commit // ""' "$manifest" 2>/dev/null)"
    receipt_source="$(jq -r '.source.mir_yoke_commit // ""' "$receipt" 2>/dev/null)"
    if [ -z "$manifest_hash" ] || [ "$manifest_hash" != "$receipt_hash" ] || \
       [ -z "$manifest_source" ] || [ "$manifest_source" != "$receipt_source" ]; then
      status=invalid
    fi
    if [ "$status" = "ready" ]; then
      local declared_paths receipt_paths evidence_rows evidence_path evidence_hash actual_hash
      declared_paths="$(jq -r '[.surfaces[]?.evidence_paths[]?] | unique | sort | .[]' "$manifest" 2>/dev/null)"
      receipt_paths="$(jq -r '[.evidence[]?.path] | sort | .[]' "$receipt" 2>/dev/null)"
      evidence_rows="$(jq -r '.evidence[]? | [.path, .sha256] | @tsv' "$receipt" 2>/dev/null)"
      jq -e '.evidence | type == "array" and length > 0 and all(.[]; (.path | type == "string") and (.sha256 | type == "string" and test("^[0-9a-f]{64}$")))' "$receipt" >/dev/null 2>&1 || status=invalid
      [ -n "$declared_paths" ] && [ "$declared_paths" = "$receipt_paths" ] || status=invalid
      while IFS=$'\t' read -r evidence_path evidence_hash; do
        [ "$status" = "ready" ] || break
        [ -n "$evidence_path" ] && [ -n "$evidence_hash" ] || {
          status=invalid
          break
        }
        case "$evidence_path" in
          /*|../*|*/../*|*/..)
            status=invalid
            break
            ;;
        esac
        [ -f "$project_dir/$evidence_path" ] && [ ! -L "$project_dir/$evidence_path" ] || {
          status=invalid
          break
        }
        actual_hash="$(_mir_bootstrap_sha256 "$project_dir/$evidence_path")" || {
          status=invalid
          break
        }
        [ "$actual_hash" = "$evidence_hash" ] || status=invalid
      done <<EOF
$evidence_rows
EOF
    fi
  elif [ "$status" = "ready" ]; then
    local output_rows output_path output_hash actual_hash
    jq -e '
      .capabilities.status == "ready" and
      .architecture_initialization.attested == true and
      (.architecture_initialization.evidence.output_hashes | type == "object") and
      (.architecture_initialization.evidence.output_hashes | length == 4) and
      (.architecture_initialization.evidence.output_hashes | has("spec/STATE.md")) and
      (.architecture_initialization.evidence.output_hashes | has("spec/index.yaml")) and
      (.architecture_initialization.evidence.output_hashes | has("spec/graph.yaml")) and
      (.architecture_initialization.evidence.output_hashes | has("spec/gaps.yaml")) and
      all(.architecture_initialization.evidence.output_hashes[]; type == "string" and test("^[0-9a-f]{64}$"))
    ' "$receipt" >/dev/null 2>&1 || status=invalid
    if [ "$status" = "ready" ]; then
      output_rows="$(jq -r '.architecture_initialization.evidence.output_hashes | to_entries[] | [.key, .value] | @tsv' "$receipt" 2>/dev/null)"
      while IFS=$'\t' read -r output_path output_hash; do
        [ -f "$project_dir/$output_path" ] && [ ! -L "$project_dir/$output_path" ] || {
          status=invalid
          break
        }
        actual_hash="$(_mir_bootstrap_sha256 "$project_dir/$output_path")" || {
          status=invalid
          break
        }
        [ "$actual_hash" = "$output_hash" ] || {
          status=invalid
          break
        }
      done <<EOF
$output_rows
EOF
    fi
  fi
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
  project_normalized="${project_normalized%/}"
  if [ "${normalized#"$project_normalized"/}" != "$normalized" ]; then
    normalized="${normalized#"$project_normalized"/}"
  else
    case "$normalized" in
      /*|[A-Za-z]:/*) return 1 ;;
    esac
  fi
  normalized="${normalized#./}"
  case "/$normalized/" in
    */../*|*/./*) return 1 ;;
  esac
  local current="$project_dir"
  local component
  while IFS= read -r component; do
    [ -n "$component" ] || continue
    current="$current/$component"
    [ ! -L "$current" ] || return 1
  done <<EOF
$(printf '%s\n' "$normalized" | tr '/' '\n')
EOF
  case "$normalized" in
    spec/*|config/bootstrap-adoption.json|config/content-onboarding.json)
      return 0
      ;;
  esac
  local manifest="$project_dir/config/bootstrap-adoption.json"
  if [ -f "$manifest" ] && [ ! -L "$manifest" ] && command -v jq >/dev/null 2>&1; then
    jq -e --arg path "$normalized" '[.surfaces[]?.evidence_paths[]?] | index($path) != null' "$manifest" >/dev/null 2>&1 && return 0
  fi
  return 1
}

_mir_bootstrap_patch_paths_allowed() {
  local patch="$1"
  local project_dir="${2:-${CLAUDE_PROJECT_DIR:-.}}"
  local paths found_path path
  printf '%s\n' "$patch" | grep -q '^\*\*\* Move to:' && return 1
  printf '%s\n' "$patch" | grep -Eq '^\*\*\* Delete File: (.*[/\\])?config[/\\]bootstrap-adoption\.json$' && return 1
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

_mir_bootstrap_shell_patch_allowed() {
  local command="$1"
  local project_dir="${2:-${CLAUDE_PROJECT_DIR:-.}}"
  local first_line last_line terminator_count
  first_line="${command%%$'\n'*}"
  last_line="${command##*$'\n'}"
  [ "$first_line" = "apply_patch <<'PATCH'" ] || return 1
  [ "$last_line" = "PATCH" ] || return 1
  terminator_count="$(printf '%s\n' "$command" | grep -c '^PATCH$' || true)"
  [ "$terminator_count" -eq 1 ] || return 1
  _mir_bootstrap_patch_paths_allowed "$command" "$project_dir"
}

_mir_bootstrap_git_add_allowed() {
  local command="$1"
  local project_dir="${2:-${CLAUDE_PROJECT_DIR:-.}}"
  local path
  printf '%s\n' "$command" | grep -Eq \
    "^[[:space:]]*git[[:space:]]+add[[:space:]]+--[[:space:]]+(\"[^\"]+\"|'[^']+'|[^[:space:]'\"]+)[[:space:]]*$" || return 1
  path="$(printf '%s\n' "$command" | sed -E 's/^[[:space:]]*git[[:space:]]+add[[:space:]]+--[[:space:]]+//; s/[[:space:]]*$//')"
  case "$path" in
    \"*\") path="${path#\"}"; path="${path%\"}" ;;
    \'*\') path="${path#\'}"; path="${path%\'}" ;;
  esac
  case "$path" in
    :*|*'*'*|*'?'*|*'['*|*']'*|*'{'*|*'}'*|*'$'*|*'~'*|*'\\'*|*'!'*|*'('*|*')'*)
      return 1
      ;;
  esac
  _mir_bootstrap_allowed_path "$path" "$project_dir" || return 1
  [ -f "$project_dir/$path" ] && [ ! -L "$project_dir/$path" ]
}

_mir_bootstrap_safe_single_command() {
  local command="$1"
  local project_dir="${2:-${CLAUDE_PROJECT_DIR:-.}}"
  local uv_project
  case "$command" in
    *$'\n'*|*$'\r'*|*';'*|*'&'*|*'|'*|*'<'*|*'>'*|*'`'*|*'$('* )
      return 1
      ;;
  esac
  if printf '%s\n' "$command" | grep -Eq \
    '^[[:space:]]*(\./setup\.sh|\.\\setup\.ps1)([[:space:]].*)?[[:space:]]*$'; then
    [ ! -e "$project_dir/config/bootstrap-adoption.json" ] && return 0
    return 1
  fi
  uv_project="(--project[[:space:]]+(\"[^\"]+\"|'[^']+'|[^[:space:]]+)[[:space:]]+)?"
  if printf '%s\n' "$command" | grep -Eq \
    "^[[:space:]]*uv[[:space:]]+run[[:space:]]+${uv_project}mir[[:space:]]+(bootstrap|bootstrap-adoption)([[:space:]].*)?[[:space:]]*$"; then
    if [ -e "$project_dir/config/bootstrap-adoption.json" ]; then
      printf '%s\n' "$command" | grep -Eq \
        "^[[:space:]]*uv[[:space:]]+run[[:space:]]+${uv_project}mir[[:space:]]+bootstrap-adoption([[:space:]].*)?[[:space:]]*$" || return 1
    else
      printf '%s\n' "$command" | grep -Eq \
        "^[[:space:]]*uv[[:space:]]+run[[:space:]]+${uv_project}mir[[:space:]]+bootstrap([[:space:]].*)?[[:space:]]*$" || return 1
    fi
    local mir_args
    case "$command" in
      *"mir bootstrap-adoption"*) mir_args="${command#*"mir bootstrap-adoption"}" ;;
      *) mir_args="${command#*"mir bootstrap"}" ;;
    esac
    if printf '%s\n' "$mir_args" | grep -Eq -- '(^|[[:space:]])--project'; then
      local remaining_args
      remaining_args="$(printf '%s\n' "$mir_args" | sed -E "s/(^|[[:space:]])--project-root[[:space:]]+(\\.|\"\\.\"|'\\.')([[:space:]]|$)/ /g")"
      printf '%s\n' "$remaining_args" | grep -Eq -- '(^|[[:space:]])--project' && return 1
    fi
    return 0
  fi
  if printf '%s\n' "$command" | grep -Eq \
    '^[[:space:]]*git[[:space:]]+status([[:space:]].*)?[[:space:]]*$'; then
    return 0
  fi
  if _mir_bootstrap_git_add_allowed "$command" "$project_dir"; then
    return 0
  fi
  if printf '%s\n' "$command" | grep -Eq \
    '^[[:space:]]*git[[:space:]]+diff([[:space:]].*)?[[:space:]]*$'; then
    case "$command" in
      *--output*|*--ext-diff*|*--textconv*) return 1 ;;
    esac
    return 0
  fi
  if printf '%s\n' "$command" | grep -Eq \
    '^[[:space:]]*(ls|pwd|head|tail|jq)([[:space:]].*)?[[:space:]]*$'; then
    return 0
  fi
  if printf '%s\n' "$command" | grep -Eq \
    '^[[:space:]]*rg([[:space:]].*)?[[:space:]]*$'; then
    case "$command" in
      *--pre*|*--pre-glob*) return 1 ;;
    esac
    return 0
  fi
  return 1
}

_mir_bootstrap_uv_project_allowed() {
  local command="$1"
  local project_dir="${2:-${CLAUDE_PROJECT_DIR:-.}}"
  local trimmed rest source_root expected_commit actual_commit
  trimmed="${command#"${command%%[![:space:]]*}"}"
  case "$trimmed" in
    "uv run --project "*) rest="${trimmed#"uv run --project "}" ;;
    *) return 0 ;;
  esac
  case "$rest" in
    \"*)
      rest="${rest#\"}"
      source_root="${rest%%\"*}"
      ;;
    \'*)
      rest="${rest#\'}"
      source_root="${rest%%\'*}"
      ;;
    *) source_root="${rest%%[[:space:]]*}" ;;
  esac
  [ -n "$source_root" ] && [ -d "$source_root" ] || return 1
  grep -Eq '^[[:space:]]*repository_type[[:space:]]*=[[:space:]]*"public_harness_template"' \
    "$source_root/.mir/repo-profile.toml" 2>/dev/null || return 1
  expected_commit="$(jq -r '.mir_yoke_source_commit // ""' "$project_dir/config/bootstrap-adoption.json" 2>/dev/null)"
  [ -n "$expected_commit" ] || return 1
  actual_commit="$(git -C "$source_root" rev-parse HEAD 2>/dev/null)" || return 1
  [ "$actual_commit" = "$expected_commit" ] || return 1
  [ -z "$(git -C "$source_root" status --porcelain --untracked-files=normal 2>/dev/null)" ]
}

_mir_bootstrap_workdir_allowed() {
  local payload="$1"
  local project_dir="${2:-${CLAUDE_PROJECT_DIR:-.}}"
  local requested project_real requested_real
  requested="$(printf '%s' "$payload" | jq -r '.tool_input.workdir // ""' 2>/dev/null)"
  [ -z "$requested" ] && return 0
  project_real="$(cd -- "$project_dir" 2>/dev/null && pwd -P)" || return 1
  requested_real="$(cd -- "$requested" 2>/dev/null && pwd -P)" || return 1
  [ "$project_real" = "$requested_real" ]
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
      _mir_bootstrap_workdir_allowed "$payload" "$project_dir" || {
        printf '[BootstrapGate BLOCK] bootstrap command workdir must remain the current project\n' >&2
        return 2
      }
      _mir_bootstrap_shell_patch_allowed "$command" "$project_dir" && return 0
      if _mir_bootstrap_safe_single_command "$command" "$project_dir"; then
        _mir_bootstrap_uv_project_allowed "$command" "$project_dir" && return 0
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
