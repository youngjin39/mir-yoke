# Plan

## Active task: Linux release-runner test fixes (2026-10-16)

Authority: the current owner brief recorded in `tasks/intent.json`.
This is the single active cursor and design record. The previous completed cursor
is preserved in `tasks/change_log.md#superseded-cursor-0131-preparation-before-linux-test-fixes-2026-10-16`.

Outcome: identify and fix all five failures from release run 38847178888 while
retaining BootstrapGate trust checks and case-sensitive relation selection.

- [x] Read the failed log, distinguish product defects from platform-dependent fixtures, and reproduce the relevant assumptions.
- [x] Apply minimal fixes and verify the five cases and both affected modules.
- [x] Run full pytest excluding the consistency module, Ruff and read-only Codex parity.
- [x] Review the final diff and record causes, commands, results and remaining Main work.

Limits: no commits, tags, pushes, releases, capability operations, runtime-home
writes, live databases, memory render/sync, secrets or generated `.codex/**` writes.
Use the owner-specified external uv cache and external fixture scratch.

Completed: five original cases reproduce before the fixture fixes and pass afterward;
both affected modules pass (45 tests). The full suite with injected runner-style
system Git LFS config passes (2,059 tests; consistency module excluded). Ruff,
Codex parity, mapping (0 errors/warnings) and strict impact pass. Regenerated
adopter SHA256 entries retain the same paths, classifications and dispositions.
Production code, the ontology map and checked-in Codex derivatives are unchanged.

Evidence: `tasks/change_log.md#linux-release-runner-fixtures-2026-10-16`.
Actual Linux CI execution and authorized delivery remain with Main; no commit,
push, tag, release or live capability operation ran here.
