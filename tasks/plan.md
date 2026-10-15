# Plan

## Active task: 0.13.0 release preparation (2026-10-16)

Authority: the current owner request recorded in `tasks/intent.json`; this is the single
active cursor and design record. Prior cursor details are preserved in
`tasks/change_log.md#superseded-cursor-covered-label-fix-before-0130-preparation-2026-10-16`.

Outcome: one consistent 0.13.0 release version, a dated changelog with empty Unreleased,
consumer migration instructions, a validated lifecycle-hooks digest acknowledgement and
an exactly generated adopter payload. Preserve runtime behavior, the ontology map and fixtures.
The release metadata assertion must accept the requested v-prefixed release heading.

- [x] Read bbc3248, post-v0.12.0 history, migration and release contracts; verify the supplied map hash.
- [x] Align release metadata, notes and digest; regenerate only the adopter payload.
- [x] Run full pytest excluding live-memory harness consistency, compare failures with HEAD,
      and run Ruff, generated parity, public-surface, mapping 0/0 and strict-impact checks.
- [x] Record results and leave the working tree for Main's ADR-80 commit/bind-lock/release sequence.

No commits, tags, pushes, publishing, capability update/attest/finalize, live databases,
memory render/sync, context sync, user-runtime writes or generated Codex writes.

Preparation is complete; release readiness is pending Main's lock binding. Before edits,
HEAD passed all 2,045 allowed tests. The prepared tree passed 2,044 and failed one:
`tests/test_capability_cli.py::test_repository_lock_is_portable_and_matches_managed_trees`
detects the version-changed plugin trees against the unchanged 0.12.0 lock. This is a new
failure introduced by preparation, not a pre-existing failure. Keep the test and lock intact;
Main must bind the committed implementation under ADR-80 and rerun the full suite.
Ruff, generated parity, classification, sanitization, links, schemas, mapping 0/0 and strict
impact passed. Final bookkeeping/payload checks are recorded in the release evidence entry.
