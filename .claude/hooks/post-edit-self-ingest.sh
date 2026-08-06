#!/usr/bin/env bash
# Keep the required local memory index current after durable Markdown edits.

set -euo pipefail

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
exec python3 "$PROJECT_DIR/scripts/post_edit_memory_sync.py" "$PROJECT_DIR"
