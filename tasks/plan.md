# Plan

## Active task: release 0.13.35 (consumer-local hook acknowledgement) (2026-10-27)

Intent authority: the owner's decision to apply the consumer-local acknowledgement rule
to the hook package (Discord 1564336518967857153), the release-chain approvals (Discord
1564297975755448493, 1564320227062186065) and the session instruction to use Claude
writers (Discord 1564282799035523227), relayed by Mir Harness Main (parent-supplied).
Design authority: this cursor and the 2026-10-27 amendments to
[ADR-91](../docs/decisions/adr-91-stdio-mcp-package-admission.md) and
[ADR-88](../docs/decisions/adr-88-active-plugin-component-admission.md). Baseline: f515bd0
on `main` (v0.13.34).

Prior cursor preserved verbatim:
[cursor before release 0.13.35](change_log.md#cursor-before-release-01335-2026-10-27).

Slice A (already in the working tree, kept): `_enrolled_plugin_matches` lets a consumer
enrolled with an older well-formed `mir-mcp` contract update, and the dry run shares the
apply enrollment verdict.

Slice B rule: `skills-hooks` packages follow the `mcp-stdio` acknowledgement rule
(ADR-91 §4.8 items 1–2, ADR-88 §2.2 item 4).
1. Only the consumer-owned config (`<consumer-root>/config/capability-sources.json` or the
   explicit `--config`) supplies a hook acknowledgement; provider-only and bundled configs
   never do.
2. Selecting or updating to hook bytes requires that acknowledgement to equal the exact
   tree digest; a provider update that changes both bytes and its own acknowledgement fails
   closed with a message naming the file and key.
3. The active receipt's `consumer_digest_acknowledgements` (replacing
   `mcp_digest_acknowledgements`) preserves the prior hook and MCP approvals; restore
   re-validates against them. Legacy receipts stay readable; their hook approval comes from
   the current consumer, never a provider config.
4. A checkout whose consumer-owned config is its own repository config keeps working while
   that config holds the exact digest.

Request matrix (initially open):
1. Fail-first tests for rules 1–3 replacing the slice-2 "hook update unchanged" test,
   with a consumer-only rollback acknowledgement and a legacy-receipt test.
2. Manager change; every existing `mir-mcp` acknowledgement test stays green.
3. Migration guide hook sentence and renewal procedure; ADR-91 and ADR-88 amendments.
4. Version surfaces, this checkout's lifecycle acknowledgement, CHANGELOG, MIGRATION,
   README, this cursor; adopter payload regenerated last.
5. Focused tests, ruff, `git diff --check`.

Constraints: no commits, tags, pushes, sub-agents, capability-lock edits, real runtime
homes or host `mir capability` operations. Scratch stays under the owner-specified
external cache directory. Main runs the full suite at acceptance.

Observed (2026-10-27, Claude writer): items 1-5 checked; the payload regeneration
follows this note. Before the fix, the new and changed tests failed (9 failed, 11 passed
in the selected `tests/test_capability_mcp.py` subset): the provider-renewed hook update
did not raise, provider-only configs still carried the hook acknowledgement, the receipt
had no `consumer_digest_acknowledgements`, and a consumer-owned hook acknowledgement
was replaced by the provider's on update. After the fix, focused capability, `mir-mcp`
and plugin-package tests: 481 passed, 1 failed. The failure is
`test_repository_lock_is_portable_and_matches_managed_trees`, because the version bump
changes tree digests that `.mir/capability-lock.json` binds; that is the separate bind
commit. Ruff and `git diff --check` pass. New tree digests: `mir-lifecycle-hooks`
ce1f5078cf61ea8bd04897863d7f68cb6445e1444e3743434452a1d60c671ecc, `mir-mcp`
e6d8adc6268d65b4af0739d49522c7c3ef6715a96835670292f0ec569013763d. No release, binding,
full-suite or runtime readiness is claimed.
