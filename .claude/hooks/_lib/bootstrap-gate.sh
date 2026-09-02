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

_mir_bootstrap_has_official_origin() {
  local repository="$1"
  local origin
  origin="$(git --no-replace-objects --no-lazy-fetch -C "$repository" \
    remote get-url origin 2>/dev/null || true)"
  case "$origin" in
    https://github.com/youngjin39/mir-yoke.git|git@github.com:youngjin39/mir-yoke.git)
      return 0
      ;;
  esac
  return 1
}

_mir_bootstrap_is_provider_source() {
  local repository="$1"
  local profile="$repository/.mir/repo-profile.toml"
  if [ -e "$profile" ] || [ -L "$profile" ]; then
    [ -f "$profile" ] && [ ! -L "$profile" ] && \
      grep -Eq '^[[:space:]]*slug[[:space:]]*=[[:space:]]*"mir-yoke"' "$profile" && \
      grep -Eq '^[[:space:]]*repository_type[[:space:]]*=[[:space:]]*"public_harness_template"' "$profile"
    return
  fi
  _mir_bootstrap_has_official_origin "$repository"
}

_mir_bootstrap_has_unsafe_git_extensions() {
  local repository="$1"
  local common_dir attributes
  if git --no-replace-objects --no-lazy-fetch -C "$repository" config --get-regexp \
    '^(filter\..*\.(clean|smudge|process|required)|core\.(hooksPath|fsmonitor|attributesFile))$' \
    >/dev/null 2>&1; then
    return 0
  fi
  common_dir="$(git --no-replace-objects --no-lazy-fetch -C "$repository" \
    rev-parse --git-common-dir 2>/dev/null)" || return 0
  case "$common_dir" in /*) ;; *) common_dir="$repository/$common_dir" ;; esac
  attributes="$common_dir/info/attributes"
  [ -e "$attributes" ] || [ -L "$attributes" ]
}

mir_bootstrap_gate_state() {
  local project_dir="${1:-${CLAUDE_PROJECT_DIR:-.}}"
  local profile="$project_dir/.mir/repo-profile.toml"
  local receipt="$project_dir/.mir/bootstrap-receipt.json"

  if [ -f "$profile" ] && [ ! -L "$profile" ] && \
     grep -Eq '^[[:space:]]*slug[[:space:]]*=[[:space:]]*"mir-yoke"' "$profile" && \
     grep -Eq '^[[:space:]]*repository_type[[:space:]]*=[[:space:]]*"public_harness_template"' "$profile"; then
    if _mir_bootstrap_has_official_origin "$project_dir"; then
      printf 'template_maintainer\n'
      return 0
    fi
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
  if [ "$status" = "restart_required" ]; then
    local restart_cli restart_cli_hash restart_actual_cli_hash restart_runtime_root
    local restart_manifest restart_manifest_hash restart_actual_manifest_hash
    local restart_source_url restart_source_commit restart_constraints_hash
    jq -e '
      .cli.externalized == true and
      (.cli.executable | type == "string" and length > 0) and
      (.cli.sha256 | type == "string" and test("^[0-9a-f]{64}$")) and
      (.cli.runtime_manifest | type == "string" and length > 0) and
      (.cli.runtime_manifest_sha256 | type == "string" and test("^[0-9a-f]{64}$")) and
      (.cli.source_url | type == "string" and length > 0) and
      (.cli.source_commit | type == "string" and test("^[0-9a-f]{40,64}$")) and
      (.cli.constraints_sha256 | type == "string" and test("^[0-9a-f]{64}$"))
    ' "$receipt" >/dev/null 2>&1 || status=invalid
    if [ "$status" = "restart_required" ]; then
      restart_cli="$(jq -r '.cli.executable' "$receipt")"
      restart_cli_hash="$(jq -r '.cli.sha256' "$receipt")"
      restart_runtime_root="$(cd -- "$(dirname -- "$restart_cli")/.." 2>/dev/null && pwd -P || true)"
      restart_manifest="$(jq -r '.cli.runtime_manifest' "$receipt")"
      restart_manifest_hash="$(jq -r '.cli.runtime_manifest_sha256' "$receipt")"
      restart_source_url="$(jq -r '.cli.source_url' "$receipt")"
      restart_source_commit="$(jq -r '.cli.source_commit' "$receipt")"
      restart_constraints_hash="$(jq -r '.cli.constraints_sha256' "$receipt")"
      case "$restart_cli" in "$project_dir"|"$project_dir"/*) status=invalid ;; esac
      [ -f "$restart_cli" ] && [ -x "$restart_cli" ] || status=invalid
      restart_actual_cli_hash="$(_mir_bootstrap_sha256 "$restart_cli" 2>/dev/null || true)"
      [ "$restart_actual_cli_hash" = "$restart_cli_hash" ] || status=invalid
      [ -n "$restart_runtime_root" ] && \
        [ "$restart_manifest" = "$restart_runtime_root/runtime-manifest.json" ] && \
        [ -f "$restart_manifest" ] && [ ! -L "$restart_manifest" ] || status=invalid
      restart_actual_manifest_hash="$(_mir_bootstrap_sha256 "$restart_manifest" 2>/dev/null || true)"
      [ "$restart_actual_manifest_hash" = "$restart_manifest_hash" ] || status=invalid
      if [ "$status" = "restart_required" ]; then
        "$restart_cli" runtime-manifest verify \
          --runtime-root "$restart_runtime_root" \
          --manifest "$restart_manifest" \
          --source-url "$restart_source_url" \
          --source-commit "$restart_source_commit" \
          --constraints-sha256 "$restart_constraints_hash" >/dev/null 2>&1 || status=invalid
      fi
    fi
  fi
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
      .cli.externalized == true and
      (.cli.executable | type == "string" and length > 0) and
      (.cli.sha256 | type == "string" and test("^[0-9a-f]{64}$")) and
      (.cli.runtime_manifest | type == "string" and length > 0) and
      (.cli.runtime_manifest_sha256 | type == "string" and test("^[0-9a-f]{64}$")) and
      (.cli.source_url | type == "string" and length > 0) and
      (.cli.source_commit | type == "string" and test("^[0-9a-f]{40,64}$")) and
      (.cli.constraints_sha256 | type == "string" and test("^[0-9a-f]{64}$")) and
      (.slim.status == "applied" or .slim.status == "already_slim") and
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
      local cli_path cli_hash actual_cli_hash runtime_root runtime_manifest runtime_manifest_hash actual_manifest_hash runtime_source_url runtime_source_commit runtime_constraints_hash slim_status boundary marker_rows marker_path marker_text
      cli_path="$(jq -r '.cli.executable // ""' "$receipt" 2>/dev/null)"
      cli_hash="$(jq -r '.cli.sha256 // ""' "$receipt" 2>/dev/null)"
      case "$cli_path" in
        "$project_dir"|"$project_dir"/*) status=invalid ;;
      esac
      [ -n "$cli_path" ] && [ -f "$cli_path" ] && [ -x "$cli_path" ] || status=invalid
      actual_cli_hash="$(_mir_bootstrap_sha256 "$cli_path" 2>/dev/null || true)"
      [ -n "$actual_cli_hash" ] && [ "$actual_cli_hash" = "$cli_hash" ] || status=invalid
      runtime_root="$(cd -- "$(dirname -- "$cli_path")/.." 2>/dev/null && pwd -P || true)"
      runtime_manifest="$(jq -r '.cli.runtime_manifest // ""' "$receipt" 2>/dev/null)"
      runtime_manifest_hash="$(jq -r '.cli.runtime_manifest_sha256 // ""' "$receipt" 2>/dev/null)"
      runtime_source_url="$(jq -r '.cli.source_url // ""' "$receipt" 2>/dev/null)"
      runtime_source_commit="$(jq -r '.cli.source_commit // ""' "$receipt" 2>/dev/null)"
      runtime_constraints_hash="$(jq -r '.cli.constraints_sha256 // ""' "$receipt" 2>/dev/null)"
      [ -n "$runtime_root" ] && [ "$runtime_manifest" = "$runtime_root/runtime-manifest.json" ] && \
        [ -f "$runtime_manifest" ] && [ ! -L "$runtime_manifest" ] || status=invalid
      actual_manifest_hash="$(_mir_bootstrap_sha256 "$runtime_manifest" 2>/dev/null || true)"
      [ -n "$actual_manifest_hash" ] && [ "$actual_manifest_hash" = "$runtime_manifest_hash" ] || status=invalid
      if [ "$status" = "ready" ]; then
        "$cli_path" runtime-manifest verify \
          --runtime-root "$runtime_root" \
          --manifest "$runtime_manifest" \
          --source-url "$runtime_source_url" \
          --source-commit "$runtime_source_commit" \
          --constraints-sha256 "$runtime_constraints_hash" >/dev/null 2>&1 || status=invalid
      fi
      [ ! -e "$project_dir/.mir/slim-transaction.json" ] && \
        [ ! -e "$project_dir/.mir/slim.lock" ] || status=invalid
      boundary="$project_dir/config/adopter-boundary.json"
      [ -f "$boundary" ] && [ ! -L "$boundary" ] || status=invalid
      if [ "$status" = "ready" ]; then
        marker_rows="$(jq -r '.provider_markers[]?' "$boundary" 2>/dev/null)"
        while IFS= read -r marker_path; do
          [ -n "$marker_path" ] || continue
          case "$marker_path" in /*|../*|*/../*|*/..) status=invalid; break ;; esac
          if [ -e "$project_dir/$marker_path" ] || [ -L "$project_dir/$marker_path" ]; then
            status=invalid
            break
          fi
        done <<EOF
$marker_rows
EOF
      fi
      if [ "$status" = "ready" ]; then
        while IFS=$'\t' read -r marker_path marker_text; do
          [ -n "$marker_path" ] && [ -n "$marker_text" ] || continue
          case "$marker_path" in /*|../*|*/../*|*/..) status=invalid; break ;; esac
          if [ -f "$project_dir/$marker_path" ] && \
             grep -Fq -- "$marker_text" "$project_dir/$marker_path"; then
            status=invalid
            break
          fi
        done <<EOF
$(jq -r '.provider_text_markers[]? | [.path, .contains] | @tsv' "$boundary" 2>/dev/null)
EOF
      fi
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
    local pinned_commit
    pinned_commit="$(jq -r '.mir_yoke_source_commit // ""' \
      "$project_dir/config/bootstrap-adoption.json" 2>/dev/null)"
    printf 'existing_repository: complete tracked adoption evidence, then reissue the receipt\n'
    printf 'recovery_command: uv run --project <provider worktree> mir bootstrap-adoption --apply\n'
    printf 'recovery_source: detached provider worktree at %s, with a clean tree\n' \
      "${pinned_commit:-the mir_yoke_source_commit in config/bootstrap-adoption.json}"
  else
    printf 'phase_1: run setup.sh with --profile, --purpose, and --stack (inside WSL on Windows hosts)\n'
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
    :*|*'*'*|*'?'*|*'['*|*']'*|*'{'*|*'}'*|*'$'*|*'~'*|*'\'*|*'!'*|*'('*|*')'*)
      return 1
      ;;
  esac
  _mir_bootstrap_allowed_path "$path" "$project_dir" || return 1
  [ -f "$project_dir/$path" ] && [ ! -L "$project_dir/$path" ]
}

_mir_bootstrap_worktree_add_allowed() {
  local command="$1"
  local project_dir="${2:-${CLAUDE_PROJECT_DIR:-.}}"
  local pattern source_root target_root commit expected_commit source_real manifest
  local target_parent target_parent_real target_name temp_root
  pattern='^[[:space:]]*git[[:space:]]+--no-replace-objects[[:space:]]+--no-lazy-fetch[[:space:]]+-c[[:space:]]+core\.hooksPath=/dev/null[[:space:]]+-c[[:space:]]+core\.fsmonitor=false[[:space:]]+-c[[:space:]]+core\.attributesFile=/dev/null[[:space:]]+-C[[:space:]]+"([^"]+)"[[:space:]]+worktree[[:space:]]+add[[:space:]]+--detach[[:space:]]+"([^"]+)"[[:space:]]+([0-9a-f]{40})[[:space:]]*$'
  printf '%s\n' "$command" | grep -Eq "$pattern" || return 1
  source_root="$(printf '%s\n' "$command" | sed -E "s@$pattern@\\1@")"
  target_root="$(printf '%s\n' "$command" | sed -E "s@$pattern@\\2@")"
  commit="$(printf '%s\n' "$command" | sed -E "s@$pattern@\\3@")"
  case "$source_root$target_root" in
    *'$'*|*'\'*|*'!'*) return 1 ;;
  esac
  case "$source_root" in /*) ;; *) return 1 ;; esac
  [ -d "$source_root" ] && [ ! -L "$source_root" ] || return 1
  source_real="$(cd -- "$source_root" 2>/dev/null && pwd -P)" || return 1
  [ "$source_root" = "$source_real" ] || return 1
  _mir_bootstrap_has_official_origin "$source_root" || return 1
  _mir_bootstrap_has_unsafe_git_extensions "$source_root" && return 1
  manifest="$project_dir/config/bootstrap-adoption.json"
  [ -f "$manifest" ] && [ ! -L "$manifest" ] || return 1
  expected_commit="$(jq -r '.mir_yoke_source_commit // ""' "$manifest" 2>/dev/null)"
  [ "$commit" = "$expected_commit" ] || return 1
  git --no-replace-objects --no-lazy-fetch -C "$source_root" \
    cat-file -e "$commit^{commit}" 2>/dev/null || return 1

  temp_root="$(cd -- "${TMPDIR:-/tmp}" 2>/dev/null && pwd -P)" || return 1
  target_parent="${target_root%/*}"
  target_name="${target_root##*/}"
  [ -d "$target_parent" ] && [ ! -L "$target_parent" ] || return 1
  target_parent_real="$(cd -- "$target_parent" 2>/dev/null && pwd -P)" || return 1
  [ "$target_parent_real" = "$temp_root" ] || return 1
  [ "$target_root" = "$target_parent_real/$target_name" ] || return 1
  [ "$target_name" = "mir-yoke-bootstrap-${commit%${commit#????????????}}" ] || return 1
  [ ! -e "$target_root" ] && [ ! -L "$target_root" ]
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
  if _mir_bootstrap_worktree_add_allowed "$command" "$project_dir"; then
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
      *--pre*) return 1 ;;
    esac
    return 0
  fi
  return 1
}

_mir_bootstrap_uv_project_allowed() {
  local command="$1"
  local project_dir="${2:-${CLAUDE_PROJECT_DIR:-.}}"
  local trimmed rest source_root expected_commit actual_commit status_output
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
  [ -n "$source_root" ] && [ -d "$source_root" ] && [ ! -L "$source_root" ] || return 1
  [ "$source_root" = "$(cd -- "$source_root" 2>/dev/null && pwd -P)" ] || return 1
  _mir_bootstrap_is_provider_source "$source_root" || return 1
  _mir_bootstrap_has_unsafe_git_extensions "$source_root" && return 1
  expected_commit="$(jq -r '.mir_yoke_source_commit // ""' "$project_dir/config/bootstrap-adoption.json" 2>/dev/null)"
  [ -n "$expected_commit" ] || return 1
  actual_commit="$(git --no-replace-objects --no-lazy-fetch -C "$source_root" \
    rev-parse HEAD 2>/dev/null)" || return 1
  [ "$actual_commit" = "$expected_commit" ] || return 1
  status_output="$(git --no-replace-objects --no-lazy-fetch \
    -c core.hooksPath=/dev/null -c core.fsmonitor=false \
    -c core.attributesFile=/dev/null -C "$source_root" \
    status --porcelain --untracked-files=normal 2>/dev/null)" || return 1
  [ -z "$status_output" ]
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
  # An invalid receipt in a greenfield repository has no repository-local recovery
  # path, so it stays hard-blocked. An adoption repository is invalid precisely
  # because a declared evidence file drifted, and the recovery is to restore that
  # file and reissue the receipt: keep its declared-evidence edits reachable by
  # falling through to the normal path screening below.
  if [ "$state" = "invalid" ] && [ ! -f "$project_dir/config/bootstrap-adoption.json" ]; then
    if [ "$tool_name" = "Bash" ]; then
      local repair_command
      repair_command="$(printf '%s' "$payload" | jq -r '.tool_input.command // ""')"
      _mir_bootstrap_workdir_allowed "$payload" "$project_dir" && \
        _mir_bootstrap_safe_single_command "$repair_command" "$project_dir" && \
        _mir_bootstrap_uv_project_allowed "$repair_command" "$project_dir" && return 0
    fi
    printf '[BootstrapGate BLOCK] bootstrap is invalid; repair the receipt-bound runtime with setup.sh\n' >&2
    return 2
  fi
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
      patch="$(printf '%s' "$payload" | jq -r '.tool_input.command // .tool_input.input // .tool_input.patch // .tool_input.content // ""')"
      _mir_bootstrap_patch_paths_allowed "$patch" "$project_dir" && return 0
      ;;
  esac
  printf '[BootstrapGate BLOCK] bootstrap is %s; normal work must wait for Phase 2 ready receipt\n' "$state" >&2
  printf '[BootstrapGate BLOCK] only setup/adoption, memory/spec verification, and declared evidence edits are allowed\n' >&2
  if [ "$state" = "invalid" ] && [ -f "$project_dir/config/bootstrap-adoption.json" ]; then
    printf '[BootstrapGate BLOCK] restore the drifted declared evidence, then reissue with uv run --project <provider worktree> mir bootstrap-adoption --apply\n' >&2
  fi
  return 2
}
