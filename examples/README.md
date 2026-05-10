# Examples

Short walk-throughs of the harness in use. Each example lives in its own
subfolder.

## How to use

Copy an example folder into your fresh repo and follow the README inside. They
are designed to be self-contained — minimal dependencies, runnable in
isolation.

## Index

- [`add-feature/`](add-feature/) — design → plan → ledger → implement → review → commit, end-to-end on a tiny feature.
- [`fix-bug/`](fix-bug/) — bug-fix workflow with a regression test.
- [`refactor/`](refactor/) — refactor workflow that keeps behavior identical.

## Add your own

Each example folder should contain:

- `README.md` — the user prompt + a step-by-step trace of what each skill produced
- `before/` — the source state
- `after/` — the post-change state, with the ledger entry that gated it
