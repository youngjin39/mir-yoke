#!/bin/bash
# Optional TaskCreated advisory: report when tasks/tdd.json has no active ledger entry.
# This script never blocks task creation.
# Multi-schema support (P1-quality): accepts 'changes', 'history', 'entries',
# root-level 'categories', and root-level 'targets'.

set -u

_MIR_HOOK_TIER="warn"

TDD_JSON="${CLAUDE_PROJECT_DIR:-.}/tasks/tdd.json"

if [ ! -f "$TDD_JSON" ]; then
  echo "[tdd-task-created WARN] no tdd.json — consider adding focused verification evidence" >&2
  exit 0
fi

if ! RESULT=$(python3 -c "
import json, sys

data = json.load(open('$TDD_JSON'))

# Try each known list-type entry key in priority order.
for key in ('changes', 'history', 'entries'):
    val = data.get(key)
    if isinstance(val, list):
        sys.stdout.write('LIST:' + str(len(val)))
        sys.exit(0)

# Flat root-level categories: treat as an active composite ledger.
root_categories = data.get('categories')
if isinstance(root_categories, dict):
    sys.stdout.write('ROOT_CATEGORIES')
    sys.exit(0)

# Flat root-level targets: allow only when there is at least one declared target.
root_targets = data.get('targets')
if isinstance(root_targets, list):
    sys.stdout.write('TARGETS:' + str(len(root_targets)))
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

# Legacy flat-object schema with no recognizable TDD shape — allow.
if [ "$RESULT" = "UNKNOWN_SCHEMA" ]; then
  exit 0
fi

if [ "$RESULT" = "ROOT_CATEGORIES" ]; then
  exit 0
fi

if [ "${RESULT#TARGETS:}" != "$RESULT" ]; then
  TARGETS_COUNT="${RESULT#TARGETS:}"
  if [ "$TARGETS_COUNT" = "0" ]; then
    echo "[tdd-task-created WARN] tdd.json has no targets (advisory only)" >&2
    exit 0
  fi
  exit 0
fi

# LIST:<count> — extract count
CHANGES_COUNT="${RESULT#LIST:}"

if [ "$CHANGES_COUNT" = "0" ]; then
  echo "[tdd-task-created WARN] tdd.json has no entries (advisory only)" >&2
  exit 0
fi

exit 0
