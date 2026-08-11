# Mir Yoke

**A minimal starter, agent-guided Project Agent Kit recipe, and portable skill provider.**

Mir Yoke is a public template and reference repository, not an agent runtime, service, or control
plane. It is not a universal installer and has no standing authority over a repository that reads
or adopts its material. The active AI agent owns the target session, inspects the real target, and
writes only under the user's target-specific authorization.

## Supported surfaces

### Minimal Starter

[`starter/`](starter/) is the only supported consumer payload. It contains exactly four Markdown
files: a repository-owned `HARNESS.md`, thin `CLAUDE.md` and `AGENTS.md` entrypoints, and an adoption
guide. It does not require a Mir CLI, installer, plugin, hook, memory database, specification tree,
sub-agent, daemon, receipt, restart, or platform-specific runtime.

### Project Agent Kit Recipe

[`recipes/project-agent-kit/`](recipes/project-agent-kit/) is a supported agent-guided recipe for a
new empty target. It does not copy a fixed payload. The target's AI uses Mir Yoke as read-only
reference and creates a purpose-specific project brief, harness, Claude/Codex reviewer, real
lint/build/test Git hook, and verified initial commit. Product planning and implementation remain a
later request.

### Portable Plugins and Reference Corpus

[`plugins/`](plugins/) publishes optional, namespaced host capabilities for Claude and Codex. A
plugin is installed explicitly in the agent host; it is not copied into a target or treated as a
readiness requirement. The remaining source, tools, examples, specifications, and history are
reference or maintainer evidence without an adopter compatibility promise.

## Start a new project

Open one explicit empty directory with Claude or Codex and send this short prompt:

```text
[Prepared project purpose and goals]

Harness: https://github.com/youngjin39/mir-yoke

Build and verify the project-specific harness and Project Agent Kit first.
Initialize a new Git repository and create the verified initial commit.
Do not start product planning or implementation yet.
```

The detailed execution contract lives in the recipe, not in the prompt. The agent must finish with
`READY_FOR_DEVELOPMENT_PLANNING`, one clean local commit, and no remote or push. If the target is not
empty or is already inside a Git worktree, use the preservation-first Starter flow instead.

## Use the minimal Starter

For an existing repository, tell the active agent to inspect current instructions, use `starter/`
as reference, merge only missing rules, replace placeholders with observed facts or owner decisions,
and run the target's own smallest relevant verification. Never recursively copy Mir Yoke over
repository-owned instructions.

## Trust boundary

Mir Yoke never discovers consumers, mutates a target, installs into a target, measures drift,
updates adopters, starts agents, configures Git remotes, commits, pushes, publishes, or messages on
their behalf. The Project Agent Kit's local Git actions happen only because the user's prompt grants
the target agent that bounded authority.

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
the four-file minimum Starter.

## License

MIT — see [`LICENSE`](LICENSE).
