#!/bin/bash
# Optional TaskCompleted advisory: report open ledger categories without blocking completion.
# Multi-schema support (P1-quality): accepts 'changes', 'history', 'entries' as list-type entry keys,
# plus root-level 'categories' for flat ledgers.
#
# Output format (pipe-delimited single line, avoiding colon-delimited fragility — BUG W1):
#   UNKNOWN_SCHEMA
#   EMPTY
#   OPEN|<entry_id>|<comma_separated_open_cats>
#   CLOSED
#   NO_CATEGORIES
#
# Pipe (|) is safe as a delimiter: entry IDs are slugs (alphanumeric + dashes),
# category names are alphanumeric + underscores — neither contains |.
# This avoids the bash 3.2 incompatibility of mapfile and the colon-split
# fragility of the original format (W1 fix).
#
# Unknown status values are treated as OPEN (fail-safe policy: unknown != closed).

set -u

_MIR_HOOK_TIER="warn"

TDD_JSON="${CLAUDE_PROJECT_DIR:-.}/tasks/tdd.json"

if [ ! -f "$TDD_JSON" ]; then
  echo "[tdd-task-completed WARN] no tdd.json — verify the task with focused evidence" >&2
  exit 0
fi

if ! RESULT=$(python3 -c "
import json, sys

CLOSED = {'pass', 'not_applicable', 'covered_existing'}

data = json.load(open('$TDD_JSON'))

# Resolve entries list from known schemas (priority order).
entries = None
for key in ('changes', 'history', 'entries'):
    val = data.get(key)
    if isinstance(val, list):
        entries = val
        break

if entries is None:
    root_categories = data.get('categories')
    if isinstance(root_categories, dict):
        entry_id = data.get('id', data.get('task', '<root>'))
        categories = root_categories
    else:
        # Legacy flat-object schema — cannot enforce; allow.
        sys.stdout.write('UNKNOWN_SCHEMA')
        sys.exit(0)
else:
    if not entries:
        sys.stdout.write('EMPTY')
        sys.exit(0)

    last = entries[-1]
    entry_id = last.get('id', '<unknown>')
    categories = last.get('categories')

# If this entry has no 'categories' key at all, the ledger uses a different semantics.
# Gracefully allow — we cannot enforce what we cannot read.
if categories is None:
    sys.stdout.write('NO_CATEGORIES')
    sys.exit(0)

# Defensive: categories must be a dict
if not isinstance(categories, dict):
    sys.stdout.write('OPEN|' + entry_id + '|_invalid_categories_type')
    sys.exit(0)

# Defensive: empty categories dict means nothing is closed
if not categories:
    sys.stdout.write('OPEN|' + entry_id + '|_no_categories')
    sys.exit(0)

open_cats = []
for name, v in categories.items():
    # Defensive: category value must be a dict with a status key
    if not isinstance(v, dict) or 'status' not in v:
        open_cats.append(name)
        continue
    status = v['status']
    # Unknown status values are treated as OPEN (fail-safe: unknown != closed)
    if status not in CLOSED:
        open_cats.append(name)

if open_cats:
    sys.stdout.write('OPEN|' + entry_id + '|' + ','.join(open_cats))
else:
    sys.stdout.write('CLOSED')
" 2>/dev/null); then
  echo "[tdd-task-completed WARN] tdd.json parse error (advisory only)" >&2
  exit 0
fi

if [ -z "$RESULT" ]; then
  echo "[tdd-task-completed WARN] tdd.json parse returned empty (advisory only)" >&2
  exit 0
fi

# Legacy flat-object schema — no list-type entries; cannot enforce; allow.
if [ "$RESULT" = "UNKNOWN_SCHEMA" ]; then
  exit 0
fi

# Entry exists but has no 'categories' key — different ledger semantics; allow.
if [ "$RESULT" = "NO_CATEGORIES" ]; then
  exit 0
fi

if [ "$RESULT" = "EMPTY" ]; then
  echo "[tdd-task-completed WARN] tdd.json has no entries (advisory only)" >&2
  exit 0
fi

if [ "${RESULT%%|*}" = "OPEN" ]; then
  # Strip leading "OPEN|" then split on first |
  REST="${RESULT#OPEN|}"
  ENTRY_ID="${REST%%|*}"
  OPEN_CATS="${REST#*|}"
  echo "[tdd-task-completed WARN] ledger entry $ENTRY_ID still has open categories: $OPEN_CATS (advisory only)" >&2
  exit 0
fi

exit 0
