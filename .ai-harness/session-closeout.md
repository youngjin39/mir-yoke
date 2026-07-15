# Session Closeout

At the end of a substantial session, update the canonical handoff at
`tasks/handoffs/session-handoff-LATEST.md`; do not create a competing session summary.

Claude wires `.claude/hooks/session-end.sh` to `SessionEnd`. This template's Codex hook surface does
not have that event, so run the same script manually only when a Codex closeout is explicitly
requested.

Keep only the state needed to resume:

- completed work and durable decisions
- unresolved issues and next actions
- changed files or coherent file groups
- observed verification results
- risks that still require attention

Move detailed chronology, completed history, and low-value notes to logs or archives. The hook
refreshes only the generated runtime snapshot inside the canonical handoff; the agent remains
responsible for curating the sections above before closeout.

When replacing the current goal, use `uv run python scripts/intent_store.py --goal "<goal>"
--updated <YYYY-MM-DD>` so the prior intent remains traceable instead of being overwritten.
