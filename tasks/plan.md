# Plan

## Active task: repository maintenance (2026-10-16)

Authority: the current owner maintenance brief, recorded in `tasks/intent.json`.
The parent-supplied Harness directive is evidence of scope, not independent authority.

Outcome: assess all 22 requested items, apply minimal evidenced improvements,
and record exact checks, integrity dependencies and remaining Main/owner work.

- [x] Inspect contracts, continuity, memory snapshot, routing and runtime boundaries.
- [x] Apply bounded improvements and retain superseded text verbatim in the log.
- [x] Run full pytest, Ruff, Codex parity and ontology checks on the final sources.
- [x] Update continuity, rebind the adopter inventory, inspect diff and report all items.

Limits: no commits, release/version changes, consumer writes, live database writes,
secrets or generated `.codex/**` edits. Scratch stays on the external SSD.

Evidence: `tasks/change_log.md#repository-maintenance-2026-10-16`.
Prior cursor and projections: `tasks/change_log.md#maintenance-continuity-inputs-2026-10-16`.

Post-split state: `fc548ec` contains maintenance records/inventory only; main
retains the 21-item skill/count contract. The targeted capability-lock regression
passes; the 2061-pass/1-failure full run describes the pre-split writer tree.
Native hook trust and fresh-session discovery remain unobserved.

Main disposition (Mir Harness, 2026-10-16): the repo-maintenance item-22 skill change, its test and the adopter-payload rehash are held on local branch `maint/repo-maintenance-item-22` (b181541), not main, by Main/owner choice D1 pending an owner-approved release merge. ADR-86 permits reconciling the lock to a committed implementation without requiring a release.

Independent-review fix scope (F2–F4, 2026-10-16): correct post-split projections,
retain superseded wording, and repair the intent evidence fragment.
Checks: targeted lock/skill/public-surface tests, evidence-anchor validation and
`git diff --check`. History: `tasks/change_log.md#independent-review-corrections-2026-10-16`.
