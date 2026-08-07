#!/usr/bin/env bash
_MIR_PYTHON_LAUNCHER="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/_lib/run-python.sh"
# Keep the required local memory index current after durable Markdown edits.

set -euo pipefail

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
exec "$_MIR_PYTHON_LAUNCHER" "$PROJECT_DIR/scripts/post_edit_memory_sync.py" "$PROJECT_DIR"
