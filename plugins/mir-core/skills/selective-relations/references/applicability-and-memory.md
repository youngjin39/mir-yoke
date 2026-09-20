# Applicability and dynamic relationship evidence

## Choose by question, available evidence, and reader

A useful relation reduces an otherwise repeated join between authoritative records. These are
candidate question families, not measured performance guarantees. Routine portable SRR use is
limited to implementation, verification and direct dependencies from a known anchor. Wider families
below require an explicit task and a compatible reader; they are not reasons to expand every query.
Confirm current evidence before answering and use ordinary search when the answer location is known.

| Question family | Useful bounded path | Reader boundary |
| --- | --- | --- |
| Project or subsystem orientation | Known feature or module to responsibilities, implementation files, and tests | Portable reader for supported declared paths; native adapter for other containment/ownership types |
| Implementation and verification | Requirement to implementing module/file and substantiating check | Portable `implementation` / `verification` |
| Explicit change-impact request | Known component to declared consumers and relevant checks | Optional portable `impact`; never add automatically to routine bundles; no runtime-call or exhaustive-impact claim |
| Module, service, or data dependencies | Known component to the next declared dependency | Portable `dependencies` at depth 1 for actual `depends_on` edges; native adapter for richer flow semantics |
| Design rationale and evidence | Known decision or claim to its evidence and affected components | Portable reader may return a supported decision/evidence locator; read its source; generic claim/evidence joins require a native adapter |
| Supersession, incident history, or changing knowledge | Known record to the applicable version, supported cause, or resolution evidence | Native adapter with explicit relation semantics and temporal/current-view filtering |

A simple directory listing, an already located definition, a broad unknown-topic overview, or a
runtime-call question normally needs ordinary search or repository analysis tools. Multiple unrelated
questions do not justify a combined graph traversal. An incident co-occurrence is not a causal edge.

The portable local YAML reader exposes only `implementation`, `verification`, `impact`, and
`dependencies`. It does not add flags or infer new relation semantics from these examples. An
adapter must support the needed predicates, direction, scope and current or temporal view; otherwise
fall back to search. Do not silently reinterpret `mentions` or `imports` as `depends_on`.

## Dynamic relations belong to the repository's write path

Relations need not be static. A repository's ingestion pipeline can create and update source-backed
relationships as documents, decisions or code change. SRR retrieval itself remains read-only. For existing Mir memory, the separate authorized ingestion
path can persist explicit `memory_relations` declarations; see [the memory reference](memory-relations.md).
No automatic prose or similarity extractor is provided.

Prefer an existing entity/fact/link/provenance schema before adding storage. A relation can itself
be a fact with entity endpoints and its own evidence and validity. A bare fact-to-fact link may not
carry enough provenance or lifecycle metadata for a truth-bearing claim. Native ingestion may
already extract cross-references such as ADR links; preserve their actual meaning.

Separate admission from retrieval:

- **Explicit or deterministically derived:** admit only with stable endpoint identity, an allowed
  directed predicate, authoritative source/version/locator, and a defined update owner.
- **Model-extracted:** retain the supporting source span and extraction method as a candidate;
  promote through the repository's source/semantic validation rule. A high model score alone is
  not validation, and validation need not mean a human review for every deterministic relation.
- **Similarity-only:** embeddings can suggest candidate neighbors for a question or further
  checking. Similarity does not establish identity, dependency, causality or supersession.

Use the existing authorized writer and transaction boundary. Commit validated facts, relations and
provenance consistently; embedding/indexing can follow as an independent retryable step. An embedding
outage must not prevent an explicit supported relation from being recorded. Do not hold a database
write transaction open for remote extraction or embedding calls. Recheck source versions when applying
an asynchronously produced candidate, and make retries idempotent.

A source change, deletion, conflict or superseded supporting fact must exclude affected relations from
current answers until revalidated; preserve history when the repository needs it. Re-embedding alone
must not duplicate or invalidate verified relationships whose source is unchanged. Model/index changes
may invalidate similarity candidates, which remain distinct from source-backed facts.

Retain only relationships with a useful recurring question and maintainable evidence. Bound candidate
fan-out and query depth/output; avoid all-pairs chunk links and stored transitive shortcuts. Retrieve
only the needed path and source passages. Do not create a graph, migrate a database or populate edges
merely to make this retrieval skill available.
