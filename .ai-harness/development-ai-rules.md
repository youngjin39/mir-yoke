# Development AI Rules

Loaded with the common rules for code writing, analysis, debugging, refactoring, review,
repository exploration, test generation, and dependency-impact work.

## Core rule

Treat code as part of a system. For a non-trivial change, understand the affected module,
public boundary, dependency direction, hidden hazards, downstream users, and validation path.

## Ponytail ladder

After understanding the real flow, stop at the first sufficient rung:

1. remove unnecessary work or solve it with guidance;
2. reuse existing project behavior;
3. use built-ins or the standard library;
4. use a justified installed dependency;
5. add one small line or adapter;
6. write the minimum custom implementation last.

Do not simplify away security, data-loss, credential, privacy, protected-scope, compatibility,
accessibility, or explicit owner requirements.

## Hard boundaries

- Do not use `git commit --no-verify` to hide a failed selected check.
- Do not silently swallow errors. Catch a failure only to handle, log, or re-raise it.
- Do not add backwards-compatibility shims without an actual consumer.
- Justify new dependencies; use a decision record only for consequential or shared choices.
- Hard blocks are reserved for deterministic destructive operations, credentials/privacy,
  protected scopes or Git operations, real integration conflicts, raw `codex exec`, and
  verification explicitly selected for the changed behavior.

## Proportional verification

- For non-trivial logic, run the smallest check that can fail for the changed behavior.
- Reuse existing coverage before adding tests.
- A truly trivial one-line or prose-only change needs a direct self-check, not a fabricated test.
- Use `tasks/tdd.json` and the 12-category matrix for broad, high-risk, release, restartable,
  delegated-across-slices, or explicitly ledger-driven work.
- A failed check explicitly required by the user or selected for the affected behavior blocks a
  completion claim until resolved or explicitly waived.

## When stuck

- Do not repeat the same failed shape merely to consume attempts. Inspect the cause, change the
  approach, or return control.
- Read unfamiliar files or branches before changing or deleting them.
- Preserve genuine merge conflicts for explicit resolution; do not abort and redo blindly.
- Treat advisory hook output as evidence, not an automatic task failure.

## Surgical scope

Touch only what the requested outcome requires. Report adjacent cleanup instead of rolling it in
silently. Remove imports, variables, or helpers made unused by your own change.
