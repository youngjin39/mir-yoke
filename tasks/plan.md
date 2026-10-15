# Plan

## Active task: Closure W2b (2026-10-15)

Authority: current W2b owner request recorded in `tasks/intent.json`; this is the single
active cursor and design authority. The preceding W2 cursor is preserved in `tasks/change_log.md`.

Outcome: resolve declared fleet anchor forms, retain strict missing-name rejection, provide
an explicit-root fleet check, and run the complete suite with scratch outside the worktree.
Design: extend the existing resolver with heading slugs, RFC 6901 traversal, declaration
modifiers/annotations/generic functions and shell declaration forms. Preserve ordinary names.
A real missing declaration remains an error and is reported without consumer edits.

- [x] Prove each new anchor regression fails against unchanged W2 code.
- [x] Implement the bounded resolver change and document an explicit-root fleet check.
- [x] Run full pytest, compare any failures with HEAD, run lint/parity and fleet checks.
- [x] Refresh the cache-free mir-core digest and adopter inventory; record exact evidence.

No generated writes, consumer writes, live operations, version bumps, commits or delivery.

Code/test boundary complete: full pytest 2,021 passed; Ruff, read-only Codex parity,
context paths, Python 3.9 grammar and strict impact pass. Fleet results are 14 requested
roots at 0/0 and one consumer at 1 error/0 warnings: its Artifact ref names an undeclared symbol,
which the target does not declare. Yoke is also 0/0. Consumer correction remains Main/owner
work; the matcher must not accept a different declaration. No derivative regeneration
is currently needed. Exact commands and per-root receipts: `tasks/change_log.md`, Closure W2b.
