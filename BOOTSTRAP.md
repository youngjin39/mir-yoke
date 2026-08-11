# Bootstrap and Adoption Layers

Mir Yoke provides three separate entrypoints. None grants standing provider authority, and the
minimum compatibility path does not require a specification tree merely to begin.

## Existing repository: Minimal Starter

Use `starter/` as reference material. The active agent first records the target root, Git status,
existing instructions, purpose, stack, generated and protected paths, external boundaries, and real
verification commands. Preserve repository-owned files and merge only missing rules.

The Starter adoption is complete when the local contract describes the actual project, no
placeholder remains, every named path and command is real or explicitly absent, the selected check
passes, and the final diff contains only the accepted harness changes.

## Empty repository: Standard Project Agent Kit

For one explicit empty directory, use the short prompt in the root README. The active agent reads
[`recipes/project-agent-kit/`](recipes/project-agent-kit/) and creates a purpose-specific agent
foundation. The supported outcome includes:

- preserved project intent and a local harness contract;
- a bounded project-owned common harness and required SQLite+FTS5 memory baseline;
- Claude and Codex entrypoints;
- a repository-unique code-review skill and read-only reviewer;
- generated Claude-to-Codex parity;
- real lint, build, and test commands behind a tracked Git pre-commit hook; and
- one verified local initial commit with no remote or push.

The generated repository owns its durable memory sources and rebuildable local database. The agent
must not copy `src/mir/`, the installed `mir` package, or provider Git history into the target. It
does create the project-owned thin `scripts/mir.sh` wrapper that executes the exact observed
provider revision with runtime state confined below ignored `.mir/`. A host-global CLI installation
is not required to complete the standard Kit.

The agent stops at `READY_FOR_DEVELOPMENT_PLANNING`. The recipe does not authorize a development
plan, product feature, API, UI, deployment, remote, push, or release.

## Explicit automation: Optional installed CLI

Owners who need the retained v0.8 automation may install the v0.9 release as a copied `uv tool` and
invoke `mir` for one named local target. This is a separate opt-in path, not a Project Agent Kit
implementation detail. Installation alone authorizes nothing; state-changing commands require the
current user's explicit target and operation, and Git, credential, external-write, or protected
scope remains separately controlled.

The installed CLI exposes no active `yoke` composer. Superseded composition sources under
`reference-templates/advanced-composition/` are read-only design references and cannot be treated
as commands, payloads, or readiness requirements.

## Unsupported target state

Do not run the Project Agent Kit flow when the target contains files, is inside another Git
worktree, lacks required Git identity or toolchain, or contains a consequential unresolved product
decision. Use Starter comparison for an existing repository or return the exact blocker before
mutation.

Do not silently switch between these layers. Existing repositories use Starter comparison unless
the owner explicitly asks for a bounded CLI operation; empty repositories use the standard Project
Agent Kit unless the owner explicitly selects installed-CLI automation. Missing prerequisites are
reported before mutation.
