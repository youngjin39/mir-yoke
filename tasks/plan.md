# Plan

## Active task: ontology reachability (2026-10-17)

Authority: owner Discord 1560995198857777253 and Mir Harness directive
`ontology-engineering-settlement-2026-10-17`, both parent-supplied. The directive
and pilot report remain in Mir Harness; they have not been independently inspected.
This single active cursor records intent and is the bounded design authority.

Make `mir-core:ontology` reachable from ordinary meaning-sensitive requests and
agent handoffs. Preserve selective lookup, add the minimum parent/child packet,
and update at most one existing bluebricks routing line. Add fail-first regression
coverage and an Unreleased note; run full pytest, Ruff, Codex parity and context
path checks. Check supported generators without writing repository `.codex/**`.

No commit, push, tag, release, version bump, release/attestation record change,
activation, restart, consumer write, secret access or live database access.
Use the external uv cache. Main owns `.codex/**` regeneration and final acceptance.

Parent-supplied pilot evidence: Mir Harness
`tasks/reports/ontology-engineering/settlement-2026-10-17/pilot/report.md` describes
30 sessions: ontology loaded but not invoked in 15 Claude sessions, map read in
8/15 Codex sessions, and six handoff briefs missing current semantic/evidence pins.
These are reported observations, not locally re-derived results or new authority.

Evidence log: `tasks/change_log.md#ontology-reachability-2026-10-17`.
Previous cursor and intent are preserved verbatim at
`tasks/change_log.md#superseded-cursor-before-ontology-reachability-2026-10-17`.

### Bounded design and evaluation

This cursor is the design authority. Extend the existing description, provenance
reference and single bluebricks route; add no skill, hook, gate or command.
Static regressions cover eight trigger groups, eight handoff packet groups and
the existing design route. They pin guidance, not actual runtime invocation rates.
Keep the body rule to retrieve only relevant sources and needed evidence.

Request matrix: (1) selective ordinary triggers, (2) minimum parent/child packet,
(3) one bluebricks route, (4) supported generated parity and Unreleased note with
version/release records unchanged, (5) fail-first and the full requested gate.
Packet semantics follow the distributed common contract's four axes and the
project map `/contract`, `/namespace`, `/error_cases/3` (selection is not execution).
The map digest matches the parent-supplied pin; it is not being edited.

### Acceptance

4/5 cells closed. Final new regression selection: 17 failed before source edits,
then 17 passed. An additional handoff-link assertion failed eight packet cases
before its one-line cue fix, then the new selection passed 17/17 again.
The final source full suite passed 2080 tests and failed one release-bound plugin
tree digest assertion; lock/attestation changes are forbidden here. All five
cells were evaluated; the full-gate cell remains open for Main. Ruff, Codex
scratch-generation parity, context paths, mapping and
strict impact passed. Main owns lock refresh under separate release authority;
no tests have been weakened or excluded. Actual runtime invocation improvement
is not claimed. Evidence remains in the single log linked above.

Main acceptance (2026-10-17, Mir Harness): every hunk reviewed. On the host the 17 new
ontology-skill tests fail against the previous skill files and pass now (239 in the module).
Full pytest: 2080 passed, 1 expected failure,
`test_capability_cli.py::test_repository_lock_is_portable_and_matches_managed_trees`, because
the plugin trees no longer match the 0.13.3 lock. The lock is rebound only by the release
procedure. Ruff, Codex parity and the context-path check (77) pass. Committed on branch
`feat/ontology-reachability`, so `main` stays at the released lock. Release, push and activation
wait on the owner's decision, because the capability source is the public repository.
