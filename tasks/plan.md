# Plan

## Active task: executor common v3.5 maintenance (2026-10-02)

Authority: the explicit owner follow-up relayed by Mir Harness on 2026-10-02.
This cursor is the intent and design authority. The follow-up authorizes the
previously deferred common executor edits and one local commit in mir-yoke.
No consumer writes, push, tag, release, credentials or capability-pinned changes.
Starting worktree: clean at `279c90f`.

Design: reproduce the isolated-TMPDIR test leak and reuse production cleanup,
which already removes its temporary base. Reject non-object agent criteria with
the resolver's normal ValueError contract. Correct the requested policy docstring
and qualify common policy references as Mir Harness ADR-88. Version this bounded
common maintenance increment as v3.5 in the sync document and changelog; keep
manifest schema version 1.

Owner extension: include items 5 and 6 in this same v3.5 increment. Only response
IDs issued by this client may resolve requests; internal turn keys are not RPC
request IDs. Treat excessive JSON nesting like other malformed lines. Unexpected
stdout-reader failure or EOF must release pending calls, including calls without
a timeout, through the existing process-error contract.

- [x] Reproduce response-ID collisions, excessive JSON nesting and unexpected reader death.
- [x] Fix request correlation and reader failure handling; record fail-first evidence.
- [x] Regenerate manifests and rerun the full verification for items 1-6.

- [x] Add regression cases and record every case failing before its fix.
- [x] Repair cleanup and criteria validation; correct policy wording.
- [x] Generate manifests; verify full executor tests leave no new mir-wt directories.
- [x] Run full pytest, touched-file Ruff, Python 3.11 compilation, sync and Codex parity.
- [x] Record evidence and refresh continuity projections and payload.
- [x] Commit locally: the Codex sandbox could not create `.git/index.lock`; the Mir Harness Main re-ran the full suite and committed.

Evidence: `tasks/change_log.md`, "Executor common v3.5 maintenance (2026-10-02)".
Other open owner items in the preceding maintenance evidence remain unchanged.

Predecessor cursor: `tasks/change_log.md`,
"Archived maintenance cursor (2026-10-02 executor follow-up)".
