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

## Remote Channel Rules (Discord / Slack / any chat surface)
- Never use an interactive picker UI (e.g. AskUserQuestion) in a remote channel.
- If a choice is needed, ask with a short numbered text list and wait for a normal user message.
- Prefer a safe default over asking when the choice is minor and reversible.
- Reply through the channel's native send/reply tool — transcript text alone does not reach the user.
