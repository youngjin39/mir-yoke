# Session Closeout

At the end of a substantial session, update the canonical handoff at
`tasks/handoffs/session-handoff-LATEST.md`; do not create a competing session summary.

`config/project-hooks.json` registers `.claude/hooks/session-end.sh` for `SessionEnd` in both
Claude and Codex; the generated configurations use 60-second and 3-second timeouts, respectively.
Previous runtime guidance is preserved in `tasks/change_log.md`, "Preserved stale closeout guidance".

Keep only the state needed to resume:

- completed work and durable decisions
- unresolved issues and next actions
- changed files or coherent file groups
- observed verification results
- risks that still require attention

Move detailed chronology, completed history, and low-value notes to logs or archives. The hook
refreshes only the generated runtime snapshot inside the canonical handoff; the agent remains
responsible for curating the sections above before closeout.

When replacing the current goal, use `scripts/mir.sh run-python --project-root . -- scripts/intent_store.py --goal "<goal>"
--updated <YYYY-MM-DD>` so the prior intent remains traceable instead of being overwritten.
