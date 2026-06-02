# Sub-agent personas

Drop additional agent personas here as `<agent-name>.md`. Each file should declare:

- the agent's responsibility (one paragraph)
- when the dispatcher should call it
- the output contract (what shape the result must take)

The starter ships with 12 agent personas and 11 built-in skills. Add personas only when a workflow needs a persistent role across multiple skills (e.g., a "security reviewer" that always runs after `code-review`).

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
