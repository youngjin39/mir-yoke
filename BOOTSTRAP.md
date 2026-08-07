# Bootstrap — turn this template into a project

Mir Yoke starts code and non-code repositories with the same minimum harness. The first product
request may be prose, fiction, analysis, infrastructure, or application code; project architecture
and memory are initialized before normal work begins.

## Prerequisites

- Git, Python 3.12+, and `uv`.
- Claude Code and Codex CLI on `PATH` for the supported dual-runtime ready state.
- macOS/Linux/WSL: Bash. Native Windows: PowerShell plus Git Bash or WSL Bash on `PATH`, because
  hook scripts use Bash.
- Authenticated Claude Code and Codex CLI sessions.

Codex IDE extensions do not expose this plugin marketplace contract and are not part of the ready
claim. They can still read the project-local agents and instruction files.

## Profiles

Choose exactly one profile. Each profile receives `mir-core`, which contains `design` and
`spec-architect`; the optional plugin and local agent packs differ.

| Profile | Shared plugins | Intended use |
|---|---|---|
| `code_app` | `mir-core`, `mir-code` | applications and services |
| `infra_runtime` | `mir-core`, `mir-code` | infrastructure, runtimes, libraries |
| `hybrid_pipeline` | `mir-core`, `mir-code`, `mir-content` | data/ML and mixed pipelines |
| `content_workspace` | `mir-core`, `mir-content` | prose, research, knowledge, content |

## Agent-guided setup

Open the clone in Claude Code or Codex CLI and ask:

> Read `BOOTSTRAP.md` and initialize this repository as a `<profile>` project for `<purpose>`.

The agent must confirm the slug, profile, purpose, and primary stack. It must not remove template
history or enable a vector service without explicit approval.

### Phase 1 — install the pinned baseline

macOS, Linux, or WSL:

```bash
./setup.sh --slug my-project --profile code_app
```

Native Windows PowerShell:

```powershell
.\setup.ps1 -Slug my-project -Profile code_app
```

### External-first storage (recommended when internal SSD capacity is constrained)

Keep the repository itself on the external volume, then give setup one shared machine-storage
root on that same volume. On this Mac, for example:

```bash
./setup.sh \
  --storage-root "/Volumes/T7 Shield/.mir-runtime" \
  --slug my-project \
  --profile code_app
```

On another machine, choose that host's external volume instead of copying the Mac path. Native
Windows example:

```powershell
.\setup.ps1 -StorageRoot "E:\.mir-runtime" -Slug my-project -Profile code_app
```

This keeps each repository's `.venv` and `.mir/memory.db` beside the project, while the shared uv
cache, uv-managed Python installations, uv tool environments, and Mir global capability provider
live under the external storage root. Bootstrap verifies that the cache root and project are on the
same filesystem, allowing uv to use its native clone/link mode instead of duplicating full package
files.

`--storage-root` configures the setup process. For later direct `uv` commands, persist the same
values in the host's shell or user environment:

```bash
export MIR_STORAGE_ROOT="/Volumes/T7 Shield/.mir-runtime"
export UV_CACHE_DIR="$MIR_STORAGE_ROOT/uv/cache"
export UV_PYTHON_INSTALL_DIR="$MIR_STORAGE_ROOT/uv/python"
export UV_TOOL_DIR="$MIR_STORAGE_ROOT/uv/tools"
export MIR_CAPABILITY_HOME="$MIR_STORAGE_ROOT/mir/capabilities"
```

Use a stable volume name and APFS on macOS. Small launchers, runtime registry metadata, and
credentials remain in the user home. Do not move the entire Claude or Codex home because those
directories may contain credentials. A user-home symlink may be used as a machine-specific
entrypoint, but the template never commits symlinks or uses them to distribute skills/plugins.

The wrapper configures any requested storage root before it runs `uv sync`, then invokes the
cross-platform Python coordinator. The coordinator:

1. validates hooks, permissions, orchestration policy, local agent surfaces, and the selected pack;
2. creates a required local SQLite+FTS5 memory index and indexes tracked Markdown;
3. fetches the trusted Git capability source, validates only allowlisted plugins and agents, pins
   their commit and hashes, and refuses duplicate standalone skill providers;
4. registers and installs the selected global plugins in Claude Code and Codex CLI; and
5. writes `.mir/bootstrap-receipt.json` with `status: restart_required`.

Common skills are not copied to `.claude/skills` or `.agents/skills`. Their runtime names are
namespaced, such as `mir-core:spec-architect`, so one managed global provider serves every project
without a same-name project copy. Project-specific skills are allowed only under distinct names.

If setup reports an existing standalone collision, move, rename, or deliberately remove that old
provider and rerun. Setup never deletes it automatically.

### Phase 2 — restart, initialize architecture, finalize

Reload Claude Code and begin a new Codex session. In that new session, explicitly run:

1. `mir-core:design` to settle the initial project boundaries;
2. `mir-core:spec-architect` to create or validate the initial implementable spec structure.

This initial structure pass is mandatory even when the first product request is prose. It does not
mean that every later prose edit must invoke `spec-architect`.

The pass must leave non-empty `spec/STATE.md`, `spec/index.yaml`, and `spec/graph.yaml`, plus
`spec/bootstrap-evidence.json`:

```json
{
  "schema_version": 1,
  "sequence": ["mir-core:design", "mir-core:spec-architect"],
  "capability_commit": "<commit from .mir/capability-lock.json>",
  "outputs": ["spec/STATE.md", "spec/index.yaml", "spec/graph.yaml"]
}
```

The boolean finalize flag is only an operator attestation; it cannot substitute for these pinned,
non-empty outputs.

After completing the two skills, attest and finalize:

```bash
./setup.sh --profile code_app --finalize --architecture-initialized
```

```powershell
.\setup.ps1 -Profile code_app -Finalize -ArchitectureInitialized
```

Finalize verifies the installed plugin paths and hashes reported by both CLIs, the architecture
evidence and output hashes, memory readiness, and the prior restart receipt. Only then may the
receipt become `status: ready`.

## Required memory contract

Every ready project has at least one real memory backend. The default is local SQLite+FTS5; it does
not require an embedding server or `sqlite-vec`.

- Tracked authored Markdown under `docs/`, `tasks/`, and `.ai-harness/` is the durable,
  cross-machine source of truth.
- `.mir/memory.db` is a required machine-local query index and is rebuilt on a new computer.
- `docs/memory-map.md` and `tasks/lessons.md` contain generated projections; do not hand-edit their
  generated regions.
- The post-edit hook re-indexes relevant durable Markdown edits after bootstrap.
- A shared network database/vector service is not included. Repositories may share tracked
  archives or an explicitly configured embedding endpoint.

Verify at any time:

```bash
uv run mir memory doctor --project-root . --json
uv run mir context pull "<query>"
```

Vector modes in `harness_a.toml` are `off` (default), `optional`, and `required`. Enabling a model or
server is an explicit operator choice. Required mode blocks readiness unless endpoint validation
and complete vector coverage both pass.

## Capability source and later updates

`config/capability-sources.json` remembers the trusted Git URL, discovery branch, plugins, agent
allowlist, and profile packs. `.mir/capability-lock.json` pins the exact commit and artifact hashes.
When requirements, agents, or skills change, the repository instructions require the agent to run
a read-only check before proposing an update:

```bash
uv run mir capability status --project-root . --json   # local, no network mutation
uv run mir capability check --project-root . --json    # remote comparison, read-only
uv run mir capability update --project-root . --json   # proposed update, dry-run
uv run mir capability update --project-root . --apply --json
```

Only the final command changes the pin and active provider. It rejects credential-bearing URLs,
path traversal, symlinks, submodules, executable remote content, local agent divergence, and a
plugin digest that conflicts with another registered project. Hooks, permissions, MCP servers, and
orchestration policy are never imported from the remote capability source.

## Completion checklist

- `.mir/bootstrap-receipt.json` says `ready`.
- `uv run mir memory doctor --project-root . --json` succeeds with indexed documents and an FTS
  probe.
- `uv run mir capability status --project-root . --json` says `ready: true` and reports both
  runtimes active at the pinned hashes.
- `python3 scripts/verify_repo_agent_management.py` succeeds.
- `python3 scripts/verify_codex_sync.py` succeeds.
- There are no tracked symlinks.
- On Windows, Git Bash/WSL Bash is present and the hook syntax smoke check succeeds.

Do not commit or push unless the operator asks.
