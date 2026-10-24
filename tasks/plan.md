# Plan

## Active task: capability-remaining-0.13.31-2026-10-24

Intent and design authority: the owner-supplied `remaining-1024/writer.md` brief,
received 2026-10-24. Baseline: f4e14d9, Mir Yoke 0.13.30.
Prepare its remaining guidance items exactly in this scratch clone, without commits,
capability-lock changes, other repository writes, or runtime behavior changes.
The previous cursor is preserved verbatim in
[the evidence log](change_log.md#cursor-before-capability-remaining-2026-10-24).

Design: edit only the named skill guidance, targeted tests, release metadata and
adopter payload. Preserve prior meanings and adaptation pins; check upstream HEADs
and licenses read-only. Keep short references below 50 lines; use a short linked
reference for additions to an already-long reference. Korean content stays Korean
with exact hash/fidelity pins. Bump current release surfaces to 0.13.31 without
rewriting historical release records. No new runtime behavior or authority.

Request matrix: items 1, 2, 3a-l each receive targeted fail-first assertions in
`tests/test_capability_remaining.py`; release versions, payload, hashes and lifecycle
digest acknowledgement receive existing consistency checks. Required final checks:
full pytest (expected pre-bind lock failure), Ruff, Codex parity and diff check.
Behavior scenarios: not applicable, because all shipped changes are guidance text
or release metadata; hooks, scripts and runtime execution remain unchanged.

Status: guidance items 14/14 prepared; request matrix 21/22 evidenced. Release
versions, payload, Korean hashes, lifecycle acknowledgement, Ruff, Codex parity
and diff checks pass. The full-suite cell remains open: final pytest returned
`7 failed, 2848 passed, 1 skipped in 374.68s (0:06:14)`. One failure is the expected
pre-bind lock. Six release-evidence fixtures require observer state outside both
target and provider, incompatible with the clone-only write boundary. No unrelated
runtime/test rule was weakened. Main should re-run that fixture group in an
owner-authorized external temporary workspace; binding remains out of scope.
Evidence and per-item placements are in
[the evidence log](change_log.md#capability-remaining-01331-preparation-2026-10-24).

Main acceptance and release (2026-10-24, owner Discord 1563513553972109346 approving option 1, parent-supplied):
- Commits: daa7e35 source (full suite 2855 passed plus the expected pre-bind lock failure); bind 3f2fe1e (full suite 2856 passed), tagged v0.13.31, pushed, GitHub release created.
- Provider update from the enrolled 0.13.30 provider-update lock (2779c96); recorded in 48d334c.
- Claude headless session c1716994: all 23 `mir-*` skills; Mir continuity line at SessionStart; SessionStart 3, UserPromptSubmit 5, PreToolUse 5 and Stop 6 hook responses.
- Codex session 01a16db5 (0.13.31 cache): all 23 skills, SessionStart, the UserPromptSubmit packet, the PreToolUse denial "Owner forbids commands in this handoff turn" and the Stop hook_prompt under `mir-lifecycle-hooks/0.13.31`.
- Attested both runtimes with no missing skills or hooks; finalized after restart; `mir capability status` ready at 3f2fe1e.
