# Plan

## Active task: Slice H5, PowerShell lifecycle hooks and 0.13.57

Intent authority: owner Slice H5 request (2026-11-01). Single current cursor.
Design: keep POSIX commands unchanged; use session-shell PowerShell Windows
selectors, prefer native executables, otherwise python3, and fail closed when
python3 is unavailable. Parent-verified Codex 0.166 shell evidence supplies the
runtime premise; local hooks/schema and process tests supply repository evidence.
Scenarios: four hooks, both PowerShell shells, native absent/present, allow/deny,
space-containing plugin roots, stdin and byte parity. Windows execution is CI-owned.
No commit, push, tag, dispatch, .codex edits or live lock edits.
Bump current release pins, correct historical shell claims, preserve native pins.
Run fail-first package assertions, lifecycle/package/capability/surface/language
checks, Ruff and Codex sync. Record results in change_log before regenerating
adopter payload as the final edit. Main owns commit and plugin digest rebind.

Evidence checked 2026-11-01: 4/5 outcome rows closed locally; Windows process
proof remains open (36 CI-only cases). Combined gate: 671 passed, 32 skipped,
5 expected commit-coupled failures. Final lifecycle: 32 passed, 36 skipped.
Plugin packages 16, public surface 3, no-korean 7 passed; Ruff and Codex sync
passed. Main owns source commit, digest rebind and Windows CI execution.
Final action: regenerate adopter payload, then read-only verification.
