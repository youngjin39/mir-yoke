#!/usr/bin/env bash
# Run hook Python through the project's managed environment. Never use host Python.

set -euo pipefail

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-${MIR_PROJECT_DIR:-.}}"

if [ -x "$PROJECT_DIR/.venv/bin/python" ]; then
  exec "$PROJECT_DIR/.venv/bin/python" "$@"
fi

if [ -x "$PROJECT_DIR/.venv/Scripts/python.exe" ]; then
  exec "$PROJECT_DIR/.venv/Scripts/python.exe" "$@"
fi

if command -v uv >/dev/null 2>&1; then
  exec uv run --project "$PROJECT_DIR" python "$@"
fi

printf '[mir hook] project Python unavailable; run setup.sh/setup.ps1 first\n' >&2
exit 127
