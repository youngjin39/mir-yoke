# Project-owned semantic mapping

The project owns `.mir/ontology-map.json` and keeps its own model, IDs and procedures.
Use the distributed [contract](common-contract.json), whose provenance is in [SOURCE.md](SOURCE.md).
The mapping describes correspondence, not a replacement domain schema or permission to act.

## Required keys and shapes

All twelve top-level keys are required:

| Key | Shape and meaning |
| --- | --- |
| `schema` | `mir-semantic-mapping/v1`. |
| `contract` | `id` = `mir.common-semantics`; exact validated `version` as SemVer; accepted `version_range` as `>=A.B.C <X.Y.Z`. Optional `sha256` is the distributed file's digest. |
| `namespace` | Owning repository Profile's `slug`, from `.mir/repo-profile.toml`. Qualify shared entity IDs with it; do not reissue existing IDs. |
| `canonical_index` | List of repository-relative refs to the project's authoritative model sources. |
| `concepts` | Object keyed by every common concept ID: Project, Agent, Capability, Requirement, Concept, Artifact, Decision, Task, Run, Evidence, Assessment, Policy. |
| `vocabularies` | List of objects with `name`, `ref`, `values`; each local value maps to an object of common axis/value pairs or `{"local_only": "reason"}`. |
| `relations` | List with `local` relation name and exactly one of `common` (contract relation ID) or `local_only` (reason). Optional `ref` locates its definition. |
| `domain` | Object with lists `concepts`, `relations`, `invariants`; each item carries a `ref` to the project-owned definition. Extra domain fields may remain local. |
| `questions` | List with at least one item, preferably about three real domain questions. Each has `id`, `question`, `evidence` (list of refs). Below three produces a warning. |
| `error_cases` | List with contract case `id` and status `covered`, `planned` or `not_applicable`; `covered` requires a `check` ref. |
| `knowledge_supply` | `memory_keeper` = `connected`, `parent_supplied` or `not_connected`; `connected` requires a `binding` ref to the project-owned interface definition. |
| `entrypoints` | List of refs to existing model-reading, maintenance or verification entrypoints. |

A concept entry has `status: mapped` with a non-empty `local` list of `{name, ref}`, or
`status: absent|not_applicable` with a non-empty `reason`. `absent` records the inspected local
model's missing representation; it is not a global claim of non-existence. Explain the scope.
`not_applicable` records why the concept does not apply. Keep project-specific concepts in `domain`.

Map each local vocabulary value onto separate lifecycle, temporal, epistemic and verification axes.
For example, an approved note definition can map to `lifecycle: accepted` and `temporal: current`;
that mapping says nothing about a passed execution. Preserve local words and state machines.
Use `local_only` for local distinctions without a common counterpart; never combine it with axes.

Relation mappings preserve direction, endpoint concepts, scope and kind. Declarations, execution
relations, associations and identity are distinct. A `verified_by` mapping names a check; it does
not establish a passed result. Similarity and co-mention cannot justify `same_as`.
The checker validates relation IDs; reviewers must check the actual domain endpoints and meaning.

## Refs, domain questions and error coverage

Refs are strings: `path`, `path:line` or `path#symbol`, relative to the repository root.
The path must exist under that root, including after symlink resolution. Absolute paths, parent
traversal and backslash paths are rejected. List refs may also be wrapped as `{"ref": "path"}`.
The checker checks path existence, not whether a line or symbol resolves or proves the claim.

Questions should expose real decisions in the domain, with evidence that can answer them:
which note is current after a revision; which citations need review after a source changes;
and whether two similarly titled notes have distinct stable identities. Avoid a checklist of
abstract contract terms. Use the project's existing workflows as entrypoints, not a new workflow.

Review all E01–E10: cross-namespace merging, invalid relation scope/direction/endpoints, obsolete
facts, declaration treated as test success, similarity treated as identity, stale revision evidence,
capability treated as permission, personal-plane leakage, outage treated as absence, and version
mismatch. Record executable coverage where available. `planned` is not a pass; give a scoped reason
for `not_applicable`. The checker validates listed cases and their refs; it does not execute checks
or require a false claim that every case is already covered.

`parent_supplied` means context arrives from a parent rather than a direct service connection;
`not_connected` means no configured supply. Neither requires a fabricated binding. See
[knowledge-supply.md](knowledge-supply.md) for pack provenance and outage handling.

## Small fictional example

An `example-notes` app already has a Profile with `slug = "example-notes"` and `docs/model.md`
that defines notes, their states, identity rules, citations and maintenance. This initial mapping
leaves work-management records unrepresented; those reasons must be reviewed against the real model.

```json
{
  "schema": "mir-semantic-mapping/v1",
  "contract": {"id": "mir.common-semantics", "version": "1.0.0", "version_range": ">=1.0.0 <2.0.0"},
  "namespace": "example-notes",
  "canonical_index": ["docs/model.md"],
  "concepts": {
    "Project": {"status": "mapped", "local": [{"name": "Repository", "ref": ".mir/repo-profile.toml"}]},
    "Agent": {"status": "absent", "reason": "The initial local model has no actor records."},
    "Capability": {"status": "absent", "reason": "The initial model has no capability records."},
    "Requirement": {"status": "absent", "reason": "The initial model has no requirement records."},
    "Concept": {"status": "mapped", "local": [{"name": "Note definition", "ref": "docs/model.md"}]},
    "Artifact": {"status": "mapped", "local": [{"name": "Note", "ref": "docs/model.md"}]},
    "Decision": {"status": "absent", "reason": "The initial model has no decision records."},
    "Task": {"status": "absent", "reason": "The initial model has no work-management tasks."},
    "Run": {"status": "absent", "reason": "The initial model has no execution records."},
    "Evidence": {"status": "absent", "reason": "The initial model has no observation records."},
    "Assessment": {"status": "absent", "reason": "The initial model has no review records."},
    "Policy": {"status": "mapped", "local": [{"name": "Identity rule", "ref": "docs/model.md"}]}
  },
  "vocabularies": [{"name": "note definition state", "ref": "docs/model.md", "values": {
    "approved": {"lifecycle": "accepted", "temporal": "current"},
    "pinned": {"local_only": "A presentation preference, not a fact status."}
  }}],
  "relations": [{"local": "cites", "common": "mentions", "ref": "docs/model.md"}],
  "domain": {
    "concepts": [{"name": "Note", "ref": "docs/model.md"}],
    "relations": [{"name": "cites", "ref": "docs/model.md"}],
    "invariants": [{"rule": "Note IDs remain stable across revisions.", "ref": "docs/model.md"}]
  },
  "questions": [
    {"id": "Q1", "question": "Which note revision is current?", "evidence": ["docs/model.md"]},
    {"id": "Q2", "question": "Which citations need review after a source edit?", "evidence": ["docs/model.md"]},
    {"id": "Q3", "question": "Are similarly titled notes distinct?", "evidence": ["docs/model.md"]}
  ],
  "error_cases": [
    {"id": "E01", "status": "planned"}, {"id": "E02", "status": "planned"},
    {"id": "E03", "status": "planned"}, {"id": "E04", "status": "planned"},
    {"id": "E05", "status": "planned"}, {"id": "E06", "status": "planned"},
    {"id": "E07", "status": "planned"}, {"id": "E08", "status": "planned"},
    {"id": "E09", "status": "planned"}, {"id": "E10", "status": "planned"}
  ],
  "knowledge_supply": {"memory_keeper": "not_connected"},
  "entrypoints": ["docs/model.md"]
}
```

Run the checker after mapping, Profile, reference or contract changes. Revalidate compatibility
before changing the validated version. Update or invalidate only records dependent on changed
sources. A warning about the optional hash says the distribution differs; a matching hash says
only that source bytes are unchanged. Neither outcome establishes truth or authority.
