# Optional repository audit and shortcut debt review

Inspired by DietrichGebert/ponytail at 09c434a.

Use for an owner-requested whole-repository audit; ordinary reviews keep the bounded
entrypoint workflow. This is a manual review recipe, not an automatic scanner.

1. Map entrypoints, dependencies, storage and the highest-impact end-to-end flows.
   State load assumptions (users, input sizes, concurrency and deployment shape),
   separating observed limits from assumptions. Sample by risk in a large repository.
2. Require concrete failure cases: input or situation, wrong result, violated
   requirement and verified file/line. Inspect correctness, security, data safety and
   risky untested paths before lean-code suggestions; preferences remain suggestions.
3. When expected load or latency makes it relevant, inspect hot-path work, repeated
   queries, unbounded growth and shared-state races against those load assumptions.
   Distinguish measured slowness from an unmeasured performance hypothesis.
4. Return ranked findings using the entrypoint severity and scope statuses, with the
   smallest sufficient remedy and consequence of deferral. End with **Not checked:**
   unread paths, unrun checks and unknown load limits, even when no findings remain.

## Manual `shortcut:` recipe

For an authorized, deliberate limitation, use a normal code comment:
`shortcut: <what is simplified>; ceiling: <supported limit>; upgrade trigger: <observable condition and next change>`.
Example: `shortcut: linear lookup; ceiling: 100 items; upgrade trigger: above 100 items, add an index`.
Never use a marker to waive security, data-loss protection, accessibility or an
explicit requirement. A known limit is not a defect unless required use exceeds it.

Manually search repository source comments for `shortcut:`, excluding ignored build,
dependency and cache trees. Discard prose examples and unrelated keyboard shortcuts.
Harvest real markers into the repository's existing evidence or debt record when
writing it is authorized; otherwise return the rows in the review. Record file/line,
limitation, ceiling, upgrade trigger, proposed change and available owner evidence.
Warn with **missing-trigger** for a marker lacking an observable upgrade trigger;
report a missing ceiling separately. Never invent either. Count markers and warnings;
compare ceilings with expected load and link existing debt rows rather than duplicating
ledgers. This recipe adds no script, hook or automatic upgrade.
