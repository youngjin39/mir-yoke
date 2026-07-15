# Bluebrick: Harness Runtime

## Purpose
Define the durable human/agent operating contract: startup context, skills, hooks, generated Codex mirrors, deny-list enforcement, and session continuity.

## Public Interface
- `CLAUDE.md`
- `AGENTS.md` generated mirror
- `.claude/hooks/*`
- `.claude/skills/*`
- `.ai-harness/*.md` and `.ai-harness/deny-list.yaml`
- `scripts/generate_codex_derivatives.sh`

## Internal Rules
- Source of truth lives in `CLAUDE.md`, `.claude/agents/*`, and `.claude/skills/*`.
- Generated Codex mirrors must be regenerated, not hand-edited.
- A path-scoped `CLAUDE.md` under `scripts/`, `src/`, `tests/`, or `tools/` generates a sibling
  `AGENTS.md`; neither path-scoped body belongs in root startup context.
- Startup context, closeout, and guardrail behavior must match the documented harness contract.
- Root guidance stays short; durable detail belongs under `.ai-harness/`.

## Non-Obvious Hazards
- Do not patch `AGENTS.md`, `.agents/`, or `.codex/` by hand.
- Do not leave deny-list as documentation-only policy; hook enforcement must stay wired.
- Do not let SessionStart/PreCompact/SessionEnd behavior drift from the runtime docs.
- Do not bloat root files with per-module detail that belongs in durable harness docs.

## Dependencies
- Claude hook runtime
- Codex derivative generator
- `jq`, shell utilities, and repo-local policy docs
- task trackers under `tasks/`

## Downstream Users
- Claude Code sessions
- Codex sessions through generated mirrors
- review/runner/handoff workflows
- future family generators that reuse this harness pattern

## Composition
- `CLAUDE.md`, `AGENTS.md`
- `.claude/**`, `.agents/**`, `.codex/**`
- `.ai-harness/**`
- `tasks/**`
- `scripts/generate_codex_derivatives.sh`

## Orchestration
Session start -> startup context load -> skill-triggered execution -> hook guardrails on tool use/edit -> validation/closeout -> regenerated Codex mirrors when source changes.

## Validation
- `./scripts/generate_codex_derivatives.sh`
- `uv run pytest -q tests/test_codex_derivation_script.py tests/test_hook_scripts.py`
- `uv run ruff check src tests`
