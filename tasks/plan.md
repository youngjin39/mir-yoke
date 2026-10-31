# Plan

## Active task: Slice H4, provider native pins and 0.13.56 (2026-11-01)

Intent authority: owner Slice H4 request. This is the single current cursor.
Use the required-commit provider lock for placement and dry-run previews; validate
portable pins, warn and retain Python on invalid native metadata or placement.
Persist placement records and verify active trees against the active receipt.
Cover provider pins without consumer pins, absence, invalid pins, opt-out and preview
with offline fixtures. Bump current release surfaces to 0.13.56; retain historical
records and native prerelease pins. No commit, dispatch, live lock or .codex writes.
Regenerate adopter payload as the LAST edit, then perform read-only verification.

Status before final payload regeneration: provider-source regressions and release
surfaces are complete. Native tests: 44 passed. Requested combined gate: 666 passed,
1 expected live-lock tree-digest failure. Native plus lifecycle check: 74 passed,
16 Windows-only skipped before the two final export fixtures were added. Ruff,
Codex sync and diff whitespace checks passed. Exact commands and semantic evidence
are in tasks/change_log.md. Final payload regeneration and read-only surface checks
follow. Main owns source commit, plugin digest rebinding and any generated Codex
delivery. Windows execution remains CI evidence, not local macOS evidence.
