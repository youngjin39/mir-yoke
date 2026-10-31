# Plan

## Active task: Mir Yoke 0.13.55 release preparation (2026-10-31)

Intent authority: owner Slice H3 request, preserving uncommitted H/H2 work.
This is the single release cursor; superseded slice cursors are preserved verbatim
in tasks/change_log.md. No commit, tag, dispatch, capability-lock or .codex edits.

Design: native placement uses lock-pinned binaries by default; only the exact
MIR_CAPABILITY_NATIVE_ARTIFACTS=0 override disables it. Preserve existing warning
and Python fallback on placement failures. Bump current release surfaces to
0.13.55, retain historical release records, and describe native lifecycle and
Windows command selection. Regenerate adopter payload as the final edit.

Request matrix:
1. Fail-first default placement and explicit opt-out; existing fallback checks.
2. Version pins, release metadata, changelog, migration and current help text.
3. Single cursor and verbatim superseded cursor archive.
4. Requested pytest modules, public-language check, Ruff and Codex sync.
5. Final adopter payload regeneration followed only by read-only checks.

Expected open delivery: Main binds the real lock after the source commit;
unbound tree-digest and committed-HEAD checks cannot pass before that step.
Windows process execution remains a CI requirement, not local macOS evidence.

Status before final payload regeneration: rows 1-3 verified. Requested gate:
315 passed, 16 Windows-only skipped, 1 expected unbound tree-digest failure.
Committed-HEAD compatibility: 5 passed, 4 prior-schema failures pending source
commit. Native publication fixtures: 39 passed. Ruff and Codex sync passed.
Final payload edit and read-only checks follow. Commands and red/green evidence
are in tasks/change_log.md. Main's source commit and lock bind remain open.
