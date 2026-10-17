# Plan

## Active task: ontology handoff packet (2026-10-18)

Intent authority: current Mir Harness Main writer brief, recorded in this single active cursor.
Make the six-field handoff packet visible in the ontology skill body, preserve owner authority,
and report actual client results/reasons and the applied configuration source.
Prior plan and intent are preserved in
`tasks/change_log.md#superseded-cursor-before-ontology-handoff-packet-2026-10-18`.

Bounded design: add a compact Handoff section without changing the description, add one sentence
to knowledge-supply guidance, add fail-first tests in the existing style and an Unreleased note,
and regenerate the adopter payload through the documented command. No version bump, commit,
release, network call, live DB write or repository `.codex/**` write is authorized.

Request matrix: (1) body packet/self-check/authority, (2) actual client result/config guidance,
(3) tests, changelog and required generated payload. Evidence:
`tasks/change_log.md#ontology-handoff-packet-2026-10-18`.

Completion: 3/3 done. Fail-first 11 failures became 11 passes; ontology/package gates passed
271 tests, adopter/classification checks passed 28 tests, and Ruff and Codex parity passed.
Final record hashes are included in adopter regeneration and exact inventory verification.
No owner decision or delivery action is part of this task.
