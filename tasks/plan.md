# Plan

## Active task: external-capability-gap-fill-2026-10-24

Intent/design authority: current owner brief, option 2 of the Harness external
capability re-review report (2026-10-24), owner Discord 1563273097539485821
(parent-supplied). This single cursor owns the bounded design and request matrix.
Baseline: clean c12cd1d2b19ab5941a13217afcc67bf59d67ebfd (0.13.27).
Predecessor plan and intent are archived verbatim in tasks/change_log.md under
"Cursor before external capability gap fill (2026-10-24)".

Design: add seven optional, fresh guidance references to existing skills: design
frontier rounds and degraded interview brief; bluebricks ladder safeguards;
code-review repository audit/debt and advisory consensus panel; automation
report-only SPINNING; verify three-document fidelity checklist. The panel belongs
in code-review because its trigger is a disputed high-impact review, not general
completion verification. No new skills, agents, commands, scripts or hooks.
Preserve every existing SKILL.md line. Use only source data from supplied clones.

Scenarios: dependent questions wait while independent frontier questions proceed;
missing replies never become answers; simplification retains safety requirements;
audits state load and unread scope; debt markers expose missing triggers;
stagnation reports do not actuate; document and panel judgments remain advisory.

Request matrix:
1. Fail-first focused reference/provenance/pointer contract, then seven references.
2. Existing skill preservation, English text and guidance-only package boundaries.
3. Complete 0.13.28 metadata, digest acknowledgement and final adopter payload.
4. Focused/full pytest, Ruff and Codex sync with every failure reported.
5. Binary patch against c12cd1d and status/stat/log evidence.

Execution: only the gapfill-1024 scratch boundary is writable. No capability-lock
edit, commit, tag, push, consumer operation or upstream execution.

## Preparation result (2026-10-24)

Request matrix: 5/5 preparation cells have checked evidence; release binding remains
outside scope. Seven focused cases failed with missing references before content,
then seven passed in 0.03s. All 21 existing SKILL.md bodies remain byte-identical
prefixes; seven references span 22-37 lines. Baseline plan and intent were archived
verbatim before this cursor was written. No size-budget or path-boundary failures.

Full `uv run pytest -q`: 1 failed, 2730 passed, 1 skipped in 351.69s (0:05:51).
Only `tests/test_capability_cli.py::test_repository_lock_is_portable_and_matches_managed_trees`
fails, as expressly allowed before binding. The capability lock is byte-identical
to c12cd1d. Ruff: `All checks passed!`; Codex sync:
`OK: Codex derivatives match Claude sources`.

First full attempt: 2 failed, 2729 passed, 1 skipped in 348.83s (0:05:48).
The additional failure was
`tests/test_harness_consistency.py::test_harness_consistency_zero_error_on_current_repo`:
global pytest used the base Python and its subprocess could not import `mir`.
Installing the locked dev extra in this scratch clone with `uv sync --extra dev`
resolved it without source or test-expectation changes. Cache and TMPDIR were kept
inside the owner-approved scratch boundary; no upstream code was executed.

Regenerate adopter-payload after this final record update, check the focused and
payload contracts, then deliver `../mir-yoke-0.13.28.patch` using `git add -N` for
new files and `git diff --binary c12cd1d`. Logs and final status/stat are retained
in the adjacent scratch evidence directory. No commit, tag, push or lock binding.
