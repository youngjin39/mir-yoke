# your-harness Harness Architecture

## Purpose
- Define the minimum architecture contract for the your-harness self-hosting harness repository.
- Keep the main-agent contract and delegated execution boundary explicit across Claude and Codex runtimes.

## Core Surfaces
- `CLAUDE.md`: root runtime contract for Claude Code.
- `AGENTS.md`: generated Codex mirror of the root contract.
- `.claude/`: source agents, skills, hooks, and settings.
- `.codex/`: generated Codex runtime files and local Codex hooks config.
- `.ai-harness/`: CLI-agnostic policy layer for gates and shared AI rules.
- `tasks/`: active plan, lessons, TDD ledger, handoffs, and session state.
- `docs/`: durable design, rollout, and decision history.

## Runtime Model
- Claude main and Codex main share the same default control-plane contract for planning, dispatch, exception handling, verification synthesis, and final judgment.
- Delegated sub-agents are the default execution lane for implementation, TDD, deterministic verification, and code review.
- Codex is the default backend for delegated backend-capable execution work unless an explicit override is recorded.
- Runtime overrides must be recorded in `tasks/plan.md` or the active handoff.

## Verification Boundary
- `scripts/verify_context_paths.py` validates required-read and context-doc path references.
- `tasks/tdd.json` remains the implementation proof ledger for code changes.
- For single-operator local use, pre-commit hooks, the TDD ledger, and the merge gate are local
  evidence.
- Team or multi-contributor use requires a server-side authoritative gate: protected `main`, CI
  rerunning tests and lint, and no direct pushes to `main`. Local evidence is not authoritative;
  this is a mandatory adoption prerequisite. See ADR-72.

## Non-Goals
- This file does not replace detailed rollout history in `docs/decisions/`.
- This file does not define generated content; edit source contracts and regenerate instead.
