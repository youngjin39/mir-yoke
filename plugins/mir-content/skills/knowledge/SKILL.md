---
name: knowledge
description: "Ingest and lint knowledge in a repository-owned or explicitly configured knowledge system. Use for knowledge, wiki, ingest, knowledge graph, taxonomy, provenance, contradiction, stale-claim, orphan, or knowledge-lint work."
---

# Knowledge

1. Locate the repository-owned or explicitly configured knowledge destination, schema, ownership,
   and write authority. If none exists, propose a local artifact or ask for a destination; do not
   assume a shared service.
2. Record source identity, retrieval date, authority, scope, and licensing or privacy constraints.
3. Separate source facts, interpretation, decisions, and open questions. Preserve citations or
   durable references for every reusable claim.
4. Normalize concepts and aliases against the selected taxonomy before creating a node or page.
5. Link each new item to owners, related concepts, superseded claims, and downstream consumers; mark
   intentional orphans explicitly.
6. Lint for contradictory active claims, expired facts, missing provenance, broken links,
   duplicates, and taxonomy gaps.
7. Write only to the user-authorized destination and report what changed and remains uncertain.

For a known anchor with maintained implementation, verification, or direct-dependency evidence,
`mir-core:selective-relations` may provide optional read-only retrieval. It does not replace the
repository's knowledge system or require graph creation, indexing, or writes.

For authorized Mir-memory ingestion of explicit typed relationships, consult the memory adapter
reference in `mir-core:selective-relations`. Preserve source evidence and source-scoped updates.
