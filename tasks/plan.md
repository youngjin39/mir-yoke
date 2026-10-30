# Plan

## Active task: release 0.13.53 (repair guard and round s checker fixes) (2026-10-31)

Intent authority: the owner's message relayed by Mir Harness Main (parent-supplied, Discord
1565830662706040974, "improve everything so that no problem remains"). Round s found a repair
guard defect and three false positives. Design authority: this cursor. Baseline: a439310 on
`main` (v0.13.52 attested on the maintainer host and the owner PC).

Prior cursor preserved verbatim:
[cursor before release 0.13.53](change_log.md#cursor-before-release-01353-2026-10-31).

Rules: count each native Stop repair message once, pairing only the two Codex record views of
one message; read/review scope, inference and misreading explanations add no grant; in
`name=value: label` the pin is `name`; same-line or nested pin labels count.

Request matrix: (1) fail-first tests and code (S-D01..S-D04); (2) docs and version surfaces;
(3) Main full suite, fresh-clone readiness and the CI validate job (including Windows) before
the tag; (4) release, maintainer-host and owner-PC re-attestation.

Status (2026-10-31, Main):
- (1) 8 new `test_round_s_*` cases (Codex; Main re-ran them: 8 failed on the 0.13.52 handler,
  8 passed after). Handoff and public surface suites 609 passed, 2 skipped.
- (2) README, CHANGELOG, MIGRATION, ADR-90 amendment, version surfaces, handler digest, payload.
- (3) Full suite before the source commit: 3977 passed, 25 skipped, 5 failed (all commit-coupled).
- (3) After the source commit 076b8d7 and the bind f2cf498 the lock-coupled files pass (67
  passed). Fresh-clone readiness at f2cf498: 3981 passed, 26 skipped, `ready: true`, exit 0. CI
  validate on f2cf498 (including the Windows job) succeeded before the tag.
- (4) Tag `v0.13.53` on f2cf498 pushed. Maintainer host: provider update applied (lock restored
  from a439310), Codex hook trust 4/4, Claude 89761c91 and Codex 01a18ef6 attested (five
  mir-mcp calls ok, four hooks), finalized, ready at f2cf498. Owner PC: recorded by Harness.
