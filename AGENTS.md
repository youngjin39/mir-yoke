<!-- GENERATED FILE: edit CLAUDE.md and rerun scripts/generate_codex_derivatives.sh -->

# Mir Yoke — Starter, Project Agent Kit, and Optional CLI Contract

Mir Yoke is a public agent-guided template and reference repository, not an agent runtime and not a universal installer;
it has no standing authority over consumer repositories.
`starter/` is the four-file compatibility payload, the Project Agent Kit is the standard greenfield
recipe, and the installed `mir` CLI acts only on the user's explicit target and operation.

## Outcome and completion

- Maintain the four-file Starter, the Project Agent Kit with common harness and required memory,
  the optional public `mir` CLI, namespaced plugins, and retrievable reference corpus.
- Finish when the affected supported-surface contracts, generated parity, and smallest relevant
  checks pass.

## Sources

- `starter/HARNESS.md` is the canonical minimum consumer contract template.
- `recipes/project-agent-kit/` owns the one-prompt empty-target bootstrap procedure.
- `src/mir/cli/` owns the optional installed v0.8-compatible command surface; the Kit never copies it.
- `plugins/*/skills/*` owns common portable skill bodies.
- ADR-83 owns current product authority; ADR-81 owns the minimum Starter.
- `config/template-assets.json` classifies the full maintainer checkout.
- `.mir/repo-profile.toml` owns this maintainer repository's local boundaries when present.

## Authority and safety

- Read, review, and status requests are non-mutating; change requests authorize only named scope.
- Get explicit direction before destructive actions, credentials, external writes, protected scope,
  commits, pushes, releases, or material scope expansion.
- Preserve unrelated local changes and keep public material generic, English, and sanitized.
- Consumers own every result. Mir Yoke never discovers them, grants standing write authority, or
  provides an active `yoke` composer; installing `mir` does not expand authority.
- The Project Agent Kit recipe may describe target-local Git initialization and one commit only when
  the user's target prompt explicitly grants that authority.
- The Kit creates bounded project-owned files and SQLite+FTS5 memory. Its thin `scripts/mir.sh`
  executes the exact provider revision with runtime state below ignored `.mir/`, without vendoring
  the package or requiring a host-global installation.
- Common plugins load from their packages and are not hidden prerequisites; local specializations
  must not shadow their slugs. ADR-82 files are inert reference templates only.
- Edit canonical sources first and regenerate `AGENTS.md`, nested `AGENTS.md`, and `.codex/`.

## Execution and evidence

- Use direct work for bounded changes; scale design, delegation, and review with uncertainty.
- Run the smallest check that can fail for changed behavior.
- For Starter or recipe changes, run
  `uv run pytest -q tests/test_project_agent_kit.py tests/test_minimal_starter.py`.
- For CLI changes, include `tests/test_installed_cli.py` and the affected command regression.
- For plugin changes, run isolated package and common-contract tests.
- Use broader tests only when affected maintainer code or release coupling requires them.

Commands: `uv run pytest`, `uv run ruff check`, `uv run python scripts/verify_codex_sync.py`.
Artifacts are English; user-facing language follows the user.

## Role policy (template summary)
