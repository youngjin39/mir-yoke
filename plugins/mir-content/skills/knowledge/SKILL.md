---
name: knowledge
description: "Knowledge ingest and lint for the shared wiki/knowledge graph.\n\nTrigger: knowledge, wiki, ingest, knowledge graph, knowledge lint\n\nAbsorbs: knowledge-ingest, knowledge-lint"
---

# Knowledge

## Use When
- When ingesting an external source into the shared wiki or knowledge graph.
- When health-checking the LLM Wiki for contradictions, stale claims, orphans, or gaps.

## Absorbed legacy skills
- knowledge-ingest — Ingest external source into LLM Wiki. Raw to wiki pages + log.
- knowledge-lint — Health-check the LLM Wiki. Contradictions, stale claims, orphans, gaps.

## Workflow
1. Record source identity, retrieval date, authority, scope, and any licensing or privacy constraint before ingesting content.
2. Separate source facts, interpretation, decisions, and open questions. Preserve citations or durable local references for every reusable claim.
3. Normalize concepts and aliases against the existing taxonomy before creating a new node or page.
4. Link each new item to owners, related concepts, superseded claims, and downstream consumers; do not leave isolated pages without an explicit reason.
5. Lint for contradictory active claims, expired facts, missing provenance, broken links, duplicates, and taxonomy gaps.
6. Publish only the scoped knowledge update and a short ingest log describing what changed and what remains uncertain.
