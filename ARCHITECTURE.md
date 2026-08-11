# Mir Yoke Supported-Surface Architecture

## Product boundary

Mir Yoke is a public template, agent-guided recipe, portable plugin provider, and reference corpus.
It is not a universal installer, target composer, runtime, service, or control plane. It has no
provider runtime and no standing authority over consumer repositories.

`starter/` is the only supported consumer payload. The Project Agent Kit recipe is guidance read by
the target's active AI; it never becomes a provider-side target writer.

## Supported flows

### Minimal adoption

1. The active AI inspects an existing target and its instructions without mutation.
2. It identifies purpose, paths, authority, protected surfaces, and real checks.
3. It merges, renames, or skips Starter material without overwriting repository-owned work.
4. It verifies the local diff with the target's own checks.

### New Project Agent Kit

1. The target AI proves one explicit target is empty and outside an existing Git worktree.
2. It reads the published recipe and Mir Yoke revision as read-only reference.
3. It creates project-owned intent, harness, runtime entrypoints, reviewer sources, generated Codex
   parity, a machine-readable toolchain foundation, and real lint/build/test verification.
4. It initializes Git locally only after verification, installs the tracked pre-commit hook, and
   creates one verified initial commit.
5. It stops before product planning or implementation.

The target agent owns every write. Mir Yoke stores no target path, plan, receipt, or adopter state.

## Modules

- **Starter** — `starter/` provides the four-file minimum contract.
- **Recipe** — `recipes/project-agent-kit/` defines the greenfield user journey and gates.
- **Plugin provider** — `plugins/` and marketplace manifests publish optional host capabilities.
- **Maintenance** — tests, classification, sanitization, generated checks, and the clean-room
  observer validate Mir Yoke without becoming a target installer.
- **Reference corpus** — retained source, tools, examples, specifications, and history remain
  inspectable without consumer support claims.

Dependencies point from the recipe to Starter concepts and portable plugin interfaces. No plugin,
maintainer CLI, reference implementation, or historical decision can become a target prerequisite
by presence alone.

## Source of truth and generation

Mir Yoke authors its root contract in `CLAUDE.md` and regenerates `AGENTS.md` and Codex surfaces.
The Project Agent Kit establishes an equivalent one-way Claude-to-Codex generator inside each new
target for repository-unique reviewer surfaces. Generated files are checked, never hand-edited.

## Data and deployment

The Starter and recipe store no provider runtime data and have no deployment topology. Optional
plugins are installed into an agent host. Generated targets are independent repositories; source
revision is provenance only, and template version lag is not drift.

## Verification

`tests/test_project_agent_kit.py` pins prompt routing, target ownership, reviewer, pre-commit, Git,
and no-composer boundaries. `tests/test_minimal_starter.py` pins the four-file core. Plugin tests,
classification, sanitization, generated parity, Ruff, and the full regression protect shared and
release-sensitive surfaces. The tag gate additionally requires separately observed Claude and Codex
target bundles with sanitized public evidence.
