# Plan

## Active task: Authority handoff guidance and 0.13.13 preparation (2026-10-21)

Intent authority: owner Discord 1562445005166223525 item 2, parent-supplied by
Mir Harness Main in the current brief. This cursor owns the bounded design.
Qualified target: mir-yoke:handoff-authority-release-0.13.13.
Verified base HEAD: acda442ce4baa14c591896cdcf5f1cf01e02aee3 (initially clean).

Design: preserve all existing Handoff rules; add verb-exact owner-grant may-list,
review/brief read-and-report boundary, separate-grant actions, author restrictions,
full HEAD/digest requirements and a final per-field/per-pin inventory in the skill
and reference. Keep SessionStart unchanged: it already points to ontology Handoff.
Prepare release metadata; refresh the lifecycle tree acknowledgement for versioned
manifests and regenerate adopter payload last. No checker behavior changes needed.

Request matrix: authority wording; author restrictions; full pins; final inventory;
release metadata/digest/payload; focused fail-first checks; full suite; parity/bytes.
Status: 7/8 closed. Full-suite green remains open for Main-owned lock binding.
Evidence: tasks/change_log.md, Authority handoff and 0.13.13 preparation heading.
TDD ledger: tasks/tdd.json. Evidence log: tasks/change_log.md.
Semantic evidence: .mir/ontology-map.json#/concepts/Task maps this cursor;
#/domain/invariants names the no-standing-consumer-authority invariant.
Parent-supplied batch F observations are evidence, not authority or local executions.

Authority: bounded checkout edits, local tests, release metadata and adopter payload.
No network, other repositories, credentials/protected files, delivery digest binding,
capability update/attest, commit/tag/push or generated .codex writes.
Unknowns: Main release binding, actual recipient adherence and post-release remeasurement.
Lifecycle: preparation; temporal: current working tree; epistemic: base checked locally,
owner grant and batch F inherited; verification: checked with explicit lock exception.
Previous cursor is preserved verbatim in tasks/change_log.md under the matching
Superseded cursor heading.

Results: new rules 14 fail-first -> 14 pass; focused packages 519 pass.
Full offline suite: 2196 passed, 3 failed in 385.44s. Public-path issue fixed and
20 surface/payload/common-skill tests passed. Isolated installed-CLI check passed
with local cached wheels and Python 3.12; no network or live activation occurred.
Only unchanged Main-owned capability lock remains unresolved. Full suite was not
rerun after these focused corrections; no full-suite green claim.
Codex parity, Ruff, ontology mapping/strict impact and diff checks passed.
SKILL.md: 10068 bytes; unchanged hook output: 783 bytes; hook source: 991 bytes.
Final evidence records precede adopter payload regeneration and read-only checks.
