#!/bin/sh
# Replace {{MIR_YOKE_REVISION}} with the full observed provider revision.
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
runtime="$root/.mir/runtime"
mkdir -p "$runtime/home" "$runtime/cache" "$runtime/data" "$runtime/tmp" "$runtime/uv"

export HOME="$runtime/home"
export XDG_CACHE_HOME="$runtime/cache"
export XDG_CONFIG_HOME="$runtime/config"
export XDG_DATA_HOME="$runtime/data"
export TMPDIR="$runtime/tmp"
export UV_CACHE_DIR="$runtime/uv/cache"
export UV_TOOL_DIR="$runtime/uv/tools"
export UV_PYTHON_INSTALL_DIR="$runtime/uv/python"

exec uvx --from "git+https://github.com/youngjin39/mir-yoke@{{MIR_YOKE_REVISION}}" mir "$@"
