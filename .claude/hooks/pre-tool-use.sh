#!/bin/bash
# PreToolUse hook: input-stage guardrail.
# Blocks destructive patterns + denied paths BEFORE the tool runs.
# Reads tool_input from stdin (JSON). Exit 2 = block; exit 0 = allow.
#
# Tier declarations per ADR-33 / R27-T02 (Choice 5=A):
#   pre-tool-use/code-path-block  : tier=block  (your-harness BLOCK code path protection)
#   pre-tool-use/deny-list        : tier=block  (security)
#   pre-tool-use/tool-contract-log: tier=warn   (MIR_TOOL_CONTRACT_LOG advisory)
_MIR_HOOK_TIER_CODE_PATH="warn"
_MIR_HOOK_TIER_DENY_LIST="block"
_MIR_HOOK_TIER_TOOL_CONTRACT_LOG="warn"
_MIR_TIER_DISPATCH="$(dirname "$0")/_lib/tier_dispatch.sh"
# shellcheck source=./_lib/tier_dispatch.sh
[ -f "$_MIR_TIER_DISPATCH" ] && . "$_MIR_TIER_DISPATCH"

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
_MIR_INVOCATION_LOG_HELPER="$(dirname "$0")/_lib/invocation_log.sh"
# shellcheck source=./_lib/invocation_log.sh
[ -f "$_MIR_INVOCATION_LOG_HELPER" ] && . "$_MIR_INVOCATION_LOG_HELPER"
if command -v mir_invocation_log_enable >/dev/null 2>&1; then
  mir_invocation_log_enable "pre-tool-use" "$PROJECT_DIR"
fi
DENY_LIST_FILE="$PROJECT_DIR/.ai-harness/deny-list.yaml"
PRE_COMMIT_VERIFICATION_SCRIPT="$PROJECT_DIR/.claude/hooks/pre-commit-verification.sh"
INPUT=$(cat)

block() {
  # Claude Code: stdout on exit 2 is shown to the agent as a tool error.
  echo "[PreToolUse BLOCK] $1" >&2
  exit 2
}

warn() {
  echo "[PreToolUse WARN] $1" >&2
}

require_jq() {
  if ! command -v jq >/dev/null 2>&1; then
    block "jq is required for PreToolUse parsing"
  fi
}

extract_json() {
  local filter="$1"
  local value
  if ! value=$(printf '%s' "$INPUT" | jq -er "$filter" 2>/dev/null); then
    return 1
  fi
  printf '%s' "$value"
}

emit_deny_patterns() {
  local file="$1"
  [ -f "$file" ] || return 0
  awk '
    function trim_field(line) {
      sub(/^[^:]+:[[:space:]]*/, "", line)
      gsub(/^"/, "", line)
      gsub(/"$/, "", line)
      return line
    }
    function emit_row() {
      if (id != "") print id "\t" pattern "\t" severity "\t" reason
      id = pattern = severity = reason = ""
    }
    /^[[:space:]]*-[[:space:]]+id:/ {
      emit_row()
      id = trim_field($0)
      next
    }
    id != "" && /^[[:space:]]+pattern:/ {
      pattern = trim_field($0)
      next
    }
    id != "" && /^[[:space:]]+severity:/ {
      severity = trim_field($0)
      next
    }
    id != "" && /^[[:space:]]+reason:/ {
      reason = trim_field($0)
      next
    }
    END {
      emit_row()
    }
  ' "$file"
}

apply_deny_list() {
  local subject="$1"
  local target_label="$2"
  [ -n "$subject" ] || return 0
  [ -f "$DENY_LIST_FILE" ] || return 0

  local row id pattern severity reason
  while IFS=$'\t' read -r id pattern severity reason; do
    [ -n "$id" ] || continue
    [ -n "$pattern" ] || continue
    local regex="$pattern"
    regex="${regex//\\\\/\\}"
    if printf '%s' "$subject" | grep -qE "$regex"; then
      if [ "$severity" = "block" ]; then
        # tier: block (deny-list security enforcement)
        block "deny-list[$id] $target_label: $reason"
      fi
      if [ "$severity" = "suggest" ]; then
        if command -v emit_tier_result >/dev/null 2>&1; then
          emit_tier_result "pre-tool-use/deny-list[$id]" "suggest" "deny-list[$id] $target_label: $reason"
          local suggest_rc=$?
          [ "$suggest_rc" -ne 0 ] && exit "$suggest_rc"
        else
          block "deny-list[$id] $target_label: $reason"
        fi
      fi
      if [ "$severity" = "warn" ]; then
        warn "deny-list[$id] $target_label: $reason"
      fi
    fi
  done < <(emit_deny_patterns "$DENY_LIST_FILE")
}

require_jq
TOOL_NAME="$(extract_json '.tool_name')" || block "Malformed PreToolUse payload for filter: .tool_name"

# ADR-60 R5 (Phase-3 enforcement parity): the Write/Edit R5 block below only
# covers Write/Edit. Codex's primary edit tool is apply_patch, and Bash can
# redirect, so extend the tasks/plan.md hard-block to those when a sub-agent /
# codex-delegated context (MIR_CODEX_SESSION_ID set) is active. Runtime-agnostic:
# protects whether Claude or Codex is the main and delegates (incl. loop_driver,
# which runs Codex in the main worktree where R4 isolation does not apply).
if [ -n "${MIR_CODEX_SESSION_ID:-}" ]; then
  case "$TOOL_NAME" in
    apply_patch|ApplyPatch)
      _r5_patch="$(extract_json '.tool_input.input // .tool_input.patch // .tool_input.content // .tool_input' 2>/dev/null || echo "")"
      if printf '%s' "$_r5_patch" | grep -qE '(^|[^[:alnum:]_./-])tasks/plan\.md([^[:alnum:]_]|$)'; then
        block "ADR-60 R5: a sub-agent/codex context must not edit the main control-plane cursor tasks/plan.md via apply_patch — the control_plane main owns it (report your result via your final message + the JobRegistry, never plan.md)"
      fi
      ;;
    Bash)
      _r5_cmd="$(extract_json '.tool_input.command' 2>/dev/null || echo "")"
      if printf '%s' "$_r5_cmd" | grep -qE 'tasks/plan\.md' && printf '%s' "$_r5_cmd" | grep -qE '(>>?|[[:space:]]tee([[:space:]]|$)|sed[[:space:]]+-i|[[:space:]]truncate([[:space:]]|$)|[[:space:]]dd([[:space:]]|$)|[[:space:]]cp([[:space:]]|$)|[[:space:]]mv([[:space:]]|$))'; then
        block "ADR-60 R5: a sub-agent/codex context must not write the main control-plane cursor tasks/plan.md via Bash — the control_plane main owns it (report your result via your final message + the JobRegistry, never plan.md)"
      fi
      ;;
  esac
fi

# --- Bash command guards ---
if [ "$TOOL_NAME" = "Bash" ]; then
  CMD="$(extract_json '.tool_input.command')" || block "Malformed PreToolUse payload for filter: .tool_input.command"
  [ -z "$CMD" ] && block "Empty Bash command payload"

  # 1. rm -rf on anything remotely dangerous
  if echo "$CMD" | grep -qE 'rm[[:space:]]+(-[rRfF]+[[:space:]]+)+(/|~|\$HOME|\*|\.|\.\./)'; then
    block "Destructive rm pattern: $CMD"
  fi
  # 2. Force push to protected branches
  if echo "$CMD" | grep -qE 'git[[:space:]]+push[[:space:]]+(-f|--force)[^|]*(main|master|release)'; then
    block "Force push to protected branch: $CMD"
  fi
  # 3. Hook bypass flags
  if echo "$CMD" | grep -qE '(--no-verify|--no-gpg-sign|-c[[:space:]]+commit\.gpgsign=false)'; then
    block "Hook/signing bypass flag: $CMD"
  fi
  # 4. History rewrite on shared refs
  if echo "$CMD" | grep -qE 'git[[:space:]]+(reset[[:space:]]+--hard[[:space:]]+origin|rebase[[:space:]]+.*main|filter-branch|filter-repo)'; then
    block "History rewrite on shared refs: $CMD"
  fi
  # 5. Piped remote install
  if echo "$CMD" | grep -qE '(curl|wget)[^|]*\|[[:space:]]*(bash|sh|zsh|python)'; then
    block "Piped remote install: $CMD"
  fi
  # 6. sudo in any form
  if echo "$CMD" | grep -qE '(^|[[:space:]])sudo([[:space:]]|$)'; then
    block "sudo requires user confirmation, not this hook: $CMD"
  fi
  # 7. Raw Codex subprocess routing is forbidden. Match a bare or absolute
  #    codex executable plus an exact exec/e shell token anywhere in its
  #    argv-shaped command text. Redirects and pipes do not create exceptions.
  if printf '%s\n' "$CMD" | grep -qE '(^|[[:space:];|&(<])([^[:space:];|&()<>#]*/)?codex([[:space:]]+[^[:space:];|&()<>#]+)*[[:space:]]+(exec|e)([[:space:];|&)>#]|$)'; then
    block "raw codex exec/e is banned — route through MCP/mir_executor"
  fi
  if [ "${MIR_PRE_COMMIT_VERIFY:-0}" = "1" ] && \
     echo "$CMD" | grep -qE '(^|[[:space:]])git[[:space:]]+commit([[:space:]]|$)'; then
    if [ -f "$PRE_COMMIT_VERIFICATION_SCRIPT" ]; then
      if ! /bin/bash "$PRE_COMMIT_VERIFICATION_SCRIPT"; then
        block "pre-commit verification failed for code changes"
      fi
    fi
  fi
  # F9. Sealed-family external push guard (sealed-repo policy 2026-05-23)
  if echo "$CMD" | grep -qE 'git[[:space:]]+push'; then
    if echo "$CMD" | grep -qE '(<your-home>/Router_Control|<your-home>/Project|<your-harness-path>'; then
      block "sealed-family external push requires explicit user override (sealed-repo policy 2026-05-23)"
    fi
  fi
  apply_deny_list "$CMD" "bash"
fi

# --- Write/Edit path guards ---
if [ "$TOOL_NAME" = "Write" ] || [ "$TOOL_NAME" = "Edit" ]; then
  FP="$(extract_json '.tool_input.file_path // .tool_input.path')" || block "Malformed PreToolUse payload for filter: .tool_input.file_path // .tool_input.path"
  [ -z "$FP" ] && block "Empty file path payload"

  # 1. Outside project root
  case "$FP" in
    /etc/*|/System/*|/Library/*|/usr/*|/bin/*|/sbin/*|/var/*|/private/*)
      block "Write outside project root: $FP"
      ;;
  esac
  # 2. Secret/env files
  case "$(basename "$FP")" in
    .env|.env.*|credentials|credentials.*|id_rsa|id_ed25519|*.pem|*.key|*.p12)
      block "Write to secret/credential file: $FP"
      ;;
  esac
  # 3. Git internal state
  if echo "$FP" | grep -qE '(^|/)\.git/(config|hooks/|refs/|objects/)'; then
    block "Write to git internal state: $FP"
  fi
  # ADR-60 R5: a sub-agent / codex-delegated context must NOT write the MAIN control-plane
  # cursor tasks/plan.md (the control_plane main owns it). Defense-in-depth behind the R4
  # worktree isolation. Detect the delegated context via MIR_CODEX_SESSION_ID.
  # The main (MIR_CODEX_SESSION_ID unset) is allowed.
  if [ -n "${MIR_CODEX_SESSION_ID:-}" ]; then
    case "$FP" in
      tasks/plan.md|*/tasks/plan.md)
        block "ADR-60 R5: a sub-agent/codex context must not edit the main control-plane cursor tasks/plan.md — the control_plane main owns it (report your result via your final message + the JobRegistry, never plan.md)"
        ;;
    esac
  fi
  apply_deny_list "$TOOL_NAME $FP" "path"
fi

# mir:bluebrick-advisory:begin
# Advisory: emit one stderr line when a Write/Edit/Bash-write targets a bluebrick-owned path.
# Never blocks (exit 0 always). Config lives in config/bluebrick-paths.json.
_MIR_BB_CONFIG="$PROJECT_DIR/config/bluebrick-paths.json"
if [ -f "$_MIR_BB_CONFIG" ] && ([ "$TOOL_NAME" = "Edit" ] || [ "$TOOL_NAME" = "Write" ]); then
  _bb_fp="$(extract_json '.tool_input.file_path // .tool_input.path' 2>/dev/null || echo "")"
  if [ -n "$_bb_fp" ]; then
    _bb_match="$(python3 - "$_bb_fp" "$_MIR_BB_CONFIG" <<'BBPY'
import sys, json, os
fp, cfg_path = sys.argv[1], sys.argv[2]
try:
    mapping = json.load(open(cfg_path))
except Exception:
    sys.exit(0)
pwd = os.environ.get("PWD", "")
candidates = [fp]
if pwd and fp.startswith(pwd + "/"):
    candidates.append(fp[len(pwd)+1:])
for prefix, brick in mapping.items():
    for c in candidates:
        if c == prefix or c.startswith(prefix):
            print(f"{brick}")
            sys.exit(0)
BBPY
)"
    [ -n "$_bb_match" ] && warn "[bluebrick] read docs/bluebricks/$_bb_match.md before changing $_bb_fp"
  fi
fi
# mir:bluebrick-advisory:end

# mir:profile:enforcement:begin
# --- your-harness profile-driven enforcement (V2.2 — phase-2 scope + ADR-23 dogfooding exemption) ---
if [ "${MIR_FAMILY_CODE_PATHS_INITIALIZED:-no}" != "yes" ]; then
    MIR_FAMILY_SLUG="${MIR_FAMILY_SLUG:-your-harness}"
    MIR_FAMILY_CODE_PATHS=()
    _MIR_CODE_PATH_HELPER="$PROJECT_DIR/.claude/hooks/lib/code-path-config.py"
    if [ -f "$_MIR_CODE_PATH_HELPER" ]; then
        while IFS= read -r line; do
            [ -n "$line" ] && MIR_FAMILY_CODE_PATHS+=("$line")
        done < <(python3 "$_MIR_CODE_PATH_HELPER" \
                 --family "$MIR_FAMILY_SLUG" --check code-paths 2>/dev/null)
    fi
    [ "${#MIR_FAMILY_CODE_PATHS[@]}" -eq 0 ] && MIR_FAMILY_CODE_PATHS=( "tools/" "src/" "scripts/" )

    # ADR-23 dogfooding exempt check
    MIR_DOGFOODING_EXEMPT="no"
    if [ -f "$_MIR_CODE_PATH_HELPER" ]; then
        MIR_DOGFOODING_EXEMPT="$(python3 "$_MIR_CODE_PATH_HELPER" \
                                --family "$MIR_FAMILY_SLUG" --check dogfooding-exempt 2>/dev/null || echo "no")"
    fi

    MIR_CODEX_DEFAULT_ENABLED="true"
    MIR_FAMILY_CODE_PATHS_INITIALIZED=yes
fi

if [ -n "${INPUT:-}" ]; then
    _mir_payload="$INPUT"
else
    _mir_payload="$(cat)"
    INPUT="$_mir_payload"
fi

_mir_tool_name="$(printf '%s' "$_mir_payload" | python3 -c 'import sys,json; print(json.loads(sys.stdin.read()).get("tool_name",""))' 2>/dev/null || echo "")"
if [ "$_mir_tool_name" = "Edit" ] || [ "$_mir_tool_name" = "Write" ]; then
    _mir_file_path="$(printf '%s' "$_mir_payload" | python3 -c 'import sys,json; d=json.loads(sys.stdin.read()); print(d.get("tool_input",{}).get("file_path") or d.get("tool_input",{}).get("path") or "")' 2>/dev/null || echo "")"
    if [ -n "$_mir_file_path" ] && [ "${#MIR_FAMILY_CODE_PATHS[@]}" -gt 0 ]; then
        _mir_match="$(python3 - "$_mir_file_path" "${MIR_FAMILY_CODE_PATHS[@]}" <<'PY'
import sys, os, fnmatch
path, *patterns = sys.argv[1:]
pwd = os.environ.get("PWD", "")
candidates = [path]
if pwd and path.startswith(pwd + "/"):
    candidates.append(path[len(pwd) + 1:])
def _match(candidate, pat):
    if pat.endswith("/"):
        return candidate.startswith(pat) or ("/" + pat) in ("/" + candidate + "/")
    return fnmatch.fnmatch(candidate, pat.replace("**", "*"))
print("yes" if any(_match(c, p) for c in candidates for p in patterns) else "no")
PY
)"
        if [ "$_mir_match" = "yes" ] && [ -z "${MIR_CODEX_SESSION_ID:-}" ] && [ "${MIR_CODEX_MAIN:-0}" != "1" ]; then
            echo "[mir ADVISORY] code-path edit on $_mir_file_path: use delegation when isolation materially helps; bounded direct-main edits are allowed." >&2
        fi
    fi
fi
# --- end your-harness profile-driven enforcement (V2.2) ---

# mir:profile:enforcement:end

# mir:enabled-phases:begin
# --- R25-T06: enabled_phases advisory check (gated by MIR_ENABLED_PHASES_CHECK=1) ---
if [ "${MIR_ENABLED_PHASES_CHECK:-0}" = "1" ]; then
    _MIR_EP_FAMILY="${MIR_FAMILY_SLUG:-your-harness}"
    _MIR_EP_PHASE="${MIR_ACTIVE_PHASE:-}"
    _MIR_EP_CONFIG="$PROJECT_DIR/config/repos/${_MIR_EP_FAMILY}.json"
    if [ -n "$_MIR_EP_PHASE" ] && [ -f "$_MIR_EP_CONFIG" ]; then
        _MIR_EP_ALLOWED="$(python3 -c "
import json, sys
try:
    d = json.load(open('$_MIR_EP_CONFIG'))
    phases = [e['phase'] for e in d.get('enabled_phases', [])]
    print('yes' if int('$_MIR_EP_PHASE') in phases else 'no')
except Exception:
    print('yes')
" 2>/dev/null || echo "yes")"
        if [ "$_MIR_EP_ALLOWED" = "no" ]; then
            warn "phase ${_MIR_EP_PHASE} is not in enabled_phases for family ${_MIR_EP_FAMILY} (advisory only)"
        fi
    fi
fi
# --- end R25-T06 enabled_phases advisory check ---
# mir:enabled-phases:end

# mir:tool-contract:begin
# --- R20-T01: phase-4 §4 tool contract validation (gated by env) ---
# Resolve project-venv python (requires 3.11+ for StrEnum); fall back to python3
_MIR_TC_PYTHON="$PROJECT_DIR/.venv/bin/python3"
if [ ! -x "$_MIR_TC_PYTHON" ]; then
    _MIR_TC_PYTHON="python3"
fi
if [ "${MIR_TOOL_CONTRACT_REQUIRED:-0}" = "1" ]; then
    _MIR_TC_VALIDATOR="$PROJECT_DIR/tools/hooks/validate_tool_contract.py"
    if [ -f "$_MIR_TC_VALIDATOR" ]; then
        # Replay INPUT through stdin to the validator
        _mir_tc_result="$(printf '%s' "${INPUT:-}" | "$_MIR_TC_PYTHON" "$_MIR_TC_VALIDATOR" 2>&1)"
        _mir_tc_exit=$?
        if [ "$_mir_tc_exit" -ne 0 ]; then
            echo "$_mir_tc_result" >&2
            echo "[mir CONTRACT BLOCK] tool contract validation failed (exit $_mir_tc_exit). Set MIR_TOOL_CONTRACT_REQUIRED=0 to disable temporarily." >&2
            exit 2
        fi
    else
        echo "[mir TC ADVISORY] MIR_TOOL_CONTRACT_REQUIRED=1 but validator missing at $_MIR_TC_VALIDATOR — skipping" >&2
    fi
elif [ "${MIR_TOOL_CONTRACT_LOG:-0}" = "1" ]; then
    # Advisory log mode — record contract presence without enforcing
    _mir_tc_has_contract="$(printf '%s' "${INPUT:-}" | "$_MIR_TC_PYTHON" -c 'import sys,json
try:
    d = json.loads(sys.stdin.read())
    tin = d.get("tool_input", {})
    print("yes" if "_mir_contract" in tin else "no")
except Exception:
    print("err")' 2>/dev/null || echo "err")"
    if [ "$_mir_tc_has_contract" = "no" ]; then
        # tier: warn (MIR_TOOL_CONTRACT_LOG advisory — MIR_HOOK_TIER_TOOL_CONTRACT_LOG=warn)
        echo "[mir TC ADVISORY LOG] tool call missing _mir_contract (advisory only, not enforced)" >&2
    fi
fi
# --- end R20-T01 tool contract validation ---
# mir:tool-contract:end

exit 0
