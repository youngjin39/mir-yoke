# Plan

## Active task: executor common v3.8 forced-mode route model guard (2026-10-02)

Authority: owner Discord 1555426386900942934, 2026-10-02, and the current
executor task. This single cursor owns intent and design. Baseline: clean
HEAD `f95dcd5`, common v3.7. Work stays in Mir Yoke; no commit/tag/push,
consumer writes, routing lock edits or generated `.codex/**` writes.

Design: only apply agent model/effort when its declared execution_backend equals
the resolved dispatch backend. CLI model/effort overrides retain precedence.
The policy/lock category and default routes declare model/effort, not a backend;
resolve_category also discards any unrelated keys. Reject a recognized opposite
backend model in forced modes before constructing or invoking the runner, unless
the user supplied an explicit model. Recognize Claude aliases sonnet/opus/fable/haiku
and claude-* versus Codex gpt-*; do not guess ownership of unknown model names.
Keep manifest schema 1 and document common v3.8 following the v3.7 convention.

- [x] Add regressions and show force_codex/Claude agent model failing before the fix.
- [x] Apply the minimum guard; verify CLI overrides, non-forced routes and bad defaults.
- [x] Update v3.8 guide/changelog/evidence; regenerate common manifests and adopter payload.
- [x] Run full pytest (zero failures), Ruff, Codex parity and common manifest check.
- [x] Record final outputs, changed paths and remaining work; remove task scratch.

The predecessor cursor is preserved in `tasks/change_log.md` under
"Archived cursor: before executor common v3.8 (2026-10-02)".

Results: fail-first observed sonnet instead of gpt-category (`1 failed in 0.07s`).
Focused regression suite: `211 passed in 4.00s`. Full pytest: `1784 passed in
220.99s (0:03:40)`, zero failures. Ruff, Codex parity, common manifest and Python
3.11 compilation passed. Both requested generators passed. Evidence:
`tasks/reports/executor-common-fail-first.md`, "Common v3.8", and the matching
`tasks/change_log.md` entry. Final record refresh passed the exact-content/public-surface checks:
`9 passed in 0.35s`. The closing cursor update uses the same payload refresh and
checks. No requested implementation or acceptance item remains; no commit/tag/push,
consumer write, lock edit or `.codex/**` write occurred. Scratch is removed after
the closing checks.
