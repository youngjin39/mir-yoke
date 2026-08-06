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
mir memory gc
```

Confirm mode (applies changes):
```
mir memory gc --apply
```

## Safety
- Default is always dry-run.
- Run apply mode only after the user explicitly requests memory mutation and reviews the dry-run count.
- Facts without `valid_to` are never expired by GC.
