---
name: selective-relations
description: Retrieve a bounded, declared evidence path for a known feature, module, file, or memory record when a repository provides typed relationship data and a read-only adapter. Use ordinary search for source behavior, unknown anchors, and unsupported relationships.
---

# Selective Relation Retrieval

Use selective relation retrieval (SRR) to find a bounded path through relationships the repository
already declares and maintains. It can answer basic project or code-structure questions from a
known feature, requirement, module, or file: which modules, files, or tests the declared evidence
connects, which declared consumers it may affect, or which components it depends on. Bundle only
when two or more unresolved purposes concern the same anchor.

SRR returns locators with provenance. It does not prove current source behavior, runtime calls, or
the completeness of the relationship inventory. Read the selected current source, tests, or decision
record before making those claims. A missing edge is not proof that no relationship exists.

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
