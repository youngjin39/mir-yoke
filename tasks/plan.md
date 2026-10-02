# Plan

## Active task: fleet Codex transport wording (2026-10-02)

Authority: owner Discord 1555375556290154528, 2026-10-02. This cursor records
intent and is the design authority. Work only in mir-yoke; preserve history,
compatibility identifiers, generated sources and unrelated changes. No executor
common-code edits, protected-path writes, commits or pushes.

Design: classify the requested grep inventory; update live transport guidance;
add the exact supersession line only to current ADRs without an equivalent note.
Preserve the dependent inactive MCP example entry and report that limitation.

- [x] Inventory and minimally update eligible sources and ADR notes.
- [x] Refresh the repository-only adopter payload and check docs, links and parity.
- [x] Record class counts, changes, generators, checks and unresolved dependencies for reporting.

Inventory (original line numbers; matching rows, not individual occurrences):

- LIVE: zero requested-regex hits; supplemental `.mcp.json.example` guidance and
  split command/args identify one live configuration source.
- HISTORY (12): `CHANGELOG.md:187`; ADR-65:16; ADR-69:32; ADR-85:104;
  ADR-90:40; `tasks/change_log.md`:681,943,944,945,958,960;
  `tasks/tdd.json`:577. ADR-69 and ADR-85 already have equivalent amendments.
- IDENTIFIER (15): `config/adopter-payload.json`:4837,4927;
  `config/mir-executor-common.json`:8; ADR-90:38 (real `codex mcp list` client
  command); `tasks/change_log.md`:1038,1239,2571,2584,2600,2604,2610,2620;
  `tasks/tdd.json`:1395,1398,1403.

Evidence: 18 tests passed via `uv run pytest -q tests/test_link_integrity.py
 tests/test_decision_authority.py tests/test_template_asset_classification.py`;
`uv run python scripts/verify_codex_sync.py` passed. No tests assert the changed
transport wording, so the conditional full-suite gate does not apply.
Generator: `uv run python -m tools.template_assets --write-adopter-payload`.
Use `UV_CACHE_DIR=/Volumes/T7 Shield/cache/uv`; temporary verification files use
`TMPDIR=/Volumes/T7 Shield/agent-cache/codex-wording/tmp` and are removed afterward.
The generator also refreshes an already-stale routing-lock digest; it does not
modify the routing lock. The inactive example has dependants in README,
MIGRATION, capability configuration, asset inventory, operations and ADRs;
its removed server entry is retained under the owner's removal condition.

## Previous completed task

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
