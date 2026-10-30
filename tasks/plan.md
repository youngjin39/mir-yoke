# Plan

## Active task: release 0.13.49 (handoff checker fixes from the round p judge) (2026-10-31)

Intent authority: the owner's message relayed by Mir Harness Main (parent-supplied, Discord
1565755109764497549, "release with everything fixed and complete the fix and improvement work").
Design authority: this cursor. Baseline: 48b0e19 on `main` (v0.13.48 installed and attested on
the maintainer host and on the owner's PC).

Prior cursor preserved verbatim:
[cursor before release 0.13.49](change_log.md#cursor-before-release-01349-2026-10-31).

Rules (from the Mir Harness round p judge, P-D01 to P-D07):
1. Scope words bound an absence claim only in the claim's own clause; a search qualifier in the
   same item still bounds it.
2. The verified-in-repo digest rule applies with or without a command ban, and the second Stop
   recheck covers digest and absence defects.
3. A table-only qualified target is recognised for recipient accounting.
4. Contract declarations citing a shared-line map read, labels with explanation in a cell,
   negated/quoted/attributed claims and an adequate Korean access-limit disclosure are not flagged.

Request matrix: (1) fail-first tests and code for rules 1-4; (2) docs and version surfaces;
(3) Main full suite and fresh-clone readiness; (4) release, maintainer-host and owner-PC
re-attestation.

Status (2026-10-31, Main):
- (1) Codex added 20 round p cases, each failing before the fix; Main found that the first
  absence fix also flagged the judged-MET P03 scoped line and added the same-item search
  qualifier with a regression case. Handoff suite 545 passed, 2 skipped.
- (2) README, CHANGELOG, MIGRATION, ADR-90 amendment, version surfaces and test version pins,
  handler digest re-pin, payload.
- (3) Full suite before the source commit: 3915 passed, 25 skipped, 6 failed. One failure was a
  private absolute path in a new test fixture, replaced by a neutral path. The other five
  (`test_update_real_080` x4, the repository lock test) read the committed tree and wait for
  the source and bind commits.
- (3) After the source commit 1c35757 and the bind ce528f4 the lock-coupled files pass (67
  passed). Fresh-clone readiness at ce528f4: 3920 passed, 26 skipped, `ready: true`, exit 0.
- (4) Tag `v0.13.49` on ce528f4 pushed. Maintainer host: provider update applied (lock restored
  from 48b0e19), Codex hook trust 4/4, Claude 04547b54 and Codex 01a18da1 attested (five
  mir-mcp calls ok, four hooks), finalized, ready at ce528f4. Owner PC: pending.
