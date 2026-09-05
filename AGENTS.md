<!-- GENERATED FILE: edit CLAUDE.md and rerun scripts/generate_codex_derivatives.sh -->

# Mir Yoke — Harness-Managed Central Capability Supply Contract

Mir Yoke is the Harness-managed central capability supply system for independently owned
repositories. It distributes versioned generic capability sources as a public agent-guided template,
not an agent runtime and not a universal installer, and has no standing authority over consumers.
`starter/` is the four-file payload; the Project Agent Kit is the greenfield recipe; installed `mir`
acts only on an explicit target and operation.

## Outcome and completion

- Mir Harness owns Yoke management direction, reuse decisions, verification, and authorized
  delivery coordination. Yoke owns the generic shared sources, plugins, separately delivered common
  agents and commands, versioned delivery, and compatibility evidence.
- Consumers own their goals, data, local policy, adapters, and execution. Maintain the four-file
  Starter, Project Agent Kit with harness and required memory, optional public `mir` CLI,
  namespaced plugins, and retrievable reference corpus without requiring any channel.
- Finish when the affected supported-surface contracts, generated parity, and smallest relevant
  checks pass.

## Sources

- `starter/HARNESS.md` is the canonical minimum consumer contract template.
- `recipes/project-agent-kit/` owns the one-prompt empty-target bootstrap procedure.
- `src/mir/cli/` owns the optional installed v0.8-compatible command surface; the Kit never copies it.
- `plugins/` owns common skills and the exact read-only global hook;
  `config/capability-sources.json` owns commit-pinned runtime selection.
- ADR-86 owns Yoke's current primary purpose and management relationship; its 2026-09-06 amendment
  takes precedence over older template-only role descriptions. ADR-79 owns the primary macOS,
  Linux/WSL compatibility, and native Windows reference-adaptation lanes; ADRs 81, 83-86, and 88-90
  own the current adoption and capability boundaries.
- `config/template-assets.json` classifies the full maintainer checkout.
- `.mir/repo-profile.toml` owns this maintainer repository's local boundaries when present.

## Authority and safety

- Mir Harness may manage Yoke directly within current user authority; `.mir/capability-lock.json` is
  managed, not protected. That responsibility does not give Yoke authority to manage consumers.
- Get explicit direction before destructive actions, credentials, consumer writes, commits, pushes,
  tags, releases, or material scope expansion.
- Preserve unrelated local changes and keep public material generic, English, and sanitized.
- Consumers own every result. Mir Yoke never discovers them, grants standing write authority, or
  provides an active `yoke` composer; installing `mir` does not expand authority.
- The Project Agent Kit recipe may describe target-local Git initialization and one commit only when
  the user's target prompt explicitly grants that authority.
- The Kit creates bounded project-owned files and SQLite+FTS5 memory. Its thin `scripts/mir.sh`
  executes the exact provider revision with runtime state below ignored `.mir/`, without vendoring
  the package or requiring a host-global installation.
- Plugins are optional; local skills must not shadow them, and ADR-82 stays inert. Agents and Claude
  commands use project sync or the user-runtime installer; Codex uses generated agents and mapped
  skills. ADR-90 admits only the global continuity hook; coupled hooks and MCP stay target-local.
- Edit canonical sources first and regenerate `AGENTS.md`, nested `AGENTS.md`, and `.codex/`.

## Execution and evidence

- Use direct work for bounded changes; scale design, delegation, and review with uncertainty.
- Run the smallest check that can fail for changed behavior.
- For Starter or recipe changes, run
  `uv run pytest -q tests/test_project_agent_kit.py tests/test_minimal_starter.py`.
- For CLI changes, include `tests/test_installed_cli.py` and the affected command regression.
- For plugin changes, run isolated package and common-contract tests.
- Use broader tests only when affected maintainer code or release coupling requires them.

Commands: `uv run pytest`, `uv run ruff check`, `uv run python scripts/verify_codex_sync.py`. Artifacts are English; user-facing language follows the user.

## Role policy (template summary)
