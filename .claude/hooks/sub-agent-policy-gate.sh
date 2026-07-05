#!/bin/bash
# Family-deploy source: standalone family-invariant force_codex Agent/Task gate. mir-self itself uses the inline gate in pre-tool-use.sh; this file is deployed to fleet families (slug-safe) via the Bash-channel + sync_family_hooks. Mirrors the inline gate logic.

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
INPUT=$(cat)

block() {
  echo "[PreToolUse BLOCK] $1" >&2
  exit 2
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

read_sub_agent_policy_mode() {
  local policy_file="$1"
  [ -f "$policy_file" ] || return 1
  if command -v jq >/dev/null 2>&1; then
    jq -er '(.mode // empty) | select(type == "string")' "$policy_file" 2>/dev/null
    return $?
  fi
  python3 - "$policy_file" <<'PY' 2>/dev/null
import json
import sys

with open(sys.argv[1], encoding="utf-8") as fh:
    data = json.load(fh)
mode = data.get("mode") if isinstance(data, dict) else None
if not isinstance(mode, str) or not mode:
    raise SystemExit(1)
print(mode)
PY
}

resolve_sub_agent_policy_mode() {
  local mode
  local policy_file="$PROJECT_DIR/config/sub-agent-policy.json"
  if ! mode="$(read_sub_agent_policy_mode "$policy_file")"; then
    printf '%s\n' "force_codex"
    return 0
  fi

  local overlay_file="${MIR_SUB_AGENT_POLICY:-}"
  if [ -n "$overlay_file" ] && [ -f "$overlay_file" ]; then
    if ! mode="$(read_sub_agent_policy_mode "$overlay_file")"; then
      printf '%s\n' "force_codex"
      return 0
    fi
  fi

  case "$mode" in
    force_codex|force_claude|select|per_project|unrestricted)
      printf '%s\n' "$mode"
      ;;
    *)
      printf '%s\n' "force_codex"
      ;;
  esac
}

require_jq
TOOL_NAME="$(extract_json '.tool_name')" || block "Malformed PreToolUse payload for filter: .tool_name"

if [ "$TOOL_NAME" != "Agent" ] && [ "$TOOL_NAME" != "Task" ]; then
  exit 0
fi

_mir_sub_agent_policy_mode="$(resolve_sub_agent_policy_mode)"
if [ "$_mir_sub_agent_policy_mode" != "force_codex" ]; then
  exit 0
fi

if [ "${MIR_R3_FALLBACK:-0}" = "1" ]; then
  echo "[mir ADVISORY] force_codex Agent/Task escape via MIR_R3_FALLBACK=1" >&2
  exit 0
fi

echo "[mir BLOCKED] sub-agent-policy mode=force_codex: Claude Agent/Task sub-agent spawn is blocked. Route sub-agent work through Codex MCP: 'mcp__codex__codex' for read-only review/investigation or 'uv run python -m tools.mir_executor execute --background --dispatch ...' for in-repo code/TDD/review writes. Raw codex exec is banned by ADR-69. To temporarily allow a Claude sub-agent set MIR_R3_FALLBACK=1; to change policy edit config/sub-agent-policy.json mode." >&2
exit 2
