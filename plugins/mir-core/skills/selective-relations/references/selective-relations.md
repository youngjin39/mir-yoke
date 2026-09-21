# Declared relationship retrieval

Selective Relation Retrieval (SRR) answers a narrow set of questions from maintained, typed
relationships. An edge is a provenance-bearing locator to an authoritative record. It is not an
inferred call graph, a source excerpt, runtime tracing, or a replacement for the target record.

## Admit and interpret relationships

Maintain a relationship only when it serves a concrete reusable question family, has an explicit type
and direction, and points to authoritative evidence with an owner or equivalent update path. Useful
families include requirement-to-implementation, requirement-to-verification, and declared module
dependencies. Do not add generic co-mention links merely because items seem related.

The portable reader reads the approved graph view exactly as supplied. It does not filter historical,
superseded, candidate, uncertain, or time-scoped facts. Use an approved current view for current
claims; use a repository-native temporal or history adapter for as-of and candidate questions.
Preserve the graph path, content hash, and edge locator with any conclusion derived from it.

## Select the smallest useful question

| Question | Purpose | Declared meaning |
| --- | --- | --- |
| Where is this requirement implemented? | `implementation` | Implementation locators. |
| Which checks substantiate this requirement? | `verification` | Verification locators. |
| What declared consumers could be affected, when explicitly requested? | `impact` | Optional downstream declared relationships; not part of routine bundles. |
| What declared components does this work depend on? | `dependencies` | Forward `depends_on` relationships. |

Prefer `implementation`, `verification`, and direct `dependencies` for routine SRR use.
For a known anchor and one unresolved purpose, use `query`. Use `bundle` only when two or more unresolved
purposes concern the same anchor. Do not bundle unrelated anchors. For a direct declared dependency,
request `--depth 1`; otherwise use only the hops needed for the evidence path. Do not include
`impact` unless the task explicitly asks for it. Fewer bundle calls do not guarantee smaller output.

```yaml
# spec/graph.yaml
edges:
  - [REQ-LOGIN, realized_by, MOD-AUTH]
  - [MOD-AUTH, implemented_in, src/auth/login.py]
  - [REQ-LOGIN, verified_by, tests/test_login.py]
  - [MOD-AUTH, depends_on, MOD-TOKEN]
  - [MOD-TOKEN, implemented_in, src/auth/token_store.py]
```

```bash
"$MIR_SRR_PROVIDER" relations query REQ-LOGIN --purpose implementation --root "$MIR_SRR_ROOT"
"$MIR_SRR_PROVIDER" relations bundle REQ-LOGIN --purpose implementation --purpose verification --root "$MIR_SRR_ROOT"
"$MIR_SRR_PROVIDER" relations query MOD-AUTH --purpose dependencies --root "$MIR_SRR_ROOT" --depth 1
"$MIR_SRR_PROVIDER" relations query REQ-LOGIN --purpose implementation --root "$MIR_SRR_ROOT" --graph relations/declared.yaml
```

`MIR_SRR_PROVIDER` and `MIR_SRR_ROOT` are delivery-selected absolute paths. Verify the selected
provider once at setup, adoption, or runtime change; do not probe every query. If it cannot serve
this adapter, return to ordinary search rather than using a bare or repository-local Mir command.

From provider 0.10.3, omitted depth defaults to 1 for `dependencies` and 3 for other purposes.
A bundle applies these defaults independently per purpose. An explicit `--depth` overrides every
requested purpose, including deeper dependency exploration when the task requires it. Earlier
providers require explicit `--depth 1` for direct dependencies. On those providers, keep a direct
dependency query separate from implementation/verification queries that need deeper traversal.

The reader uses an explicit `--root`, defaults to `spec/graph.yaml`, and accepts a repository-relative
`--graph`. Its default result budget is 16 edges and 6000 bytes; hard ceilings are depth 4, 64 edges,
and 16000 bytes. A truncated result is incomplete evidence. Do not raise every limit or claim
completeness because a result was truncated.

The reader validates graph and file locators beneath the explicit root, rejects unsafe and protected
paths, and respects target Profile protections when present. By default it reads a local declared YAML triple
file. The explicit `--memory` adapter is described in [the memory reference](memory-relations.md). It never creates source files or graphs, writes a database, extracts relations, or changes
the repository.

## Fallback and verification

An unavailable graph makes `query` report an error. An eligible `bundle` returns `route=search` as a
hint to use ordinary search; it does not perform that search. Unknown anchors, unsupported relation
types, ambiguous ownership, multi-anchor joins, graph-wide discovery, and source-level questions
also require ordinary search and direct evidence.

After retrieval, use the compact result to select the minimum current source span needed for a
behavioral claim or edit. Do not read every connected file merely because it was returned.
Distinguish the declared relation from observed behavior, and stop when the stated question is
answered.
