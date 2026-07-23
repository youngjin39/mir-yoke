# Embedding Index Lifecycle Shape (template guidance)

Status: adopted template direction (2026-07-23). This document proposes the
target shape for any repository bootstrapped from this template that stores
embedding vectors. It is guidance only: it adds no runtime dependency and does
not change the shipped memory engine.

## Why

The shipped memory engine (`src/mir/core/engine/memory/`) stores vectors in a
single `facts_vec` table keyed only by row id, with no record of which encoder
produced them. That is safe while exactly one embedding model ever exists, and
unsafe the moment a model is added or replaced: old vectors get silently
compared against new-model query vectors, and a destructive rebuild is the only
recovery. Treat the current shape as a **registered legacy active index**, not
as the target design.

## Identity rules (adopt from day one)

1. **A vector is valid only together with its complete encoder fingerprint** —
   model identity/revision, dimension, normalization, pooling, and any
   query/document instruction. A model name alone is not an identity.
2. **Cache and skip decisions key on `(document_fingerprint, content_hash)`** —
   never on a text hash alone.
3. **Query and document roles may differ** (instruction-aware models); plan for
   `encode_documents` / `encode_query` rather than a single `encode`.
4. Never compare vectors or mix raw distances across fingerprints; cross-model
   comparison fuses independent rankings (e.g. RRF).

## Target metadata shape (when versioning is needed)

One physical vector table per index version, plus lifecycle metadata:

```sql
CREATE TABLE embedding_index_version (
  logical_index         TEXT NOT NULL,
  version_id            TEXT NOT NULL,
  physical_table        TEXT NOT NULL UNIQUE,   -- generated: <logical>__e_<version>
  document_fingerprint  TEXT NOT NULL,
  query_fingerprint     TEXT NOT NULL,
  dimension             INTEGER NOT NULL,
  metric                TEXT NOT NULL,
  state                 TEXT NOT NULL,          -- declared|preparing|backfilling|shadow|active|previous|retired|gc|failed
  created_at            TEXT NOT NULL,
  activated_at          TEXT,
  retired_at            TEXT,
  PRIMARY KEY (logical_index, version_id)
);
-- partial-unique: one active, one previous, one in-flight candidate per logical_index
```

Invariants: exactly one `active` version per logical index; cutover and
rollback are atomic pointer rotations (rollback never re-embeds); retention
ceiling of candidate + active + previous; garbage collection is explicit and
last. Consumers resolve logical index → physical table through one resolver.

## What a new project should do

- **At bootstrap**: nothing extra — but record the encoder fingerprint next to
  any vectors you write, and key caches on `(fingerprint, content_hash)`.
- **Before adding or replacing a model**: adopt a lifecycle manager implementing
  the shape above (a maintained implementation exists in the operator's fleet as
  the `mir-embedding-lifecycle` package — versioned sidecars, resumable backfill,
  shadow evaluation, atomic cutover/rollback, read-only MCP). Do not bolt a
  second model onto a single fingerprint-less table.
- **Never** rebuild an index destructively as the migration strategy; build the
  candidate next to the active index and switch pointers.
