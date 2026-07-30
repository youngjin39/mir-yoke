# 00 — The completeness lattice (what this skill guarantees)

Purpose: start from what the user stated and produce an implementation blueprint that is **complete
and unambiguous**. The claim that nothing is missing is proven by the coverage of four lattices.

## Principles

| # | Principle |
|---|---|
| C-1 | The lattice does not create requirements. It creates **questions**. Filling a blank by guessing violates X-1 |
| C-2 | Every cell closes as exactly one of: `filled` / `derived` plus basis / `na` plus reason / `tbd` plus question |
| C-3 | Never leave a cell silently blank. A blank cell is itself the omission |
| C-4 | Report coverage as counts. A completeness claim without numbers is prohibited |
| C-5 | Each layer catches a different class of omission. One layer does not substitute for another |
| C-6 | **Attempt derivation before asking.** Question count is not a quality metric |
| C-7 | A candidate from the lattice must also pass the **necessity check** (01 §5.2 Necessary) before it becomes a requirement |

### `derived` — closing without asking (C-6)

When a blank appears, check whether the answer already follows from one of these before turning it
into a question:

1. Requirements, constraints, or quality targets already settled
2. Facts in the target repository's code (evidence gathered in MODE-R/S)
3. Crosscutting concepts in force and the domain difference rules

If it follows, close it as `derived` and **record the basis**. Raise only the specific unresolved
item as `tbd`.

```yaml
- {axis: E, subject: "booking list", item: "zero results", verdict: derived,
   basis: "concepts/error-handling: an empty result is an empty list response, not an error"}
```

Many cells closed as `derived` is a good outcome. Many `tbd` cells is not an achievement.

### C-7 — the lattice finds omissions; excess needs a separate filter

L1 through L4 all look for what is missing. Turning every candidate into a requirement puts features
nobody needs into the spec, and they get built. The lattice output is a **candidate**, not a decision.

Ask each candidate once more: **what breaks without it.** No answer means it is not a requirement.

| Judgement | Handling |
|---|---|
| Something breaks without it | Confirm as a requirement. Record that answer in `origin` |
| No answer emerges | `na` plus the reason "necessity unconfirmed". Do not raise it as a question |
| Already satisfied by something present | `derived` plus the id that satisfies it |

Completeness and minimality do not conflict. **Review exhaustively; confirm only what is needed.**

## The unit of a cell (defining the denominator)

Reporting coverage as counts requires a deterministic denominator per layer. Without this definition
two sessions count the same spec differently and the numbers stop being comparable.

| Layer | One cell | Total |
|---|---|---|
| L1 | axis x subject | 8 axes x (entity count + actor count). Axes with no subject (F operations, G time) count as one cell each |
| L2 | use case x axis | use case count x 7 |
| L3 | quality characteristic | always 9 |
| L4 | check item | always 10 |

When an L1 axis holds several scenarios, **the axis takes the lowest judgement**: any `tbd` makes the
cell `tbd`; otherwise any `derived` makes it `derived`; all filled makes it `filled`.

Report the total together with how it was computed, for example
`L1 48 cells (8 axes x 4 entities + 2 subjectless axes)`.

## The four layers

| Layer | Omission caught | When | Detail |
|---|---|---|---|
| **L1 elicitation** | The requirement or feature **itself** | F4 (once the requirement set exists, before modelling) | This document |
| **L2 scenario** | Paths **inside** a use case (seven axes) | F6 (**after** use-case modelling) | 01 §5.5 |
| **L3 quality** | Non-functional requirements (nine characteristics) | F4 | 01 §6.1 |
| **L4 implementation** | Holes in the blueprint itself | after C2 | This document |

L2 requires use cases to exist. Never run the seven axes before modelling (F5).

---

## L1 elicitation lattice — finding what was not said

A stated requirement usually covers only the main function on its happy path. Cross the eight axes
below to surface candidates mechanically.

### L1-A entity x lifecycle

Extract the nouns (entities) from the input and cross them with lifecycle operations.

| Column | Question |
|---|---|
| Create | Who creates it, and from what |
| Read | Is there a path to read a single one |
| Search / list | Are the filter, sort, and paging rules defined |
| Update | Which fields may change. Which are immutable |
| Delete | Physical or logical. What happens if it is still referenced |
| Restore | Can a deletion be undone, and for how long |
| Archive | Where do old ones go |
| Transfer | Does ownership or assignment ever change hands |

### L1-B actor x function

Put actors on the rows and the derived functions on the columns. Each cell decides permitted or not.
**"Not permitted" is also a requirement** — record it as a permission constraint (IR/CR). An
undecided cell is a permission hole.

### L1-C state x event

For every entity that holds state, build a transition matrix: rows are current states, columns are
events.

A blank is an undefined transition. "Ignore it" and "reject it" are decisions too, so state them.
If a state turns out to be unreachable or inescapable, mark it `tbd`.

### L1-D forward x reverse

Check whether each forward action needs a counterpart. If it does not, record the reason.

| Forward | Reverse candidate |
|---|---|
| Request, apply | Cancel, withdraw |
| Register, sign up | Terminate, withdraw, deactivate |
| Pay, charge | Refund, partial refund, void |
| Start, execute | Stop, pause, roll back, compensate |
| Approve | Reject, revoke approval |
| Publish, deploy | Retire, recall, roll back |
| Connect, subscribe | Disconnect, unsubscribe |
| Lock, hold | Release, force release, expiry release |

### L1-E boundaries (0 / 1 / N)

Check the count boundaries of each function's target.

| Boundary | Question |
|---|---|
| Zero | What is shown when there is nothing |
| One | The single-item rule |
| Many | Is it allowed, what is the cap, paging and sorting |
| Over the cap | Reject, queue, or partially process |
| Duplicate | What happens when the same request arrives twice (idempotence) |
| Partial failure | Three of ten fail: roll everything back, or keep the seven |

### L1-F operational functions

The ones users rarely mention but without which operation does not work.

Configuration change / status and health check / audit log / backup and restore / data migration /
permission and account management / maintenance mode and notices / rate limits and quotas / a manual
intervention path when something breaks

### L1-G time

Expiry and validity / periodic execution / delayed or scheduled execution / retries and their cap /
time zones / business hours and holidays / ordering guarantees / precedence among concurrent requests

### L1-H data lifetime

What is collected / retention period / anonymisation / how and when it is destroyed / export and
download / access history / the link to legal and policy constraints (§6.3 Technical Constraint)

### L1 output

```yaml
lattice_l1:
  entities: ["booking", "payment"]
  cells:
    - {axis: A, subject: "booking", item: "cancel", verdict: tbd,
       question: "Is cancellation needed. If so, what is the cutoff and the penalty rule"}
    - {axis: F, subject: "-", item: "audit log", verdict: na,
       reason: "internal tool, not subject to audit"}
    - {axis: D, subject: "payment", item: "refund", verdict: filled, ref: FR-012}
    - {axis: E, subject: "booking list", item: "zero results", verdict: derived,
       basis: "concepts/error-handling: empty result is an empty list response"}
  coverage: {total: 48, filled: 28, derived: 3, na: 12, tbd: 5}
```

Record every `tbd` cell in `gaps.yaml` by id.

### Questions follow the design skill's protocol

**This skill does not define its own questioning protocol.** How to ask is owned by the `design`
skill's Intent Extraction section (ADR-70, ADR-78). Apply its grill-style elicit, derive-first
ordering, remote-channel rules, and authority separation as written there.

Only two things are specific to the lattice:

1. **Batch them.** Finish traversing the lattice, then present the `tbd` cells together. Do not ask
   cell by cell.
2. **Order by impact.** Structural changes first, then behavioural, then value-only. Separate
   blocking (`blocking: true`) from non-blocking when presenting.

When an answer arrives, close the cell as `filled` and record `origin: "user confirmed <date>"`.

---

## L4 implementation lattice — holes left in the blueprint

Apply after C2 (view allocation). A single blank means implementation cannot start from this
blueprint.

| Check | What a blank means |
|---|---|
| Is every requirement allocated to a module | Some requirement has no one to build it |
| Is every use case allocated to at least one module | A function has no implementing owner |
| Does every interface item carry type, unit, and range | Contract-violating code will be generated |
| Does every module state the crosscutting concepts it follows | Each module will do it differently |
| Does every asynchronous connector define timeout, saturation, and retry | Behaviour under failure is undefined |
| Is every shared resource protected | A race condition remains |
| Does every stateful execution unit have a recovery path | It cannot resume after an interruption |
| Does every structural constraint have an executable check | The constraint will not hold |
| Does every task have a completion condition and a means of verification | "Done" becomes subjective |
| Does every quality requirement have a tactic and a measurement | The quality requirement stays on paper |

```yaml
lattice_l4:
  coverage: {total: 10, filled: 8, na: 0, tbd: 2}
  open: [{check: "shared resource protection", refs: [SR-002], question: "..."}]
```

---

## Coverage report (mandatory)

Report exactly this at the end of every run. Do not omit the numbers.

```
L1 elicitation  48 cells: filled 28 / derived 3 / na 12 / tbd 5
L2 scenario     9 UC x 7 axes: filled 51 / derived 0 / na 12 / tbd 0
L3 quality      9 characteristics: filled 6 / derived 0 / na 3 / tbd 0
L4 implementation 10 items: filled 8 / derived 0 / na 0 / tbd 2
AI-Ready        ready 23 / incomplete 5 / blocked 2
7 unresolved -> gaps.yaml
```

Never report completeness while `tbd` is non-zero. Present the unresolved list together with the
questions. `derived` is shown as its own column because closing by derivation is a better outcome
than leaving a question.

## Per-feature coverage

The unit of management is the feature, not the document. Aggregate coverage per feature and project
it into `views/features.md` (04 §Projections). A total-only report hides a feature that is entirely
empty behind the average.

## The lattice and the ban on invention

The lattice does not conflict with X-1. What it produces is not a requirement but the fact that a
cell is empty, plus the question that would close it.

| Allowed | Prohibited |
|---|---|
| "Confirmation needed on whether booking cancellation is required" | "Added a booking cancellation feature" |
| "The cancellation cutoff is undecided `[TBD]`" | "Assumed cancellation is allowed up to 24 hours before" |
| `verdict: na, reason: "internal tool, not subject to audit"` | Closing a cell as `na` without a reason |
