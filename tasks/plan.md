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

Main acceptance and release (2026-10-23): 7/7 cells closed.
- Cell 7: `scripts/verify_codex_sync.py` reports Codex derivatives match their sources, so nothing was regenerated.
- Fail-first re-run by Main: 21 failed / 26 passed with the old sources, 47 passed after.
- Commits:
  - 9aa995d: source, version 0.13.26 and lifecycle digest acknowledgement. Full suite: 2708 passed, plus the expected lock failure.
  - Bind 0ff984b: full suite 2709 passed. Tagged v0.13.26 and pushed.
- Provider update: from the registered fd3c2bb lock, recorded in cfbf106.
- Attestation used fresh 0.13.26 sessions; each listed 18 `mir-*` skills.
  - Claude headless session 2fc9996f (owner option 2, Discord 1563037835139747902) showed all four hooks:
    - SessionStart: the `(+scenarios)` line;
    - UserPromptSubmit: the packet supply;
    - Stop: a repair block;
    - PreToolUse: 5 runs per Bash call against 4 non-plugin registrations.
  - Codex sessions:
    - 01a166e1, 01a166e4 and 01a166e8 showed SessionStart;
    - 01a166e4 and 01a166e8 showed the UserPromptSubmit supply;
    - 01a166e4 showed the Stop hook_prompt under `mir-lifecycle-hooks/0.13.26`;
    - 01a166e8 showed the PreToolUse denial "Owner forbids commands in this handoff turn".
- Finalize: registration is active at 0ff984b and integrity is true.
