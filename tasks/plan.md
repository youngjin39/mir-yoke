# Plan

## Active task: default-work-method-behaviour-scenarios

2026-10-23: prepare the portable behaviour-scenario amendment before 0.13.26.
Authority: current owner-approved writer brief, relayed by Main (parent-supplied).
This single active cursor is the design authority. Requirement: ADR-92,
2026-10-23 amendment, decision items 1–9; its forensic record is evidence,
not a new authority or a claim about model causality.

Design: extend the existing method matrix with changed-flow scenarios; preserve
all existing rules and proportional guidance without adding a blocking gate.
Testing maps rows to production/platform evidence; review challenges missing,
unreachable or wrongly expected rows and producer mocks. Only the Design phrase
changes in the two identical SessionStart messages (`+scenarios`).

Behaviour scenarios for this instruction/configuration change are not applicable:
no product flow, state transition, async operation or shipped platform changes.
The contract tests instead exercise published guidance and actual hook output.

Request matrix (checked evidence required):
1. Portable method preserves amendment items 1–9 and the existing completion rule.
2. Testing skill preserves boundary, outcome, async and neighbouring-state rules.
3. Review skill preserves scenario-first review, findings and fix re-review rules.
4. Both SessionStart sources match, with only the short Design addition.
5. Contract tests fail before source edits and pass after; full pytest, Ruff and
   Codex parity run, reporting expected unchanged-lock digest failures separately.
6. Cursor/history, prepared-source changelog and final adopter payload are current.
7. Main regenerates checked-in Codex derivatives; writer must not write them.

No commits, network, consumer/other-repository writes, live databases, versions,
capability sources/locks, handler SHA admission or release operations are allowed.
Use the approved external cache and scratch; preserve unrelated files.
Previous cursor and intent archived verbatim in
tasks/change_log.md#superseded-cursor-before-behaviour-scenarios-2026-10-23.
Evidence: tasks/change_log.md#behaviour-scenarios-prepared-source-2026-10-23.

Writer result: cells 1–6 have bounded repository evidence (6/7); cell 7 remains
Main-owned because this writer must not regenerate checked-in Codex files.
Fail-first: 20 failed; focused source/package checks: 47 passed. Final offline
full suite: 2639 passed, 70 expected unchanged-lock/digest failures (2709 total).
Ruff and official Codex comparison pass; the comparison produces no checked-in
drift. Main owns release digest acknowledgements/lock refresh and any required
Codex regeneration. This is prepared source, not release or fleet activation.
After the final record, regenerate adopter payload and check its exact bytes.
