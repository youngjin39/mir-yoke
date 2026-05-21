#!/bin/bash
# SessionStart hook: inject startup context into the session
# stdout → Claude's context window

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"

echo "=== SESSION CONTEXT ==="

if [ -f "$PROJECT_DIR/tasks/plan.md" ]; then
  echo "--- plan.md ---"
  head -50 "$PROJECT_DIR/tasks/plan.md"
fi

echo ""

if [ -f "$PROJECT_DIR/tasks/lessons.md" ]; then
  echo "--- lessons.md ---"
  head -50 "$PROJECT_DIR/tasks/lessons.md"
fi

echo ""

if [ -f "$PROJECT_DIR/docs/memory-map.md" ]; then
  echo "--- memory-map.md ---"
  head -80 "$PROJECT_DIR/docs/memory-map.md"
fi

echo ""

# Latest session snapshot (if exists) — use find to avoid glob expansion issues
LATEST_SESSION=$(find "$PROJECT_DIR/tasks/sessions" -name "*.md" -type f 2>/dev/null | sort -r | head -1)
if [ -n "$LATEST_SESSION" ] && [ -f "$LATEST_SESSION" ]; then
  echo "--- latest session ---"
  head -50 "$LATEST_SESSION"
fi

echo ""

LATEST_RUNNER=$(find "$PROJECT_DIR/tasks/runner" -name "*.md" -type f 2>/dev/null | sort -r | head -1)
if [ -n "$LATEST_RUNNER" ] && [ -f "$LATEST_RUNNER" ]; then
  echo "--- latest runner ---"
  head -80 "$LATEST_RUNNER"
fi

echo "=== END SESSION CONTEXT ==="

# harness:profile:enforcement:begin
# Generated harness session-start banner. See README for customization.
# To update this block, edit .mir/harness-config.json (optional) and
# re-run scripts/generate_codex_derivatives.sh if present.
_get_session_family_slug() {
    local cfg="${CLAUDE_PROJECT_DIR:-.}/.mir/harness-config.json"
    if [ -f "$cfg" ]; then
        python3 -c "import json,sys; print(json.load(open('$cfg')).get('family_slug', ''))" 2>/dev/null || true
    fi
}
_session_slug="$(_get_session_family_slug)"
HARNESS_FAMILY_SLUG="${_session_slug:-$(basename "${CLAUDE_PROJECT_DIR:-.}")}"
HARNESS_CODEX_DEFAULT_ENABLED="true"
echo "[$HARNESS_FAMILY_SLUG] role policy active: claude=control_plane codex=code_tdd_review_plane codex_default=$HARNESS_CODEX_DEFAULT_ENABLED family=$HARNESS_FAMILY_SLUG" >&2
if [ -n "${HARNESS_CODEX_SESSION_ID:-}" ]; then
    echo "[$HARNESS_FAMILY_SLUG] active codex session: $HARNESS_CODEX_SESSION_ID modes=$HARNESS_CODEX_ALLOWED_MODES" >&2
elif [ "$HARNESS_CODEX_DEFAULT_ENABLED" = "true" ]; then
    echo "[$HARNESS_FAMILY_SLUG] no active codex session — code edits in code_paths will be blocked by pre-tool-use hook" >&2
fi

# harness:profile:enforcement:end
