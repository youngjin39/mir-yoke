# Plan

## Active task: release 0.13.52 (round r checker fixes and source-claim re-read) (2026-10-31)

Intent authority: the owner's message relayed by Mir Harness Main (parent-supplied, Discord
1565830662706040974, "improve everything so that no problem remains" = fix the round r checker
false positives, address the source misreading failures, then measure again). Design authority:
this cursor. Baseline: 8ee8649 on `main` (v0.13.51 attested on the maintainer host and, per the
Harness record e7a6862d, on the owner PC).

Prior cursor preserved verbatim:
[cursor before release 0.13.52](change_log.md#cursor-before-release-01352-2026-10-31).

Rules: a bare basename resolves only to one distinct path read this turn; a May scope line and a
conditional suggestion add no grant; `provenance` is a label; a pin label may carry a Hangul
suffix; a universal claim about cited source output gets one first-block re-read request
(authors only).

Request matrix: (1) fail-first tests and code (R-D01..R-D05, S-01); (2) docs and version
surfaces; (3) Main full suite, fresh-clone readiness and the CI validate job (including Windows)
before the tag; (4) release, maintainer-host and owner-PC re-attestation.

Status (2026-10-31, Main):
- (1) 30 new `test_round_r_*` cases (Codex, each failing before the fix; Main added a time-stamp
  negative case for S-01 and proved it fails on the looser citation pattern). Handoff and public
  surface suites 601 passed, 2 skipped. On the nine latest my-life author finals S-01 fires on
  the three known misreadings (Q03, R01, R03) and on one accurate claim (P03).
- (2) README, CHANGELOG, MIGRATION, ADR-90 amendment, version surfaces, handler digest, payload.
- (3) Full suite before the source commit: 3969 passed, 25 skipped, 5 failed (all commit-coupled).
