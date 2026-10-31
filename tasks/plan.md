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

Release record (Main, 2026-11-01): source eef83b4, bind 9e02dc5; fresh-clone readiness
exit 0; CI validate on 9e02dc5 (including the Windows job) succeeded before the tag
`v0.13.56`. Maintainer host: provider update applied from the 0.13.55 consumer lock;
the dry run listed both lifecycle binaries for aarch64-apple-darwin, and the apply placed
`bin/handoff-packet` and `bin/runtime-continuity` in the Claude and Codex plugin caches
with SHA-256 equal to the lock. Codex hook trust 4/4 (after a Harness verifier fix for
the native-or-Python command form). Claude 8d71b653 and Codex 01a192e7 attested (five
mir-mcp calls ok, four lifecycle hooks ran), finalized, ready at 9e02dc5. Owner PC:
recorded by Harness.
