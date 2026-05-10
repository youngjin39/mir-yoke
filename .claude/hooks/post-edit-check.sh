#!/bin/bash
# post-edit-check.sh
# Reads tool_input from stdin (JSON) after an Edit / Write / apply_patch.
# Soft warnings only — never blocks the edit, just surfaces concerns.

set -u

INPUT=$(cat)

require_jq() {
  command -v jq >/dev/null 2>&1 || exit 0
}

require_jq

FP=$(printf '%s' "$INPUT" | jq -er '.tool_input.file_path // .tool_input.path' 2>/dev/null) || exit 0
[ -n "$FP" ] && [ -f "$FP" ] || exit 0

# Skip checks on test files and non-source extensions.
case "$FP" in
  *test_*|*_test*|*.test.*) exit 0 ;;
esac

EXT="${FP##*.}"

# ---- Debug-statement scan ----
case "$EXT" in
  js|ts|jsx|tsx|mjs|cjs)
    HITS=$(grep -nE "\bconsole\.(log|debug|trace)\b" "$FP" 2>/dev/null | head -3)
    [ -n "$HITS" ] && echo "[PostEdit warn] debug statements in $FP:" >&2 && echo "$HITS" >&2
    ;;
  py)
    HITS=$(grep -nE "(^|[^a-zA-Z_])print\(|breakpoint\(\)|pdb\." "$FP" 2>/dev/null | head -3)
    [ -n "$HITS" ] && echo "[PostEdit warn] debug statements in $FP:" >&2 && echo "$HITS" >&2
    ;;
  go)
    HITS=$(grep -nE "fmt\.Print|log\.Print|println\(" "$FP" 2>/dev/null | head -3)
    [ -n "$HITS" ] && echo "[PostEdit warn] debug statements in $FP:" >&2 && echo "$HITS" >&2
    ;;
  rb)
    HITS=$(grep -nE "puts |binding\.pry|byebug" "$FP" 2>/dev/null | head -3)
    [ -n "$HITS" ] && echo "[PostEdit warn] debug statements in $FP:" >&2 && echo "$HITS" >&2
    ;;
esac

# ---- Credential-shape scan ----
# Patterns chosen to catch the obvious cases without flagging every base64 string.
CREDS=$(grep -nE "(AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,}|xox[baprs]-[A-Za-z0-9-]{10,}|eyJ[A-Za-z0-9_-]{20,}\\.[A-Za-z0-9_-]{20,}\\.)" "$FP" 2>/dev/null | head -3)
if [ -n "$CREDS" ]; then
  echo "[PostEdit WARN] credential-shaped strings in $FP — verify before committing:" >&2
  echo "$CREDS" >&2
fi

exit 0
