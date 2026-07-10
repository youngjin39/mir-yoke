---
name: memory-gc
description: "Run GC scan on memory facts: mark expired entries (valid_to < today). User-triggered only — never auto-fire."
context: fork
---

# memory-gc

Scan the the memory database for facts whose `valid_to` date has passed and mark them `expired`.

## Usage

Dry-run (default — no changes):
```
python scripts/memory_gc_runner.py --dry-run
```

Confirm mode (applies changes):
```
python scripts/memory_gc_runner.py --confirm
```

## Safety
- Default is always dry-run.
- Never enable the launchd plist automatically. Manual `launchctl load` required.
- Facts without `valid_to` are never expired by GC.
