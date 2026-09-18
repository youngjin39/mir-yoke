# Declared relationships in repository memory

Use this adapter when the repository already has Mir memory and the task needs maintained explicit
relationships. Provider versions that include the memory adapter support `--memory` on
`mir relations query` and `mir relations bundle` below. Older versions continue with their existing adapter or
ordinary search. Do not initialize a DB or populate a corpus solely to make retrieval available.

## Authorized ingestion

From the owning repository root, an authorized author can add `memory_relations` to an already
whitelisted Markdown source. Each entry is exactly `[subject, predicate, object]`. The initial
allowlist is `realized_by`, `implemented_in`, `verified_by`, and `depends_on`. These are explicit
source declarations, not inferred links from prose, imports, co-mentions, or embedding similarity.

```yaml
---
title: Checkout structure
status: accepted
memory_relations:
  - [REQ-CHECKOUT, realized_by, MOD-CHECKOUT]
  - [MOD-CHECKOUT, implemented_in, src/checkout.py]
  - [REQ-CHECKOUT, verified_by, tests/test_checkout.py]
  - [MOD-CHECKOUT, depends_on, MOD-PAYMENT]
---
The declaration records the maintained checkout boundary.
```

The referenced files must exist and satisfy the repository's protections. With an existing memory
DB, ingest the source through the normal writer:

```bash
mir memory ingest-md docs/decisions/adr-checkout.md
```

The writer stores entity-object facts and stated provenance in the existing schema. It preserves
multiple targets and independent sources, and reconciles changes per declaring source rather than
applying scalar replacement to all dependencies. Repeated unchanged ingestion is a no-op; removing
or changing a declaration retires that source's previous relation evidence while preserving history.
Malformed declarations must not leave partially written memory. No embedding call is needed.

## Read-only retrieval

```bash
mir relations bundle REQ-CHECKOUT --memory --root . --purpose implementation --purpose verification
mir relations query MOD-CHECKOUT --memory --root . --purpose dependencies --depth 1
```

`--memory` selects only `.mir/memory.db` beneath the explicit root and cannot be combined with
`--graph`. The existing YAML default and four purposes remain unchanged. Read only current declared
relation facts with matching scope and provenance; changed, missing or inactive sources cannot
substantiate a current answer. Returned evidence identifies memory facts and original source
locators, not fictitious YAML line numbers. Read the selected current source before claiming behavior.

Declarations are limited to 64 per source and 1 MiB of physical source bytes. The reader limits
its scan to 2,048 rows, source validation to 4 MiB total, and retained evidence to eight proofs per
edge. Use the same bounded depth, edge and output-byte budgets. Independent supporting sources are retained as
provenance without making duplicate traversal paths. A truncated answer is incomplete. An absent
or unusable source may yield a bundle search hint; no ordinary search is performed by that hint.

Retrieval does not create tables, upgrade a database, index facts, perform checkpoints or write
sidecars. A non-empty WAL can make an immutable snapshot stale; follow the repository's existing
owner-controlled memory operation rather than bypassing that refusal. Source deletion excludes its
relations from current retrieval; persistent retirement follows the existing reconciliation flow.

This adapter does not implement natural-language relation extraction, similarity-based admission,
automatic backfill of old memory, historical/as-of queries, or new relationship families. Extending
those requires separate semantics and evidence, not merely adding a predicate name to a document.
