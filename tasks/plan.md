# Plan

Executor common base, local split and explicit sync, 2026-10-01.
Authority: current user task and the full owner-approved executor-common specification.
This cursor owns the current intent; the completed predecessor is preserved in
`tasks/change_log.md`, "Executor common split successor (2026-10-01)".

Design authority: this cursor and the supplied spec. Keep common code byte-identical,
repository hooks/data local, and routing policy in existing deployed files.

- [x] Prove missing policy, dispatch, client, job, CLI and sync behavior with failing tests.
- [x] Implement common modules, optional local adapter and cycle-free CLI split.
- [x] Generate independent common manifests and document explicit sync/drift checks.
- [x] Run full pytest, Ruff, Python 3.11 compilation and Codex parity checks.
- [ ] Commit scoped files locally; both dry-run pilots and migration reports are complete.

Only mir-yoke writes and local commits are authorized. No push, tag, release,
capability-lock or plugin edits. Pilot repositories remain read-only. Leave
`tasks/handoffs/session-handoff-LATEST.md` unstaged and uncommitted.

Verification completed: 89 new test nodes have explicit fail-first and pass lines in
`tasks/reports/executor-common-fail-first.md`. Full `uv run pytest`: 1417 passed;
Python 3.11.16 full pytest: 1417 passed. Ruff (both environments), Python 3.11
compilation of 15 common files, Codex parity and manifest drift checks pass.
Both pilot dry-runs report eight changed, six added and two identical files.
Package/config/index hashes remain unchanged in both pilots. Migration details remain
in temporary pilot reports; no consumer file was written. Common source commits and
final pilot revision binding remain pending the Git write boundary below.

Final compatibility follow-up: both legacy executor paths now honor local child
environment filtering and extra keys. Two more nodes failed first and passed;
both final full suites passed all 1417 tests.

Commit blocker: `git add` returned Operation not permitted when creating
`.git/index.lock`. The session grants read-only Git metadata access. No staging,
commit, push, tag or release occurred. The implementation and all requested checks
are complete; source and consumer manifests retain the generated source placeholder
until a writable Git session can commit and bind the consumer manifest.
