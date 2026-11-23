# Plan

## Active task: v0.14.1 release preparation (item 11)

Intent authority: owner Discord messages 1574276820516217004 (items 6 and 11)
and 1574366612612714497 (ship the pre-tag consumer stage without a tag receipt).
Baseline: `release/v0.14.1` at `e46761a7`. Prepare source commit B for Main
review. Include the agreed MIG-RETRO release changes and METHOD-FLEET guidance.
The macOS native build and bind, promotion, tagging, and consumer rollout are
later release steps.

Source preparation: align the version pins, record the Darwin installer
limitation and bind procedure, refresh managed package and command digests, and
regenerate the adopter payload last. Verify with the offline SQLite vector
preflight, focused release and public-surface tests, full pytest and Ruff.
Clean-tree readiness remains a gate for B after commit. The Darwin pin checks
and pre-tag consumer stage remain gates for bind C before promotion and tagging.

Prior cursor and release records: [change log](change_log.md).
