#!/bin/sh
# Run hook Python through the exact project-owned Mir wrapper without network access.
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/../../../.." && pwd)
export UV_OFFLINE=1
exec "$root/scripts/mir.sh" run-python --project-root "$root" -- "$@"
