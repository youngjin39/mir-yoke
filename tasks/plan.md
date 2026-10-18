# Plan

## Active task: delta re-verification 2026-10-18

Intent authority: owner Discord 1561379127401910383 (2026-10-18), relayed by
Mir Harness Main; parent-supplied bounded writer brief. This single cursor is
the authority for this task design. Main owns review, gate reruns and delivery.

Scope: Mir Yoke only, acceptance 2b89087 through b6dcd62 plus F1 fake app-server
success-test timing. No commit/push/tag/release, generated instruction/Codex/agent
writes, consumers, service changes, secret reads or live memory/database writes.
Use owner-specified external UV cache and task scratch; remove scratch at finish.

Design: assess the 22 maintenance items only against changed surfaces. Preserve
superseded continuity verbatim in the existing log. Add deterministic fake-server
delay to reproduce the old one-second success budget, then give successful calls
a shared load-tolerant budget; retain short timeout/stall kill/reject tests.
Inspect executor manifests and declared consumer evidence, stash metadata and
stale worktree registration read-only. Do not discover or modify consumers.

Request matrix: (1) 22-row delta evidence, (2) deterministic fail-first and F1 fix,
(3) common-base/consumer/version/hash finding, (4) stash/worktree observation,
(5) full pytest/Ruff/Codex parity and ontology mapping/impact, (6) continuity,
integrity refresh and final changed-file/remaining-work report.
Status: 6/6 assessed, 4/6 closed. F1 fail-first 1 failed/1 passed, then 2/2 passed;
module 52/52, delta contracts 330/330, record checks 18/18. Full gate 2135 passed,
5 failed: three stale generated-inventory effects; two provider-snapshot failures
caused by concurrent record edits passed 2/2 with writes paused. Ruff, Codex parity,
77 references, common manifest, mapping (0 errors/0 warnings) and strict impact pass.
Items 18/19/21 remain Main-owned (19/22 bounded repository closure). Requests 5/6
remain open: regenerate config/adopter-payload.json after final records, run the
full gate without concurrent provider writes, and re-observe native sessions/trust.
Do not regenerate repository Codex files; their parity already passes.
Evidence: tasks/change_log.md#delta-re-verification-2026-10-18.
Previous continuity: tasks/change_log.md#superseded-continuity-before-delta-re-verification-2026-10-18.
