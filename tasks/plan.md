# Plan

## Active task: H1 handoff inventory and 0.13.12 preparation (2026-10-21)

Intent authority: owner Discord 1562370913666601052 item 4, parent-supplied by
Mir Harness Main in the bounded fix-yoke-h1 brief. This cursor owns the design.
Qualified target: mir-yoke:handoff-h1-release-0.13.12. Verified clean base HEAD:
a5a54ac6feb2f8381b0956a1b1b69c4a536c891f.
Design source: parent-supplied diagnosis-supply-handoff-2026-10-21.md sections H1,
Exact Yoke wording diff proposals, Additive mapping --handoff output change,
Required Yoke tests Y1-Y5 and release step 1. Apply the three exact wording diffs;
mirror the hook; add one pure finalizer for inventory on every handoff return.
Preserve existing pins, validation, non-handoff output, exit codes and authority.
Request matrix: Y1 inventory/edge/read-only; Y2 both runners; Y3 exact print-only
hook/budgets; Y4 mirror/digest/security; Y5 scope/data wording; release metadata;
generated parity; final gates. Status: 7/8 closed. Only full-gate green remains open for Main-owned lock binding.
Method: fail-first tests, implement bounded change, evaluate affected checks,
prepare patch metadata and digest, regenerate derivatives and adopter payload,
run full local gates and record real results. Main owns final lock binding.
Semantic evidence: .mir/ontology-map.json#/concepts/Task identifies this cursor;
contract mir.common-semantics@1.1.0, mapping@1.1.0. Map SHA256:
516c5b160c0fa49de51e4a0dc6f14c6e6a955d1baf72cc75dc2c93de7ea23e79.
Contract SHA256: b2f1ecd01aaa88d41caac2bc2481e7f4c5a429cff3983aaa85ddfb0fc2f1b93f.
Lifecycle: prepared for release; temporal: current working tree; epistemic: local base pins
verified-in-repo, design/approval parent-supplied; verification: expected lock exception.
Authority: bounded checkout edits, local checks, canonical-source generation only.
No commit/tag/push/network/capability commands, capability-lock edits, manual Codex
edits, other repository writes, Memory Keeper, secrets or memory database access.
Unknowns: Main binding, release/tag/provider pins, delivery and actual fresh recipient uptake.
Previous cursor is archived verbatim in tasks/change_log.md under
Superseded cursor before H1 and 0.13.12 preparation (2026-10-21).

Evidence: tasks/change_log.md#h1-handoff-inventory-and-01312-preparation-2026-10-21
owns exact fail-first nodes and source pins. Before implementation: 34 failed/425 passed
(exit 1), plus 2 failed (exit 1). After: 504 affected tests passed (exit 0).
Full offline suite: 2184 passed, 1 expected unchanged-lock failure in 385.69s (exit 1).
Installed CLI: 1 passed (exit 0). Hook: 783 output bytes, 984 source bytes; exact wording
and byte-identical method/completion prefix. Lifecycle tree acknowledgement:
4fc38964da96bb8ccce65286d860d4cfe4d7a8555f302be574fabc250a558963.
Ruff passed. Scratch generation matched all checkout bytes; Codex parity passed.
Main-owned capability lock is byte-identical to HEAD; no delivery operation ran.
Post-record release/payload/package/digest checks: 25 passed in 2.73s (exit 0).
Final Codex parity, Ruff and diff checks passed. Adopter hashes are regenerated after
this final evidence update; exact equality is checked read-only before returning.
