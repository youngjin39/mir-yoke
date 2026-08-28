#!/bin/bash
# PostToolUse hook for Edit|Write|apply_patch: debug statements + credential leak detection
# Reads tool_input from stdin (JSON)

INPUT=$(cat)

block() {
  echo "[PostToolUse BLOCK] $1" >&2
  exit 2
}

require_jq() {
  if ! command -v jq >/dev/null 2>&1; then
    block "jq is required for PostToolUse parsing"
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

require_jq
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
DIRECT_PATH="$(extract_json '.tool_input.file_path // .tool_input.path // ""')" || DIRECT_PATH=""
PATCH_BODY="$(extract_json '.tool_input.command // .tool_input.input // .tool_input.patch // .tool_input.content // ""')" || PATCH_BODY=""
PATHS="$(
  {
    [ -n "$DIRECT_PATH" ] && printf '%s\n' "$DIRECT_PATH"
    printf '%s\n' "$PATCH_BODY" | sed -nE \
      -e 's/^\*\*\* (Add|Update|Delete) File: (.*)$/\2/p' \
      -e 's/^\*\*\* Move to: (.*)$/\1/p'
  } | awk 'NF && !seen[$0]++'
)"

[ -n "$PATHS" ] || exit 0
WARNINGS=""

while IFS= read -r RAW_PATH; do
  [ -n "$RAW_PATH" ] || continue
  case "$RAW_PATH" in
    /*) FILE_PATH="$RAW_PATH" ;;
    *) FILE_PATH="$PROJECT_DIR/$RAW_PATH" ;;
  esac
  [ -f "$FILE_PATH" ] || continue

  DISPLAY_PATH="${FILE_PATH#"$PROJECT_DIR"/}"
  EXT="${FILE_PATH##*.}"

  # 1. Debug statement check (capture output, don't leak to stdout)
  case "$EXT" in
    js|ts|jsx|tsx)
      DEBUG_HITS=$(grep -n "console\.log" "$FILE_PATH" 2>/dev/null | head -3)
      if [ -n "$DEBUG_HITS" ]; then
        WARNINGS="${WARNINGS:+$WARNINGS
}[WARNING] console.log detected in $DISPLAY_PATH
$DEBUG_HITS"
      fi
      ;;
    py)
      DEBUG_HITS=$(grep -n "^\s*print(" "$FILE_PATH" 2>/dev/null | grep -v "# keep" | head -3)
      if [ -n "$DEBUG_HITS" ]; then
        WARNINGS="${WARNINGS:+$WARNINGS
}[WARNING] print() detected in $DISPLAY_PATH
$DEBUG_HITS"
      fi
      ;;
  esac

  # 2. Credential leak check (20+ char after sk- to avoid false positives)
  case "$EXT" in
    md|json|yaml|yml|sh|ts|js|py|env|toml|cfg)
      CRED_HITS=$(grep -nE '(sk-[a-zA-Z0-9_-]{20,}|ghp_[a-zA-Z0-9]{36}|gho_[a-zA-Z0-9]{36}|AIza[a-zA-Z0-9_-]{35}|xoxb-[0-9]{10,}|AKIA[A-Z0-9]{16}|aws_secret_access_key[[:space:]]*=)' "$FILE_PATH" 2>/dev/null | cut -d: -f1 | head -3 | paste -sd, -)
      if [ -n "$CRED_HITS" ]; then
        WARNINGS="${WARNINGS:+$WARNINGS
}[CRITICAL] Possible credential/API key detected in $DISPLAY_PATH at line(s) $CRED_HITS — value redacted; rotate immediately if real."
      fi
      ;;
  esac
done <<EOF
$PATHS
EOF

if [ -n "$WARNINGS" ]; then
  echo "$WARNINGS"
fi

exit 0
