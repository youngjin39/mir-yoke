# Plan

The current phase summary, in compact form. The session-start hook reads
this file on every launch — keep it short.

## Conventions

- One section per phase (`## <phase id> — <one-line goal>`).
- Each phase ends with a one-line `Step <id>: DONE | finished=YYYY-MM-DD | artifacts=[...]` summary or `IN_PROGRESS | started=...` for the active phase.
- Old phases get archived to `tasks/log/` once the next two phases are done.

## P0 — bootstrap

Step P0: IN_PROGRESS | started=YYYY-MM-DD | scope=initial template install. Run `./setup.sh`, verify the hooks fire on a sample edit, write the first real plan entry.

## Runtime Overrides

- 2026-07-02: Direct main-agent patch for ADR-66 MCP backend because raw `codex exec` is prohibited for this task and native sub-agent execution is not available as a mutating harness lane in this session.
