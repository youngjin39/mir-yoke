# Sub-agent personas

Drop additional agent personas here as `<agent-name>.md`. Each file should declare:

- the agent's responsibility (one paragraph)
- when the dispatcher should call it
- the output contract (what shape the result must take)

This maintainer checkout carries an optional agent pack; the four-file Starter carries none.
Portable skills are distributed separately through namespaced plugins. Add a persona only when a
workflow needs persistent role isolation across multiple skills, and prefer dynamic model selection
unless the repository records a justified role-specific pin.

## Example skeleton

```markdown
---
name: security-reviewer
description: Runs after every code-review to check for auth/secret/sandbox boundary breaks.
trigger: explicit dispatch only
---

# security-reviewer

## Responsibility
...

## Trigger
...

## Output contract
...
```
