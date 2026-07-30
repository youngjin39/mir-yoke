# 02 — AI-Ready Requirement Gate

A requirement is judged "implementable by an AI coding agent without further questions" only when it
satisfies all eight items below. If any one fails, `status` is not `ready`.

## The eight gate items

| ID | Item | Criterion | On failure |
|---|---|---|---|
| ARR-1 | Identity | Has a unique id, linked to its origin (original text, stakeholder, or code location) | Assign an id; `origin` as [TBD] |
| ARR-2 | Singularity | States exactly one thing | Re-atomise |
| ARR-3 | Unambiguity | No forbidden words (01 §5.2); the criterion is quantified | Write the refined form |
| ARR-4 | Acceptance | given/when/then, one normal case plus at least one exception | Write acceptance criteria |
| ARR-5 | Data contract | Every input and output item has name, direction, type, format, unit, and valid range | Complete the item spec |
| ARR-6 | Exceptions | Behaviour on failure, invalid input, timeout, and resource exhaustion is stated | Re-run the seven-axis sweep |
| ARR-7 | Allocation | A responsible module is named (or a planned `MOD-` id) | Perform allocation |
| ARR-8 | Verification | The means of checking is named (test kind, measurement method) | Name the verification means |

## §4.1 Acceptance criteria form

| Part | Content |
|---|---|
| given | What state the system or data is in |
| when | What input or event occurs |
| then | What observable output or state change results |

- The expected result must be observable from outside. "Handled internally" does not qualify.
- Write a normal case and at least one exception as a pair.
- When the target is non-deterministic (AI_SYSTEM), write a judgement criterion and a tolerance
  rather than exact equality. See 05 §AI_SYSTEM.

## §4.2 Mandatory data-contract fields

```
name (noun form, no direction words) / direction (I or O) / type / format /
unit (measurement unit and meaning) / range (valid range) / nullable / default /
precision (where applicable) / tolerance (where applicable)
```

## §4.3 Gate output

Record the judgement in each requirement's `status` field. Do not build a separate judgement table
that keeps the same fact in two places.

| Value | Meaning |
|---|---|
| `ready` | All eight items satisfied |
| `incomplete` | A shortfall that more information can resolve |
| `blocked` | A shortfall that cannot be resolved without stakeholder confirmation |

Always report the pass rate as counts and reflect it in `index.yaml` under `counts`, for example
"ready 23 / incomplete 5 / blocked 2".

If a human-readable judgement table is requested, produce it only as a derived artifact, with this
header verbatim (04 §Derived output).

```
ID | Requirement | ARR-1 | ARR-2 | ARR-3 | ARR-4 | ARR-5 | ARR-6 | ARR-7 | ARR-8 | status
```

## Order of judgement

1. Check ARR-2 (singularity) first. If the statement is compound, atomise and judge each part again.
2. An ARR-3 violation gets a refined statement. Preserve the original in `origin`.
3. ARR-5 and ARR-6 reference each other. Once `range` is set, the behaviour on violating it (ARR-6)
   must be defined alongside.
4. ARR-7 allocation is settled after C2 (view allocation). Before that, leave it `incomplete` and
   re-judge after C2.
5. ARR-8 at C1 requires only "how it will be checked" (test kind, measurement method). The
   executable command is settled at C6 as `tasks.yaml` `done_when.command`; reconcile the two then.
6. Never fill any item by guessing. Leave `[TBD: needs confirmation - <what>]`.

## Handling shortfalls

- A requirement whose `status` is not `ready` is recorded in `gaps.yaml` **by id only**. Do not copy
  the requirement's content.
- Never report a gate failure as PASS.
- After three consecutive gate failures, stop and return the additional information needed.
