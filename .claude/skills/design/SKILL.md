---
name: design
description: Hard gate before coding. Compare 2-3 alternatives, surface trade-offs, get user approval.
trigger: design, brainstorm, brainstorming, architecture, new feature
---

# design

Loaded when the request is "design X", "brainstorm Y", "architecture for Z", or "new feature N".

## Purpose

Before any non-trivial code is written, produce a small alternatives matrix that the user can react to. The trap this skill prevents: agent picks the first plausible design, writes 800 lines, then discovers it does not match the user's mental model.

## Output shape

A short table (3 columns × 3-5 rows). One row per alternative.

| | Alt A | Alt B | Alt C |
|---|---|---|---|
| Idea (one line) | … | … | … |
| Cost to build | … | … | … |
| Cost to maintain | … | … | … |
| Failure mode | … | … | … |
| Reversibility | … | … | … |

Then a single sentence recommending one — with the lens you used. Recommendations without a stated lens get pushed back.

## What this skill does NOT do

- Write code.
- Run tests.
- Decide unilaterally.

The user is in the loop. This skill produces a thing the user can react to, not a thing the user has to ratify.

## Counter-narrative requirement

Every recommendation includes a one-line "the case against this": the strongest argument someone would make for picking a different alternative. If you cannot make that argument, the alternatives matrix was not honest.

## Exit criteria

- User picks an alternative (explicit "go with B" or paraphrase).
- Or the user adds a constraint that collapses the matrix.

Do not start writing code until one of those happens.
