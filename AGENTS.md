<!-- GENERATED FILE: edit CLAUDE.md and rerun scripts/generate_codex_derivatives.sh -->

# Mir Yoke — Starter, Recipe, and Plugin Provider Contract

Mir Yoke is a public, agent-guided template and reference repository, not an agent runtime. It is
not a universal installer and has no standing authority over consumer repositories. `starter/` is
the only supported consumer payload; the Project Agent Kit is a separate supported guidance recipe.

## Outcome and completion

- Maintain the four-file documentation-only Starter, the Project Agent Kit recipe, portable
  namespaced plugins, and the retrievable reference corpus.
- Finish when the affected supported-surface contracts, generated parity, and smallest relevant
  checks pass.

## Sources

- `starter/HARNESS.md` is the canonical minimum consumer contract template.
- `recipes/project-agent-kit/` owns the one-prompt empty-target bootstrap procedure.
- `plugins/*/skills/*` owns common portable skill bodies.
- `docs/decisions/adr-83-project-agent-kit-recipe-and-supported-surfaces.md` owns current product
  authority; ADR-81 owns the minimum Starter.
- `config/template-assets.json` classifies the full maintainer checkout.
- `.mir/repo-profile.toml` owns this maintainer repository's local boundaries when present.

## Authority and safety

- Read, review, and status requests are non-mutating; change requests authorize only named scope.
- Get explicit direction before destructive actions, credentials, external writes, protected scope,
  commits, pushes, releases, or material scope expansion.
- Preserve unrelated local changes and keep public material generic, English, and sanitized.
- Consumer repositories own every adapted or generated result. Mir Yoke never discovers or mutates
  them and provides no target-writing composer.
- The Project Agent Kit recipe may describe target-local Git initialization and one commit only when
  the user's target prompt explicitly grants that authority.
- Common plugins must load from their own package. Repository-local files and Mir CLI commands are
  optional context, never hidden plugin prerequisites.
- Edit canonical sources first and regenerate `AGENTS.md`, nested `AGENTS.md`, and `.codex/`.

## Execution and evidence

- Use direct work for bounded changes; scale design, delegation, and review with uncertainty.
- Run the smallest check that can fail for changed behavior.
- For Starter or recipe changes, run
  `uv run pytest -q tests/test_project_agent_kit.py tests/test_minimal_starter.py`.
- For plugin changes, run isolated package and common-contract tests.
- Use broader tests only when affected maintainer code or release coupling requires them.

Commands: `uv run pytest`, `uv run ruff check`, `uv run python scripts/verify_codex_sync.py`.
Artifacts are English; user-facing language follows the user.

## Role policy (template summary)

- The opened Claude or Codex session owns final scope and verification for this repository.
- Delegation is optional and proportional, never a direct-work gate.
- A consumer agent reads the actual target and adapts the smallest sufficient supported flow.
