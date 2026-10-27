# Migration Guide

## 0.13.13 handoff authority and final inventory

Handoff authors must copy the current request's owner-granted actions by verb.
Review/brief-only requests permit only allowed reading and reporting; ungranted
commands, tests, edits, writes, deployment or delegation need a separate owner grant.
Author restrictions apply during brief composition, including scratch files.
Carry full HEADs and digests and end with individual field/pin inventory states.
No schema/database migration, automatic execution or consumer update is required.

## 0.13.12 handoff pin inventory

The optional `mapping --handoff` block adds `pin_inventory` and types Git-derived
source revisions as `last_change_commit`. Existing pin values, validation, exit
codes and mapping-only output remain unchanged. Inventories describe availability,
not verification or permission; unavailable required pins stay individually unknown.
No schema/database migration, automatic command execution or consumer update is required.


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

Current version: `0.13.37`. See `CHANGELOG.md` for release details.

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

Version 0.13.3 is a patch release and keeps `mir.common-semantics` contract 1.1.0. The
`mir-core:repo-maintenance` checklist adds item 22 (proportionate Agent, Loop, Graph and Ontology
engineering), `mir-core:verify` requires a request matrix before a completion claim, and the
ontology runner moves its active-distribution checks into `select_active_distribution` with no
behavior change. Consumers that keep a byte copy of the ontology runner refresh that copy from the
active distribution after updating. No database migration or memory re-ingestion is required.

Version 0.13.4 is a patch release and keeps `mir.common-semantics` contract 1.1.0.
The `mir-core:ontology` guidance names ordinary meaning-sensitive requests and the minimum
parent/child handoff packet; the existing bluebricks route points to that packet.
No database migration, memory re-ingestion or automatic consumer update is required.

Version 0.13.5 is a patch release and keeps `mir.common-semantics` contract 1.1.0.
The `mir-core:ontology` skill body now carries the six-field handoff packet, missing-pin
self-check and owner authority limits; knowledge-supply guidance requires actual client results,
reasons and applied configuration sources. No database migration, memory re-ingestion or
automatic consumer update is required.

Version 0.13.6 is a patch release and keeps `mir.common-semantics` contract 1.1.0.
The MK client filters response nodes and citations by requested namespaces, using the
federation set by default, and appends a content-free namespace-filtering degradation entry.
Claude activation verification requires an explicit installed-package `user` scope.
No database migration, memory re-ingestion or automatic consumer update is required.

Version 0.13.7 is a patch release and keeps `mir.common-semantics` contract 1.1.0. The always-delivered SessionStart reminder preserves owner-granted handoff authority and requires the ontology handoff fields, naming missing fields as unknowns. No database migration, memory re-ingestion or automatic consumer update is required.

Version 0.13.8 is a patch release and keeps `mir.common-semantics@1.1.0` unchanged. The SessionStart reminder names all six ontology handoff fields inline, including status axes, current pins and a final self-check naming missing fields or pins as unknowns. No database migration, memory re-ingestion or automatic consumer update is required.

Version 0.13.9 is a patch release and keeps `mir.common-semantics@1.1.0` unchanged.
The ontology mapping size warning budget increases from 12,288 to 32,768 bytes;
warning-only behavior and mapping preservation guidance remain unchanged.
No database migration, memory re-ingestion or automatic consumer update is required.

Version 0.13.10 is a patch release and keeps `mir.common-semantics@1.1.0` unchanged.
Ontology mapping reports include the map path, loaded contract ID and full file
SHA-256 digests alongside existing versions, with a Handoff hint for obtaining pins.
No database migration, memory re-ingestion or automatic consumer update is required.

Version 0.13.11 is a patch release and keeps `mir.common-semantics@1.1.0` unchanged.
The ontology mapping command can emit one-command handoff pins in text or JSON, and
the SessionStart reminder names that block. No database migration, memory re-ingestion
or automatic consumer update is required.

Version 0.13.27 adds the optional `mir-content:no-ai-slop` and
`mir-content:fluent-korean` skills for draft editing/detection and Korean output.
Both runtimes share the plugin skill tree. Existing profile packs are unchanged:
`hybrid_pipeline` and `content_workspace` include `mir-content`; `code_app` and
`infra_runtime` exclude it. Global policies and existing user-scope installations
are not automatically changed. No database migration is required.
The second 0.13.27 slice adds optional references for controlled experiments,
instruction-change evaluation and trace-derived skill patches, plus owner-requested
`mir-core:memory-evaluation`. These are guidance only; no store migration, runtime
installation, automatic memory write or consumer update follows from adoption.

## 0.13.28 optional capability gap fills

Existing design, bluebricks, code-review, automation and verify skills now point to
seven optional references. Frontier rounds extend the existing elicitation rules;
interview fallback preserves unanswered decisions. The audit/debt recipe is manual,
SPINNING only reports, and fidelity/panel judgments remain advisory. No new skills,
agents, commands, scripts, hooks, schema migration or automatic consumer update are
introduced. Existing deterministic checks and owner authority remain in force.

## 0.13.29 final guidance gap fills

Two optional skills join the shared provider catalog: `mir-content:korean-writing`
(Korean-language authoring and contextual revision) and `mir-core:app-investigation`
(explicitly requested, permitted-artifact investigation and reconstruction review).
Metadata-only reference-app-profile retains its original bounds. Existing profile
packs and fluent-korean source are unchanged. Refresh plugin versions explicitly
through the existing authorized workflow; no automatic consumer update follows.

Existing skills gain optional recovery, PRD, diff-review, selective learning-safe
proposal, cache-diagnosis, document-only review and visual memory-case guidance.
No tools are bundled, no memory migration is required, and all judgments remain
advisory under Main. The lifecycle package digest acknowledgement changes only
because release metadata changes; hook code and capability-lock binding stay intact.

## 0.13.30 guidance corrections and bounded gap recipes

Round-9 guidance exposes ordinary memory/notes lookup, confirms scope-bearing
free-text interview answers before decision/frontier updates, and requires whole-tree
proof before unused-code deletion advice with merge/split alternatives. Automation
and ontology share handoff/resume/run-state precedence. No runtime migration or lock binding.

Round-8 guidance adds proportional, write-authorized intent write-back to existing
repository docs, Korean technical-form and notice checks, and trace-based proposals
for canonical instruction sources with regenerated derivatives. Descriptions route
Korean diagnosis and expose experiments; explicit grills cover all unresolved human
decisions while deriving facts. No new doc layout, runtime migration or lock binding.

Round-7 guidance closes assumed load-bearing decisions before freeze, adds
contextual Korean cues and applies only general no-ai-slop principles to Korean.
Memory answers cite exact records and retain premise contradictions and unknowns.
Efficiency exposes per-turn inventory/placement; audit routes have explicit
precedence. The lifecycle entrypoint documents the existing PreToolUse command
and file-write guard; only its package acknowledgement changes. No runtime
migration, lock binding or hook behavior change is required.

Round-6 guidance keeps Korean detection in diagnosis-only mode; no-ai-slop Detect
applies only to English. Genre register and preserved author voice take precedence
where required, while agent messages and default prose follow fluent-korean.
Spec questions batch by prerequisite frontier. Runnable service/CLI/UI claims need
a safe, permitted observed-behavior check beside unit tests or remain unevaluated.
Existing triggers now expose user-reported stalls, trace-based skill patches and
concise output. Recovery remains report-only; no hook or runtime migration.

Round-5 guidance adds proportional pre-edit reach checks, a self-contained terse
baseline and manual, write-authorized evidence rules for lesson/memory notes.
Existing test names take precedence; unmeasured coverage stays "not measured".
Legacy verification/design roles use host-provided agents. Korean drafts route to
korean-writing; grill and repository-audit triggers are explicit. Automation reuses
the existing cursor or ledger and creates one only when none exists and writes
are authorized. No runtime migration or new learning loop.

Round-4 guidance marks deliberate implementation limitations immediately with the
existing shortcut recipe and verifies changing Korean draft facts against current
sources, retaining source dates/versions and unconfirmed labels. Spec readiness is
advisory to Main and the owner; three failures end only the spec-repair loop, not
already authorized implementation. Automation ledgers require persistent/long-running
work and write authority; one-off read-only browser observations create no record.
The MODE-S pointer now names the existing comparison heading. No runtime migration.

Round-3 guidance selects Korean diagnosis without rewriting, routes generic pattern
checks to no-ai-slop Detect, and requires action owners, delivery dates and next actions
(or explicit undecided fields). Migration interviews separate code from owner intent,
confirm dangerous inferred policy and ask about important rules absent from code.
File impact traverses modules before requirements. Read-only requests record nothing;
when lifecycle-hooks is absent, design uses the repository method or its own order.

Round-2 corrections distinguish implementability readiness from executed verification,
unify Gateway/Timer actor boundaries, allow target-relative evidence and check commands,
and route as-built architecture analysis to bluebricks while design owns open choices.
Coding identifiers require grounding before use; no-ai-slop eval retains contextual
exceptions, and the long-form finish reference now uses Korean. No runtime migration.

No migration or new runtime is required. Existing skills now distinguish declared
verification links from executed revision-bound proof, define task edge endpoints
and a reproducible L1 denominator, preserve technical names in style editing,
route diff/PR review to code-review and completion/spec evidence to verify, and
limit GUI procedures to changed GUI behavior. AI-readiness is qualitative because
no weighted rubric was supplied; dashboard-ready refers only to report formatting.

Optional guidance adds pre-spec intent audit, bounded integration, interview
prototype escape and conversation-only applicability, long-form finishing and
owner-requested style profiles, choice memos, approved-spec issue drafting and
reconstruction proof applicability. External issue publication still requires
explicit authority. REA provenance is MIT at cd10ee1; the unlicensed 9e6c624 origin
remains recorded. Refresh versions only through the existing authorized workflow.
The lifecycle acknowledgement covers release manifests and the read-only method
exception; no hook code changes and no capability-lock binding or consumer update is performed here.

## 0.13.31 remaining guidance corrections

No runtime migration or new tools are required. Artifact comparisons use stable
identities and mark additions/removals Unknown unless both versions are covered.
Korean business and public forms gain short checks; fluent-korean restores the
settled-idiom exception under its existing MIT notice. Public guidance now uses
resolvable citations, generic terminology and project-owned handoff authority.
The experiment recipe stops over-budget or timed-out runs as unscored failures;
required claims without runnable verification commands become recommended decisions
for Main or the owner. Approved-spec issue drafting is an explicit routing exception.
Ouroboros adaptations retain 5520a3e and were re-checked at 7783d9f on 2026-10-24;
REA version-comparison ideas were checked at dd02d8f (MIT).
The lifecycle package acknowledgement covers guidance and version manifests only.
Hook behavior and the capability lock are unchanged; release binding remains Main's work.

## 0.13.32 read-only stdio MCP package

No migration is required for existing skill and hook selections; no default Profile
selects `mir-mcp`. Schemas 1-4 still validate. To register the package, a consumer adds
the exact `mir-mcp` tree digest to `active_package_digest_acknowledgements` in its own
`config/capability-sources.json` and runs an explicit `mir capability sync --mcp --apply`;
a provider config or provider update never supplies that acknowledgement. Finalization
needs fresh MCP evidence from both runtimes. See
[the plugin migration guide](docs/operations/global-plugin-migration.md) and
[ADR-91](docs/decisions/adr-91-stdio-mcp-package-admission.md).
The lifecycle package acknowledgement covers version manifests only; hook behavior is unchanged.
The capability-lock binding remains Main's release work.

## 0.13.33 `mir-mcp` test portability fix

No migration is required. Only tests and one guidance line changed, apart from version surfaces; the
`mir-mcp` package keeps its eight-file inventory and server behavior. A consumer that
registered `mir-mcp` renews its own tree-digest acknowledgement for the new version, as
for any package update. The lifecycle package acknowledgement covers version manifests
and one delegation line in the `runtime-continuity` work-method reference; hook behavior
is unchanged. The capability-lock binding remains Main's release work.

## 0.13.34 `mir-mcp` Codex launcher fix

The Codex `mir-mcp` declaration changed to `python3 -I -B -u ./mir_mcp.py` with `cwd: "."`,
so the package tree digest changed. A consumer that registered `mir-mcp` renews its own
tree-digest acknowledgement and runs `mir capability sync --mcp --apply`; the provider
config never supplies that acknowledgement. The locked Codex launcher now includes
`cwd: "."`, so a lock or receipt written by an earlier version does not match until that
sync. Record a fresh Codex MCP receipt whose `launcher` is
`{command:"python3",args:["-I","-B","-u","./mir_mcp.py"],cwd:"<installed-root>",env:{}}`;
Claude receipts keep the absolute script form. See
[the plugin migration guide](docs/operations/global-plugin-migration.md) and the
2026-10-27 amendment to [ADR-91](docs/decisions/adr-91-stdio-mcp-package-admission.md).
The lifecycle package acknowledgement covers version manifests only; hook behavior is
unchanged. The capability-lock binding remains Main's release work.

## 0.13.35 Consumer-local hook acknowledgement

Every consumer must now record its own `mir-lifecycle-hooks` acknowledgement. A provider-only
or bundled configuration no longer approves the hook package, so a consumer without its own
configuration cannot select it, and an update fails closed until the consumer acts. Review the
candidate checkout, then compute each selected package's tree digest:

```sh
uv run --no-sync python -c 'from pathlib import Path; from mir.core.capabilities.manager import _tree_digest; print(_tree_digest(Path("/absolute/reviewed-yoke/plugins/mir-lifecycle-hooks")))'
```

Set `active_package_digest_acknowledgements["mir-lifecycle-hooks"]` in
`<consumer-root>/config/capability-sources.json` (or the explicit `--config` file) to that full
digest. If the consumer selected `mir-mcp`, also set
`active_package_digest_acknowledgements["mir-mcp"]` to the digest printed for
`plugins/mir-mcp`. Then run `mir capability update --apply --project-root
/absolute/consumer-root`, adding `--mcp` when `mir-mcp` is selected and `--config` when
applicable. For 0.13.35 the digests are `mir-lifecycle-hooks`
`ce1f5078cf61ea8bd04897863d7f68cb6445e1444e3743434452a1d60c671ecc` and `mir-mcp`
`e6d8adc6268d65b4af0739d49522c7c3ef6715a96835670292f0ec569013763d`; record them only
after your own review.

The active receipt field `mcp_digest_acknowledgements` is replaced by
`consumer_digest_acknowledgements`; existing receipts remain readable for rollback. A consumer
enrolled with the 0.13.33 `mir-mcp` launcher can update again. See
[the plugin migration guide](docs/operations/global-plugin-migration.md) and the 2026-10-27
amendments to [ADR-91](docs/decisions/adr-91-stdio-mcp-package-admission.md) and
[ADR-88](docs/decisions/adr-88-active-plugin-component-admission.md). The capability-lock
binding remains Main's release work.

## 0.13.36 Codex 0.164 legacy MCP interoperability

The `mir-mcp` server bytes changed, and the version manifests changed in every package. Review
the candidate checkout, then compute each selected package's tree digest:

```sh
uv run --no-sync python -c 'from pathlib import Path; from mir.core.capabilities.manager import _tree_digest; print(_tree_digest(Path("/absolute/reviewed-yoke/plugins/mir-mcp")))'
```

A consumer that selected `mir-mcp` sets
`active_package_digest_acknowledgements["mir-mcp"]` in
`<consumer-root>/config/capability-sources.json` (or the explicit `--config` file) to that full
digest. Every consumer also renews `active_package_digest_acknowledgements["mir-lifecycle-hooks"]`
to the digest printed for `plugins/mir-lifecycle-hooks`. Then run `mir capability update --apply
--project-root /absolute/consumer-root`, adding `--mcp` when `mir-mcp` is selected and `--config`
when applicable. For 0.13.36 the digests are `mir-lifecycle-hooks`
`555ac29c1b3b81a55972b2fa3c87cd71ebda03f3460e2a4998dc94d3d7cc8cf2` and `mir-mcp`
`02fc33c01eca29d0c7a0803955da2378477c9eacb3efa96ddc14eda3d9a64390`; record them only
after your own review.

Codex CLI 0.164 can now complete the legacy handshake and call tools. Modern-era requests,
the tool inventory and results are unchanged. See the 2026-10-27 legacy-negotiation amendment
to [ADR-91](docs/decisions/adr-91-stdio-mcp-package-admission.md). The lifecycle package
acknowledgement covers version manifests only; hook behavior is unchanged. The capability-lock
binding remains Main's release work.

## 0.13.37 Host-local consumer approvals

Consumer approvals now live only in the git-ignored
`<consumer-root>/config/capability-acknowledgements.local.json`. An
`active_package_digest_acknowledgements` entry in any `capability-sources.json` (tracked,
provider, bundled or `--config`) still loads but never approves. A `mir` older than 0.13.37
cannot load this release's provider config, so the order matters:

1. Update the `mir` code first, for example with the `uv tool install` command in `README.md`
   pinned to `v0.13.38` (`v0.13.37` has no release). Do not update the provider with an older `mir`.
2. Review the candidate checkout. The `mir-mcp` server bytes and the version manifests of every
   package changed, so compute each selected package's tree digest:

   ```sh
   uv run --no-sync python -c 'from pathlib import Path; from mir.core.capabilities.manager import _tree_digest; print(_tree_digest(Path("/absolute/reviewed-yoke/plugins/mir-lifecycle-hooks")))'
   ```

   Repeat with `plugins/mir-mcp` when `mir-mcp` is selected.
3. Create `<consumer-root>/config/capability-acknowledgements.local.json` with those new full
   digests, also when using `--config`:

   ```json
   {"active_package_digest_acknowledgements": {"mir-lifecycle-hooks": "<64-hex digest>", "mir-mcp": "<64-hex digest>"}}
   ```

   Omit `mir-mcp` when it is not selected. The digests you approved for 0.13.36 do not match
   this release. Keep the file out of Git; it must not be a symlink, and a malformed file fails
   closed.
4. Remove the old `active_package_digest_acknowledgements` entries from
   `capability-sources.json`, or leave them; they are ignored either way.
5. Run `mir capability update --apply --project-root /absolute/consumer-root`, adding `--mcp`
   when `mir-mcp` is selected and `--config` when applicable.

No sync, update or rollback writes the local file; rollback restores the approvals recorded in
its receipt. Modern `mir-mcp` `tools/list` and `server/discover` results now carry caching
hints, `isError` results carry a short text reason, and a failed Git query in `handoff_pins`
marks only its own pin unknown. The lifecycle package acknowledgement covers version manifests
only; hook behavior is unchanged. See
[the plugin migration guide](docs/operations/global-plugin-migration.md) and the two newest
2026-10-27 amendments to [ADR-91](docs/decisions/adr-91-stdio-mcp-package-admission.md). The
capability-lock binding remains Main's release work.

## 0.13.38 Republish of 0.13.37

0.13.38 carries the 0.13.37 behavior; follow the 0.13.37 steps above. Only the version
manifests changed, so every package digest changes again: review and re-acknowledge the
selected packages' tree digests for this release in the host-local approval file.

## 0.13.39 Cloud-synced roots refused

- A repository inside OneDrive (or other Windows cloud files), macOS `~/Library/CloudStorage`
  or iCloud Drive is now refused by `mir-mcp` (`E_CLOUD_SYNC`) and by `mir capability`. Move
  such a repository to a local folder.
- Every package digest changes (version manifests; `mir-mcp` and `mir-core` code). Update the
  `mir` code first, then review and write the new `mir-lifecycle-hooks` and `mir-mcp` digests
  into `<project root>/config/capability-acknowledgements.local.json` before
  `mir capability update --apply`.
