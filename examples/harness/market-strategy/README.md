# market-strategy

Opt-in example-harness for **product / market discovery and go-to-market
strategy**. Eight role-skills, distilled from a real product-strategy harness,
that turn a raw idea into an evidence-backed Discovery Package: who it's for,
the market, positioning, GTM, pricing, and a risk register — with an adversarial
critic that gates the target.

## Suited repo type

`product_market` — any repo where you are validating a product/market pair:
defining the target audience, sizing the market, positioning against
alternatives, planning go-to-market, and stress-testing assumptions before you
build.

## What it provides

| skill | role |
|---|---|
| `discovery-package` | Lead orchestrator — sequences the role skills into a 7-section Discovery Package |
| `c-level` | Executive decision advisor — scores options, runs pre-mortems, commits to a call |
| `market-intel` | Evidence engine — owns the perspective library, customer research, evidence memory |
| `market-research` | TAM/SAM/SOM sizing, competitive landscape, pricing benchmarks, trends |
| `target-definition` | Defines primary persona + anti-persona with evidence |
| `positioning` | Positioning statement via Dunford's five components |
| `gtm-plan` | Awareness, channels, launch sequence, pricing hypothesis, CAC/LTV sanity |
| `assumption-challenge` | Adversarial critic — maintains the assumption risk register, holds target veto |

It also ships `harness/docs/perspectives.md` — a reusable market-economic
**perspective library** (Five Forces, JTBD, Mom Test, TAM/SAM/SOM, Van
Westendorp pricing, Dunford positioning, stages of awareness, …) that the skills
apply rather than re-deriving each time.

## How to apply

1. Copy `harness/skills/*` into your repo's `.claude/skills/`.
2. Copy `harness/docs/perspectives.md` into your repo's `docs/` (the skills
   reference it at `docs/perspectives.md`).
3. Run `discovery-package` to start a discovery pass; it sequences the other
   skills and writes its outputs to a `discovery/` directory.

## Notes

- The skills reference a long-term memory store and an optional founder/operator
  profile. Both are optional — keep them in your own project docs if you want
  the calibration loop; the skills degrade gracefully without them.
- The source repo's personal founder profile and calibration log were
  intentionally left out (private data).
