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

Writer pass finished: full pytest has 2061 passes and one committed-lock failure.
Harness Main must review/commit the implementation and reconcile its lock under
ADR-80/86. Native hook trust and fresh-session discovery remain unobserved.

Main disposition (Mir Harness, 2026-10-16): the repo-maintenance item-22 skill change, its test and the adopter-payload rehash are held on local branch `maint/repo-maintenance-item-22` (b181541), not main, because the capability lock binds only at a release; merging needs an owner-approved release.
