# Plan

## Active task: release 0.13.54 (round t checker fixes) (2026-10-31)

Intent authority: the owner's message relayed by Mir Harness Main (parent-supplied, Discord
1565960047412908143, option 1 of the round t report: fix T-D01..T-D05). Round t found four
checker false positives and one missed source-claim re-read. Design authority: this cursor.
Baseline: 1efd8db on `main` (v0.13.53 attested on the maintainer host and the owner PC).

Prior cursor preserved verbatim:
[cursor before release 0.13.54](change_log.md#cursor-before-release-01354-2026-10-31).

Rules: owner-only reservations and evidential preconditions add no grant; a `pin`/`pins` heading
is not a pin and a pin claim stays on one line; "not executed" shell/interpreter disclosures count
as reader disclosures; a nested list item under a parent naming a file, with a sibling citing line
numbers, counts as cited for the source-claim re-read.

Request matrix: (1) fail-first tests and code (T-D01..T-D05); (2) docs and version surfaces;
(3) Main full suite, fresh-clone readiness and the CI validate job (including Windows) before
the tag; (4) release, maintainer-host and owner-PC re-attestation.

Status (2026-10-31, Main):
- (1) 5 new `test_round_t_*` cases (Codex; Main re-ran them: 5 failed on the 0.13.53 handler,
  passed after). `tests/test_mechanical_handoff.py` 611 passed, 2 skipped. Replay of the four
  retained round t drafts: the four false positives are gone and the T01 claim gets a re-read.
- (2) README, CHANGELOG, MIGRATION, ADR-90 amendment, version surfaces, handler digest, payload.
- (3) Full suite before the source commit: 3982 passed, 25 skipped, 5 failed (all commit-coupled).
