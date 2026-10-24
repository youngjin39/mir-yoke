---
name: knowledge
description: "Ingest and lint knowledge in a repository-owned or explicitly configured knowledge system. Use for knowledge, wiki, ingest, knowledge graph, taxonomy, provenance, contradiction, stale-claim, orphan, or knowledge-lint work. Also use for answer from notes or memory, what did we decide, or prior decision lookup."
---

# Knowledge

When identity, relation or status meaning affects the task, apply `mir-core:ontology` using the project-owned mapping.

1. Locate the repository-owned or explicitly configured knowledge destination, schema, ownership,
   and write authority. If none exists, propose a local artifact or ask for a destination; do not
   assume a shared service.
2. Record source identity, retrieval date, authority, scope, and licensing or privacy constraints.
3. Separate source facts, interpretation, decisions, and open questions. Preserve citations or
   durable references for every reusable claim.
   When answering from repository memory or notes, cite the exact supporting record. If
   evidence contradicts the question's premise, state the contradiction; never substitute
   a near-match record, and keep conflicting records as an explicit unknown.
   For a learned lesson or memory note, default to no write. A positive note requires evidence
   that directly supports the claim or contradicts its premise. Near-matches and insufficient
   evidence are never positive evidence: omit them or retain them only as an explicitly labeled
   caution. This is manual and write-authorized only; add no learning loop.
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

Inspired by xiaowu0162/LongMemEval-V2 at 2cc8c54. Ideas only; wording is original.
