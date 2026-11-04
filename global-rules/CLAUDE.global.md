# Global CLAUDE.md — shared baseline coding rules

Optional universal rules for Claude Code. Copy or merge these into your own global
`~/.claude/CLAUDE.md` so they apply across ALL your repositories, not just this one. They are
CLI-agnostic — the paired Codex copy is `AGENTS.global.md` in this folder. The project-local
`CLAUDE.md` is self-sufficient without these; this is a convenience baseline.

## Think Before Coding
- Do not assume hidden requirements.
- State assumptions when they affect the implementation.
- If multiple interpretations are plausible, surface them instead of picking silently.
- Prefer the simpler path when it satisfies the request.
- If the task is unclear, stop and ask.

## Simplicity First
- Write the minimum code that solves the requested problem.
- Do not add speculative flexibility, configurability, or abstraction.
- Do not add features that were not asked for.
- Do not add error handling for impossible scenarios.
- If the solution feels overbuilt, simplify it before finalizing.

## Surgical Changes
- Touch only the files and lines required for the task.
- Do not improve adjacent code, comments, or formatting unless the task requires it.
- Match the local codebase style instead of imposing a new one.
- Report unrelated dead code or design issues instead of rewriting them.
- Remove imports, variables, or helpers made unused by your own change.

## Goal-Driven Execution
- Turn requests into verifiable outcomes before editing.
- Prefer test-first or proof-first verification when the repository supports it.
- For multi-step work, keep a short plan with a concrete verification check per step.
- Do not stop at implementation when verification is available.
- Report only what you observed; if a cause is unknown, say so — never invent an environment, tool, or failure to explain it, and never send a user-facing report in the same step as the check that backs it.

## Main and Sub-agent Delegation
- The Main owns user intent, design, orchestration, context budget, delegation, and result adjudication; sub-agents own file edits, tests, verification, review, and iteration.
- Read `policy.delegation` in the Harness-generated `config/model-routing.lock.json`; never hardcode a backend or edit the generated lock. Change its upstream Harness source instead. `mode` is the only policy switch: `user_command_priority`, `unrestricted`, `force_codex`, or `per_project`.
- `user_command_priority` resolves backend selection from the session's explicit user command, then the project declaration, then `default_backend`. `per_project` uses the project declaration, falling back to `default_backend`; `unrestricted` lets the Main choose an available backend. Under `force_codex`, a Claude Main delegates every execution step to Codex; a different backend requires an explicit user override recorded in the session.
- Read project task boundaries from `[execution]` in `.mir/repo-profile.toml`: `delegated_execution_contract`, `delegation_required_tasks`, `delegation_recommended_tasks`, and `main_direct_tasks`. Keep each delegated slice small, with explicit ownership and required evidence.
- When `tools/mir_executor` is present, a Claude Main delegates directly from its shell tool (Bash or PowerShell): `python -m tools.mir_executor execute --dispatch --dispatch-brief brief.json --background`. Run from the repository root using the shell tool's background execution; the flag does not detach dispatch. Find the job ID with `python -m tools.mir_executor list-jobs`, then read `status --job-id <id>` and `result --job-id <id>` through the same module.
- Without `tools/mir_executor`, a Claude Main falls back to `codex:codex-rescue`, which adds a Claude forwarder turn. App-server-backed executor dispatch is admitted; ADR-69 bans raw `codex exec`.
- The Main accepts work only after reading or re-running filesystem state, `git diff`, and relevant test command output. A sub-agent's narrative or status JSON alone is never acceptance evidence.

## Remote Channel Rules (Discord / Slack / any chat surface)
- Never use an interactive picker UI (e.g. AskUserQuestion) in a remote channel.
- If a choice is needed, ask with a short numbered text list and wait for a normal user message.
- Prefer a safe default over asking when the choice is minor and reversible.
- Reply through the channel's native send/reply tool — transcript text alone does not reach the user.
