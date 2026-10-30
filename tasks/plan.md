# Plan

## Active task: release 0.13.48 (bounded absence claims and digest labels in the handoff hook) (2026-10-30)

Intent authority: the owner's messages relayed by Mir Harness Main (parent-supplied, Discord
1565672217159802942 "continue all improvements and finish", release choice 1565675558291902488
"release as 0.13.48"). Design authority: this cursor. Baseline: 6298592 on `main` (v0.13.47
installed and attested on the maintainer host and on the owner's PC).

Prior cursor preserved verbatim:
[cursor before release 0.13.48](change_log.md#cursor-before-release-01348-2026-10-30).

Rules:
1. A final handoff message must not claim repository-wide absence after only bounded searches:
   the author and recipient Stop checks flag such a line unless this turn searched the
   repository root or the line names the bounded scope.
2. Under a command ban, a digest pin (`*.digest`, `*.sha256`) labelled verified-in-repo is a
   defect; a value read from a file is parent-supplied or unchecked.
3. Author and recipient context state that a hook or gate pass is not read or act permission.

Request matrix: (1) fail-first tests and code for rules 1-3; (2) docs and version surfaces;
(3) Main full suite and fresh-clone readiness; (4) release and maintainer-host re-attestation.
The owner's PC stays on 0.13.47 (owner choice 1565675558291902488).

Status (2026-10-30, Main):
- (1) New tests fail without the handler change (26 failed) and pass with it; handoff 524 passed,
  2 skipped. Main narrowed the absence pattern so that no-change lines ("no files changed in the
  repository") are not flagged.
- (2) README, CHANGELOG, MIGRATION, ADR-90 amendment, version surfaces and test version pins,
  handler digest re-pin, payload.
- (3) Main full suite before the source commit: 3892 passed, 25 skipped, 8 failed. Four were test
  version pins (fixed). Three `test_update_real_080` cases and the lock test read committed
  `HEAD`, so they need the source commit and the bind.
