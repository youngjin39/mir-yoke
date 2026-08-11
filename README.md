# Mir Yoke

**A four-file compatibility starter, standard Project Agent Kit, and optional public Mir CLI.**

Mir Yoke is a public template and reference repository, not an agent runtime, service, or control
plane. It is not a universal installer and has no standing authority over a repository that reads
or adopts its material. The active AI agent owns the target session, inspects the real target, and
writes only under the user's target-specific authorization.

## Supported layers

### 1. Minimal Starter compatibility

[`starter/`](starter/) is the only fixed consumer payload. It contains exactly four Markdown
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
Install it outside a target checkout from an immutable release:

```bash
uv tool install --force --link-mode copy \
  "git+https://github.com/youngjin39/mir-yoke.git@v0.9.0"
mir --help
```

Installation grants no repository authority. A state-changing command may act only after the user
names the target and operation; read-only inspection remains read-only, and the Project Agent Kit
does not depend on this host-global installation or vendor its source.

### Optional plugins and inert references

[`plugins/`](plugins/) publishes optional, namespaced host capabilities for Claude and Codex. A
plugin is installed explicitly in the agent host; it is not copied into a target or treated as a
readiness requirement. Superseded ADR-82 composition files are preserved under
`reference-templates/advanced-composition/` as non-default, non-executable design references; Mir
Yoke publishes no active `yoke` composer. The remaining source, tools, examples, specifications,
and history are reference or maintainer evidence without an adopter compatibility promise.

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
uv run ruff check
```

ADR-83 owns the current supported-surface and Project Agent Kit boundary. ADR-81 continues to own
the four-file minimum Starter, while ADR-74 governs the explicitly invoked CLI and required-memory
implementation retained from v0.8.

## License

MIT — see [`LICENSE`](LICENSE).
