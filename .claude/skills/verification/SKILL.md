---
name: verification
description: Evidence-based done check. "Should work" is forbidden. Run the tests yourself.
trigger: verify, done check, proof, self-check
---

# verification

Loaded at the end of a task. Confirms the work is actually complete by running tests, checking artifacts, and producing evidence.

## Banned phrases

- "should work"
- "probably fine"
- "I expect this to pass"
- "implementation looks correct"

If you cannot replace these with a runnable command and its actual output, the task is not done.

## Required evidence

For every claim in the task closeout, attach the runnable proof:

| Claim | Evidence |
|---|---|
| "tests pass" | exact command + last 3 lines of output |
| "no regression" | full-suite count before vs after |
| "lint clean" | ruff/eslint command + exit code |
| "ADR is authored" | path + line count + status header |
| "ledger entry is closed" | jq query + before/after status fields |

## Red Team 5Q

After the gate appears to pass, ask five adversarial questions:

1. What is the failure mode this change is most likely to introduce in production?
2. Which test would catch that failure mode? Does it exist?
3. What user input would surface the worst behavior of this change?
4. What concurrent state could expose a race in this change?
5. What does this change cost (latency, memory, cognitive load) that the spec did not budget for?

Document the answers. If any answer is "no test covers this", the task is not yet done — return to the testing skill.

## Closeout format

```
## Static
- tests: <N passed, M skipped, total time>
- lint: <PASS / errors>
- type-check: <PASS / errors>
- diff hygiene: <git diff --check exit code>

## E2E
- <step 1 result with evidence>
- <step 2 result with evidence>

## Findings
- <severity-tagged residual issues>

## Verdict
<PASS / PARTIAL / FAIL> — <one-line reason>
```

If verdict is PASS, the next session can ship. If PARTIAL or FAIL, name the unblocking step.
