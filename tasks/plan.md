# Plan

## Active task: namespace fence and activation scope (2026-10-18)

Intent authority: current Mir Harness Main writer brief, owner Discord 1561086355767824457
(2026-10-18), active Harness run `ontology-engineering-settlement-2026-10-17`, parent-supplied.
This single active cursor is the bounded design authority for this task.
Previous cursor: `tasks/change_log.md#superseded-cursor-before-namespace-fence-and-activation-scope-2026-10-18`.

Implement only the MK client's fail-closed output namespace fence, the Claude activation
verifier's explicit returned `user` scope check, and their regression tests/reference/changelog.
Keep unavailable/empty exit contracts, content-free refusals and feedback behavior. No version
bump, commit, push, tag, release, network, activation, live database, secret/consumer access,
or repository `.codex/**` writes. Main owns derivative regeneration and the later 0.13.6 release.

Bounded design: retain only nodes/citations within explicit requested namespaces, otherwise
`ns:core`, `ns:shared-ops`, `ns:fleet-ops`, `ns:skills`; missing namespace fails closed.
Record a content-free filtering reason in degradation, including when all nodes are dropped.
Apply the fence to every query response, preserving refusal status.
Compare the single enabled Claude inventory record's scope to `user` before path/digest checks.
Use the existing synthetic MCP fixture and isolated synthetic CLI inventory; run tests first.

Request matrix: (1) requested/default namespace and citation isolation plus degradation,
(2) unchanged empty/unavailable/refusal/feedback contracts, (3) user-scope positive/negative
inventory verification, (4) one-line reference and Unreleased notes, (5) relevant verification,
canonical records and generated-parity assessment within the sandbox constraints.
Previous pass: 5/5 evaluated, 4/5 closed. Behavior tests: 323 passed; surface checks: 37 passed.
Cell 5 remains open only for the release-coupled capability-lock digest gate (1 failure).
Ruff, mapping/strict impact, context paths and scratch-only Codex parity passed.
Main remaining: bind the modified plugin tree in the later 0.13.6 release, then rerun the
repository-lock check and release gate. No lock or repository Codex derivatives were written.
Evidence: `tasks/change_log.md#namespace-fence-and-activation-scope-2026-10-18`.

Continuation authority: Main's current namespace-fence degradation-shape writer brief.
Use MK's real `degradation` list shape in the fixture and fail-first regressions. When filtering
drops nodes or citations, append a separate `{"scope":"client","reasons":["namespace_filtered"]}`
entry, creating the list only when absent and preserving every supplier entry. Keep no-echo,
refusal and filtered-empty contracts. Clarify the guide's shape clause, refresh adopter payload
digests with the documented generator, and run the full suite offline. Update the existing
evidence entry; leave the release lock and repository `.codex/**` files to Main.
Continuation matrix: (1) recorded fail-first, (2) list append/preservation and client contracts,
(3) accurate guide clause, (4) payload parity, (5) full-suite evidence and remaining lock gate.
Continuation status: 5/5 writer requests evidenced. Fail-first reproduced the list `setdefault`
AttributeError (1 failed, 281 deselected); corrected regressions passed (44 passed, 249 deselected).
Full suite: 2138 passed, 1 failed in 244.93s. The only failure is the explicitly deferred
`test_repository_lock_is_portable_and_matches_managed_trees`; Main owns release binding.
Payload generation passed for all 887 classified files before the full suite; regenerate after
these final evidence edits and check exact parity again. Mapping/strict impact and scoped Ruff
passed. No release-lock or repository `.codex/**` writes were made.
