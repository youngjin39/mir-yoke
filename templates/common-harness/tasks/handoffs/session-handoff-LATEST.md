# Session Handoff

## Current state

The verified Project Agent Kit foundation exists. Product planning and implementation have not
started.

## Resume boundary

Wait for a later user request before planning product work. Pull task-scoped context with the
declared `context_pull` command before substantial work.

## Durable context

`PROJECT.md`, `HARNESS.md`, `docs/`, and `tasks/` are the tracked sources. `.mir/memory.db` is an
ignored local index and can be rebuilt with the declared `memory_init`, `memory_sync`, and
`memory_doctor` commands.

## Verification

The foundation was verified with `scripts/verify.sh`; later sessions must record new observed
results here when they materially change the repository.
