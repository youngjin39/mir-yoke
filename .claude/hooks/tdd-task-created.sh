#!/bin/bash
# TaskCreated advisory: payloads have no stable change id, so this never blocks.
# Multi-schema support (P1-quality): accepts 'changes', 'history', 'entries',
# root-level 'categories', and root-level 'targets'.

set -u

_MIR_HOOK_TIER="warn"

TDD_JSON="${CLAUDE_PROJECT_DIR:-.}/tasks/tdd.json"

if [ ! -f "$TDD_JSON" ]; then
  echo "[tdd-task-created WARN] no tdd.json — add relevant verification evidence first" >&2
  exit 0
fi

if ! RESULT=$(python3 -c "
import json, sys

data = json.load(open('$TDD_JSON'))

keyed_entries = [
    value for key, value in data.items()
    if key not in ('version', 'changes', 'history', 'entries')
    and isinstance(value, dict) and isinstance(value.get('categories'), dict)
    and value['categories']
]
if keyed_entries:
    sys.stdout.write('KEYED:' + str(len(keyed_entries)))
    sys.exit(0)

# Try each known list-type entry key in priority order.
for key in ('changes', 'history', 'entries'):
    val = data.get(key)
    if isinstance(val, list):
        valid = [
            entry for entry in val
            if isinstance(entry, dict) and isinstance(entry.get('categories'), dict)
            and entry['categories']
        ]
        sys.stdout.write('LIST:' + str(len(valid)))
        sys.exit(0)

# Flat root-level categories: treat as an active composite ledger.
root_categories = data.get('categories')
if isinstance(root_categories, dict):
    sys.stdout.write('ROOT:' + str(len(root_categories)))
    sys.exit(0)

sys.stdout.write('UNKNOWN_SCHEMA')
" 2>/dev/null); then
  echo "[tdd-task-created WARN] tdd.json parse error (advisory only)" >&2
  exit 0
fi

if [ -z "$RESULT" ]; then
  echo "[tdd-task-created WARN] tdd.json parse returned empty (advisory only)" >&2
  exit 0
fi

if [ "$RESULT" = "UNKNOWN_SCHEMA" ]; then
  echo "[tdd-task-created WARN] tdd.json has no recognizable ledger entry (advisory only)" >&2
  exit 0
fi

CHANGES_COUNT="${RESULT#*:}"

if [ "$CHANGES_COUNT" = "0" ]; then
  echo "[tdd-task-created WARN] tdd.json has no entries (advisory only)" >&2
  exit 0
fi

exit 0
