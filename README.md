# Mir Yoke

**A local project-harness platform with a minimal agent-guided core and optional capability packs.**

Mir Yoke is a public template-backed local harness platform and reference implementation, not an
agent runtime, hosted service, or control plane. It is not a universal installer and has no
standing authority over a repository that uses it. The active AI agent first reads the target
repository's current state and local instructions, then adapts only the useful baseline.

## Supported product

[`starter/`](starter/) is the only required and default consumer payload. It contains four Markdown
files:

- `HARNESS.md` — the repository-owned operating contract;
- `CLAUDE.md` — a thin Claude entrypoint;
- `AGENTS.md` — the generated Codex entrypoint; and
- `README.md` — the adoption guide.

The core does not require a Mir CLI, installer, plugin, hook, memory database, specification tree,
sub-agent, daemon, service, receipt, restart phase, or operating-system-specific runtime.

Optional features are declared under [`packs/`](packs/) with explicit compatibility, support, and
verification metadata. `safety` is stable; `memory`, `collaboration`, and `assurance` are preview.
The implementations already present under `src/`, `tools/`, `plugins/`, `.claude/`, `.codex/`, and
`spec/` remain available as those packs' source and regression corpus. Their presence never makes
them a project requirement.

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

## Optional capability packs

Profiles under [`profiles/`](profiles/) are advisory presets. They never make recommended packs
mandatory:

| Profile | Default | Recommended when justified |
|---|---|---|
| `minimal` | core only | none |
| `code` | core + safety | collaboration, assurance |
| `content` | core only | memory |
| `collaboration` | core + safety | collaboration, memory |
| `assured` | core + safety | memory, collaboration, assurance |

The local `yoke` CLI can inspect and compose an explicit target. Planning never writes to the
target; apply refuses conflicts rather than replacing repository-owned files:

```bash
uv run yoke plan ../my-project --profile code --output /tmp/mir-plan.json --json
uv run yoke apply ../my-project --plan /tmp/mir-plan.json --json
```

For manual adoption or when no pack is justified, keep using the four-file flow above. When a pack
is justified:

1. begin with the four-file starter;
2. identify a concrete recurring failure or risk;
3. select the smallest relevant stable or preview pack;
4. adapt it to the target's local contract; and
5. verify and own it in that repository.

Mir Yoke does not discover consumers, measure their drift, update them, start their agents, or
commit, push, publish, or message on their behalf. Machine-local receipts and provider pins are
ignored; repository policy and composed files are owned by the consumer.

## Distribution

Maintainers build a Git-independent core archive and one archive per pack. The build is
deterministic and emits `manifest.json`, `SHA256SUMS`, and `provenance.json`:

```bash
uv run yoke build --output-dir dist --json
uv run yoke provider install --provider-home ~/.mir-yoke --json
```

Providers are stored by content digest, so different projects can pin different versions without
a host-global active-version conflict.

## Maintainer checkout

This full repository is the source and evidence corpus used to maintain the public starter. It is
not meant to be transformed into a product repository.

```bash
uv sync
uv run pytest tests/test_minimal_starter.py tests/test_product_planes.py \
  tests/test_distribution_builder.py tests/test_yoke_composer.py tests/test_safety_pack.py -q
uv run python scripts/verify_codex_sync.py
uv run ruff check
```

Release and historical implementation details remain available under `docs/`, `spec/`, `src/`,
`tools/`, and Git history. ADR-82 is the current product-plane and composition decision; ADR-81
continues to own the minimum starter boundary.

## License

MIT — see [`LICENSE`](LICENSE).
