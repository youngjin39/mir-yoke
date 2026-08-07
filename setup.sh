#!/usr/bin/env bash
# Thin macOS/Linux/WSL wrapper. The Python coordinator owns bootstrap logic.

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

say() { printf '%s\n' "$*"; }
die() { printf '[ERROR] %s\n' "$*" >&2; exit 1; }

command -v uv >/dev/null 2>&1 || die "uv is required: https://docs.astral.sh/uv/"

STORAGE_ROOT=""
EXPECT_STORAGE_ROOT=false
for arg in "$@"; do
  if "$EXPECT_STORAGE_ROOT"; then
    STORAGE_ROOT="$arg"
    EXPECT_STORAGE_ROOT=false
    continue
  fi
  case "$arg" in
    --storage-root)
      EXPECT_STORAGE_ROOT=true
      ;;
    --storage-root=*)
      STORAGE_ROOT="${arg#--storage-root=}"
      ;;
  esac
done
"$EXPECT_STORAGE_ROOT" && die "--storage-root requires a path"

if [[ -n "$STORAGE_ROOT" ]]; then
  mkdir -p -- \
    "$STORAGE_ROOT/uv/cache" \
    "$STORAGE_ROOT/uv/python" \
    "$STORAGE_ROOT/uv/tools" \
    "$STORAGE_ROOT/mir/capabilities"
  STORAGE_ROOT="$(cd -- "$STORAGE_ROOT" && pwd -P)"
  export UV_CACHE_DIR="$STORAGE_ROOT/uv/cache"
  export UV_PYTHON_INSTALL_DIR="$STORAGE_ROOT/uv/python"
  export UV_TOOL_DIR="$STORAGE_ROOT/uv/tools"
  export MIR_CAPABILITY_HOME="$STORAGE_ROOT/mir/capabilities"
  export UV_PROJECT_ENVIRONMENT="$ROOT/.venv"
  say "external-first storage ▸ root=$STORAGE_ROOT"
fi

say "mir-yoke setup ▸ root=$ROOT"
say "syncing Python environment"
uv sync --project "$ROOT"

say "running portable bootstrap coordinator"
uv run --project "$ROOT" mir bootstrap --project-root "$ROOT" "$@"
