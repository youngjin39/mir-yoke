# Mir Yoke — Harness-Managed Central Capability Supply Contract

Mir Yoke is the Harness-managed central capability supply system for independently owned repositories.
It distributes generic versioned sources as a public agent-guided template, not an agent runtime
and not a universal installer, and has no standing authority over consumers.

## Outcome and completion

- Mir Harness owns management direction, reuse decisions, verification and authorized delivery coordination. Yoke owns shared sources, plugins, separately delivered common agents/commands, versioned delivery and compatibility evidence.
- Consumers own goals, data, local policy, adapters, execution and every result. No channel is required.

## Sources

- `starter/HARNESS.md` owns the four-file Starter; `recipes/project-agent-kit/` owns the greenfield recipe; `src/mir/cli/` owns the optional installed CLI, which acts only on an explicit target and operation.
- The Kit creates bounded project-owned harness files and required SQLite+FTS5 memory. Its thin wrapper runs the exact provider revision below ignored `.mir/`, without vendoring CLI code or requiring a global install.
- `plugins/` owns common skills and the exact read-only global hook; `config/capability-sources.json` pins runtime selection.
- ADR-86 and its 2026-09-06 amendment own purpose and management; ADR-79 owns platform lanes; ADRs 81, 83-86 and 88-90 own adoption and capability boundaries.
- `config/template-assets.json` classifies assets; `.mir/repo-profile.toml` owns local boundaries; `ARCHITECTURE.md` describes supported flows.

## Authority and safety

- Mir Harness may manage Yoke directly within current user authority; `.mir/capability-lock.json` is managed, not protected. This grants no consumer authority.
- Get explicit direction before destructive actions, credentials, consumer writes, commits, pushes, tags, releases or material scope expansion.
- Preserve unrelated local changes; public material stays generic, English and sanitized.
- Yoke never discovers consumers or provides an active `yoke` composer. Installing `mir` grants no authority.
- The Kit may initialize target-local Git and make one commit only when the target prompt explicitly grants that authority.
- Plugins are optional; local skills must not shadow them. ADR-82 stays inert. Agents/Claude commands use project sync or the user-runtime installer; Codex uses generated agents and mapped skills.
- ADR-90 admits only the global continuity hook; coupled hooks and MCP stay target-local.
- Edit canonical sources first; regenerate `AGENTS.md`, nested `AGENTS.md` and `.codex/`.

## Execution and evidence

- Use direct work for bounded changes; scale design, delegation and review with uncertainty.
- Finish when affected supported-surface contracts, generated parity and the smallest relevant checks pass. Broaden tests only for affected maintainer code or release coupling.
- Starter/recipe: `uv run pytest -q tests/test_project_agent_kit.py tests/test_minimal_starter.py`.
- CLI: include `tests/test_installed_cli.py` and the affected command regression. Plugins: run isolated package and common-contract tests.
- Checks: `uv run pytest`, `uv run ruff check`, `uv run python scripts/verify_codex_sync.py`.
- Artifacts stay English; user-facing language follows the user.
- Repository-only SRR invocation and prior wording: `tasks/change_log.md`, 2026-09-23 preserved inputs.

## Role policy (template summary)
