# Plan

## Active task: executor common v3.7 review corrections (2026-10-02)

Authority: the current owner follow-up; this cursor owns intent and design.
Preserve the existing uncommitted v3.7 work. The owner corrects the prior decision
that agent backends override forced modes: force_codex and force_claude must
return their forced backend unconditionally. Explicit user backend selection
still wins in the selected user_command step; agent routes otherwise beat
project/default steps. The committed routing lock decides the live-policy test.
Do not change the lock, consumers, protected paths or generated `.codex/**`.
No commit, tag or push is authorized. Use the owner-provided external UV cache.

- [x] Review existing diff, cursor and v3.7 evidence.
- [x] Add the force_codex/conflicting agent-route regression; capture its failure.
- [x] Restore forced backend resolution; update route matrix and lock-based assertion.
- [x] Correct v3.7 guide/changelog/evidence; run both requested generators.
- [x] Run full pytest (zero failures), Ruff, Codex parity and executor manifest check.
- [x] Record final outputs, changed paths and remaining work; remove scratch.

The prior cursor is preserved in `tasks/change_log.md` under
"Archived cursor: before executor common v3.7 review corrections (2026-10-02)".

Results: the force_codex/conflicting-agent regression failed first (`1 failed in
0.06s`); focused tests passed (`177 passed in 3.86s`). Full pytest passed:
`1750 passed in 248.36s (0:04:08)`, zero failures. Ruff, Codex parity and executor
manifest checks passed; both requested generators succeeded. Final evidence:
`tasks/reports/executor-common-fail-first.md`, "v3.7 owner review corrections",
and the matching entry in `tasks/change_log.md`. Final record edits were followed by the
same payload refresh and exact-content/public-surface checks: `9 passed in 0.41s`. No requested item
remains; no commit/tag/push, consumer write, lock edit or `.codex/**` write occurred.
