# Plan

## Active task: executor common v3 (2026-10-01)

Authority: the current user request and supplied `spec-executor-v3.md`.
This cursor is the design authority for the six specified common execution changes.
Write only in mir-yoke; named consumers are read-only. No commit, push or tag.

- [x] Per item: add regression tests, observe fail, implement and observe pass.
- [x] Cover CLI routes, agent API, execution writer lease, strict item shape,
      provider hook and optional timeout bounds with compatible absent defaults.
- [x] Update sync guide and regenerate common manifests and affected payload.
- [x] Run full pytest, Ruff, Python 3.11 compilation and self-target drift check.

Evidence: `tasks/reports/executor-common-fail-first.md` owns per-item fail/pass
results. Final full pytest: `1546 passed in 205.29s (0:03:25)`; all 88 v3 tests
passed. Ruff, Python 3.11.16 common-file compilation, generated parity,
self-target sync and regenerated-payload checks passed. No commit, push, tag
or consumer write occurred.

The predecessor records below are preserved as historical evidence.

## Active task: executor common base v2 (2026-10-01)

Authority: the current user request and the supplied `spec-executor-v2.md`.
This cursor is the design authority for the v2 extension hooks and resume integrity.
Write only in mir-yoke; consumers remain read-only. Do not commit or push.

- [x] Add fail-first tests for lifecycle events, identity, rendered briefs, root selection and resume.
- [x] Implement optional hooks with compatible defaults and additive job options storage.
- [x] Document semantics and regenerate common manifests and affected adopter payload.
- [x] Run focused/full pytest, Ruff, Python 3.11 compilation, sync and parity checks.

Fail-first evidence: `test_hooks_v2.py` initially reported `13 failed in 0.39s`:
7 lifecycle nodes, 2 identity nodes, 2 rendered-brief nodes and 2 root-selection nodes.
Durable-review, started/running, effective-options and absent-render-hook regressions
each subsequently failed in a focused run before their respective fixes.
Resume tests first reported `4 failed in 0.11s`; after schema-only implementation,
`2 failed, 2 passed in 0.09s` independently proved lost options and digest acceptance.
The portable manifest test failed with common CLI drift before regeneration.

Final focused pass lines:
- Lifecycle: `9 passed, 8 deselected in 0.30s`.
- Identity: `2 passed, 15 deselected in 0.09s`.
- Rendered brief: `2 passed, 15 deselected in 0.09s`.
- Root selection: `2 passed, 15 deselected in 0.10s`.
- Resume and effective options: `6 passed, 16 deselected in 0.16s`.
- Common manifest and adopter classification: `7 passed in 0.32s`.
- All new v2 tests, including absent-hook compatibility: `22 passed in 0.68s`.

Final full pytest: `1452 passed in 190.83s (0:03:10)`.
Ruff (`tools tests`): `All checks passed!`. Python 3.11.16 compiled all 15
manifest common files. Self-target sync and Codex derivative parity passed.
`policy.py` has no diff and remains self-contained. `cli.py`: 960 lines;
`dispatch.py`: 1211 lines. No commit, push or consumer write occurred.
Fail-first and final suite logs are in `/tmp/mir-executor-v2-*.txt`; resume
fail-first output is explicitly labeled as a transcription of observed tool output.

The completed follow-up below is preserved as evidence, not active authority.

## Active follow-up: executor fixes (2026-10-01)

Authority: the current user request and the supplied `spec-executor-fix1.md`.
This cursor is the design authority for three bounded common-executor fixes.
The predecessor record below is retained as evidence; its commit permission does
not apply to this follow-up. Write only in mir-yoke; do not commit or push.

- [x] Fail first, fix and pass: blocked-dispatch hint uses the actual artifacts path.
- [x] Fail first, fix and pass: backend resolution accepts per-project objects and ignores malformed entries.
- [x] Fail first, fix and pass: fallback policies preserve routing and monitoring.
- [x] Regenerate manifests and adopter payload; run focused/full pytest, Ruff and Python 3.11 compilation.

Fail-first and immediate pass evidence (pytest selectors):
- `blocked_prints_retry_diagnostic`: `2 failed, 118 deselected in 0.35s` -> `2 passed, 118 deselected in 0.23s`.
- `should_return_backend_when_per_project`: `8 failed, 1 passed, 120 deselected in 0.30s` -> `9 passed, 120 deselected in 0.04s`.
- `should_return_routing_and_monitoring`: `3 failed, 33 deselected in 0.07s` -> `3 passed, 33 deselected in 0.03s`.

Focused executor/sync suite: `438 passed in 48.62s`. Ruff: `All checks passed!`.
Full suite: `1430 passed in 200.40s (0:03:20)`. Adopter payload tests: `6 passed`.
Python 3.11.16: all 15 manifest common files compiled. Codex derivatives match sources.
Use `UV_CACHE_DIR=/tmp/mir-yoke-uv-cache` because the default cache is outside writable roots.
All three fixes are complete. No commit, push or other-repository write occurred.

## Preserved predecessor

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
