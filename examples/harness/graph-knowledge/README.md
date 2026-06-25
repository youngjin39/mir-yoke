# graph-knowledge

Opt-in example-harness for **knowledge navigation over large corpora and
personal-knowledge repos**. Two skills, distilled from a real personal-knowledge
harness, that make a big body of files cheap to query and a hard decision worth
arguing about.

## Suited repo type

`personal_knowledge` -- any repo that is mostly a corpus you read and reason
over: a large codebase, a notes/PDF/paper collection, a second-brain vault, or
a decision journal. The skills help you query it without burning tokens and
think through it without an echo chamber.

## What it provides

| skill | role |
|---|---|
| `graphify` | Automated knowledge-graph layer over a large codebase or doc corpus -- graph-first navigation (~70x fewer tokens per query) instead of raw `grep`/`Glob`. Wraps the external `graphifyy` tool. |
| `think` | Think-Tank sparring-partner mode -- pushes back before agreeing, names weaknesses first, runs thinking lenses and a confirmation-bias blocker, and refuses to hand over the conclusion. |

## How to apply

1. Copy `harness/skills/*` into your repo's `.claude/skills/`.
2. For `graphify`, install the external tool in your own terminal:
   `pip install graphifyy && graphify install` (note: the package is
   **graphifyy**, two y's). This adds the `/graphify` command and a global
   PreToolUse routing hook. The skill degrades to a no-op if the tool isn't
   installed -- it just hands you the install command.
3. `think` needs no setup; it activates from its triggers when you share a
   concern or decision.

## Notes

- `graphify` is an **automated, machine-generated** read-optimization layer. It
  complements -- it does not replace -- any hand-curated knowledge docs you
  keep. Keep Graphify's auto-generated pages at repo root as raw sources; distill
  anything worth keeping into your curated docs by hand, with a citation.
- Only the two generically reusable skills were extracted; the source repo's
  private configuration and personal content were intentionally excluded.
