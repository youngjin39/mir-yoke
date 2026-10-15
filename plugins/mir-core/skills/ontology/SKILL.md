---
name: ontology
description: "Apply a project-owned ontology mapping to the common semantic contract. Use for ontology, semantic contract, identity, same entity, relation meaning, status meaning, provenance, impact analysis, or a mapping file."
---

# Ontology and Shared Meaning

Use this skill when a task depends on what an entity, relation, status or claim means.
The project owns its domain model and workflow. The distributed
[common contract](references/common-contract.json) supplies shared meanings; its
[owner and digest](references/SOURCE.md) identify the immutable distribution.
Do not invent a competing contract, install a service or restructure the project to use it.

## Workflow

1. Find the project model. Read `.mir/ontology-map.json` and only the relevant sources named by
   its `canonical_index`. If the mapping is absent, report that explicitly and work from the
   project's own documents. Do not claim contract compatibility or invent a mapping silently.
2. Identify the entities and relations the task touches. Qualify identifiers as
   `<profile-slug>:<local-id>` (or a project-owned sub-namespace). Equal names across namespaces,
   aliases, similar concepts and retrieval neighbours do not establish identity. A `same_as`
   relation requires reviewed evidence; preserve existing IDs and record replacements.
3. Retrieve only evidence needed to answer the task. Start with local authoritative sources.
   Use a knowledge service only through the project's configured interface; consult the
   [knowledge supply guidance](references/knowledge-supply.md) for context packs and outages.
   Record source, revision or hash, observation time, method, basis and conclusion scope when
   available. Distinguish direct retrieval from a parent-supplied pack.
4. Check identity, separate status axes, relation direction/endpoints/scope and authority.
   Distinguish declared, evidenced, association and identity relations. `verified_by` names a
   check; a recorded execution establishes its result. Historical, proposed, superseded and
   retracted material cannot establish a current confirmed fact. Record conflicting sources and
   uncertainty; do not resolve owner decisions by confidence, similarity or tool availability.
   Missing evidence proves absence only within a demonstrably complete scope.
5. Apply the finding through the project's existing design, implementation, knowledge or review
   workflow. Preserve local vocabulary and domain invariants. Capability, access, confidence,
   semantic compatibility and passing checks grant no authority; follow current owner policy.
6. Maintain dependencies after a source change: update or invalidate only dependent relations,
   mappings, derived knowledge and evidence. Preserve unaffected records. Recheck declared
   version compatibility when the contract changes; do not claim a newer validated version
   until its mapping has actually been reviewed and checked.

## Deterministic checker

Read the [mapping guide](references/mapping-guide.md) when authoring or changing a mapping.
Run the [checker](scripts/ontology_check.py) after mapping, Profile, referenced source or
contract-distribution changes, and before claiming mapping compatibility. Invoke it explicitly
with Python 3.9 or newer from the installed skill directory:

```sh
python3 scripts/ontology_check.py contract
python3 scripts/ontology_check.py mapping --repo "$PROJECT_ROOT"
python3 scripts/ontology_check.py mapping --repo "$PROJECT_ROOT" --json
python3 scripts/ontology_check.py impact --repo "$PROJECT_ROOT" --git-diff HEAD --strict
python3 scripts/ontology_check.py lookup --repo "$PROJECT_ROOT" "current artifact identity" --limit 3
```

The default contract is the sibling `references/common-contract.json`; `--contract PATH`
selects another owner-provided distribution explicitly. The checker reads files and writes nothing.
Prefer `path#symbol` refs: every anchor must resolve to a declaration, test name, heading or key.
Use line refs only for content without a symbol. Mapping preserves 1.x line compatibility with an
informational count; strict Git impact rejects line refs into changed files and requires re-anchoring.
Consumers copy the [canonical runner](scripts/mir_ontology_runner.py) byte-identically to
`scripts/mir_ontology.py`; the [mapping guide](references/mapping-guide.md) defines updates,
active runtime selection, disagreement failures and read-only `--which` inspection.
Each text finding is `ERROR|WARN <json-pointer>: message`, followed by counts and versions.
JSON reports `ok`, `errors`, `warnings`, `contract_version` and `mapping_version`; findings carry
`pointer` and `message`. Exit 0 means no errors (warnings may remain), 1 means invalid records,
and 2 means a usage or IO problem. An E10 version mismatch is an error; a differing optional
contract hash is a warning. Report warnings and scope rather than presenting them as resolved.

For mappings validated against 1.1.0 or newer, common relation entries require `from`/`to`
common concept IDs (arrays or `"*"`) permitted by the contract's endpoints. Legacy 1.0.0 mappings
retain their endpoint behavior. This is structural validation; review actual domain meaning too.

Wire `impact` into the repository's existing verify path after edits: review affected entries,
run the selected **checks to run** using the repository's own runner, repair **stale refs**, then
run `mapping` when prompted to **re-validate**. `--paths path ...` selects explicit changes;
`--git-diff [BASE]` defaults to `HEAD` and includes staged and unstaged changes. It never executes
checks or scans the repository tree. Normal selection exits 0; `--strict` exits 1 for stale refs
or invalid mappings; usage/IO failures exit 2. `--json` provides bounded machine-readable reports.
Checks are selected when their file changes or their ref shares a source path with an affected
entry. This navigation does not infer undeclared dependencies or prove executed verification (E04).

`lookup` supplies up to three term-matching questions, concepts and domain entries with evidence
refs and the declared contract id/version. Use `--limit N` to change the bound or `--json` for
scripts. It reads the map without dumping it and requires no Harness CLI.

For external context, the supported consumer path is the stdlib [MK client](scripts/mk_query.py):

```sh
python3 scripts/mk_query.py --repo "$PROJECT_ROOT" --soft query "bounded question" --k 3
```

It reads host-local configuration, initializes an on-demand MCP stdio child, calls
`federation_serve`, prints the ContextPack JSON, then terminates and reaps the child. No resident
server or database access is needed in the consumer. `--soft` makes unavailable or empty supply
exit 0 so local work remains independent (E09); otherwise those outcomes exit 2. Use the
[knowledge supply guide](references/knowledge-supply.md) for configuration, refusal handling,
provenance and explicit feedback. Never add host paths, credentials or config to a repository.

## Four verification layers

- **Format:** the checker validates declared structure, values, versions and local reference paths.
- **Semantic:** review actual identities, relation endpoints, scopes, local meanings and conflicts.
- **Execution:** exercise relevant behaviour and retain results for the checked revision and scope.
- **Authority:** confirm that current project policy and owner instructions permit the action.

Reading this skill does not itself guarantee consistency. A format pass does not establish truth,
execute project checks, inspect every domain relation or approve an action. Use the project's
specialist reviewers for their own boundaries; this workflow does not replace them.
