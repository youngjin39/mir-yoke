# Proportional TDD Matrix

Executed evidence is the primary proof for changed behavior. The matrix is a risk-analysis tool,
not a universal pre-write ceremony.

## Core rule

- For non-trivial logic, run at least the smallest command that can fail for the changed behavior.
- Reuse existing coverage before adding tests.
- A truly trivial one-line or prose-only change does not require a fabricated test.
- A failed check explicitly required by the user or selected for the affected behavior blocks a
  completion or merge claim until resolved or explicitly waived by the user.

## When to use `tasks/tdd.json`

Use the machine-readable ledger when work is broad, high-risk, restartable, delegated across slices,
release-bound, or explicitly requires an auditable test matrix. A bounded change with one obvious
verification command may record that command in the plan, commit message, or final report instead.

When a ledger is used, each entry should identify the target, affected boundary when useful, and only
the relevant categories and evidence.

## Risk menu

Consider these categories; classify all twelve only for a broad or high-risk matrix:

- `unit` — local logic
- `integration` — module or service boundary
- `e2e` — top-level user flow
- `browser` — browser or UI behavior
- `edge` — meaningful boundary and error cases
- `architecture` — dependency or structural invariant
- `availability` — retry, timeout, fallback, recovery
- `load` — throughput or concurrency
- `soak` — long-running resource lifecycle
- `security` — trust boundary, auth, secret, injection
- `compatibility` — schema, migration, public API, older data
- `transaction_locking` — transactional or concurrent state

Omitting an irrelevant category is valid for bounded work. When a full matrix is explicitly used,
`not_applicable` should carry a concrete reason.

## Evidence quality

- Preserve the real exit status. Piped commands use `set -o pipefail` or inspect the original status.
- A selector that collects zero expected tests is not evidence for that behavior.
- Prefer one focused check over many unrelated green commands.
- Add a full suite only when shared runtime, broad refactoring, release, or observed coupling warrants it.

Runtime hooks may enforce a ledger for a repository profile that explicitly opts into it. Missing
ledger ceremony is not, by itself, a universal safety failure under ADR-73.
