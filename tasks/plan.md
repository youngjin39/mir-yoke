# Plan

## Active task: Domain common relation audit fix (2026-10-15)

Authority: the current owner request is recorded in `tasks/intent.json`; this document is
the single active cursor and design record. Previous cursor details are preserved in
`tasks/change_log.md#superseded-cursor-closure-w2b-before-domain-relation-audit-fix-2026-10-15`.

Outcome: common declarations in `domain.relations` receive the same relation-ID and
version-gated endpoint validation as top-level relations. The mapping guide permits only
common concept IDs or a contract-allowed wildcard; local concept IDs remain invalid.
Entries without `common` retain ref-only validation. Extract and reuse the existing validator.

- [x] Capture baseline results for the 16 owner-listed maps and prove new regressions fail at HEAD.
- [x] Share the relation validation, add the guide line and unreleased changelog entry.
- [x] Run focused/full pytest, lint, read-only parity, mapping/impact and all 16 maps; report new pointers.
- [x] Refresh cache-free mir-core digest and adopter payload; record evidence and remaining work.

No generated derivatives, consumer writes, database inspection, commits or delivery.

Completed implementation and verification: 18 fail-first regressions against the byte-identical
HEAD checker; 217 focused tests and 2,046 full-suite tests passed. All 16 explicit owner-listed
maps report 0 errors and 0 warnings before and after; there are no new finding pointers.
Ruff, read-only Codex parity, contract, own mapping, strict impact and Python 3.9 grammar pass.
The mir-core digest and adopter inventory are refreshed; final inventory/public checks follow
bookkeeping. No consumer correction or generated regeneration is needed. Evidence:
`tasks/change_log.md#domain-common-relation-audit-fix-2026-10-15`.
