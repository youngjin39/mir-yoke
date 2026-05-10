# Session closeout checklist

Run before signing off a session — the SessionEnd hook drops a snapshot but the snapshot is only useful if the closeout was honest.

## What worked
- One bullet per non-trivial decision that turned out right.
- Include the *reason* the decision worked, not just the outcome.

## What did not work
- One bullet per non-trivial decision that turned out wrong.
- Include the cost (time / tokens / scope creep) so the next session can avoid it.
- This list is the input to `tasks/lessons.md` — patterns that show up twice get promoted to a rule.

## Decisions
- One bullet per choice that locks future work.
- If the choice is reversible, note that.
- If it was a guess, mark it as a guess.

## Next step
- Single sentence. The very first thing the next session should do.
- Should be concrete enough that pasting it as the next prompt produces useful work.

## Closeout discipline

- Do not write "all green, looks great". Look harder.
- Do not write "blocked, will retry". Identify the unblocking step.
- Do not write "we should refactor X someday". Either it goes in `lessons.md` as a rule or it goes in `docs/decisions/` as a deferred ADR.

## When you do not have answers

If "What worked" is empty, the session probably did not produce value. Say so. The next session will adjust scope.

If "What did not work" is empty, the session probably did not stress-test anything. Say so. The next session can add adversarial review.
