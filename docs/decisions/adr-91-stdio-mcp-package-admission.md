---
adr: 91
title: "Admit the read-only stdio MCP package (`mir-mcp`)"
type: template-adr
created: 2026-10-26
status: accepted
amends: [adr-74, adr-88, adr-89, adr-90]
template_scope: mir-yoke
schema: docs/templates/_schema/adr.schema.json
---

# ADR-91 — Admit the Read-Only Stdio MCP Package (`mir-mcp`)

## 1. Context

Design authority is the owner's 2026-10-26 ADR-only request: public Yoke source, tools only,
exactly five read-only v1 tools, and native Windows after macOS/Linux. Relayed owner decisions
and the Harness inventory are parent-supplied evidence [E8]; repository citations relied upon
were rechecked below. The maintainer cursor is outside this request's two-file write scope.
This proposal performs no implementation, digest acknowledgement, delivery, or registration.

Yoke supplies shared capabilities under Harness ADR-86 management; consumers retain their own
policy, data, and execution authority. Agent Hub tools `hub_agents`, `hub_dispatch`, and
`hub_task` are excluded: they are owner-only, owned by Mir Agent Hub, and not package dependencies.
Current schema 4 admits only `skills` and exact `skills-hooks`, reserves `mcp`, and acknowledges
only active hook digests [E1]. Native MCP declarations are evidenced [E7]; that does not prove
Yoke admission or activation. ADR-88's implementation and runtime-evidence gates still apply.

## 2. Decision Drivers

- Supply bounded local tools to other users without private services or credentials.
- Preserve skills-only role packages and independent no-MCP workflows.
- Bound reads and token costs; expose no mutation or network path.
- Retain immutable provenance, explicit selection, and Claude/Codex semantic parity.

## 3. Considered Alternatives — HARD

| Alternative | Disposition |
|---|---|
| Public, separate `mir-mcp` with a closed validator | Chosen; concrete opt-in tools under active-package admission. |
| Private Harness source or tools in `mir-core` | Rejected; unavailable public source or a skills-only policy violation. |
| Hub tools, write tools, or DB relation adapters | Rejected for v1; different authority or storage contracts. |
| HTTP/SSE transport or generic MCP admission | Rejected; unnecessary listener or unreviewed package classes. |

## 4. Decision

### 4.1 One kind and one opt-in package

After acceptance and implementation verification, admit `package_kind: mcp-stdio` only for
`mir-mcp` at `plugins/mir-mcp` and its human-acknowledged, exact computed tree SHA256. Kind
equality admits no other package, shape, tool, or digest. Generic `mcp` stays reserved and
rejected. No default Profile selects `mir-mcp`; marketplace presence does not select it.

This fulfils ADR-90 §2.4's reserved `mir-mcp` use case and admission conditions. It narrowly
amends ADR-88 §2.1 lines 38–40 (admitted kinds) and 46–50 (sole active package/MCP reservation),
ADR-74's 2026-09-04 amendment lines 18–20 and §2 lines 77–79 (MCP rejection), and ADR-90 §2.3
line 92 and §2.4 lines 96–99. Their restrictions continue for every other shape; all three role
plugins remain skills-only. These line locations were checked on 2026-10-26.

The implementing change introduces capability-source schema 5 with a dedicated `mcp-stdio`
metadata branch, exact server/tool inventory, no fictitious skill, and acknowledgements for
both admitted active kinds. Preserve schema 1–4 validation; legacy locks cannot bypass current
tree validation [E1–E2]. ADR-88 §2.3 and ADR-89 still govern project-local integration. This
separate plugin supply path never writes or merges consumer runtime settings, `.mcp.json`, or policy.

### 4.2 Exact v1 tool contract

All inputs are closed JSON objects (`additionalProperties: false`) requiring
`target_root: absolute-directory-path[≤4096 bytes]`; no cwd, environment, or client-root inference.
Common optional fields are `cursor: string[≤1024 bytes]` and `page_size: integer[1,64]=16`.
Other paths are root-relative and ≤4096 bytes each. The map is fixed at `.mir/ontology-map.json`;
the contract is the bundled byte-pinned common contract. `?` marks optional fields;
`enum[...]` lists the only choices. All tools share §4.4's input/read/output caps.

| Tool and one-line description | Additional input schema | Compact `data` shape | Bounds |
|---|---|---|---|
| `ontology_validate`: Validate the common contract and target mapping. | `scope?: enum[contract,mapping,both]=both` | `{valid,contract_version,mapping_version,counts,findings:[{code,pointer}]}` | Fixed map/contract; guarded reference reads only. |
| `ontology_lookup`: Find term-matching map entries and declared evidence. | `query: string[1,256 bytes]`, `limit?: integer[1,16]=3` | `{contract,matches:[{pointer,score,label,refs}]}` | ≤16 matches; no source excerpts or semantic-identity inference. |
| `ontology_impact`: Select declared affected entries and checks for changed paths. | `paths: unique path-array[1,64]` | `{affected_entries,checks_to_run,stale_refs,undeclared_check_links,revalidate}` | Explicit paths only; no Git-diff mode, tree scan, or check execution. |
| `handoff_pins`: Collect repository, source, mapping, and contract pins with availability. | `paths: unique path-array[1,16]` | `{repository_root,head,dirty,sources,mapping_path,mapping_version,mapping_sha256,contract_id,contract_version,contract_sha256,observed_at,unknowns,pin_inventory}` | ≤16 source files; full hashes/commits or explicit unknowns; §4.5 Git only. |
| `relations_query`: Retrieve bounded declared YAML relations for one known anchor. | `adapter?: enum[yaml]=yaml`, `graph?: path=spec/graph.yaml`, `anchor: string[1,4096 bytes]`, `purpose: enum[implementation,verification,impact,dependencies]`, `depth?: integer[1,4]`, `max_edges?: integer[1,64]=16` | `{anchor,purpose,scope,source:{graph,sha256},edges,notices,truncated,resolved_anchors}` | Depth defaults: dependencies=1, others=3; graph ≤1 MiB/10,000 triples; no DB adapter. |

Results use `structuredContent: {ok,data,error,next_cursor}` with a declared `outputSchema`.
`error` is null or `{code}`; codes are `E_SCHEMA`, `E_PATH`, `E_PROTECTED`, `E_LIMIT`,
`E_FORMAT`, `E_VERSION`, `E_IO`, `E_GIT`, `E_TIMEOUT`, and `E_CURSOR`. Validation findings
use stable codes/pointers, never source values or raw exceptions. Missing pins stay explicitly
unavailable. Declared evidence, hashes, and selected checks prove neither truth, execution, nor permission.

The first four tools wrap `Checker.contract`/`Checker.mapping`, `lookup`, `impact`, and
`handoff_pins` in `ontology_check.py` [E3]. YAML traversal exists as
`src/mir/core/relations.py#query_relations` and its CLI route [E4]. There is no existing
`relations_query` MCP wrapper or standalone package backend; those are new implementation work.

### 4.3 One source of shared logic; independent skill use

Use **byte-identical build-time copies enforced by tests**, not imports from sibling plugin
caches. The canonical `plugins/mir-core/skills/ontology/scripts/ontology_check.py` and its
`references/common-contract.json` are copied into the package's matching `ontology/` layout.
Changes begin in those sources; drift tests compare every byte. First add guarded read/Git
interfaces to the canonical checker so the server can enforce §4.4–4.5 on every indirect
operation. Do not reimplement checker rules in the server or allow raw checker I/O to bypass guards.

Add a canonical standalone `plugins/mir-core/skills/selective-relations/scripts/relations_query.py`,
extracting existing purpose/direction/traversal rules [E4], and copy it identically into
`mir-mcp/shared/`. Keep it stdlib-only: v1 accepts the documented `edges:` mapping with
three-string flow-sequence rows; reject unsupported YAML forms, tags, anchors, aliases,
duplicate keys, and multiple documents with `E_FORMAT`. Differential fixtures against the
existing YAML CLI must prove equivalence on that admitted subset, not full PyYAML parity.
Canonical helper scripts remain passive skill assets; only `mir-mcp` declares the active server.

Isolation is evidenced by versioned `mir-core` cache resolution, per-plugin Claude `installPath`,
and tests copying each plugin alone [E5]. `mir-mcp` must work without `mir-core`, the Mir CLI,
or a source checkout. With `-I`, load only the two fixed in-package module paths; never search
sibling caches or import target code. Skills keep their direct scripts, CLI, files, and text
search paths. `spec-architect`'s no-CLI/IDE/MCP dependency contract and inventory constraint 12
remain intact [E6, E8]; tool introduction does not justify deleting templates or references.

### 4.4 Testable read-only security rules

- **Tools only, stdio only:** advertise no resources, prompts, apps, sampling, elicitation,
  tasks, subscriptions, or hidden action modes. No listener, HTTP/SSE, or background service.
- **No network:** static import/call-graph checks reject `socket`, `http`, `urllib`, other
  network libraries, and dynamic code loading except the two fixed package-module loads.
  Allow only reviewed stdlib and copied modules; runtime tests deny indirect network calls too.
- **No credentials or environment input:** the application allowlist is empty. No `getenv`,
  environment-derived roots/config, home discovery, credential files, or forwarded names.
  Host-expanded plugin-root argv is not server environment input. Git gets only §4.5's constants.
- **No writes anywhere:** prohibit file creation/modification, caches, logs, telemetry,
  temporary files, installs, bytecode, DB sidecars, and child writes. `-B` suppresses `.pyc`.
  Test read-only target, package, home and scratch surfaces and trace filesystem calls through
  success, refusal, malformed input, and shutdown. Stdout is protocol-only; stderr is short codes.
- **Root confinement:** realpath the explicit root and every input/derived path before access;
  require containment and refuse traversal, symlink escapes, special files, and replacement
  races. Guard checker references, graph endpoints, Profile protections, and Git metadata too.
  Immutable bundled code/contract reads are separately confined to the exact package tree.
- **Protected paths:** before reading, deny case-insensitive component/glob matches for
  `.env*`, `secrets/**`, `*.db*`, `*.sqlite*`, `.ssh/**`, `.aws/**`, `.gnupg/**`, `.netrc`,
  `.npmrc`, `.pypirc`, `.git-credentials`, `credentials*`, `token.json`, `tokens.json`,
  `id_rsa*`, `id_ed25519*`, `*.pem`, `*.key`, `*.p12`, `*.pfx`, and `*.keystore`.
  Union target Profile protected/secret patterns; malformed protections fail closed. Where
  stdlib `tomllib` is absent (Python 3.9–3.10), the fixed list alone applies and every result
  reports `profile_protections: unavailable`; the server never claims Profile rules it did not read.
  Check both lexical and resolved paths before lookup projection or source hashing.
- **Bounds:** frames ≤64 KiB; each file ≤1 MiB; aggregate reads ≤4 MiB/256 files per call,
  including indirect reads; parse depth ≤32; call deadline ≤10 s. Stream at most limit+1
  bytes before rejection. Output including the envelope ≤16 KiB UTF-8; strings ≤4096 bytes.
- **No protected output:** only schema-allowlisted metadata, labels, locators, codes, and
  hashes; never protected contents, raw bodies, subprocess output, tracebacks, or credentials.
  Sentinel tests cover indirect reads and every error path.

Paginate deterministically without persistent/process result caches. A bounded stateless cursor
binds tool, root, arguments, source digests, and offset; recheck all guards on each page.
Changed inputs return `E_CURSOR`; an indivisible oversized item returns `E_LIMIT`. Never
abbreviate pins or present truncated evidence as complete.

### 4.5 Git is the sole subprocess exception

Only `handoff_pins` needs Git; all other tools forbid children. Use existing trusted
`/usr/bin/git`, `shell=False`, ≤5 s per child within the call deadline, and a streamed
64-KiB stdout/stderr cap; kill and reap on overflow/timeout. The fixed argv prefix is:

```text
/usr/bin/git --no-optional-locks --literal-pathspecs
-c core.fsmonitor=false -c core.untrackedCache=false -c core.hooksPath=/dev/null
-c core.attributesFile=/dev/null -c submodule.recurse=false -C <validated-root>
```

Only four suffix templates are allowed: `rev-parse --verify HEAD`,
`status --porcelain=v1 --untracked-files=all --ignore-submodules=all`,
`log -1 --format=%H -- <validated-relative-path>`, and
`diff --quiet --no-ext-diff --no-textconv --ignore-submodules=all HEAD -- <validated-relative-path>`.
The last replaces file-body retrieval for modification status. Slots accept validated paths
only, never options, revisions, shell text, or arbitrary argv. Decode only commits/status booleans.

Replace inherited child environment with constant `GIT_CONFIG_NOSYSTEM=1`,
`GIT_CONFIG_SYSTEM=/dev/null`, `GIT_CONFIG_GLOBAL=/dev/null`, `GIT_ATTR_NOSYSTEM=1`, and
`GIT_TERMINAL_PROMPT=0`; each disables external settings/attributes or prompts, not an operator
input. Before each spawn, require `.git` to be a real directory inside the validated root;
refuse symlinks, gitfiles, worktree/submodule pointers, `commondir`, object alternates,
config includes (`include`/`includeIf`), and `core.worktree`/`core.gitDir` redirection.
Also refuse `core.excludesFile` and `diff.orderFile` regardless of their values: these
settings redirect child reads to additional files, and `--quiet` does not suppress orderfile reads.
Inspect only fixed metadata locations and the `HEAD` reference, without walking `.git`.
Refuse configured filters, submodules, worktree config, and partial-clone/promisor settings:
the fixed argv cannot safely disable their possible helper or network operations. No hook,
helper, filter, external diff, textconv, or fsmonitor command may execute.

This bounded Git exception permits Git to read repository metadata and stat/compare the
worktree, including protected tracked files solely to produce a dirty boolean. Git's internal
reads are not per-path Guard reads; neither file contents nor status paths leave the child
decoder. Explicit path slots still require validated, nonprotected relative paths. The
preflight establishes the fixed checks above, not recursive validation of every object/ref.
Same-user concurrent replacement of repository metadata or worktree paths during a Git read
is outside this exception's threat model. Other server reads retain §4.4's confinement and
replacement checks. Refused or failed Git queries preserve available non-Git pins and mark
Git pins unavailable with `E_GIT`; time/output failures retain their bounded error codes.
Verify the stated preflight, child and filesystem behavior; existing CLI Git calls do not
already prove this boundary [E3].

### 4.6 Exact package and launcher

Only these eight files and their parent directories are admitted under `plugins/mir-mcp/`:

| File | Purpose |
|---|---|
| `.claude-plugin/plugin.json` | Claude identity; `mcpServers: "./.mcp.claude.json"`. |
| `.codex-plugin/plugin.json` | Codex compatibility identity; `mcpServers: "./.mcp.codex.json"`. |
| `.mcp.claude.json` | One Claude stdio declaration. |
| `.mcp.codex.json` | One Codex compatibility stdio declaration. |
| `mir_mcp.py` | Protocol, closed schemas, guards, pagination, fixed module loader. |
| `ontology/scripts/ontology_check.py` | Byte-identical canonical checker. |
| `ontology/references/common-contract.json` | Byte-identical common contract distribution. |
| `shared/relations_query.py` | Byte-identical standalone YAML adapter from §4.3. |

Reject symlinks, submodules, executable bits, special files, and undeclared/transient files or
directories. No skills, hooks, agents, commands, dependency installs, or network bootstrap.
Tests/setup docs live outside the active tree. Require existing Python 3.9+, matching the
canonical checker's floor, and Git. macOS's system `python3` is 3.9 (observed 3.9.6 on the
maintainer host, 2026-10-26), so a 3.11 floor would fail on stock hosts; §4.4 states the
`tomllib` fallback. Independent skill-script Python support is unchanged.

Claude manifest keys are exactly `name`, `version`, `description`, `mcpServers`. Codex adds
only `author: {name}` and `interface: {displayName,shortDescription}` as native metadata.
Both names are `mir-mcp`; versions/descriptions agree and versions pass the safe grammar.
Reject unknown/duplicate keys, inline/array/remote MCP references, and extra servers.
Each declaration is exactly `{mcpServers:{"mir-mcp":<server>}}`: Claude server keys are
`type: stdio`, `command`, `args`; Codex keys are `command`, `args`, `env_vars: []` [E7].
Reject env values, URLs, headers, credentials, `cwd`, and all extra launch options.

On macOS (primary), Linux and WSL (separate compatibility lanes), launch exactly
`python3 -I -B -u <runtime-plugin-root>/mir_mcp.py`, keeping the module path one argv element
with spaces. Only `${CLAUDE_PLUGIN_ROOT}` or `${PLUGIN_ROOT}`, respectively, substitutes that
path [E7]. No shell, wrapper, `-c`, `-m`, interpreter fallback, or install command.

Native Windows activation is refused in v1 per decision 1564223563987427390 and ADR-79.
Later admission must specify native interpreter/path/null-device forms, Git/environment
behavior, filesystem/protection tests, and address POSIX discovery such as
`mir_ontology_runner.py:9`'s `pwd` import if that runner is used. Require a new reviewed
shape/digest and both Windows runtime receipts. WSL keeps its own Linux homes/cache/receipts;
no native-Windows readiness follows.

### 4.7 Dual-era protocol and token budget

Use newline-delimited JSON-RPC over stdio: MCP `2026-07-28` stateless per-request metadata,
`server/discover`, and direct modern calls without initialization; plus legacy `initialize`
and `notifications/initialized` for `2025-11-25`, scoped to the stdio process [E9]. Normalize
era-specific envelopes to identical tool semantics. Reject unsupported versions; no deprecated
features, HTTP/SSE fallback, or optional capabilities beyond tools.

`tools/list` returns exactly the five tools in §4.2 table order, with one-line descriptions,
closed input schemas, `outputSchema`, and `readOnlyHint: true`, `destructiveHint: false`,
`openWorldHint: false` annotations. No examples, instruction dumps, dynamic tools, or extra
discovery tools. Compact `structuredContent` with `content: []`
avoids prose/JSON duplication. A client requiring duplication cannot pass unchanged.
Tool-result cursors are independent of MCP discovery pagination.

**B4 implementation evidence:** deterministically serialize the complete `tools/list` result;
record UTF-8 bytes and SHA256; require ≤16 KiB and ≤6000 tokens using each runtime's evidenced
accounting/tokenizer. In fresh Claude and Codex sessions record versions, discovery requests,
initial model-visible schema/token load, and load after selecting/calling one tool. Exercise
each host's supported deferred loading and retain observations. List size alone proves neither
deferral nor savings. Record eager behavior and unavailable counters honestly; neither supports
a deferred-loading/measured-budget claim. B4 remains open until both measurements support the
claimed behavior and budget.

### 4.8 Parity, selection, acknowledgement, rollback, and attestation

Installed Codex `code-review` declares `mcpServers` and stdio fields [E7]; its shell,
environment forwarding, and extra options are not admitted here. Yoke's existing MCP-field
rejection is policy, not a Codex limitation [E2]. Normalize server identity, launcher, schemas,
exact inventory, bounds, errors, and results; preserve raw host-prefixed tool names in evidence.
Unsupported layouts fail parity, with no project-config fallback.

Tracked consumer selection explicitly records `mir-mcp`, runtimes, server, and tools.
ADR-89 §2.2 registration remains host-wide at user scope: unrelated repository sessions can see
the tools. Guarded read-only operations with explicit roots cannot dispatch or mutate, but can
expose allowed metadata. Roots are not authentication/session isolation; target read permission
and local policy remain necessary. Keep each selected set separate from the host-active union;
removing one consumer cannot unregister a package another consumer still selects.

Apply ADR-88 §2.2 items 4–5 without relaxation:

1. Validate complete materialized inventory and both marketplaces before registration, including
   unselected packages without activating them. Bind provider commit, marketplace/tree digests,
   kind, launcher, schemas, and exact inventory into locks/receipts. A human locally acknowledges
   the computed tree SHA256 in `active_package_digest_acknowledgements`; generic enable/apply
   is insufficient. Every changed byte invalidates acknowledgement and blocks new registration,
   finalization, and READY claims. Status reports drift, not a remotely stopped process.
2. Rollback restores preceding provider, lock, registry, and runtime registration only after
   revalidating all restored inventory/digests/acknowledgements. No prior MCP selection means
   no restored MCP registration. Reject incomplete/downgraded receipts; failed activation restores
   prior registration. Tools write no target state requiring undo.
3. Fresh Claude/Codex sessions outside the provider checkout must each prove installed digest,
   client/version/session, OS/interpreter, stdio invocation, protocol era, exact five-tool inventory
   without extras, and a bounded safe call per tool. Skill/hook discovery or manifests alone
   cannot attest MCP. Finalize only after integrity, parity, B4, and both receipts pass.

## 5. Rejected Alternatives — HARD

- **Source in Mir Harness:** private source is unavailable to other users; public tools belong
  in Yoke under Harness management.
- **Tools inside `mir-core`:** violates skills-only admission and enlarges ordinary skill-update authority.
- **Agent Hub tools:** owner-only Agent Hub capabilities outside this public read-only contract.
- **Write tools in v1:** require separate mutation, recovery, and authority decisions.
- **DB relation adapters in v1:** add consistency/WAL/sidecar contracts; v1 denies DB files.
- **HTTP or SSE:** adds listener/deployment/authentication concerns to local tools.
- **Generic MCP admission:** one reviewed use case cannot admit arbitrary servers.
- **Sibling-cache imports:** violate independent package selection/version/cache isolation.

## 6. Positive Consequences

Public, bounded tools need no owner services or credentials. Shared checks have tested byte
identity; skills work without MCP. Compact results and runtime measurements make costs reviewable.

## 7. Negative Consequences — HARD

Read access still needs review, confinement, digest renewal, and host-wide visibility accounting;
stdio/annotations alone provide no sandbox. Guarded checker interfaces and the standalone YAML
subset adapter are new work, not present CLI guarantees. Exact copies need drift tests;
unsupported YAML and native Windows fail closed. Interpreter/Git prerequisites and real B4/runtime
evidence remain necessary; source tests and proposed text cannot establish delivery.

## 8. Out-of-Scope — HARD

Out of scope:
- native Windows activation;
- write tools and DB relation adapters;
- the Agent Hub tools;
- generic MCP admission;
- any change to the `skills-hooks` acknowledgement or update behaviour.

Accepted at release 0.13.32 (owner Discord 1564297975755448493), after implementation
f715b19 and e38add3. Runtime attestation on both hosts remains a per-host gate (§4.8).

## 9. Verification

The implementing change must supply these checks; none is claimed executed here:

- Configuration tests admit schema 5 only for the exact kind/name/path/inventory; reject generic,
  mixed/unknown kinds and policy relaxation; preserve legacy checks; omit MCP from every default Profile.
- Package/declaration tests prove all eight files, safe versions, closed manifests/argv,
  credential-free content, empty environment inputs, and reject symlinks, submodules, executable
  bits, undeclared files, duplicate keys, extra servers, shell/URL options, and launch drift.
- Security tests cover path traversal/realpath/symlink escape/replacement races, direct/indirect
  protected paths, Profile deny rules, special files, all size/count/depth/time/output caps,
  sentinel non-disclosure, and stale cursors. Static no-network/environment checks plus runtime
  no-network/no-write traces cover success/error/shutdown and descendants; no `.pyc` or caches.
- Git tests permit only §4.5 argv/environment, disable hooks/external diff/textconv/fsmonitor,
  refuse configured filters/submodules/partial clones and fixed metadata redirections/config
  includes and `core.excludesFile`/`diff.orderFile` read redirections before spawning, bound
  combined capture/time, and prove protected tracked changes
  yield only dirty booleans. Verify partial non-Git pins and short error codes on refusal;
  forbid shell/listener/credential access, child writes, and non-Git subprocesses. Do not claim
  recursive per-path Git read confinement or same-user concurrent-replacement protection.
- Hermetic dual-era tests cover discovery/direct modern calls, legacy initialization/calls,
  unsupported versions, era-specific envelopes, malformed/oversized frames, exact order/schemas,
  short errors, cursor pagination, stdout purity, and rejection of deprecated/unadvertised features.
- Single-source tests compare checker/contract/YAML-adapter bytes and guard every backend read.
  YAML differential fixtures preserve declared traversal on the admitted subset; unsupported
  forms/DB adapters fail. Isolated package tests work without sibling caches/CLI/source checkout;
  skill no-MCP paths and `spec-architect` neutrality still pass.
- Manager tests enforce exact acknowledgement, complete inventory/marketplace digests,
  stale/downgrade rejection, selected-set versus active-union integrity, rollback to validated
  prior registration/absence, and MCP-specific attestation/finalization extensions [E2].
- Real isolated-home Claude/Codex checks use two consumer directories and fresh sessions for exact
  installed inventory and safe calls plus B4 size/deferred-loading measurements. Verify macOS,
  Linux, and WSL independently; refuse native Windows. Run affected admission/security tests
  and generated parity in that later implementing change.

For this ADR-only change, behavior scenarios are not applicable. Check frontmatter/required
sections, links, evidence locations, requested coverage, and diff scope; future runtime/security
checks remain future gates, not current passes.

## 10. References

- [ADR-74](adr-74-portable-bootstrap-capability-sources-and-memory.md),
  [ADR-79](adr-79-agent-guided-platform-scope.md),
  [ADR-86](adr-86-mir-harness-managed-repository-maintenance.md),
  [ADR-88](adr-88-active-plugin-component-admission.md) §§2.1–2.3, 5,
  [ADR-89](adr-89-dual-runtime-capability-management.md) §2.2, and
  [ADR-90](adr-90-role-plugins-and-common-hooks.md) §§2.3–2.4, 5.
- **E1, verified in repository, 2026-10-26:** `config/capability-sources.json:30–40` and
  `src/mir/core/capabilities/config.py:192–263`: current kinds, nonempty skills, closed
  component policy, and hook-only acknowledgements.
- **E2, verified in repository, 2026-10-26:**
  `src/mir/core/capabilities/manager.py:455–473,503–550,1314–1318`: validation/acknowledgement;
  `:1745` (`attest`), `:1976` (`finalize`), `:3066` (`_rollback_runtime_registration`)
  are extension points, not MCP implementation. `tests/test_plugin_skill_packages.py:53`
  forbids MCP fields in current role manifests.
- **E3, verified in repository, 2026-10-26:**
  `plugins/mir-core/skills/ontology/scripts/ontology_check.py:153,214` contract/mapping;
  `:639` lookup; `:577` impact; `:697` handoff pins; `:534–574,724–769` existing Git
  behavior, which differs from §4.5; `:14` relative contract location.
- **E4, verified in repository, 2026-10-26:** `src/mir/core/relations.py:218,328,389`
  loads/bounds/queries YAML; `:54–84` owns purpose/direction rules;
  `src/mir/cli/relations.py:21,46,96–104` routes YAML separately from DB.
  These implementations contain no MCP wrapper.
- **E5, verified in repository, 2026-10-26:**
  `plugins/mir-core/skills/ontology/scripts/mir_ontology_runner.py:47–72,99–123` resolves
  versioned per-plugin caches/installation records; `tests/test_plugin_skill_packages.py:227–235`
  copies and validates each plugin alone.
- **E6, verified in repository, 2026-10-26:**
  `plugins/mir-core/skills/spec-architect/SKILL.md:25` promises files/text search without
  a particular CLI/IDE/MCP;
  `plugins/mir-core/skills/ontology/scripts/mir_ontology_runner.py:9` imports `pwd`.
- **E7, installed artifact and official docs rechecked 2026-10-26:** host-relative
  `.codex/plugins/cache/openai-bundled/code-review/26.928.21956/.codex-plugin/plugin.json:18`
  references `./.mcp.json`; its `.mcp.json:2–12` shows stdio launch/`env_vars` fields.
  Read-only external evidence proves declaration support, not activation. OpenAI's
  [packaging guide](https://developers.openai.com/plugins/build/plugins) retains Codex
  compatibility manifests; its [local MCP guide](https://developers.openai.com/plugins/deploy/desktop-only#configure-a-local-mcp-server)
  documents stdio/`${PLUGIN_ROOT}`. Claude's [manifest reference](https://code.claude.com/docs/en/plugins-reference#mcpservers)
  documents JSON references/`${CLAUDE_PLUGIN_ROOT}`.
- **E8, parent-supplied owner authority/evidence:** Discord 2026-10-26 decisions
  `1564217596600131598` (Hub exclusion/public tools), `1564220383337517089` (public Yoke
  source/tools only), `1564223563987427390` (five tools/platform order/ADR).
  Harness `tasks/reports/yoke-public-mcp-tool-inventory-2026-10-26.md` is planning evidence,
  not added authority; constraint 12's repository source is independently verified in E6.
- **E9, official protocol docs retrieved 2026-10-26:** MCP
  [modern versioning](https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning),
  [discovery](https://modelcontextprotocol.io/specification/2026-07-28/server/discover),
  [tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools), and
  [legacy lifecycle](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle).
- **Semantic scope:** `.mir/ontology-map.json#/domain/concepts/2` indexes admitted kinds;
  `#/domain/invariants/0` preserves consumer authority, `#/domain/invariants/1` separates
  installation/discovery, and `#/domain/invariants/2` indexes the current hook/local-MCP
  boundary. This proposal does not claim current map/implementation admission of `mir-mcp`.

## Amendment: 2026-10-27 — Codex launcher form

Design authority is the owner-approved Yoke release chain for this session (Discord
`1564297975755448493`, `1564320227062186065`, parent-supplied). This amends §4.6 and the
§4.8 attestation launcher for Codex only.

After 0.13.33 was installed, Codex did not start the server. Its log showed that Codex
passed `${PLUGIN_ROOT}/mir_mcp.py` literally, resolved that path against the session working
directory, and closed the connection before the initialize response. Claude Code expands
`${CLAUDE_PLUGIN_ROOT}` and called all five tools in a fresh session. A bundled Codex plugin
uses `"cwd": "."`, which Codex resolves to the installed plugin root.

The Codex declaration is now exactly
`{command:"python3",args:["-I","-B","-u","./mir_mcp.py"],cwd:".",env_vars:[]}`, with no
variable substitution. `cwd` is admitted only as `"."`; any other value or extra launch option
is still rejected. The server already resolves its bundled modules from its own resolved file
path, so loading is unchanged. The locked Codex launcher adds `cwd:"."`. The Codex attestation
launcher is `{command:"python3",args:["-I","-B","-u","./mir_mcp.py"],cwd:"<installed-root>",env:{}}`
with the absolute installed root. Claude's declaration, locked launcher and attestation launcher
`{command:"python3",args:["-I","-B","-u","<installed-root>/mir_mcp.py"],env:{}}` are unchanged.
Each runtime's evidence must match its own form exactly. The package digest changes, so each
consumer renews its own `mir-mcp` acknowledgement.

## Amendment: 2026-10-27 — Consumer-local hook acknowledgement

Owner decision: Discord `1564336518967857153` (parent-supplied), applying the consumer-local
acknowledgement rule to the hook package. This amends the §8 exclusion of `skills-hooks`
acknowledgement and update behaviour; §4.8 items 1–2 now apply to both `mcp-stdio` and
`skills-hooks` packages.

Only the consumer-owned configuration supplies an acknowledgement for either kind:
`<consumer-root>/config/capability-sources.json`, or the explicit `--config`. A provider-only or
bundled configuration never does. Selecting or updating to hook bytes requires that consumer
acknowledgement to equal the exact tree digest, so a provider update that changes both the
bytes and its own acknowledgement fails closed until the consumer renews
`active_package_digest_acknowledgements["mir-lifecycle-hooks"]`. The active receipt's
`consumer_digest_acknowledgements` replaces `mcp_digest_acknowledgements` and records the
consumer approval for both kinds; rollback re-validates restored bytes against it. A receipt
that holds only the older field is still read: its MCP approval comes from that field and its
hook approval from the current consumer configuration, never from a provider configuration.

## Amendment: 2026-10-27 — Legacy version negotiation and request metadata

Owner decision: Discord `1564465079863484509` (parent-supplied). This amends §4.7; the
original "Reject unsupported versions" sentence above is kept as history.

Codex CLI 0.164.0 sends a legacy `initialize` requesting `2025-06-18`, then sends
`_meta: {"progressToken": 0}` on `tools/list` and its own `_meta` keys on `tools/call`. The
server refused the first with `E_VERSION` and treated each later `_meta` as a modern request
without a protocol version (`E_SCHEMA`). The
[2025-11-25 lifecycle](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle)
requires a server to answer an unsupported request with a version it supports, and leaves
disconnection to the client.

A legacy `initialize` that requests any string version now negotiates `2025-11-25`; every
other `initialize` check is unchanged. After legacy initialization, `_meta` without
`io.modelcontextprotocol/protocolVersion` is ordinary request metadata and is ignored. A
`_meta` that carries that key still takes the modern path, which still refuses any version
other than `2026-07-28` with `E_VERSION`. Before initialization, a request whose `_meta` lacks
the key is still refused. The package digest changes, so each consumer renews its own
`mir-mcp` acknowledgement.

## Amendment: 2026-10-27 — Caching hints, failure text and per-pin Git failures

Owner decision: Discord `1564607534323732632` (parent-supplied; the recommended options of the
Harness items 10 and 11 preparation, each designed against its behavioural intent). This amends
§4.7 and the Git limits; the original sentences above are kept as history.

- Caching hints: the
  [2026-07-28 caching utility](https://modelcontextprotocol.io/specification/2026-07-28/server/utilities/caching)
  requires `ttlMs` and `cacheScope` on `resultType: "complete"` results of `server/discover`
  and `tools/list`. Modern results now carry `ttlMs: 3600000` and `cacheScope: "public"`: the
  five-tool list is the same for every caller, carries no authorization, and changes only with
  the package bytes, which require re-acknowledgement and a restart. Legacy results are
  unchanged.
- Failure text: Claude Code shows the model only "Unknown error" for an `isError` result with
  `content: []`. An `isError` result now carries exactly one TextContent: compact JSON with the
  error `code`, the result's `unknowns` when present, and `omitted` when unknowns were dropped to
  keep the text within 512 bytes. Successful results keep `content: []`.
- Per-pin Git failures: one slow `git status` (over the old 5 s child limit, trigger unknown)
  used to set a call-wide Git error and skip every later Git query, so `handoff_pins` returned
  `ok: false` and lost `head` and every revision. A failed or timed-out Git query now marks
  only its own pin unknown as `<label>: <code> after <seconds> s`. A Git child may use the call
  deadline minus a 1 s reserve, so the call still answers before the 10 s alarm. The call is
  `ok: false` only when Git never answered (preflight refusal or every query failed).

The package digest changes, so each consumer renews its own `mir-mcp` acknowledgement.

## Amendment: 2026-10-27 — Host-local consumer acknowledgements

Owner decision: Discord `1564633173516755045` (parent-supplied), choosing a git-ignored local
file after a Main check showed the earlier recommendation broke opt-in. This amends the
"Consumer-local hook acknowledgement" amendment and every rule above that names
`config/capability-sources.json` as the consumer's approval.

In a Yoke checkout, `config/capability-sources.json` is both the provider default and the
checkout's own consumer config. A fresh clone running `mir capability update --mcp
--project-root .` was therefore admitted by whatever acknowledgement the repository committed,
without its user reviewing anything; the committed `mir-lifecycle-hooks` acknowledgement leaked
the same way. An approval is host-local state of the consumer that made it.

- The only consumer approval source is `<project root>/config/capability-acknowledgements.local.json`,
  shaped `{"active_package_digest_acknowledgements": {"<package>": "<sha256>"}}`. It is
  git-ignored in Yoke, never part of the adopter payload or a provider copy, and must not be a
  symlink. A missing file approves nothing; a malformed one fails closed.
- `active_package_digest_acknowledgements` in any `capability-sources.json` is still validated
  (names only active packages) so older provider configs stay loadable for update and rollback,
  but it never approves. When a consumer config still carries one, the missing-approval error
  says to move it into the local file. Yoke's committed config now carries `{}`.
- Each update re-reads the local file, so an approval written for a package the update introduces
  applies. A provider update never writes or renews the local file; rollback restores the
  approvals recorded in its receipt.
- Compatibility: a `mir` older than 0.13.37 requires a hook acknowledgement in every schema 4+
  config and cannot load this release's provider config. Update the `mir` code before updating
  the provider. A file force-added to git (`git add -f`) would still travel with a clone; that is
  not checked.

## Amendment: 2026-10-28 — Cloud-synced roots and byte-stable checkouts

Owner decisions: Discord `1564632417304838205` (answer 7: refuse OneDrive-like synced storage
with a warning; answer 6: the same behaviour on every OS) and `1564710844560969759` (start
0.13.39), parent-supplied. This is the first of three releases toward a native Windows lane;
the lane itself (§4.4-§4.8 for `windows`) is a later amendment and stays refused until then.

- Cloud-synced roots: a resolved `target_root` inside cloud-synced storage is refused before it
  is opened, with the new code `E_CLOUD_SYNC`. The result's `data` is `{"unknowns": [<warning>]}`
  (the only non-null `data` of a refusal), so the failure text of the previous amendment shows the
  warning: `target_root is inside a cloud-synced folder (<kind>); Mir does not run there. Move
  the repository to a local folder.` Detection: on Windows any component of the resolved root
  with a cloud-file attribute (`PINNED` 0x80000, `UNPINNED` 0x100000, `RECALL_ON_OPEN`
  0x40000, `RECALL_ON_DATA_ACCESS` 0x400000, `OFFLINE` 0x1000; measured on the owner's Windows
  11 PC, OneDrive folders carry `UNPINNED` and are not reparse points); on any OS a resolved root
  whose parts start with `/`, `Users`, any user, `Library` and then `CloudStorage` or
  `Mobile Documents` (a macOS home's File Provider or iCloud Drive storage), compared
  case-insensitively. Linux has no OS marker and nothing more is refused there. The
  `mir capability` manager refuses such a project root with the same text (`project root ...`)
  after checking it is a real directory and before reading consumer state.
- Byte-stable checkouts: package and reviewed-handler digests hash raw bytes, and Git for
  Windows converts LF to CRLF on checkout by default (153 reviewed-handler failures in a Windows
  test run of 8aff20d). The repository's `.gitattributes` is `* -text`, so every checkout is
  byte-identical to its blob. Tree digests sort entries by relative path parts, which equals the
  previous order on macOS/Linux (digests unchanged) and does not case-fold on Windows.
- Portability fixes with no behaviour change elsewhere: copied derivative paths are stored with
  `/` separators; the ontology runner and the Memory Keeper client import `pwd` only where it
  exists and fall back to `Path.home()`.

Every package digest changes (version manifests, plus `mir-mcp` and `mir-core` code), so each
consumer renews its `mir-lifecycle-hooks` and `mir-mcp` acknowledgements.

## Amendment: 2026-10-28 — Native Windows manager and hooks (0.13.40)

Owner decisions: Discord `1564632417304838205` (answer 6: the manager and the hooks behave on
Windows as on other OSes) and `1564744151088627924` (start 0.13.40), parent-supplied. Second of
three releases; `mir-mcp` activation on native Windows stays refused (§4.4-§4.8 for `windows`
remain the next amendment).

- Derivatives: the manager runs `scripts/generate_codex_derivatives.py` with its own
  interpreter. Its output is byte-identical to the former Bash generator (checked on every test
  fixture and this repository), written as UTF-8 with LF. The Bash script is a wrapper; a
  consumer without the `.py` still uses Bash.
- Private files: mode 0600 on POSIX; on Windows a protected DACL with one ACE granting the
  current user full access. The check accepts only a present, protected DACL whose ACEs are all
  access-allowed for the current user, SYSTEM or Administrators; a NULL DACL or any other ACE is
  not private. Rollback restores private files as private.
- Hook: on Windows the handoff hook refuses a transcript that is a link or reparse point or whose
  identity changes between `lstat` and open, and kills a timed-out pin runner's process tree with
  `%SystemRoot%\System32\taskkill.exe /T /F`. POSIX paths are unchanged. The reviewed handler
  digest changes accordingly.
- Evidence: on the owner's Windows PC (Korean locale) the manager, generator, hook and ontology
  test files ended at 1256 passed and 1 failed (the capability lock, rebound at release); tests
  of POSIX shell entrypoints, native Windows bootstrap and `mir-mcp` activation are skipped on
  Windows with those reasons (252). A `windows_native` CI job runs
  the same files.

## Amendment: 2026-10-28 — Windows consumer sync fixes (0.13.41)

The 0.13.40 exit check, a consumer `sync --apply` on the owner's Windows PC with isolated
capability, Claude and Codex homes, failed natively twice: removing the exported `.git` raised
WinError 5 (Git for Windows object files are read-only), and Codex 0.164 for Windows writes the
local marketplace source as `\\?\C:\...`, so the persisted source never equalled the active
path. Tree removal now clears the read-only attribute and retries; every Codex marketplace
source read drops the extended-length prefix (`\\?\` and `\\?\UNC\`) before resolving. With
both fixes the PC run registered the four selected plugins in both CLIs and kept the binding
ledger private. The third release of the lane (`mir-mcp`, `windows` receipts, Python 3.11 floor)
becomes 0.13.42.

## Amendment: 2026-10-28 — mir-mcp native Windows lane and the Python 3.11 floor (0.13.42)

Implements the Windows admission design (owner answers of 2026-10-28: option B guard, `python3`
launcher, the default Git for Windows path, the same deadline behaviour, Python 3.11 on every OS).

- Guard: on `win32`, each path component is opened with `CreateFileW` (`GENERIC_READ`, share
  read/write, `OPEN_EXISTING`, `FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_BACKUP_SEMANTICS`) and
  converted with `msvcrt.open_osfhandle`. A reparse point, a non-regular non-directory, a final
  path (`GetFinalPathNameByHandleW`) that differs from the requested one under `normcase`, or a
  final path that is UNC is `E_PATH`; ancestors stay open (no delete sharing) until the read
  ends; protected names are checked on the lexical, resolved and final paths. Lexical refusals:
  `:` in a component, device names (`CON`, `PRN`, `AUX`, `NUL`, `CONIN$`, `CONOUT$`, `COM0`-`COM9`,
  `LPT0`-`LPT9`, superscript digits included) with or without an extension, `*?"<>|` outside
  Profile patterns, and a trailing dot or space. Roots must be local drive-letter paths. The only
  native surface is `kernel32` `CreateFileW`, `GetFinalPathNameByHandleW`, `CloseHandle` and
  `msvcrt.open_osfhandle` (static test). POSIX paths are unchanged.
- Deadline: on `win32`, `tools/call` runs `execute()` in one worker thread joined for 10 s; on
  overrun the server writes the `E_TIMEOUT` result and exits with `os._exit(0)`. POSIX keeps
  `SIGALRM`; the cooperative `tick()` deadline and the Git reserve apply on both.
- Git: on `win32` the first argv element is `C:\Program Files\Git\mingw64\bin\git.exe` (no `PATH`
  search, no `cmd\git.exe` wrapper), with `CREATE_NO_WINDOW` and two reader threads bounded at
  64 KiB in place of `selectors`. The five `GIT_ENV` entries are unchanged; no `SystemRoot` entry
  is needed (measured on the PC), so no fourth `kernel32` function is admitted.
- Startup: the `win32` refusal is removed; any interpreter below 3.11 exits non-zero with a
  stderr reason before reading stdin. `mir_mcp.py` stays parseable by Python 3.9 so that refusal
  is reachable.
- Receipts: `platform` accepts `windows` only when the validator runs on `win32`, and refuses it
  elsewhere; `interpreter.executable` must be absolute in the host's native form (a drive-letter
  path on Windows); `interpreter.version` must be 3.11+; the Claude launcher is compared as
  `str(installed) + "/mir_mcp.py"` (equal to the former value on POSIX).
- Manager: `mir-mcp` activation is admitted on Windows x64 with 64-bit Python; ARM64 and 32-bit
  Python stay refused with the architecture named.
- Evidence: macOS full suite 3836 passed with 1 failure, the capability lock, rebound at release.
  On the owner's Windows PC the in-scope files ran natively before the version bump, including
  the Windows-only guard, deadline and Git tests. Two runs found product and test defects: a
  hook-source pin, CRLF test fixtures, a launcher-separator case, a FIFO case, the
  environment-variable length of a test ID, and receipt lookups by the consumer key. After those
  fixes, 114 targeted Windows tests passed and 1 was skipped: the 8.3 short-name case, because
  short-name generation is disabled on that volume. The full PC run before the last test-only
  fixes ended at 1945 passed and 4 failed: the lock and the three consumer-key lookups.
- Admission stays incomplete until fresh Claude Code and Codex receipts with `platform: windows`
  exist on the owner's PC (design §5.5). They need the PC's user-scope CLI homes, which still hold
  stale 0.8.0 registrations; that is an owner decision.

## Amendment: 2026-10-28 — Windows Git binary location (0.13.43)

The 0.13.42 release check failed on `windows-latest` (Git for Windows 2.56.0): the fixed
`mingw64\bin\git.exe` no longer exists there, because Git for Windows 2.56 moved the real
binary to `ucrt64\bin`; the project names only `cmd\git.exe`, a wrapper this design refuses, as
stable. On `win32` the Git argv now starts with the first present of two fixed paths under the
default install location, `C:\Program Files\Git\ucrt64\bin\git.exe` then
`C:\Program Files\Git\mingw64\bin\git.exe` (owner answer 4, "the Windows default Git location"),
checked with `os.path.isfile` at start; neither present leaves the first, so Git pins report
`E_GIT`. No `PATH` search, wrapper or environment input is added. The same check also failed on
Ubuntu for lack of a Python 3.11 compatibility interpreter; the release workflow now installs
3.11 beside 3.12. `v0.13.42` stays tagged without a GitHub Release; 0.13.43 carries it.

## Amendment: 2026-10-28 — direct migration from a 0.8.0 enrollment (0.13.44)

The owner's Windows PC still held a project enrolled by the shipped 0.8.0 provider (schema-1
registry, active receipt, lock and `capability-sources.json`). Update checked that state against
the current configuration, which names `mir-mcp`, so it refused with `MCP package rejected: root
must be a real directory`. Update now validates a schema-1 provider and consumer against their own
evidence (the receipt's source, materialized root and plugin digests; the consumer's locked
plugins and agents), exports the target `capability-sources.json` first and takes the export
paths from it, and on apply rewrites the consumer config, lock and registry to the current
schemas. `mir-mcp` is only added when the target profile selects it, so this path admits no MCP
package by itself. Registry keys are compared in `normcase` form and the `\\?\` prefix is
stripped from recorded paths, as Windows writes them. Evidence: a test built from the real 0.8.0
tree (`26cf2a4`) fails with the PC's message against 0.13.43 and passes now, on macOS and
natively on the Windows PC; partial, invented, digest, receipt and active-tree forgeries are
refused.

Correction (0.13.45): stripping the `\\?\` prefix must not resolve the recorded install path.
0.13.44 resolved it, so on a host whose Claude config home is a symbolic link the launcher Claude
actually ran (`<recorded path>/mir_mcp.py`) no longer matched and the receipt was refused. The
install path is compared as recorded, after prefix stripping only; a test with a linked
capability home covers it.
