---
name: testing
description: Test writing and execution. Cover the 12-category matrix honestly.
trigger: test, TDD, unit test, integration test, regression
---

# testing

Loaded for any task that adds or modifies tests, or that runs them.

## Discipline

- One assertion per test, when feasible.
- Test names describe the behavior, not the function.
- A test that needs >5 lines of setup is a sign the production code has bad seams. Refactor production first.
- Tests that depend on other tests' execution order are bugs.
- Tests that read live filesystem state outside `tmp_path` are integration tests; mark them as such.

## The 12-category matrix

Required for every `change` entry in `tasks/tdd.json`. See `.ai-harness/tdd-matrix.md` for the full schema. The categories are:

`unit` · `integration` · `e2e` · `browser` · `edge` · `architecture` · `availability` · `load` · `soak` · `security` · `compatibility` · `transaction_locking`

Most rows will be `not_applicable` for a given change — that is fine. The point is forcing the agent to consider each dimension. Review the entry against the surface area of the change; do not just copy the previous entry.

## Edge cases worth exercising

- Empty input
- Single-element input
- Maximum-size input within reason
- Unicode (CJK, emoji, RTL)
- BOM-prefixed text
- CRLF line endings
- Time-of-day boundaries (midnight, leap second, DST)
- Negative numbers, NaN, infinity (for numeric code)
- Concurrent write (for stateful code)

If your `edge` row is `not_applicable`, the implementation is genuinely pure-function. If your function takes any input, walk this list before declaring it edge-free.

## Running

- Test command goes in the ledger entry's `categories.<name>.command`.
- Failure output gets surfaced to the user, not summarized.
- A test that "sometimes fails" is a flaky test; mark it as such and open a ledger entry to fix it.
