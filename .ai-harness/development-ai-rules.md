# Development AI rules

Loaded on top of common-ai-rules.md when the task includes code.

## Hard rules

1. **No implementation edits without a TDD ledger entry.** `tasks/tdd.json` must have a `change` entry whose `targets` array contains every implementation file you are about to touch. The pre-tool-use hook enforces this; treat hook blocks as the spec, not as a hassle.

2. **No `git commit --no-verify`.** Hook failures are the harness telling you the work is not ready. Fix the failure, do not bypass.

3. **No silent error swallowing.** A `try/except: pass` is a bug. If you must catch, log or re-raise.

4. **No backwards-compatibility shims unless an external consumer relies on the old surface.** Internal callers get refactored together.

5. **No new dependencies without a decision record.** Add an entry to `docs/decisions/` naming the dependency, its purpose, and the alternatives you considered.

## Comments

- Default is no comment. Identifiers do the explaining.
- A comment exists only when the WHY is non-obvious — a hidden constraint, a workaround for an external bug, a behavior that would surprise a reader.
- Never write comments that explain the WHAT (the code already does that).
- Never write comments that reference the current task ("// added for issue #123") — they rot.

## Error handling

- Validate at boundaries (user input, external APIs, file I/O).
- Trust internal callers; do not validate parameters that came from your own code.
- Specific exceptions over generic catches. `except Exception:` only at the top of a process or a thread, never mid-flow.
- Logging is for failures that operations cares about. Not "function X started".

## Tests

- One assertion per test, when possible.
- Tests that read the production state of `.mir/`, `.harness/`, or any other top-level state directory are integration tests. Mark them as such; do not let them masquerade as unit tests.
- A test that needs >5 lines of setup is a sign of bad seams. Refactor the production code first.
- Tests that depend on test execution order are bugs.

## Development output policy

- Default to concise output for routine status, summaries, and explanations.
- Keep exact technical terms, commands, paths, identifiers, code blocks, diffs, schemas, and exact error strings unchanged.
- Expand for clarity when the task involves safety-critical steps, destructive actions, ambiguous procedures, confused users, architecture hazards, or disputed review reasoning.
- Do not compress away review severity, evidence, citations, validation results, blocking conditions, or TDD state.

## TDD ledger (12 categories)

Every `change` entry in `tasks/tdd.json` declares status for all twelve categories: `unit`, `integration`, `e2e`, `browser`, `edge`, `architecture`, `availability`, `load`, `soak`, `security`, `compatibility`, `transaction_locking`. Each is one of:

- `pass` (with a runnable command + a notes line)
- `covered_existing` (the change is fully covered by tests that already pass — name them)
- `not_applicable` (with a written reason)
- `planned` (only valid before commit; pre-commit hook rejects this)

Empty categories or unbacked `not_applicable` entries are the failure mode. The matrix exists because most reviewers, given a free-form review, skip half of these dimensions.

Terse output is subordinate to these safeguards and must not weaken warning quality, review depth, or verification clarity.

## When you are stuck

- 3 failures on the same step → stop and revisit the architecture. Do not retry harder.
- An unfamiliar file or branch in a clean directory → read first, do not delete.
- A merge conflict → resolve, do not abort and redo.
- A hook block → read the message, fix the underlying issue.

## Surgical scope

If the user asked for a bug fix, do the bug fix. The cleanup adjacent to it is a separate task. State it as such, then ask whether to roll it in or defer.
