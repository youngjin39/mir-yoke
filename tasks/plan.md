# Plan

## Active task: release 0.13.50 (handoff checker fixes from the round q judge) (2026-10-31)

Intent authority: the owner's message relayed by Mir Harness Main (parent-supplied, Discord
1565775910966141068, "go with 1" = option 1 of the 0.13.49 report: fix the round q checker findings,
release, then measure round r). Design authority: this cursor. Baseline: b97b843 on `main`
(v0.13.49 installed and attested on the maintainer host and on the owner's PC).

Prior cursor preserved verbatim:
[cursor before release 0.13.50](change_log.md#cursor-before-release-01350-2026-10-31).

Rules (from the Mir Harness round q judge, Q-D01 to Q-D04):
1. A root Glob is a complete search only for a whole-tree pattern; any other pattern is a bounded
   scope.
2. A contract declaration whose map citation is in the source section is supported.
3. A recipient access-limit disclosure phrased as "without running commands" or
   "shell/interpreter not called", with an unavailable reader, is adequate.
4. A may-line that restates a read-only condition of the owner's grant is not extra authority;
   genuinely enlarged authority stays flagged.

Request matrix: (1) fail-first tests and code for rules 1-4; (2) docs and version surfaces;
(3) Main full suite and fresh-clone readiness; (4) release, maintainer-host and owner-PC
re-attestation.

Status (2026-10-31, Main):
- (1) Codex added 23 round q cases; Main re-ran them against the 0.13.49 handler (8 failed) and
  the fix (handoff and public-surface suites 571 passed, 2 skipped). One existing case changed its
  root Glob input from `*item*` to `**/*` because the old input encoded the defect.
- (2) README, CHANGELOG, MIGRATION, ADR-90 amendment, version surfaces and test version pins,
  handler digest re-pin, payload.
- (3) Full suite before the source commit: 3938 passed, 25 skipped, 6 failed. One failure was a
  Korean quotation in this cursor, replaced by an English paraphrase. The other five
  (`test_update_real_080` x4, the repository lock test) read the committed tree and wait for
  the source and bind commits.
