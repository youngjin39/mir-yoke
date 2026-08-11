#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"
if [ ! -f .mir/memory.db ]; then
    echo "memory index is absent; run the declared memory_init command" >&2
    exit 2
fi
exec scripts/mir.sh context sync --db .mir/memory.db --project-root .
