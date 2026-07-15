# Session closeout contract

Update `tasks/handoffs/session-handoff-LATEST.md`; do not create a competing session summary.
Keep only the state needed to resume:

- completed work and durable decisions
- unresolved issues and next actions
- changed files or coherent file groups
- observed verification results
- risks that still require attention

Move detailed chronology, completed history, and low-value notes to logs or archives. The
`SessionEnd` hook refreshes only the generated runtime snapshot inside the canonical handoff; the
agent remains responsible for curating the sections above before closeout.
