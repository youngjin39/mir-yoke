# Composite TDD matrix

The 12-category matrix that backs `tasks/tdd.json`. Every `change` entry must declare a status for each row, even if the answer is `not_applicable`.

The matrix exists because freeform review consistently skips half of these dimensions. Forcing the agent to declare a status for `transaction_locking` (most often `not_applicable`) costs nothing when the answer is no, and catches the rare cases when the answer should have been yes.

| Category | What it covers | Common reasons for `not_applicable` |
|---|---|---|
| `unit` | function-level tests of changed modules | docs/config-only changes |
| `integration` | how the change interacts with existing modules in-process | leaf utility with no callers |
| `e2e` | full workflow from CLI / API entry point to side effects | internal helper |
| `browser` | UI-driven test (Playwright / Cypress / Selenium) | no UI surface |
| `edge` | input edge cases (empty, max, unicode, malformed) | no input surface |
| `architecture` | the change does not violate module boundaries / layering | docs/test-only |
| `availability` | retry, timeout, queue, recovery behavior | no failure mode added |
| `load` | throughput-sensitive code paths | not on a hot path |
| `soak` | long-running resource lifecycle | no long-running surface |
| `security` | auth, secrets, sandbox boundaries | no boundary touched |
| `compatibility` | older clients, schema migrations, API versions | no external surface |
| `transaction_locking` | concurrent writers, lock boundaries, atomicity | single-writer code path |

## Status values

- **`pass`** — the test ran and passed. Requires `command` (runnable) and `notes` (one line, what was checked).
- **`covered_existing`** — the change is already covered by tests that pass. Name them in `notes`.
- **`not_applicable`** — there is no meaningful test for this dimension. `reason` (one line) is mandatory.
- **`planned`** — only valid before `git commit`. The pre-commit hook rejects entries still in this state.

## Schema

```jsonc
{
  "version": 1,
  "changes": [
    {
      "id": "<short-slug>-<YYYY-MM-DD>",
      "scope": "one-paragraph description of what this change does and why",
      "targets": [
        "src/foo/bar.py",
        "tests/test_bar.py"
      ],
      "categories": {
        "unit": {
          "status": "pass",
          "command": "pytest -q tests/test_bar.py",
          "notes": "covers the new branch and the existing happy path"
        },
        "integration": {
          "status": "covered_existing",
          "notes": "tests/test_bar_integration.py already exercises the call site"
        },
        "e2e": { "status": "not_applicable", "reason": "internal helper, no entry point" },
        "browser": { "status": "not_applicable", "reason": "no UI surface" },
        "edge": {
          "status": "pass",
          "command": "pytest -q tests/test_bar.py -k edge",
          "notes": "empty input + unicode + max-int"
        },
        "architecture": {
          "status": "covered_existing",
          "notes": "no new module boundaries crossed"
        },
        "availability": { "status": "not_applicable", "reason": "no retry/queue path added" },
        "load": { "status": "not_applicable", "reason": "not on a hot path" },
        "soak": { "status": "not_applicable", "reason": "no long-lived resource" },
        "security": {
          "status": "covered_existing",
          "notes": "no auth/secret/sandbox surface touched"
        },
        "compatibility": {
          "status": "covered_existing",
          "notes": "no public schema or API surface changed"
        },
        "transaction_locking": { "status": "not_applicable", "reason": "single-writer" }
      }
    }
  ]
}
```

## Rule of thumb

`not_applicable` outnumbers `pass` in most ledger entries — that is fine. The point is forcing the agent to *consider* each dimension, not to write twelve tests per change.
