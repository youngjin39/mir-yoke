#!/usr/bin/env bash
# Thin macOS/Linux/WSL wrapper. The Python coordinator owns bootstrap logic.

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

say() { printf '%s\n' "$*"; }
die() { printf '[ERROR] %s\n' "$*" >&2; exit 1; }

command -v uv >/dev/null 2>&1 || die "uv is required: https://docs.astral.sh/uv/"

say "mir-yoke setup ▸ root=$ROOT"
say "syncing Python environment"
uv sync --project "$ROOT"

say "running portable bootstrap coordinator"
uv run --project "$ROOT" mir bootstrap --project-root "$ROOT" "$@"
