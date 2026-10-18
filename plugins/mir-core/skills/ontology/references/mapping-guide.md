# Project-owned semantic mapping

The project owns `.mir/ontology-map.json` and keeps its own model, IDs and procedures.
Use the distributed [contract](common-contract.json), whose provenance is in [SOURCE.md](SOURCE.md).
The mapping describes correspondence, not a replacement domain schema or permission to act.

## Required keys and shapes

All twelve top-level keys are required:

| Key | Shape and meaning |
| --- | --- |
| `schema` | `mir-semantic-mapping/v1`. |
| `contract` | `id` = `mir.common-semantics`; exact validated `version` as SemVer (inside its own range, never newer than the loaded contract; older warns to re-validate); accepted `version_range` as `>=A.B.C <X.Y.Z`. Optional `sha256` is the distributed file's digest. |
| `namespace` | Owning repository Profile's `slug`, from `.mir/repo-profile.toml`. Qualify shared entity IDs with it; do not reissue existing IDs. |
| `canonical_index` | List of repository-relative refs to the project's authoritative model sources. |
| `concepts` | Object keyed by every common concept ID: Project, Agent, Capability, Requirement, Concept, Artifact, Decision, Task, Run, Evidence, Assessment, Policy. |
| `vocabularies` | List of objects with `name`, `ref`, `values`; each local value maps to an object of common axis/value pairs or `{"local_only": "reason"}`. |
| `relations` | List with `local` relation name and exactly one of `common` (contract relation ID) or `local_only` (reason). Optional `ref` locates its definition. Validated version >=1.1.0 requires `from` and `to` on common entries: nonempty arrays of common concept IDs, or `"*"`, allowed by the contract endpoints. `local_only` needs none. |
| `domain` | Object with lists `concepts`, `relations`, `invariants`; each item carries a `ref` to the project-owned definition. Invariants may declare an optional executable `check` ref. Extra domain fields may remain local. |
| `questions` | List with at least one item, preferably about three real domain questions. Each has `id`, `question`, `evidence` (list of refs). Below three produces a warning. |
| `error_cases` | List with contract case `id` and status `covered`, `planned` or `not_applicable`; `covered` requires a `check` ref. |
| `knowledge_supply` | `memory_keeper` = `connected`, `parent_supplied` or `not_connected`; Optional `binding` names `on_demand_stdio` or `resident_stdio` in 1.1.0. Legacy 1.0.0 connected mappings retain existing binding refs. |
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
For validated version >=1.1.0, the checker validates declared endpoint types against the loaded
relation's `from`/`to`: a contract `"*"` allows any common concept or wildcard, while specific
endpoints cannot be widened. Arrays containing unknown IDs or empty arrays are invalid.
For example, `realized_by` allows `"from": ["Requirement", "Capability"], "to": ["Artifact"]`.
Legacy 1.0.0 endpoint declarations remain optional. Reviewers still check actual domain meaning.
`domain.relations` entries declaring `common` follow these same rules; entries without it retain ref-only validation.

## Size and selection

Keep the map an index, at most 32,768 bytes (the checker warns above this). Keep the canonical index,
the twelve concept refs, questions with evidence paths, domain identities and invariants, error
cases and knowledge supply. Map vocabulary values only where a reader could misread them (for
example `ready`, `done`, `completed`, `passed`, `active`, `verified`, `accepted`); leave obvious
values and restated definitions in the canonical sources. Fleet evaluation (2026-10) found answer
changes from evidence paths and identity or dependency entries, not from exhaustive vocabularies.

## Refs, domain questions and error coverage

Refs are strings: `path`, `path:line` or `path#symbol`, relative to the repository root.
The path must exist under that root, including after symlink resolution. Absolute paths, parent
traversal and backslash paths are rejected. List refs may also be wrapped as `{"ref": "path"}`.
Prefer `#symbol` for every ref field. The shared resolver requires a definition, assignment,
test name, Markdown heading text, JSON key, or TOML key/table with that name; an arbitrary prose
mention is insufficient. Dotted check names retain last-segment compatibility. An unresolved or
empty anchor is an error. Examples: `src/model.py#Artifact`, `tests/test_model.py#test_identity`,
`docs/model.md#Identity rules`, `config/model.toml#repo`.
Use line refs only for content without a symbol. Mapping retains 1.x line compatibility and
reports an informational count (`line_ref_count` in JSON), with no warning. Git impact reports
`re-anchor to a symbol: <entry>` for a line ref into any changed file; `--strict` fails even if
that line still exists. A symbol ref into a changed file remains valid while its declaration resolves.
For `covered` checks the checker also requires a file and validates one-based line bounds;
`.md`, `.txt` and `.rst` checks warn that covered needs a repeatable check. Resolving a check
does not execute it or prove its claim.
Optional `domain.invariants[].check` refs use the same file/anchor validation as covered checks.
Impact selects that check when any ref in its invariant is affected and deduplicates exact refs.
Unaffected invariants remain unselected. Affected invariants without `check` are reported in
`undeclared_check_links`; the checker never searches for or invents missing test links.


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


## Existing verification and retrieval paths

Consumers copy `scripts/mir_ontology_runner.py` from this skill directory to their own
`scripts/mir_ontology.py` **byte-identically**. To update, replace the whole consumer file from
the approved plugin distribution and verify byte equality; keep local behavior outside the copy.
The supply repository may keep its own checkout runner, explicitly selecting its checkout checker.
It does not use consumer runtime selection.

The consumer runner honors `MIR_ONTOLOGY_CHECKER` first (the file must exist). Otherwise it reads
active Claude `installed_plugins.json` records and the enabled Codex plugin table in `config.toml`,
checking the process home and account home. Claude supplies `version` and `installPath`; Codex's
current record has `enabled = true` without a version, so exactly one cached version must exist.
An explicit Codex `version` selects that cache directory. Multiple unpinned Codex versions are
ambiguous and fail closed. Active version disagreement exits 2 with `runtime distributions disagree`;
an active missing path also exits 2. Only when no active record exists does newest-cache fallback
apply, with a stderr warning naming the version. `python3 scripts/mir_ontology.py --which` prints
the version, checker path and selection reason without running the checker or MK.

From the installed skill directory, add selection to the repository's existing verify path:

```sh
python3 scripts/ontology_check.py impact --repo "$PROJECT_ROOT" --git-diff HEAD --strict
python3 scripts/ontology_check.py mapping --repo "$PROJECT_ROOT"
python3 scripts/ontology_check.py lookup --repo "$PROJECT_ROOT" "artifact identity" --limit 3
python3 scripts/mk_query.py --repo "$PROJECT_ROOT" --soft query "bounded external question"
```

Run selected checks with the repository's runner and record their actual results. `impact`
selects map entries and covered checks by changed/shared referenced paths, reports missing refs
(including deleted/renamed paths and broken covered-check lines/names), and requests `re-validate`
when the map changes. It does not execute checks. `--paths P ...` replaces Git selection;
`--git-diff [BASE]` includes index/worktree changes and defaults to `HEAD`. Selection exits 0;
`--strict` exits 1 for stale refs or invalid maps. Usage/IO errors exit 2.

`lookup` returns only term-matching questions, common concepts and domain identities with their
evidence and declared contract id/version; default limit is three. Both commands accept `--json`.
Local lookup and verification need no MK availability. Configure external retrieval only through
host-local configuration described in [knowledge-supply.md](knowledge-supply.md). The supported
client prints ContextPack JSON, bounds the wait and reaps its on-demand server. Do not store
host configuration or credentials in the map. Mark missing external evidence without failing
unrelated local work; neither retrieval nor a declared check proves a passed result.
