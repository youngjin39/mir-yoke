# Plan

## Active task: release 0.13.44 (direct 0.8.0 migration, Windows hook UTF-8, 8.3 coverage) (2026-10-28)

Intent authority: the owner's message relayed by Mir Harness Main (parent-supplied, Discord
1564891404659069039): fix the migration from the shipped 0.8.0 enrollment and re-register the
owner's Windows PC, fix the Windows handoff hook's output decoding, and cover real 8.3 short
names; with the release-chain approvals (1564297975755448493, 1564320227062186065). Design
authority: this cursor and the ADR-91 amendment this release adds. Baseline: 45d5fe8 on `main`
(v0.13.43 installed and attested on the maintainer host).

Prior cursor preserved verbatim:
[cursor before release 0.13.44](change_log.md#cursor-before-release-01344-2026-10-28).

Rules:
1. `mir capability update` migrates a real 0.8.0 enrollment (schema-1 consumer registry, active
   receipt and lock, schema-1 `capability-sources.json`) directly: it validates the legacy
   provider and consumer against their own evidence, reads the target config before the export,
   and rewrites the consumer config, lock and registry to the current schemas. Forged or partial
   legacy state is refused.
2. The handoff hook decodes the pin runner's output as UTF-8 with replacement, whatever the
   console code page.
3. The Windows guard's final-path check is covered with an injected 8.3 short-name case, since
   the owner's PC volume has short-name generation disabled.

Request matrix: (1) fail-first tests and code for rules 1-3; (2) ADR-91 amendment, docs, version
surfaces; (3) Main full suite, fresh-clone readiness, Windows PC in-scope tests; (4) release and
host re-attestation; (5) PC re-registration of `daily_reward_runner` and Windows receipts.

Status (2026-10-28, Main):
- (1) done: da2045e. The new migration test reproduces the PC's real refusal ("MCP package
  rejected: root must be a real directory") against 45d5fe8's manager, and the UTF-8 test fails
  against 45d5fe8's hook; both pass with the fix.
- (3) partly done: macOS full suite 3847 passed, 5 failed: the release lock, the adopter payload
  (three tests, regenerated) and Hangul literals in the new hook test (now escapes); those re-ran
  at 506 passed. Windows PC in-scope run at da2045e: 921 passed, 9 skipped, 1 failed (the lock).
- (2) done: ADR-91 and ADR-90 amendments, CHANGELOG, MIGRATION, README, version surfaces 0.13.44,
  adopter payload.
- (4), (5) open.
