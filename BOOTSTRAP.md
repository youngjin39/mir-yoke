# Bootstrap — turn this template into a project

Mir Yoke provides a minimum harness-engineering baseline for code and non-code repositories. The
active AI agent first reads the target's current state and local contract, then adapts only the
applicable template assets. The first product request may be prose, fiction, analysis,
infrastructure, or application code; project architecture and memory are initialized before
normal work begins.

## Adopter payload boundary — blocking

A raw Mir Yoke clone begins as provider and maintainer source. Greenfield bootstrap is responsible
for converting that exact release tree into a slim product-adopter payload, but only as the last
successful action of Phase 2 finalize. Phase 1 first installs a copied Mir CLI outside the project,
writes the product Profile, rewrites exact release-matched provider contracts and task state,
installs the exact commit from the tracked `.mir/capability-lock.json` under a project-specific
runtime namespace, binds that source and executable in the machine-local receipt, installs
capabilities, records a deterministic manifest of the installed Python runtime closure, and records
`restart_required`; it removes nothing. Setup and startup reject dependency, executable-mode, or
symlink drift even if the small launcher file itself is unchanged.

Provider maintainers can inspect the pre-bootstrap boundary with:

```bash
uv run python -m tools.harness_consistency run
```

`R20 adopter_payload_boundary` is expected between greenfield Phase 1 and Phase 2. It remains a
blocking error for product work. Do not delete paths manually: finalize uses the release's
hash-bound adopter payload manifest, refuses modified or unlisted files inside provider roots,
moves eligible files into an ignored recovery quarantine, and restores them if a concurrent path
change, post-slim external CLI check, capability verification, or ready-receipt publication fails.
An fsynced `.mir/slim-transaction.json` journal makes the next bootstrap restore or finish any
interrupted finalization before starting another transaction.

The safe states are:

- a Mir Yoke maintainer checkout with the canonical `mir-yoke/public_harness_template` identity;
- a product repository containing only its locally owned contract and explicitly selected adopter
  assets; or
- an existing repository being assessed read-only before any selected adoption.

A product identity mixed with the full provider tree is not ready. A successful greenfield final
receipt must record `slim.status` as `applied` or `already_slim`, identify the external CLI, and
leave no configured provider marker. Existing-repository adoption remains a separate
preservation-first path and never invokes this removal transaction.

## Prerequisites

- Git, Python 3.12+, `uv`, and `jq` (hook JSON parsing).
- Claude Code and Codex CLI on `PATH` for the supported dual-runtime ready state.
- macOS, Linux, or WSL with Bash for the supported automated bootstrap and ready receipt.
- Native Windows is guidance-only. Run automation inside WSL, or let the agent use this repository
  as a non-ready reference while preserving the target repository's own contract.
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

Open the intended product repository in Claude Code or Codex CLI and ask:

> Read `BOOTSTRAP.md`, verify the adopter payload boundary, and initialize this repository as a
> `<profile>` project for `<purpose>` without importing Mir Yoke provider or maintainer sources.

The agent must confirm the slug, profile, purpose, primary stack, and payload disposition. It must
not remove dependency-coupled provider paths, import maintainer history, or enable a vector service
without explicit approval.

Before setup, detach the product's push path from the provider. Keep the provider as a fetch-only
reference if useful, then optionally add the product-owned remote:

```bash
git remote rename origin mir-yoke-upstream
git remote set-url --push mir-yoke-upstream DISABLED
# Optional after creating the product repository on your Git host:
git remote add origin <product-repository-url>
```

Setup checks every effective push URL before installing or writing anything. It never changes
remotes, commits, pushes, or rewrites history for you. No `origin` means an explicit local-only
baseline and is accepted until the owner adds a product remote.

### Phase 1 — install the pinned baseline

macOS, Linux, or WSL:

```bash
./setup.sh --slug my-project --profile code_app \
  --purpose "Build a portable project service." \
  --stack python --stack sqlite
```

Native Windows PowerShell does not bootstrap the repository:

```powershell
.\setup.ps1
```

The command exits before mutation and directs you to open the repository in WSL. An agent may
instead adapt individual controls as reference material after inspecting the target's existing
instructions and boundaries, but that manual path does not produce a Mir Yoke `ready` receipt.

`--profile` has no default. Phase 1 also requires a single-line, non-placeholder `--purpose` and
at least one `--stack` value. Bootstrap writes those values into the canonical repository profile;
finalize refuses an empty or placeholder identity.

For a content workspace, classify each discovered pre-existing record root or file. Bootstrap
records its path, format set, document count, and a deterministic search acceptance query:

```bash
./setup.sh --slug career-harness --profile content_workspace \
  --purpose "Organize career transitions and application evidence." \
  --stack markdown --stack sqlite \
  --archive applications=career-records \
  --archive interviews=interview-notes.md
```

`config/content-onboarding.json` is the tracked classification manifest. Custom top-level record
content blocks Phase 1 until covered by a `CLASSIFICATION=PATH` input. UTF-8 text formats (`md`,
`txt`, `rst`, `json`, `yaml`, `toml`, or `csv`) are indexed directly. PDF, office, and similar
formats are still discovered and reported, but require a tracked UTF-8 text projection before they
can satisfy memory acceptance. Harness-owned template paths are excluded from this discovery scan.

### External-first storage (recommended when internal SSD capacity is constrained)

Keep the repository itself on the external volume, then give setup one shared machine-storage
root on that same volume. On this Mac, for example:

```bash
./setup.sh \
  --storage-root "/path/to/external-volume/.mir-runtime" \
  --slug my-project \
  --profile code_app \
  --purpose "Build a portable project service." \
  --stack python
```

On another machine, choose that host's external volume instead of copying the Mac path. On a
Windows host, run the Linux command inside WSL and use a WSL-visible mount such as
`/mnt/e/.mir-runtime`; native PowerShell is not a supported storage/bootstrap path.

This keeps each repository's `.venv` and `.mir/memory.db` beside the project. The uv cache,
uv-managed Python installations, and Mir global capability provider are shared under the external
storage root; each repository's uv tool and bin directories live under a distinct
`mir/cli/<runtime-id>/` namespace. Bootstrap verifies that the cache root and project are on the
same filesystem, allowing uv to use its native clone/link mode instead of duplicating full package
files.

`--storage-root` configures the setup process. For later direct `uv` commands, persist the same
values in the host's shell or user environment:

```bash
export MIR_STORAGE_ROOT="/path/to/external-volume/.mir-runtime"
export UV_CACHE_DIR="$MIR_STORAGE_ROOT/uv/cache"
export UV_PYTHON_INSTALL_DIR="$MIR_STORAGE_ROOT/uv/python"
export MIR_CAPABILITY_HOME="$MIR_STORAGE_ROOT/mir/capabilities"
```

Do not set one shared `UV_TOOL_DIR` or `UV_TOOL_BIN_DIR`; `setup.sh` derives both from the canonical
project path and locked provider source so one project cannot replace another project's Mir CLI.

Use a stable volume name and APFS on macOS. Small launchers, runtime registry metadata, and
credentials remain in the user home. Do not move the entire Claude or Codex home because those
directories may contain credentials. A user-home symlink may be used as a machine-specific
entrypoint, but the template never commits symlinks or uses them to distribute skills/plugins.

The supported Unix wrapper configures any requested storage root, installs Mir from the exact
HTTPS commit in `.mir/capability-lock.json` into a copied, project-specific `uv tool` environment,
applies the production pins in `config/cli-runtime-constraints.txt`, then invokes the Python
coordinator through that external executable. It never installs dirty working-tree code.
The coordinator:

1. validates hooks, permissions, orchestration policy, local agent surfaces, and the selected pack;
2. creates a required local SQLite+FTS5 memory index, onboards classified records, and proves that
   each project-specific acceptance query returns its expected path;
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

The pass must leave `spec/STATE.md`, `spec/index.yaml`, `spec/graph.yaml`, `spec/gaps.yaml`, and
`spec/bootstrap-evidence.json`. Non-empty files are not sufficient: the evidence must report all
four requirement layers, AI-ready counts, zero open gaps, and the final project review:

```json
{
  "schema_version": 2,
  "sequence": ["mir-core:design", "mir-core:spec-architect"],
  "capability_commit": "<commit from .mir/capability-lock.json>",
  "outputs": ["spec/STATE.md", "spec/index.yaml", "spec/graph.yaml", "spec/gaps.yaml"],
  "coverage": {
    "l1": {"total": 1, "filled": 1, "derived": 0, "na": 0, "tbd": 0},
    "l2": {"total": 1, "filled": 1, "derived": 0, "na": 0, "tbd": 0},
    "l3": {"total": 9, "filled": 9, "derived": 0, "na": 0, "tbd": 0},
    "l4": {"total": 10, "filled": 10, "derived": 0, "na": 0, "tbd": 0},
    "ai_ready": {"ready": 1, "incomplete": 0, "blocked": 0}
  },
  "open_gaps": 0,
  "full_review": {
    "project_structure": "pass",
    "memory": "pass",
    "discoverability": "pass",
    "requirements": "pass",
    "organization": "pass"
  }
}
```

Layer 3 uses all 9 system slots and Layer 4 uses all 10 operation slots. Counts must add up, every
`tbd`/incomplete/blocked count must be zero, `spec/gaps.yaml` must contain a `gaps` list with no open
entry, and required outputs must not contain placeholder markers. The boolean finalize flag is only
an operator attestation; it cannot substitute for this evidence.

After completing the two skills, attest and finalize:

```bash
./setup.sh --profile code_app --finalize --architecture-initialized
```

On Windows hosts, run the same `./setup.sh` finalize command inside WSL. Native PowerShell does not
run Phase 2 and cannot publish a ready receipt.

Finalize verifies the installed plugin paths and hashes reported by both CLIs, architecture
coverage/gaps, the full-review result, project-specific memory search, output hashes, and the prior
restart receipt. It then performs the adopter slim transaction as the final mutation: exact
unchanged provider files are moved to `.mir/slim-quarantine/<transaction>/`, empty provider
directories are pruned, the external CLI runs capability status from the resulting tree, and the
ready receipt records the CLI and slim report. The durable journal is committed only after that
receipt is atomically published; publication failure restores the moved files and preserves the
prior receipt. On restart, an interrupted transaction is recovered before any new move. Only then
may the receipt become `status: ready`.

Until that ready receipt exists, SessionStart identifies the incomplete state and PreToolUse blocks
normal mutations. Setup/adoption validation, read-only inspection, and scoped Phase 2 evidence
edits remain allowed; arbitrary test and lint runners remain blocked because their options or
inputs can execute code or write outside the bootstrap evidence boundary. This gate applies even
when the first request is prose or document organization.

## Existing repository adoption

Do not run the greenfield coordinator over an established repository. Preserve its authored
profile, hook layout, archive slugs, memory database, and native specification system. Add the
tracked `config/bootstrap-adoption.json` manifest described by
`docs/templates/_schema/bootstrap-adoption.schema.json`, then check it without writing:

```bash
./scripts/mir.sh bootstrap-adoption --project-root . --json
```

After the read-only report is ready, write only the machine-local receipt:

```bash
./scripts/mir.sh bootstrap-adoption --project-root . --apply --json
```

The manifest must name all seven surfaces. Use `repository_owned` for native mechanisms that pass
the same live checks. Use `exception` only with a concrete reason, blockers, and existing
evidence; exceptions remain visible in a ready receipt so they cannot masquerade as completed
implementation. Non-content repositories may mark only `content_onboarding` as
`not_applicable`. The command never installs hooks, reclassifies content, rebuilds memory, or
rewrites native spec artifacts. ADR-77 records the preservation and exception semantics.

For an applied or repository-owned Phase 2 surface, `native_evidence` maps the manifest to the
repository's YAML coverage metadata, gap list, and five-dimension review record. The adoption
command parses those native files and requires their counts and results to match the manifest;
copying passing numbers into the manifest is not sufficient. Every review dimension records
`status: pass`, one or more tracked `evidence_paths`, and a concrete `verification` observation;
those paths must also be declared as Phase 2 evidence and are hash-bound into the receipt.

If assessment finds Mir Yoke provider or maintainer markers in a product repository, classify the
state as over-included and keep the assessment read-only. Do not continue product implementation or
remove the markers until setup, CLI, hook, and import dependencies have been traced and externalized.

The ready receipt is valid only while its source commit, manifest hash, complete declared evidence
path set, and every evidence hash still match the working tree. Any drift closes the startup gate
until `mir bootstrap-adoption --apply` revalidates the repository. While closed, the shell route is
fail-closed: only a single recognized setup, adoption, or read-only inspection command,
an exact `apply_patch` heredoc limited to declared bootstrap evidence, or
`git add -- <one-declared-evidence-file>` is allowed. The scoped staging command accepts only a
current regular file with no shell expansion syntax, so a new adoption can make required evidence
Git-tracked without opening broader mutation, recursive-directory, deletion, or pathspec access.

## Required memory contract

Every ready project has at least one real memory backend. The default is local SQLite+FTS5; it does
not require an embedding server or `sqlite-vec`.

- Tracked authored content selected by `config/content-onboarding.json`, plus harness Markdown under
  `docs/`, `tasks/`, and `.ai-harness/`, is the durable cross-machine source of truth.
- `.mir/memory.db` is a required machine-local query index and is rebuilt on a new computer.
- `docs/memory-map.md` and `tasks/lessons.md` contain generated projections; do not hand-edit their
  generated regions.
- The post-edit hook re-indexes relevant durable Markdown edits after bootstrap.
- Every Python-based hook uses `.claude/hooks/_lib/run-python.sh`, which selects the project venv or
  `uv run`; hooks never fall back to the host `python3`.
- A shared network database/vector service is not included. Repositories may share tracked
  archives or an explicitly configured embedding endpoint.

Verify at any time:

```bash
./scripts/mir.sh memory doctor --project-root . --json
./scripts/mir.sh context pull "<query>"
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
./scripts/mir.sh capability status --project-root . --json   # local, no network mutation
./scripts/mir.sh capability check --project-root . --json    # remote comparison, read-only
./scripts/mir.sh capability update --project-root . --json   # proposed update, dry-run
./scripts/mir.sh capability update --project-root . --apply --json
```

Only the final command changes the pin and active provider. It rejects credential-bearing URLs,
path traversal, symlinks, submodules, executable remote content, local agent divergence, and a
plugin digest that conflicts with another registered project. Hooks, permissions, MCP servers, and
orchestration policy are never imported from the remote capability source.

## Completion checklist

- `.mir/bootstrap-receipt.json` says `ready`.
- The receipt records an external `cli.executable` and `slim.status` is `applied` or
  `already_slim`; no R20 provider marker remains.
- `./scripts/mir.sh memory doctor --project-root . --json` succeeds with indexed documents and an FTS
  probe.
- `./scripts/mir.sh capability status --project-root . --json` says `ready: true` and reports both
  runtimes active at the pinned hashes.
- `uv run python scripts/verify_repo_agent_management.py` succeeds.
- `uv run python scripts/verify_codex_sync.py` succeeds.
- There are no tracked symlinks.
- On a Windows host, bootstrap and hook checks ran inside WSL; native PowerShell did not claim a
  ready receipt.

Do not commit or push unless the operator asks.
