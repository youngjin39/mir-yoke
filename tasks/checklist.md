# Checklist

Status projection for `tasks/plan.md`: executor common v3.5 now includes all six items.
All sixteen new regression cases failed before their fixes, then passed.
Combined full pytest: 1621 passed; executor tests: 615 passed, with zero new
mir-wt temporary directories. Ruff, Python 3.11 compilation, sync and Codex parity
passed. Committed locally by the Mir Harness Main after its own full re-run
(the Codex sandbox could not create `.git/index.lock`).
Evidence: `tasks/change_log.md`, "Executor common v3.5 maintenance (2026-10-02)".
