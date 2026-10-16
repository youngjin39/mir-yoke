# Migration Guide

## Unreleased capability-source schema 4

The tracked `config/capability-sources.json` now uses `schema_version: 4`, retaining the explicit
`package_kind: skills` for the three role plugins and admitting the exact `skills-hooks` shape for
`mir-lifecycle-hooks`. The canonical `plugin_component_policy` and exact active-package digest
acknowledgement prevent other executable shapes from entering through the new kind.
It adds a command allowlist that maps each Claude command source to the existing Codex plugin skill
that absorbs the same workflow, plus explicit target-local hook and MCP integration records.
Schema-1 and schema-2 capability sources remain readable and select no managed commands or active
hook package. Copy the schema-4 fields from the current template before expecting command or hook
delivery from a newer capability manager.
The existing plugin and skill inventories do not change.
Schema-1 locks remain readable, but their active provider is revalidated under the current
skills-only manifest and marketplace rules. After adopting the schema-4 source, explicit
`update --apply` adds package kinds and
marketplace digests to a schema-2 lock and receipt. Schema-2 records require those bindings and the
receipt's complete materialized-plugin inventory. Schema-2 provider registry state separately binds
the selected installed set used for rollback.

Do not translate a local enforcement hook or MCP configuration into a plugin entry.
`mir-lifecycle-hooks` contains only the admitted target-independent `SessionStart` reminder. Keep
repository-coupled registrations local unless a later decision introduces and verifies an adapter.
No MCP server is registered or implemented, so do not publish an empty MCP plugin from the inert
`.mcp.json.example`.

The first explicit schema-4 `update --apply` copies and digest-locks selected
`.claude/commands/*.md` alongside
selected agent sources. A project-owned command that differs from its prior lock or the exact
incoming source is not overwritten. Codex receives no generated command file; it uses the mapped
namespaced plugin skill.

Agents and Claude commands can alternatively be installed outside every repository:

```bash
python3 scripts/install_user_runtime_agents.py \
  --claude-home /absolute/claude-config-root \
  --codex-home /absolute/codex-home
```

The first run is a dry run. Add `--apply` only after reviewing the planned paths. The installer
refuses symlinked homes and unmanaged divergence and writes a SHA-256 receipt. Project-local agent
and command files continue to take precedence.

Schema-4 readiness requires current schema-2 state evidence. `sync` remains pinned to the existing
lock and reports that an update is required when that old commit lacks a newly selected package.
If multiple repositories register the
same provider commit, the host-active plugin set is their union; each project lock remains its own
subset. A failed apply restores that prior union and removes candidate-only plugins.

## 0.9.0 from 0.8.x

### Product boundary

- `starter/` remains the only fixed consumer payload and the four-file compatibility layer.
- New empty repositories use the standard `recipes/project-agent-kit/` guidance flow, which now
  requires a bounded project-owned common harness and SQLite+FTS5 memory baseline.
- Common plugins remain optional host capabilities and are portable outside the Mir Yoke checkout.
- The 0.9 package restores the public v0.8 `mir` command surface as an optional installed operator
  tool. It is not copied into Project Agent Kit targets and grants no authority until explicitly
  invoked for the user's named scope.
- ADR-82 product-plane and `yoke` composition sources remain superseded. Preserved files live only
  under `reference-templates/advanced-composition/`; no `yoke` console entrypoint is active.

### Existing 0.8 adopters

Existing users may install v0.9 to retain the public v0.8 `mir` command contract. Mir Yoke performs
no automatic migration, state deletion, repository rewrite, target update, or implicit command.
Adopt the Project Agent Kit or a changed local contract only through an owner-reviewed repository
change.

### New projects

Open one empty target and use the short prompt from `README.md`. The agent creates and verifies a
project-owned common harness and memory foundation, one initial commit, and then stops before
development planning. Do not vendor the Mir CLI source into the target.

### Rollback

Discard an uncommitted Project Agent Kit adaptation in the target or restore the target's own prior
commit. For an explicitly invoked CLI transaction, use that command's recorded rollback/recovery
contract. Installing the CLI does not itself mutate a target.

Current version: `0.13.2`. See `CHANGELOG.md` for release details.

Version 0.10.0 adds opt-in `memory_relations` ingestion and read-only `mir relations query|bundle --memory`
query/bundle selection using the existing memory schema. No automatic corpus backfill, database
migration or vector re-embedding is performed. Re-ingest an authorized declaring source to update
its relations; keep existing memory and source ownership.

Version 0.10.1 repairs relation validation budgets, snapshot change detection and memory fallback
diagnostics. Optional short authored summary/reason fields enrich the same relation facts; existing
triples and schema remain compatible. Use the supported provider executable for both relation
ingestion and retrieval: a plugin install alone does not upgrade a repository-local `uv run mir`.
Ingestion into an existing compatible schema does not apply migrations. No corpus backfill or
re-embedding is required. A concurrent database change now discards the read and requires a stable
retry or existing owner-controlled snapshot operation.

Version 0.10.2 narrows memory SRR at the SQL boundary. Existing schema, ingestion, embeddings, source
validation and compact evidence format remain unchanged. Candidate/source limits now apply to the
selected neighborhood; depth boundaries may report unvalidated continuation candidates without
opening their source bodies. No migration, re-ingestion or permanent cache is required solely for
this reader update. Use the same existing memory command when an agent elects to read a body.


Version 0.10.3 changes omitted dependency depth from three hops to one for the CLI and both public
relation adapters, including each dependency facet of a bundle. Implementation, verification and
explicitly requested impact retain the three-hop default. Pass `--depth 3` (or `depth=3` in Python)
to retain prior transitive dependency behavior. Existing explicit depths, result shapes, source
validation and ordinary memory operations are unchanged. No schema migration or re-ingestion is needed.

Version 0.10.4 makes shared SRR guidance select a supported provider and explicit target root.
Existing local consoles are not upgraded, and unsupported providers continue with ordinary search.

Version 0.10.5 changes guidance and records only: Claude reaches Codex through the official Codex
plugin and `mir_executor` uses `codex app-server`. Plugin skill content, schemas and memory are unchanged;
no migration or re-ingestion is needed.

Version 0.10.6 adds the optional `mir-core:repo-maintenance` skill, a twenty-item periodic maintenance
checklist for agent-operated repositories. It is read-only unless a fix is requested; nothing else changes.

Version 0.10.7 strengthens that checklist to twenty-one items: documented database/memory/graph
inspection and repair, explicit Claude/Codex harness consistency, and observable parity when either
CLI is Main. Parity repairs cannot introduce restrictions or recreate owner-removed hooks. Nothing else
changes for adopters.

Version 0.10.8 adds the optional `mir-core:reference-app-profile` skill for evidence-labeled
reference application metadata profiles. Nothing else changes.

Version 0.11.0 adds the optional `mir-core:ontology` skill and its self-contained, read-only
semantic contract checker. Projects explicitly map their own identity, relations, status meaning,
and provenance through `.mir/ontology-map.json` to the distributed common contract. The contract
owner remains authoritative; each project owns its mapping and domain model. The package does not discover or modify consumers,
install a runtime, or migrate existing memory or knowledge data. Existing package admission rules
and target-local integration ownership remain unchanged.

Version 0.12.0 distributes contract 1.1.0. Mappings validated against 1.0.0 stay valid and warn to
re-validate; to adopt 1.1.0, declare `from`/`to` on each relation that names a common relation.
Covered error cases must name a resolvable repeatable check. New optional `impact` and `lookup`
subcommands and the `mk_query.py` client change nothing until a project wires them in.

Version 0.13.0 keeps contract 1.1.0. Consumers that adopt the ontology runner must copy
`plugins/mir-core/skills/ontology/scripts/mir_ontology_runner.py` from the approved distribution
to their own `scripts/mir_ontology.py` byte-identically. Replace the whole file on update,
verify byte equality and keep project-specific behavior outside the copy. The runner rejects
active Claude/Codex version disagreement, ambiguous unpinned Codex caches and missing active
paths; `--which` explains the selected distribution. Yoke retains its separate checkout runner.

Replace mapping line refs with resolvable `#symbol` anchors wherever a definition exists,
including covered error-case checks. Mapping still accepts legacy line refs and reports their
count, but strict Git impact rejects line refs into changed files, stale refs and invalid maps.
Run mapping and `impact --git-diff --strict`, then execute the selected checks separately;
impact selection does not execute them or establish a passing result.

Review `domain.relations` entries that declare `common`: common IDs and version-gated endpoint
rules now match top-level relations. Under validated contract 1.1.0, declare compatible `from`
and `to` endpoint types. Entries without `common` retain ref-only validation. No database
migration, memory re-ingestion or automatic consumer update is required.

Version 0.13.1 is a patch release and keeps `mir.common-semantics` contract 1.1.0.
After updating the approved ontology distribution, strict impact may list additional
`checks_to_run` from affected `domain.invariants` entries with a declared `check`.
Run those checks separately; selection does not execute them or establish a passing result.
Invariants without a check are reported as undeclared check links; no test link is inferred.

Mapping validation now reports an error when a declared invariant `check` ref does not
resolve. Correct its repository-relative path and `#symbol` anchor to an existing check,
or remove the optional `check` field if the invariant has no declared executable check.
Run `python3 scripts/mir_ontology.py mapping` and
`python3 scripts/mir_ontology.py impact --git-diff --strict`, then execute the selected checks.
No database migration, memory re-ingestion or automatic consumer update is required.

Version 0.13.2 is a patch release and keeps `mir.common-semantics` contract 1.1.0. The
`mir-lifecycle-hooks` SessionStart line now also states the seven-step default work method and
the completion rule, and its `runtime-continuity` skill packages the full method as
`references/default-work-method.md`. A user-level instruction file that already carries the same
method text should drop it so the method is injected once. No database migration, memory
re-ingestion or automatic consumer update is required.
