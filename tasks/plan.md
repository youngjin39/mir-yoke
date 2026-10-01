# Plan

## Active task: repository maintenance pass (2026-10-02)

Authority: the owner's 2026-10-02 maintenance instruction, relayed by the
Mir Harness Control Plane: run `mir-core:repo-maintenance` (21 items) over this
repository, then improve it. This cursor is the intent and design authority.
mir-yoke only; local commits of own files only. No push, tag, release, consumer
write, secret access, `config/model-routing.lock.json` or synced
`tools/mir_executor` common edits (those go to NEEDS HARNESS).
Starting worktree: clean at `cf2aa6c`.

- [x] Baseline: full pytest, Ruff, Codex parity.
- [x] Audit 21 items; re-verify the 2026-09-23/24 fixes, the ADR-88 lock and executor v3.4.
- [x] Fix in-scope defects; each new regression test fails first, then passes.
- [x] Re-run documented gates; regenerate the adopter payload; commit own files locally.

Final gates (resumed run): `uv run pytest` over `tools` 699 passed and `tests` 906
passed (1605); Ruff, Codex parity, context paths, harness consistency and the
executor common manifest pass. No task item remains open.

Evidence, owner decisions and Mir Harness requests: `tasks/change_log.md`,
"Repository maintenance pass (2026-10-02)".

## Predecessor cursor sections

Executor common v3.3, v3.2, v3, base v2, the executor fixes follow-up and the
preserved executor-common predecessor (2026-10-01; its open commit item was resolved
by 79536b2) moved verbatim to `tasks/change_log.md`,
"Archived cursor sections: executor common (moved 2026-10-02)".
