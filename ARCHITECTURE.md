# Mir Yoke Supported-Surface Architecture

## Product boundary

Mir Yoke is the Harness-managed central capability supply system for independently owned
repositories. It versions and distributes generic sources through a public template, agent-guided
recipe, optional installed CLI, portable plugin provider, and reference corpus. Mir Harness owns
management direction, reuse decisions, verification, and authorized delivery coordination. Yoke is
not a universal installer, target composer, agent runtime, service, or control plane; it has no
provider runtime and no standing authority over consumer repositories. Consumers retain their
goals, data, local policy, adapters, and execution.

`starter/` is the only fixed consumer payload. The Project Agent Kit recipe is guidance read by the
target's active AI; it never becomes a provider-side target writer. The installed `mir` CLI is a
separate operator-selected surface and never becomes an implicit recipe dependency.

## Supported flows

### Minimal adoption

1. The active AI inspects an existing target and its instructions without mutation.
2. It identifies purpose, paths, authority, protected surfaces, and real checks.
3. It merges, renames, or skips Starter material without overwriting repository-owned work.
4. It verifies the local diff with the target's own checks.

### New Project Agent Kit

1. The target AI proves one explicit target is empty and outside an existing Git worktree.
2. It reads the published recipe and Mir Yoke revision as read-only reference.
3. It creates project-owned intent, a bounded common harness, required local SQLite+FTS5 memory,
   runtime entrypoints, reviewer sources, generated Codex parity, a machine-readable toolchain
   foundation, and real lint/build/test verification.
4. It initializes Git locally only after verification, installs the tracked pre-commit hook, and
   creates one verified initial commit.
5. It stops before product planning or implementation.

The target agent owns every write. The generated repository owns its harness, tracked durable
memory sources, and rebuildable local database. It receives no copy of the Mir package or CLI
source. Its thin project-owned wrapper executes the exact recorded provider revision with all
runtime state confined below ignored `.mir/`. Mir Yoke stores no target path, plan, receipt, or
adopter state for this recipe.

### Optional installed CLI

An owner may separately install the v0.8-compatible public `mir` command set from an immutable
release. This host-global operator tool is distinct from the Kit's thin revision-pinned wrapper.
It supplies explicit bootstrap, memory, capability, context, execution, hook, and verification
operations. Installation is not authorization: read-only commands remain read-only, and every
mutation requires the user's explicit target and operation. The CLI starts no standing provider
process and exposes no `yoke` composer.

## Modules

- **Starter** — `starter/` provides the four-file minimum contract.
- **Recipe** — `recipes/project-agent-kit/` defines the greenfield user journey and gates.
- **Optional CLI** — `src/mir/` supplies the installed v0.8-compatible operator surface without
  becoming a Project Agent Kit payload.
- **Plugin provider** — `plugins/` and marketplace manifests publish three role-oriented,
  skills-only packages plus the exact read-only `mir-lifecycle-hooks` package. All four are shared
  by Claude and Codex. Project-coupled hooks still require repository-owned adapters. No MCP server
  or MCP plugin currently exists.
- **Capability management** — `config/capability-sources.json` selects commit-pinned plugins,
  project agent sources, Claude command sources with Codex skill equivalents, and target-local hook
  and MCP integration boundaries. Explicit sync copies and locks only selected agents and commands;
  it never copies target hook or MCP policy.
- **User runtime distribution** — `scripts/install_user_runtime_agents.py` separately installs the
  reviewed agent and Claude-command allowlists into explicitly named user homes. It defaults to a
  dry run, refuses unmanaged divergence, and records exact source and target digests. Repository
  definitions retain precedence.
- **Upgrade guide** — `docs/operations/harness-engineering-upgrade.md` routes existing repositories
  through selective, target-owned harness improvements without creating another payload.
- **Maintenance** — tests, classification, sanitization, generated checks, and the clean-room
  observer validate Mir Yoke without becoming a target installer.
- **Reference corpus** — retained source, tools, examples, specifications, history, and the inert
  ADR-82 advanced-composition templates remain inspectable without active-command claims. The
  centralization-era harness phase corpus is historical and not current operational guidance.

Dependencies point from the recipe to Starter concepts and its project-owned common harness and
memory contract. No plugin, installed CLI, reference implementation, or historical decision can
become a target prerequisite by presence alone.

## Source of truth and generation

Mir Yoke authors its root contract in `CLAUDE.md` and regenerates `AGENTS.md` and Codex surfaces.
Agents use Claude Markdown as their source and generated Codex TOML as their projection. They may
be delivered as project files by capability sync or as separate user-level files by the explicit
runtime installer. Claude commands use the same two delivery scopes, while Codex resolves each
mapped workflow through an existing namespaced plugin skill instead of a duplicate command wrapper.
The Project Agent Kit establishes an equivalent one-way Claude-to-Codex generator inside each new
target for repository-unique reviewer surfaces. Generated files are checked, never hand-edited.

## Data and deployment

The Starter stores no runtime data. A Project Agent Kit target owns tracked durable memory sources
and a rebuildable local SQLite+FTS5 database; these are target data, not provider state. Optional
plugins and the CLI are installed into the operator's host. Generated targets are independent
repositories; source revision is provenance only, and template version lag is not drift.

## Verification

`tests/test_project_agent_kit.py` pins prompt routing, target ownership, common harness, required
memory, reviewer, pre-commit, Git, and no-composer boundaries. `tests/test_minimal_starter.py` pins
the four-file core, and `tests/test_installed_cli.py` proves the CLI runs outside the source tree.
Plugin tests, classification, sanitization, generated parity, Ruff, and the full regression protect
shared and release-sensitive surfaces. The real-CLI plugin probe also validates identical installed
plugin and skill digests from two non-provider working directories. Tag validation does not claim a generated-repository runtime
run; after publication, the owner performs separate Claude and Codex acceptance and may validate
the resulting bounded evidence with the retained verifier.
