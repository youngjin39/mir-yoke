# Plan

## Active task: release 0.13.51 (POSIX Glob scope on Windows) (2026-10-31)

Intent authority: the owner's message relayed by Mir Harness Main (parent-supplied, Discord
1565775910966141068, "go with 1" = release the round q checker fixes, then measure round r). The
0.13.50 Windows CI validate job failed, and completing that release needs this patch. Design
authority: this cursor. Baseline: 694be8b on `main` (v0.13.50 attested on both hosts).

Prior cursor preserved verbatim:
[cursor before release 0.13.51](change_log.md#cursor-before-release-01351-2026-10-31).

Rule: the bounded Glob scope in the absence message is POSIX on every platform.

Request matrix: (1) code fix (the failing Windows CI cases are the test); (2) docs and version
surfaces; (3) Main full suite, fresh-clone readiness and the Windows CI job before the tag;
(4) release, maintainer-host and owner-PC re-attestation.

Status (2026-10-31, Main):
- (1) `handoff_packet.py` keeps the Glob scope via `.as_posix()`; a `PureWindowsPath` check gives
  `.mir/*.json`. Handoff suite 568 passed, 2 skipped on macOS.
- (2) README, CHANGELOG, MIGRATION, ADR-90 amendment, version surfaces, handler digest, payload.
- (3) Full suite before the source commit: 3939 passed, 25 skipped, 5 failed (all commit-coupled).
