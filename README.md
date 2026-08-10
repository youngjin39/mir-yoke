# Mir Yoke

**A minimal, agent-guided harness-engineering starter and reference repository.**

Mir Yoke is a public template, not an agent runtime, service, or control plane. It is not a
universal installer and has no standing authority over a repository that uses it. The active AI
agent first reads the target repository's current state and local instructions, then adapts only
the useful baseline.

## Supported product

[`starter/`](starter/) is the only supported consumer payload. It contains four Markdown files:

- `HARNESS.md` — the repository-owned operating contract;
- `CLAUDE.md` — a thin Claude entrypoint;
- `AGENTS.md` — the generated Codex entrypoint; and
- `README.md` — the adoption guide.

The core does not require a Mir CLI, installer, plugin, hook, memory database, specification tree,
sub-agent, daemon, service, receipt, restart phase, or operating-system-specific runtime.

Everything outside `starter/` is Mir Yoke maintainer code, optional reference material, examples,
or history. It may help a project later, but it is not part of the supported starter contract and
does not become a project requirement merely because it exists here.

## Start a project

Open the target repository with the AI agent you intend to use and give it this instruction:

> Inspect this repository's current state and existing instructions. Use Mir Yoke's `starter/`
> directory as reference material. Preserve repository-owned content, adapt only the missing
> harness rules, replace every placeholder with observed facts or an explicit owner decision, and
> run the repository's own smallest relevant verification. Do not install optional Mir Yoke
> machinery or begin product work until the harness diff is reviewed.

For an empty repository, the four starter files can become root files after their placeholders are
filled. For an existing repository, the agent must merge only missing rules; a recursive copy over
local `CLAUDE.md`, `AGENTS.md`, or equivalent instructions is not supported.

See [`BOOTSTRAP.md`](BOOTSTRAP.md) for the assessment checklist.

## What the agent adapts

The agent derives a small local contract from evidence already present in the target:

- project purpose and observable completion;
- implementation, documentation, generated, and protected paths;
- repository-owned authority and actions that still need approval;
- the smallest real build, test, lint, or inspection commands; and
- whether any additional harness mechanism is justified by actual risk.

If a fact cannot be observed and materially affects the result, the agent asks the owner. It does
not infer product policy from Mir Yoke examples or force a missing mechanism into the project.

## Optional reference material

The rest of this checkout shows patterns for hooks, skills, agents, memory, specification,
delegation, provenance, and validation. Treat those as a pattern library:

1. begin with the four-file starter;
2. identify a concrete recurring failure or risk;
3. select the smallest relevant pattern;
4. adapt it to the target's local contract; and
5. verify and own it in that repository.

Mir Yoke does not discover consumers, measure their drift, update them, start their agents, or
commit, push, publish, or message on their behalf.

## Maintainer checkout

This full repository is the source and evidence corpus used to maintain the public starter. It is
not meant to be transformed into a product repository.

```bash
uv sync
uv run pytest tests/test_minimal_starter.py tests/test_public_template_identity.py \
  tests/test_template_asset_classification.py -q
uv run python scripts/verify_codex_sync.py
uv run ruff check
```

Release and historical implementation details remain available under `docs/`, `spec/`, `src/`,
`tools/`, and Git history. ADR-81 is the current support-boundary decision.

## License

MIT — see [`LICENSE`](LICENSE).
