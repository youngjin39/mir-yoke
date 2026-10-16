# Plan

## Active task: local and CI validation fixes (2026-10-16)

Authority: the owner request recorded in `tasks/intent.json`; this is the single active
cursor and design record. Preserve the completed memory render guard (section A), whose
cursor is archived in `tasks/change_log.md#superseded-cursor-memory-render-guard-before-local-and-ci-fixes-2026-10-16`.

Outcome: strict release metadata and committed capability digests agree with supported
sources; runtime caches do not affect bind/verify; every validate job command has fresh
checkout evidence, with actual Actions and platform limits stated explicitly.

- [x] Reproduce release, cache and fresh-checkout inventory failures; inspect release history.
- [x] Apply minimum fixes, prove cache fail-first and unchanged committed lock digests.
- [x] Run focused checks, full pytest with required deselect, lint and read-only parity.
- [x] Overlay only final candidate changes onto fresh HEAD clone; run each validate command.
- [x] Record root causes, commands/counts and remaining Main verification; regenerate payload.

Limits: one writer; no commits, pushes, tags, GitHub access, capability lock refresh,
live memory databases, secrets or generated `.codex/**` writes. Every pytest command uses
`--deselect tests/test_harness_consistency.py`. UV cache and scratch remain on external
storage. Ontology map remains unchanged at the owner-supplied SHA-256; semantic assertions
must cite map entries or direct source/test evidence. No cross-project authority is inferred.

Completed: the fixed implementation passed 2,050 tests with one required deselection.
Fresh HEAD plus the complete candidate overlay passed all four validate job command sets
on macOS/Python 3.12, including the pinned real CLI activation probe. See
`tasks/change_log.md#local-and-ci-validation-fixes-2026-10-16` for commands, counts and causes.
The committed capability lock and generated Codex files remain unchanged.

Main must verify actual Ubuntu/macOS Actions matrix results after authorized delivery and
run the guarded shared consistency test separately on the host. This sandbox did not
run Actions, publish, commit, or access a live memory database.
