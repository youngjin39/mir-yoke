# Mir Yoke

**A Harness-managed central capability supply system for independently owned repositories.**

Mir Harness manages Yoke's direction, reuse decisions, verification, and authorized delivery
coordination. Yoke versions and distributes generic shared sources through its public template,
standard Project Agent Kit, optional public Mir CLI, plugins, and reference corpus. It is not an
agent runtime, service, or control plane, is not a universal installer, and has no standing
authority over a repository that reads or adopts its material. Consumers retain their goals, data,
local policy, adapters, and execution; the active AI agent writes only under the user's
target-specific authorization.

## Project documents

- [Architecture](ARCHITECTURE.md) describes the current supported flows and source layout.
- [Decision index](docs/decisions/INDEX.md) identifies current authority and lists every ADR.
- [Specification snapshot](spec/STATE.md) preserves the completed v0.8 automation requirements;
  ADR-83 defines the current supported surface. There is no separate active product PRD.
- [Current maintainer plan](tasks/plan.md) is the single active cursor. Completed work and the
  outstanding owner decision are recorded in the [change log](tasks/change_log.md).

Before forming a project on another computer, the AI must run the
[new-machine global setup check](docs/operations/new-machine-setup.md).
Propose missing user-scope setup for confirmation; global adoption remains optional.

## Supported layers

### 1. Minimal Starter compatibility

[`starter/`](starter/) is the four-file compatibility payload. It contains exactly four Markdown
files: a repository-owned `HARNESS.md`, thin `CLAUDE.md` and `AGENTS.md` entrypoints, and an adoption
guide. It does not require a Mir CLI, installer, plugin, hook, memory database, specification tree,
sub-agent, daemon, receipt, restart, or platform-specific runtime.

### 2. Standard Project Agent Kit

[`recipes/project-agent-kit/`](recipes/project-agent-kit/) is a supported agent-guided recipe for a
new empty target. It does not copy a fixed payload. The target's AI uses Mir Yoke as read-only
reference and creates a purpose-specific project brief, project-owned common harness, required
local SQLite+FTS5 memory, Claude/Codex reviewer, real lint/build/test Git hook, and verified initial
commit. A thin project-owned wrapper executes the exact recorded Mir revision while keeping runtime
state below ignored `.mir/`; it copies no Mir CLI implementation or provider Git history. Product
planning and implementation remain a later request.

### 3. Optional installed `mir` CLI

The v0.9 package restores the public v0.8 `mir` command surface for owners who explicitly choose
the automated bootstrap, memory, capability, context, execution, hook, or verification workflows.
The [explicit automation guide](BOOTSTRAP.md#explicit-automation-optional-installed-cli) defines
its target, consent, and verification boundary. Install it outside a target checkout from an
immutable release:

```bash
uv tool install --force --link-mode copy \
  "git+https://github.com/youngjin39/mir-yoke.git@v0.13.46"
mir --help
```

Installation grants no repository authority. A state-changing command may act only after the user
names the target and operation; read-only inspection remains read-only, and the Project Agent Kit
does not depend on this host-global installation or vendor its source.

### Optional plugins and inert references

[`plugins/`](plugins/) publishes optional, namespaced host capabilities for Claude and Codex. A
plugin is installed explicitly in the agent host; it is not copied into a target or treated as a
readiness requirement. Three role plugins group the common workflows formerly copied into
repositories: core, code, and content. A fourth `mir-lifecycle-hooks` plugin supplies the same
read-only `SessionStart` continuity reminder and supporting skill to Claude and Codex. Its exact
handler digest is acknowledged by schema 4+, and it has no repository, file, environment, or network
access. [ADR-90](docs/decisions/adr-90-role-plugins-and-common-hooks.md) keeps all project-coupled
hooks behind repository-owned adapters. The separate `mir-mcp` package supplies five read-only
stdio tools under [ADR-91](docs/decisions/adr-91-stdio-mcp-package-admission.md).
Schema 5 admits its exact package shape; no default Profile selects it. Registration requires
an explicit `mir capability sync --mcp --apply` and an owner-acknowledged tree digest.
Fresh MCP-specific evidence from both runtimes is required before finalization; source tests
do not establish runtime readiness. `.mcp.json.example` remains inactive target-local guidance.
Codex still requires the operator to review and trust the current hook hash in a fresh session;
installing or enabling the plugin alone does not prove hook execution.
The real-CLI probe installs all four packages into isolated Claude and Codex homes and verifies
identical plugin, skill, and hook inventories from two independent consumer working directories.
[ADR-89](docs/decisions/adr-89-dual-runtime-capability-management.md) defines the wider central
management contract: explicit project sync supplies selected Claude agent and command sources, the
generator projects agents to Codex, existing plugin skills absorb Codex command intent, and
target-owned hook and MCP configuration remains separate from global plugin installation. For a
host-wide, repository-neutral setup, `scripts/install_user_runtime_agents.py` installs the union of
Profile-selected agents and Claude commands into explicit user configuration roots; it is dry-run by
default, records file digests, and never edits a consumer repository. Yoke-only allowlist entries are
excluded, and project-local definitions still win.

Version 0.9.1 adds `mir-core:selective-relations`, an on-demand
selective relation retrieval (SRR) skill. `mir-code:bluebricks` and `mir-content:knowledge` point
to it when declared, typed relationship evidence can answer a bounded question. The skill treats
relations as provenance-bearing locators and does not promise token savings, require a per-repository
database migration, or generate a graph. The published immutable v0.9.0 does not include this
capability; older installations continue with ordinary source search.
Version 0.9.2 adds on-demand project/code and dynamic-memory applicability guidance. It prefers
existing fact/link/provenance storage and separates verified relations from similarity candidates;
it does not add a database writer or automatic extraction to the portable reader.

Version 0.13.27 also adds owner-requested `mir-core:memory-evaluation` and optional
methodology references in testing, efficiency and governance for controlled experiments,
instruction changes and trace-derived skill patches. These additions ship guidance only.

Version 0.13.28 fills verified guidance gaps in existing skills: frontier interview
rounds and fallback briefs, a sufficient-solution ladder, repository audit and
shortcut debt review, report-only stagnation, three-document fidelity and an
advisory consensus panel. These optional references add no executable components.

Version 0.13.29 adds opt-in `mir-content:korean-writing` (authored in Korean) and
`mir-core:app-investigation`, plus Main-directed recovery and product PRD recipes.
Existing skills add relevant diff load/performance/lean checks, learning-safe
per-skill proposals, observed cache diagnostics, artifact-only executability review
and synthetic visual memory cases. These are optional guidance, using existing
authorized tools and preserving metadata profiling and language-policy boundaries.

Version 0.13.30 corrects seven guidance defects and adds bounded pre-spec intent
review, task integration, prototype escape, long-form finishing and reusable style
profiles, consequential-choice memos, approved-spec issue drafts and version-bound
reconstruction proof. AI-readiness review is qualitative; no dashboard is supplied.
All additions remain optional, advisory and Main-directed; no runtime is added.

Version 0.13.31 adds identity-based artifact version comparison and Korean business
and public-document checks, restores the settled-idiom exception, and clarifies
portable provenance, handoff authority, experiment timeouts and verification decisions.
These are guidance-only corrections; no runtime behavior or tools are added.

Version 0.13.32 adds the opt-in, read-only stdio `mir-mcp` package under ADR-91 and
capability-source schema 5. Registration requires explicit MCP selection and a
consumer-owned digest acknowledgement; no default Profile selects it.

Version 0.13.33 fixes `mir-mcp` test portability: tests no longer write bytecode into
plugin trees and no longer assume the system Python lacks `tomllib`. Runtime behavior is
unchanged.

Version 0.13.34 fixes the `mir-mcp` Codex launcher: Codex starts the server from the
installed plugin root (`cwd: "."`) with a relative script path, because it does not expand
`${PLUGIN_ROOT}`. The Claude launcher is unchanged.

Version 0.13.35 applies the consumer-local acknowledgement rule to the `mir-lifecycle-hooks`
package: only the consumer's own capability configuration approves its exact digest, as for
`mir-mcp`. It also lets consumers enrolled with an older `mir-mcp` launcher update again.

Version 0.13.36 lets Codex CLI 0.164 use `mir-mcp`. A legacy `initialize` that requests another
protocol version now negotiates `2025-11-25` instead of being refused, and legacy request
`_meta` such as `progressToken` is treated as request metadata, not as a modern request.

Version 0.13.37 moves every consumer approval into the git-ignored
`<project root>/config/capability-acknowledgements.local.json`; acknowledgements in `capability-sources.json`
no longer approve. `mir-mcp` adds caching hints to modern `tools/list` and `server/discover`
results, gives `isError` results a short text reason, and lets one failed Git query cost only
its own pin. Update the `mir` code before the provider.

Version 0.13.38 republishes 0.13.37, whose release workflow stopped on a README path check
that only a fresh checkout could see. Behavior is unchanged; `v0.13.37` has no release.

Version 0.13.39 refuses repositories inside cloud-synced folders (OneDrive, macOS CloudStorage,
iCloud Drive) with a warning, in both `mir-mcp` and `mir capability`, and keeps every checkout
byte-identical to Git's blobs on all operating systems. It prepares a native Windows lane that
later releases add.

Version 0.13.40 runs the `mir capability` manager, the agent-derivative generator and the
lifecycle hooks natively on Windows (Python generator, owner-only DACL for private state,
Windows-safe transcript reads and timeouts), checked by a Windows CI job.

Version 0.13.41 fixes two Windows consumer sync failures found on a real Windows PC: read-only
Git object files in the export and Codex's `\\?\` marketplace paths.

Version 0.13.42 runs `mir-mcp` natively on Windows x64 (handle-based no-reparse guard, a worker
thread deadline, the fixed Git for Windows binary) and accepts `windows` receipts. Python 3.11 is
the floor for everything launched as `python3`.

Version 0.13.43 carries 0.13.42, which is tagged without a release, and finds Git for Windows
2.56+ at its new `ucrt64` location.

Version 0.13.44 updates a project enrolled by the 0.8.0 provider directly and makes the Windows
handoff hook decode its pin output as UTF-8.

Version 0.13.45 fixes Claude attestation when the Claude config home is a symbolic link.

Version 0.13.46 completes the 0.8.0 migration on Windows: legacy receipts are checked with the
0.8.0 digest rule, and derivative scripts run under Git for Windows Bash.

### Platform use

macOS is the primary central-provider and release-evidence lane. Linux and WSL are separate
compatibility lanes; they use their own runtime homes, caches, trust decisions, receipts, and
storage, and their failure does not invalidate a proven macOS provider. Native Windows x64 is a
separate lane for the `mir capability` consumer flow, the lifecycle hooks and `mir-mcp`; automated
bootstrap is not supported there. A Windows project may give an AI agent the Git repository as a
versioned example, then let that agent select and adapt the needed plugin, skill, agent, command
intent, hook semantics, and structure under the target's own policy and checks.

Cloning or pulling Yoke never installs user-scoped capabilities by itself. The
[Windows and WSL Reference Adaptation](docs/operations/windows-wsl-reference-adaptation.md) guide
lists the non-portable assumptions and provides a bounded prompt for a Windows project agent.

Superseded ADR-82 composition files are preserved under
`reference-templates/advanced-composition/` as non-default, non-executable design references; Mir
Yoke publishes no active `yoke` composer. The remaining source, tools, examples, specifications,
and history are reference or maintainer evidence without an adopter compatibility promise.

## Improve an existing harness

Use the [Harness Engineering Upgrade Guide](docs/operations/harness-engineering-upgrade.md) to
assess repository governance, context and token efficiency, memory, embeddings, agents, skills,
hooks, and Claude/Codex generated parity. It is reference-only: inspect the target, select only the
missing capability, edit target-owned sources, and verify with the target's checks.

The older `docs/harness-engineering/` phase corpus preserves centralization-era design history. It
may name removed tools and is not current operational guidance. Start from ADR-83, ADR-84, current
bluebricks, and the upgrade guide; open historical material only for a specific provenance question.

## Start a new project

Open one explicit empty directory with Claude or Codex and send this short prompt:

```text
[Prepared project purpose and goals]

Harness: https://github.com/youngjin39/mir-yoke

Complete and verify the project-specific harness and Project Agent Kit first.
Initialize a new Git repository and create the verified initial commit.
Do not start development planning or product implementation yet.
```

Replace the bracketed first line with concrete project purpose and goals, or include that material
elsewhere in the same request. Without it, the prompt is incomplete and the agent must ask before
writing. The detailed execution contract lives in the recipe, not in the prompt. The agent must
finish with `READY_FOR_DEVELOPMENT_PLANNING`, a verified project-owned harness and memory baseline,
one clean local commit, and no remote or push. If the target is not empty or is already inside a Git
worktree, use the preservation-first Starter flow instead.

## Use the minimal Starter

For an existing repository, tell the active agent to inspect current instructions, use `starter/`
as reference, merge only missing rules, replace placeholders with observed facts or owner decisions,
and run the target's own smallest relevant verification. Never recursively copy Mir Yoke over
repository-owned instructions.

## Trust boundary

Mir Yoke has no standing behavior that discovers consumers, mutates targets, measures drift,
updates adopters, starts agents, configures Git remotes, commits, pushes, publishes, or sends
messages on their behalf. The Project Agent Kit's local Git actions happen only because the user's
prompt grants the target agent that bounded authority. The optional `mir` CLI acts only when the
user separately invokes it for an explicit target and operation; installing it creates no standing
authority.

## Maintainer checkout

This full repository maintains the starter, recipe, plugins, and reference corpus. It is not a new
project payload.

```bash
uv sync
uv run pytest -q tests/test_project_agent_kit.py tests/test_minimal_starter.py \
  tests/test_public_template_identity.py tests/test_template_asset_classification.py
uv run python scripts/verify_codex_sync.py
uv run python scripts/verify_plugin_cli_activation.py
uv run ruff check
```

ADR-83 owns the supported-surface and Project Agent Kit boundary. ADR-84 owns the current harness
upgrade and runtime-hygiene guidance. ADR-81 continues to own the four-file minimum Starter, while
ADR-74 governs the explicitly invoked CLI and required-memory implementation retained from v0.8.
ADR-79 separates the primary macOS lane, Linux/WSL compatibility lanes, and native Windows
reference adaptation.

## License

MIT — see [`LICENSE`](LICENSE).

### Source-backed memory relations

Version 0.10.0 supports explicit `memory_relations` declarations through the existing authorized
`mir memory ingest-md` writer and bounded read-only `mir relations query|bundle --memory` retrieval.
The adapter reuses entity-object facts and provenance; it does not infer edges from prose or vectors.
See the [memory relation reference](plugins/mir-core/skills/selective-relations/references/memory-relations.md)
for the opt-in source format, update lifecycle, supported predicates and read-only limits.

SRR 0.10.1 returns compact, source-backed summaries, authored relationship reasons and source
locations. Agents can select the relevant original span when needed. Full source bodies remain
inside bounded validation and are not included in retrieval output. Select the supported provider
writer explicitly if the repository also has an older local Mir package.

SRR 0.10.2 resolves the requested memory anchor and selects its purpose-specific neighborhood in SQL
before validating source evidence. Disconnected relation growth does not consume that query's
candidate/source budget. Ordinary memory search and body retrieval remain unchanged.


SRR 0.10.3 focuses routine skill selection on implementation, verification and direct dependencies
from known anchors. Omitted dependency depth is one hop in both adapters and in mixed bundles;
explicit depth remains available. Broader impact traversal is reserved for explicit requests.
Ordinary memory/body retrieval is unchanged; fewer relation calls do not guarantee fewer tokens.

SRR 0.10.4 requires a delivery-selected provider and explicit target root for portable examples.
It does not upgrade repository-local consoles, install providers, or change memory ownership.
