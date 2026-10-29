# Plan

## Active task: release 0.13.47 (hook wrapper root, deterministic archive scan and doctor probe, scoped command bans) (2026-10-29)

Intent authority: the owner's message relayed by Mir Harness Main (parent-supplied, Discord
1565298172165890140, reports from consumer repositories; option 1 chosen in 1565300649078300744),
with the release-chain approvals (1564297975755448493, 1564320227062186065). Design authority:
this cursor. Baseline: 8d8691d on `main` (v0.13.46 installed and attested on the maintainer host
and on the owner's PC).

Prior cursor preserved verbatim:
[cursor before release 0.13.47](change_log.md#cursor-before-release-01347-2026-10-29).

Rules:
1. The template hook wrapper `templates/common-harness/.claude/hooks/_lib/run-python.sh` resolves
   the project root three levels above `_lib` (it resolved one level above the root).
2. The external archive scan indexes, deletes and rechecks documents in sorted path order, so the
   first indexed chunk does not depend on hash randomization; `mir memory doctor`'s FTS5 probe takes
   the first indexed chunk that holds a usable token instead of failing on a first chunk without one.
3. The handoff hook reads a command prohibition with a stated exception ("other than", "except",
   "besides" a named command) as scoped, not as a blanket command ban.

Request matrix: (1) fail-first tests and code for rules 1-3; (2) docs and version surfaces;
(3) Main full suite and fresh-clone readiness; (4) release and maintainer-host re-attestation.
The owner's PC update to 0.13.47 is a separate owner decision.

Status (2026-10-29, Main):
- (1) Each rule has a test that failed before its fix: the template wrapper test (exit 1, `mir.sh`
  not found), the doctor test (`indexed sample contains no stable probe token`) and the scan-order
  test (unsorted), and three scoped-ban cases (restricted). Fixes pass; handoff 485 passed.
- (2) README, CHANGELOG, MIGRATION, ADR-90 amendment, version surfaces, handler digest re-pin,
  payload.
