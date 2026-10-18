# Plan

## Active task: ontology mapping budget 32 KiB (2026-10-19)

Intent authority: owner Discord 1561414331802058836 (raise the map budget with headroom),
parent-supplied by Mir Harness Main. Design: change `MAPPING_BUDGET` and the mapping guide
sentence to 32,768 bytes, keep the warning-only behavior and the keep-list, test first,
then release 0.13.9 through the ADR-80 chain (prepare, bind, tag, update, attest, finalize).

Request matrix: (1) fail-first budget tests; (2) checker/guide/changelog parity;
(3) release chain; (4) consumer maps re-checked under the new budget.
Status: (1)-(2) done (2 failed -> 294 passed); (3)-(4) pending.
Evidence: tasks/change_log.md#0139-mapping-budget-change-2026-10-19.
Previous cursor: tasks/change_log.md#superseded-cursor-before-the-0139-mapping-budget-change-2026-10-19.
