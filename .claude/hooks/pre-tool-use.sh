#!/bin/bash
# PreToolUse hook: input-stage guardrail.
# Blocks destructive patterns + denied paths BEFORE the tool runs.
# Reads tool_input from stdin (JSON). Exit 2 = block; exit 0 = allow.

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
DENY_LIST_FILE="$PROJECT_DIR/.ai-harness/deny-list.yaml"
TDD_GUARD_SCRIPT="$PROJECT_DIR/.claude/hooks/tdd-guard.sh"
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
        block "deny-list[$id] $target_label: $reason"
      fi
      if [ "$severity" = "warn" ]; then
        warn "deny-list[$id] $target_label: $reason"
      fi
    fi
  done < <(emit_deny_patterns "$DENY_LIST_FILE")
}

require_jq
TOOL_NAME="$(extract_json '.tool_name')" || block "Malformed PreToolUse payload for filter: .tool_name"

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
  if echo "$CMD" | grep -qE '(^|[[:space:]])git[[:space:]]+commit([[:space:]]|$)'; then
    if [ -f "$PRE_COMMIT_VERIFICATION_SCRIPT" ]; then
      if ! /bin/bash "$PRE_COMMIT_VERIFICATION_SCRIPT"; then
        block "pre-commit verification failed for code changes"
      fi
    fi
  fi
  # F6-hook. Codex exec stdin guard (advisory — open stdin hangs on EOF)
  if echo "$CMD" | grep -qE 'codex[[:space:]]+exec' && ! echo "$CMD" | grep -qE '(<[[:space:]]*/dev/null|--stdin)'; then
    warn "append < /dev/null (open stdin hangs on EOF)"
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
  if [ -f "$TDD_GUARD_SCRIPT" ]; then
    if ! /bin/bash "$TDD_GUARD_SCRIPT" "$FP"; then
      exit 2
    fi
  fi
  # ADR-33 design-complete gate (R11-T10)
  DESIGN_GATE_SCRIPT="$PROJECT_DIR/.claude/hooks/design-complete-gate.sh"
  if [ -f "$DESIGN_GATE_SCRIPT" ]; then
    if ! /bin/bash "$DESIGN_GATE_SCRIPT" "$FP" "$TOOL_NAME"; then
      exit 2
    fi
  fi
  apply_deny_list "$TOOL_NAME $FP" "path"
fi

# mir:profile:enforcement:begin
# --- Mir profile-driven enforcement (V2.2 — phase-2 scope + ADR-23 dogfooding exemption) ---
if [ "${MIR_FAMILY_CODE_PATHS_INITIALIZED:-no}" != "yes" ]; then
    MIR_FAMILY_SLUG="${MIR_FAMILY_SLUG:-mir-harness}"
    MIR_FAMILY_CODE_PATHS=()
    _MIR_CODE_PATH_HELPER="$PROJECT_DIR/.claude/hooks/lib/code-path-config.py"
    if [ -f "$_MIR_CODE_PATH_HELPER" ]; then
        while IFS= read -r line; do
            [ -n "$line" ] && MIR_FAMILY_CODE_PATHS+=("$line")
        done < <(python3 "$_MIR_CODE_PATH_HELPER" \
                 --family "$MIR_FAMILY_SLUG" --check code-paths 2>/dev/null)
    fi
    [ "${#MIR_FAMILY_CODE_PATHS[@]}" -eq 0 ] && MIR_FAMILY_CODE_PATHS=( "tools/" "src/" )

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
            if [ "${MIR_DOGFOODING_EXEMPT:-no}" = "yes" ]; then
                echo "[mir ADVISORY] code-path edit on $_mir_file_path; family $MIR_FAMILY_SLUG is ADR-23 dogfooding exempt (no BLOCK)" >&2
            else
                echo "[mir BLOCKED] code-path edit on $_mir_file_path requires the Codex execution lane. If Claude is main, delegate via scripts/spawn_codex_session.sh; if Codex is main or the loop driver is running, export MIR_CODEX_MAIN=1." >&2
                exit 2
            fi
        fi
    fi
fi
# --- end Mir profile-driven enforcement (V2.2) ---

# mir:profile:enforcement:end

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

exit 0
