---
name: testing
description: "Test writing and execution.\n\nTrigger: test, TDD, unit test, integration test"
context: fork
---

# Testing

## Procedure
1. Detect test framework (package.json scripts, config files).
2. Identify the smallest existing check that can fail for the changed behavior.
3. Choose direct or delegated execution according to isolation and context value.
4. Use `tasks/tdd.json` and the full category matrix only when breadth, risk, release, or restartability warrants it.
5. Reuse existing coverage; add or extend tests only when the changed behavior lacks evidence.
6. Follow local test patterns and add only meaningful edge or boundary cases.
7. Run the selected commands. On failure, inspect the cause before deciding whether to fix, change approach, or return control.

## Rules
- Test names: `should_return_X_when_Y`.
- Edge cases: null, empty, boundary, error, concurrent.
- No mocks for external services unless explicitly approved.
- Code review is not proof of correctness. Executed TDD evidence is.
- `planned` TDD categories may be used in a ledger but are not completion evidence.
- `not_applicable` requires a concrete reason.
- `pass` and `covered_existing` require runnable commands.
- Browser and E2E evidence is needed only when those user-facing boundaries are affected.

## GUI Testing (Computer Use)
When the project has GUI components and computer-use MCP is enabled:
1. Build and launch the app.
2. Execute UI flows: tap, scroll, navigate between screens.
3. Screenshot any visual anomalies or errors.
4. Report layout issues with screenshot evidence.

Ref: `docs/integrations/computer-use-gui-testing.md`

## Output
```
## Test Results
| File | Tests | Pass | Fail | Coverage |
|---|---|---|---|---|
| {file} | {N} | {N} | {N} | {%} |

### Failures (if any)
- {test_name}: {root cause} → {fix applied}
```
