#!/bin/bash
_MIR_PYTHON_LAUNCHER="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/_lib/run-python.sh"
# Pre-commit verification helper: run project verification only for code changes.
#
# Tier declarations per ADR-33 / R27-T02 (Choice 5=A):
#   pre-commit/lint     : tier=block    (code quality gate)
#   pre-commit/typecheck: tier=block    (code quality gate)
#   pre-commit/test     : tier=suggest  (large tests — bypass via MIR_SUGGEST_TIER_CONFIRM=1)
_MIR_HOOK_TIER_LINT="block"
_MIR_HOOK_TIER_TYPECHECK="block"
_MIR_HOOK_TIER_TEST="suggest"
_MIR_PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
_MIR_TIER_DISPATCH="$(dirname "$0")/_lib/tier_dispatch.sh"
# shellcheck source=./_lib/tier_dispatch.sh
[ -f "$_MIR_TIER_DISPATCH" ] && . "$_MIR_TIER_DISPATCH"

set -u

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
TDD_MATRIX_GUARD_SCRIPT="$PROJECT_DIR/.claude/hooks/tdd-matrix-guard.py"

# The consumer repository owns its tools/ commit-gate posture through the local
# harness-consistency manifest. Catalog presence never changes authority or bypasses checks.
_MIR_TOOLS_COMMIT_GATE=""
_MIR_HC_MANIFEST="$PROJECT_DIR/config/harness-consistency.json"
if [ -f "$_MIR_HC_MANIFEST" ]; then
  _MIR_TOOLS_COMMIT_GATE="$("$_MIR_PYTHON_LAUNCHER" -c "
import json, sys
try:
    print(json.load(open(sys.argv[1]))['repo']['enforcement']['tools_commit_gate'])
except Exception:
    pass
" "$_MIR_HC_MANIFEST" 2>/dev/null)"
fi

collect_changed_files() {
  git diff --cached --name-only --diff-filter=ACMR 2>/dev/null | awk 'NF { print }' | sort -u
}

is_code_path() {
  local path="$1"
  case "$path" in
    src/*|tests/*|app/*|apps/*|packages/*|pipelines/*|infra/*|content/*|lib/*)
      ;;
    tools/*)
      # The local manifest may explicitly defer tools/ checks. Without a manifest, tools/
      # remains gated; an agent catalog is only reference data and never grants an exemption.
      if [ -n "$_MIR_TOOLS_COMMIT_GATE" ]; then
        [ "$_MIR_TOOLS_COMMIT_GATE" = "deferred" ] && return 1
      fi
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

is_implementation_path() {
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

run_step() {
  local label="$1"
  local cmd="$2"
  [ -n "$cmd" ] || return 0
  echo "[PreCommitVerification] $label: $cmd" >&2
  if ! /bin/bash -lc "$cmd"; then
    echo "[PreCommitVerification BLOCK] $label failed" >&2
    return 1
  fi
  return 0
}

main() {
  cd "$PROJECT_DIR" || exit 0
  if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    exit 0
  fi

  local code_change=0 path
  local changed_code_file
  changed_code_file="$(mktemp)"
  trap 'rm -f "$changed_code_file"' EXIT
  while IFS= read -r path; do
    [ -n "$path" ] || continue
    if is_code_path "$path"; then
      code_change=1
      if is_implementation_path "$path"; then
        printf '%s\n' "$path" >>"$changed_code_file"
      fi
    fi
  done < <(collect_changed_files)

  if [ "$code_change" -eq 0 ]; then
    echo "[PreCommitVerification] Skipped: no code changes detected" >&2
    exit 0
  fi

  local tdd_commands_file
  tdd_commands_file="$(mktemp)"
  trap 'rm -f "$changed_code_file" "$tdd_commands_file"' EXIT
  : >"$tdd_commands_file"
  if [ -s "$changed_code_file" ]; then
    if [ ! -f "$TDD_MATRIX_GUARD_SCRIPT" ]; then
      echo "[PreCommitVerification BLOCK] Missing helper: $TDD_MATRIX_GUARD_SCRIPT" >&2
      exit 2
    fi
    if ! "$_MIR_PYTHON_LAUNCHER" "$TDD_MATRIX_GUARD_SCRIPT" precommit "$PROJECT_DIR" "$changed_code_file" >"$tdd_commands_file"; then
      exit 2
    fi
  fi

  local lint_cmd typecheck_cmd test_cmd build_cmd
  local changed_code_paths=""
  while IFS= read -r path; do
    [ -n "$path" ] || continue
    if is_code_path "$path"; then
      changed_code_paths="$changed_code_paths $path"
    fi
  done < <(collect_changed_files)
  changed_code_paths="${changed_code_paths# }"

  local changed_python=""
  for path in $changed_code_paths; do
    case "$path" in
      *.py) changed_python="$changed_python $path" ;;
    esac
  done
  changed_python="${changed_python# }"

  local changed_test_paths=""
  for path in $changed_code_paths; do
    case "$path" in
      tests/*) changed_test_paths="$changed_test_paths $path" ;;
    esac
  done
  changed_test_paths="${changed_test_paths# }"

  local default_lint default_typecheck default_test default_build
  if [ -f package.json ]; then
    default_lint="npm run lint --if-present"
    default_typecheck="npm run typecheck --if-present"
    default_test="npm run test --if-present"
    default_build="npm run build --if-present"
  elif [ -f pyproject.toml ]; then
    if [ -n "$changed_code_paths" ]; then
      default_lint="uv run ruff check $changed_code_paths"
    else
      default_lint="uv run ruff check src tests"
    fi
    if [ -n "$changed_python" ]; then
      default_typecheck="uv run mypy --follow-imports=silent $changed_python"
    else
      default_typecheck="echo skip-typecheck-no-python-changes"
    fi
    if [ -n "$changed_python" ] || [ -n "$changed_test_paths" ]; then
      default_test="uv run pytest -q $changed_test_paths"
    else
      default_test="echo skip-test-no-python-changes"
    fi
    default_build=""
  else
    default_lint="echo skip-lint-no-product-command"
    default_typecheck="echo skip-typecheck-no-product-command"
    default_test="echo skip-test-no-product-command"
    default_build=""
  fi
  lint_cmd="${MIR_PRE_COMMIT_LINT:-$default_lint}"
  typecheck_cmd="${MIR_PRE_COMMIT_TYPECHECK:-$default_typecheck}"
  test_cmd="${MIR_PRE_COMMIT_TEST:-$default_test}"
  build_cmd="${MIR_PRE_COMMIT_BUILD:-$default_build}"

  local tdd_cmd idx
  idx=1
  while IFS= read -r tdd_cmd; do
    [ -n "$tdd_cmd" ] || continue
    run_step "tdd[$idx]" "$tdd_cmd" || exit 2
    idx=$((idx + 1))
  done <"$tdd_commands_file"
  # tier: block for lint+typecheck; tier: suggest for test
  run_step "lint" "$lint_cmd" || exit 2          # tier: block
  run_step "typecheck" "$typecheck_cmd" || exit 2 # tier: block
  if ! run_step "test" "$test_cmd"; then
    # tier: suggest — bypass allowed via MIR_SUGGEST_TIER_CONFIRM=1
    if [ "${MIR_SUGGEST_TIER_CONFIRM:-0}" = "1" ]; then
      _mir_record_suggest_bypass "pre-commit/test" "test step failed; bypassed by MIR_SUGGEST_TIER_CONFIRM=1"
      echo "[hook SUGGEST bypass] pre-commit/test: test failed but MIR_SUGGEST_TIER_CONFIRM=1 set" >&2
    else
      echo "[hook SUGGEST block] pre-commit/test: test failed (set MIR_SUGGEST_TIER_CONFIRM=1 to bypass)" >&2
      exit 2
    fi
  fi
  run_step "build" "$build_cmd" || exit 2
  exit 0
}

main "$@"
