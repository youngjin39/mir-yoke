---
name: writing-plans
description: Concrete implementation plan with bite-sized steps + commands + expected output. No abstract verbs.
trigger: plan, implementation plan, step design, breakdown
---

# writing-plans

Loaded after the design skill has produced an approved alternative. Turns the design into a step-by-step plan that another agent (or you in a new session) can execute mechanically.

## Output shape

```
Step N — <one-line goal>
  files: <comma-separated paths or "(NEW)">
  commands:
    - <runnable shell or test command 1>
    - <runnable shell or test command 2>
  expected:
    - <one-line outcome 1>
    - <one-line outcome 2>
```

3-7 steps for most tasks. If you produce >10 steps, the design was not yet narrow enough — go back.

## Banned phrases

- "add tests" → name the test files
- "refactor as needed" → name what gets renamed
- "improve performance" → name the metric and the target
- "wire up" → name the call sites
- "make it more X" → describe X concretely

If the plan reads like a CV bullet, it is not yet a plan.

## Required: TDD ledger entry

The plan ends with the exact `tasks/tdd.json` `change` entry that will gate the implementation. All 12 categories declared. Statuses are `planned` (will pass), `covered_existing` (already covered), or `not_applicable` (with reason).

## Exit criteria

- Plan covers every file the implementation will touch.
- Each step has a runnable verification command.
- The TDD ledger entry is written.
- The user (or the dispatching agent) approves the plan.

Then dispatch to the executor.
