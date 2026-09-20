---
name: selective-relations
description: Find maintained implementation, verification, or direct-dependency evidence for a known requirement, module, or file through a read-only relation adapter. Use ordinary search for known answer locations, runtime behavior, and unknown anchors.
---

# Selective Relation Retrieval

Use selective relation retrieval (SRR) when a known anchor and maintained declared relationships
can answer an unresolved implementation, verification, or direct-dependency question. Prefer ordinary
search when the answer location is already known; SRR is not a mandatory preflight for code work.

Use one purpose at a time unless multiple unresolved purposes concern the same anchor. A bundle can
avoid repeated source reads, but its metadata may make the response larger. For direct dependencies,
use depth 1. Inspect the compact result and stop when the question is answered; do not automatically
increase depth or edge limits. Treat truncation as incomplete evidence.

Broader `impact` traversal is available only when the task explicitly asks for declared downstream
impact. Do not add it to implementation or verification bundles automatically, and do not interpret
it as an upstream dependency query or a complete runtime impact inventory.

SRR returns bounded evidence with locators, provenance and short authored summaries/reasons when
available. Start with that compact result. Open only the relevant source span when a behavioral
claim, ambiguity, contradiction or edit requires it; do not preload every related document.
The result does not prove runtime calls or inventory completeness. Missing edges do not prove
absence, and a declared rationale is source evidence rather than an independently verified cause.

Use ordinary targeted search and direct reading when the answer location is known, the task is
symbol-level debugging or runtime investigation, the anchor is unknown, or the question is outside
the repository's declared relationship types. Do not create a graph, extract links, index a memory
store, migrate a database, or write records merely to make SRR available.

## Retrieve declared evidence

When the repository has a compatible adapter and maintained declared relation source or view, read
[the retrieval reference](references/selective-relations.md) before using it. It defines the portable
reader's four supported purposes, bounded commands, current-view requirement, and fallback behavior.

Prefer an existing repository-native adapter when it supports the needed relationship.
The portable `mir relations` reader supports only `implementation`, `verification`, `impact`,
and `dependencies`. Use a compatible repository-native adapter for relationship families or storage
that this reader does not support. When evaluating a new question family or designing dynamic
relation maintenance during ingestion, read
[the applicability and memory reference](references/applicability-and-memory.md).

For existing Mir memory, read [the memory adapter reference](references/memory-relations.md)
when selecting `--memory` or handling an authorized explicit relation-ingestion task. Retrieval
itself remains read-only.

The portable reader is optional and works only in provider revisions that include it. If a compatible
adapter or relation source is absent, continue with ordinary search; do not install or preflight a tool
only for this task.
