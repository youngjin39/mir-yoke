# Plan

## Active task: repository maintenance (2026-10-16)

Authority: the current owner maintenance brief, recorded in `tasks/intent.json`.
The parent-supplied Harness directive is evidence of scope, not independent authority.

Outcome: verify each of the 22 items against current main, improve evidenced gaps,
and record checks and remaining owner/Main work in the existing evidence log.

- [x] Inspect current contracts, continuity, memory snapshot, routing and runtime boundaries.
- [x] Assess all items; retain superseded continuity text verbatim in the evidence log.
- [x] Execute full pytest, Ruff, read-only parity, ontology and synthetic runtime checks.
- [x] Record all 22 assessments and align the status projection and resume pointer.

Assessment coverage: 22/22 cells have evidence checked in this run; 19/22 cells
are PASS or IMPROVED, one retains owner D1, and two await generated inventory
rebinding. Full pytest: 2058 passed / 4 failed; after removing this run's stray
bytecode, the four-test recheck returned 1 passed / 3 inventory-related failures.
Main acceptance: Mir Harness Main (2026-10-17) regenerated the adopter inventory (`python -m tools.template_assets --write-adopter-payload`) and re-ran the host gate: 2062 passed, ruff clean; items 16 and 18 PASS, 21/22 complete, D1 remains owner-only.

Limits: no commit, push, release, consumer write, live database write, secret read,
`uv sync`, service restart, generated `.codex/**` edit or generated-file refresh.
Scratch is confined to the owner-specified external task directory.

Evidence: `tasks/change_log.md#matrix-pass-2026-10-16`.
Prior cursor and projections: the superseded continuity text in that section.
Historical passes: `tasks/change_log.md#repository-maintenance-2026-10-16` and
`tasks/change_log.md#independent-review-corrections-2026-10-16`.

Main disposition (Mir Harness, 2026-10-16): the repo-maintenance item-22 skill change, its test and the adopter-payload rehash are held on local branch `maint/repo-maintenance-item-22` (b181541), not main, by Main/owner choice D1 pending an owner-approved release merge. ADR-86 permits reconciling the lock to a committed implementation without requiring a release.
Recommendation for D1: retain the hold until the owner authorizes the release merge.

Next action: matrix pass 2026-10-16: reviewed and committed by Mir Harness Main.
