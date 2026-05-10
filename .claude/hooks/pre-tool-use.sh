#!/bin/bash
# pre-tool-use.sh
# Input-stage guardrail. Reads tool_input from stdin (JSON).
# Exit 2 = block. Exit 0 = allow.

set -u

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$PWD}"
DENY_LIST_FILE="$PROJECT_DIR/.ai-harness/deny-list.yaml"
TDD_GUARD_SCRIPT="$PROJECT_DIR/.claude/hooks/tdd-guard.sh"

INPUT=$(cat)

block() {
  echo "[PreToolUse BLOCK] $1" >&2
  exit 2
}

warn() {
  echo "[PreToolUse WARN] $1" >&2
}

require_jq() {
  command -v jq >/dev/null 2>&1 || block "jq is required for PreToolUse parsing"
}

extract_json() {
  local filter="$1"
  local value
  if ! value=$(printf '%s' "$INPUT" | jq -er "$filter" 2>/dev/null); then
    return 1
  fi
  printf '%s' "$value"
}

# ---- Deny list scan ----
emit_deny_patterns() {
  # Tiny YAML reader for the limited shape used in deny-list.yaml.
  # Each entry: `- id: ...\n  pattern: ...\n  severity: ...\n  reason: ...`
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
    /^[[:space:]]*-[[:space:]]+id:/ { emit_row(); id = trim_field($0); next }
    id != "" && /^[[:space:]]+pattern:/  { pattern  = trim_field($0); next }
    id != "" && /^[[:space:]]+severity:/ { severity = trim_field($0); next }
    id != "" && /^[[:space:]]+reason:/   { reason   = trim_field($0); next }
    END { emit_row() }
  ' "$1"
}

apply_deny_list() {
  local subject="$1"
  local label="$2"
  [ -n "$subject" ] || return 0
  [ -f "$DENY_LIST_FILE" ] || return 0

  while IFS=$'\t' read -r id pattern severity reason; do
    [ -n "$id" ] || continue
    [ -n "$pattern" ] || continue
    if printf '%s' "$subject" | grep -qE "$pattern"; then
      case "$severity" in
        block) block "deny-list[$id] $label: $reason" ;;
        warn)  warn  "deny-list[$id] $label: $reason" ;;
      esac
    fi
  done < <(emit_deny_patterns "$DENY_LIST_FILE")
}

require_jq
TOOL_NAME="$(extract_json '.tool_name')" || block "Malformed PreToolUse payload"

# ---- Bash command guard ----
if [ "$TOOL_NAME" = "Bash" ]; then
  CMD="$(extract_json '.tool_input.command')" || exit 0
  apply_deny_list "$CMD" "bash"
  exit 0
fi

# ---- Edit/Write/apply_patch path guard ----
case "$TOOL_NAME" in
  Edit|Write|apply_patch)
    FP="$(extract_json '.tool_input.file_path // .tool_input.path')" || exit 0
    [ -n "$FP" ] || exit 0
    apply_deny_list "$FP" "path"
    if [ -f "$TDD_GUARD_SCRIPT" ]; then
      bash "$TDD_GUARD_SCRIPT" "$FP" || exit 2
    fi
    ;;
esac

exit 0
