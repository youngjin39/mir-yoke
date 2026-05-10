---
name: code-review
description: Adversarial review against the diff. Severity-tagged findings with file:line evidence.
trigger: review, PR, quality, merge check, post-completion
---

# code-review

Loaded after the executor has produced a diff. Read the diff against the spec and produce a finding list.

## Output shape

```
[CRITICAL] file.py:42 — finding — suggested fix
[HIGH]     file.py:87 — finding — suggested fix
[MEDIUM]   file.py:150 — finding — suggested fix
[LOW]      file.py:200 — finding — suggested fix
```

Severities:
- **CRITICAL** — data loss, security boundary breach, atomicity violation, irrecoverable state
- **HIGH** — incorrect behavior in a common case, hidden race, contract violation
- **MEDIUM** — incorrect behavior in an edge case, unclear semantics, deferred risk
- **LOW** — style, minor naming, minor doc gaps

If you produce zero CRITICAL/HIGH findings, you either reviewed a small change well or you did not look hard. Review the diff a second time before declaring it clean.

## Mandatory checks

- Every new function has at least one test that exercises it (or `covered_existing` is justified).
- Every error path either logs or re-raises.
- Every public surface has a one-line docstring or doc comment.
- Every TODO has a name and a deadline; otherwise it is not a TODO, it is a forgotten task.
- Every comment that explains the WHAT is a code smell; remove it. Keep only WHY-comments.

## Diff hygiene

- Whitespace-only changes are tolerated only when the file already had them.
- Reordered imports without functional change → flag if the file did not need it.
- Reformatted code outside the change scope → flag.

## Adversarial questions

After the finding list, write one paragraph naming three ways the change could go wrong in production that the tests do not cover. If you cannot name three, write the strongest two and acknowledge the gap.

## Exit criteria

- Finding list with severities is delivered.
- Every CRITICAL or HIGH item has a suggested fix or a clear "reject — requires redesign" note.
- The reviewer does NOT apply the fixes themselves. Hand the list to the planner.
