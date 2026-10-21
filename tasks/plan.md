# Plan

## Active task: Stateless mechanical handoff hooks, 0.13.14 (2026-10-22)

Intent/design authority: current owner writer brief and addendum (decision
1562495356552355994, parent-supplied). The previous adapter/state cursor is
preserved in tasks/change_log.md and is superseded by this addendum.
Qualified target: mir-yoke:mechanical-handoff-packet.
Verified HEAD: 22125d66642c5cc87234ed610012af2e83fa776b.
Verified map SHA256:
516c5b160c0fa49de51e4a0dc6f14c6e6a955d1baf72cc75dc2c93de7ea23e79.
Contract: mir.common-semantics@1.1.0. Semantic sources:
.mir/ontology-map.json#/concepts/Task and #/domain/invariants/2;
docs/decisions/adr-90-role-plugins-and-common-hooks.md#Amendment: 2026-10-22.
No inherited external measurement is treated as authority.

Design: common UserPromptSubmit supply and Stop check; unchanged SessionStart.
No adapter, persisted state, writes, network or model. Root-local runner only,
argv and 5-second deadline. Explicit native transcript tail at most 1 MiB,
exact prompt SHA256 guard, final assistant text, fresh pins, stop_hook_active
one-shot repair. Missing evidence/errors warn/fail open. Explicit grants use
lexical containment; no explicit sections defaults to read/inspect only.
English/Korean authority/prohibition patterns and detection limits are documented
in plugins/mir-lifecycle-hooks/skills/runtime-continuity/references/handoff-packet.md.
Stateless limitation: fresh pin observation time differs from supplied time;
the latter is format-checked, all other canonical pin bytes are compared freshly.
ADR-90/schema-4 exact event and handler admission is implemented (R19).

Current evidence: fail-first 18 failed/64 passed; added boundaries 2 failed;
mechanical green 90 passed. Direct R19 rerun: 18 passed. Focused suite:
209 passed/30 expected pre-bind acknowledgement failures. Full suite:
2232 passed/75 failed in 329.95 s: 69 acknowledgement failures, managed lock (1),
stale adopter payload (3), empty isolated offline dependency cache (1), and a
new ledger absolute path (1). The ledger path was corrected; final relevant
selection including public-surface tests passed 143 tests (109 deselected).
No post-correction full-suite rerun is claimed. Ruff, Codex parity and strict
ontology impact pass. Matrix: 10/11 complete; full-suite green remains open.
All requested checks were executed and every remaining cause is inventoried
in tasks/change_log.md. This is prepared source, not binding or activation.
Evidence sink: tasks/change_log.md; structured ledger: tasks/tdd.json.

May: bounded plugin/tests/ADR/validator/release metadata edits and offline checks.
May not: commit/push/tag/release/bind; generated .codex writes; network/MK;
real agents/probes; other repositories; protected data; session-handoff-LATEST edits.
Main owns binding, digest acknowledgements, generated derivatives and live-host
verification. No activation or native-host parity claim.
