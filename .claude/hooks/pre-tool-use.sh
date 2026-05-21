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
  apply_deny_list "$TOOL_NAME $FP" "path"
fi

# harness:profile:enforcement:begin
# --- Harness profile-driven enforcement (V2.1) ---
_get_family_slug() {
    local cfg="$PROJECT_DIR/.mir/harness-config.json"
    if [ -f "$cfg" ]; then
        python3 -c "import json,sys; print(json.load(open('$cfg')).get('family_slug', ''))" 2>/dev/null || true
    fi
}
if [ "${HARNESS_FAMILY_CODE_PATHS_INITIALIZED:-no}" != "yes" ]; then
    _slug="$(_get_family_slug)"
    HARNESS_FAMILY_SLUG="${_slug:-$(basename "$PROJECT_DIR")}"
    HARNESS_FAMILY_CODE_PATHS=( "tools/" "src/" )
    HARNESS_CODEX_DEFAULT_ENABLED="true"
    HARNESS_FAMILY_CODE_PATHS_INITIALIZED=yes
fi

if [ -n "${INPUT:-}" ]; then
    _harness_payload="$INPUT"
else
    _harness_payload="$(cat)"
    INPUT="$_harness_payload"
fi

_harness_tool_name="$(printf '%s' "$_harness_payload" | python3 -c 'import sys,json; print(json.loads(sys.stdin.read()).get("tool_name",""))' 2>/dev/null || echo "")"
if [ "$_harness_tool_name" = "Edit" ] || [ "$_harness_tool_name" = "Write" ]; then
    _harness_file_path="$(printf '%s' "$_harness_payload" | python3 -c 'import sys,json; d=json.loads(sys.stdin.read()); print(d.get("tool_input",{}).get("file_path") or d.get("tool_input",{}).get("path") or "")' 2>/dev/null || echo "")"
    if [ -n "$_harness_file_path" ] && [ "${#HARNESS_FAMILY_CODE_PATHS[@]}" -gt 0 ]; then
        _harness_match="$(python3 - "$_harness_file_path" "${HARNESS_FAMILY_CODE_PATHS[@]}" <<'PY'
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
        if [ "$_harness_match" = "yes" ] && [ -z "${HARNESS_CODEX_SESSION_ID:-}" ]; then
            echo "[$HARNESS_FAMILY_SLUG BLOCKED] code-path edit on $_harness_file_path requires an active Codex session. Run scripts/spawn_codex_session.sh first." >&2
            exit 2
        fi
    fi
fi
# --- end harness profile-driven enforcement (V2.1) ---

# harness:profile:enforcement:end

exit 0
