#!/bin/bash
# SessionEnd hook: refresh the canonical handoff only.

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
HANDOFF_FILE="$PROJECT_DIR/tasks/handoffs/session-handoff-LATEST.md"
export CLAUDE_PROJECT_DIR="$PROJECT_DIR"

/bin/bash "$SCRIPT_DIR/pre-compact.sh"

echo "[SessionEnd] Closeout state: $HANDOFF_FILE"
