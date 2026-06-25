---
title: Market-economic perspective library
keywords: [perspective, framework, five-forces, jobs-to-be-done, mom-test, tam-sam-som, pricing, van-westendorp, positioning, competitive-intelligence, customer-research, segmentation, awareness, channel, acquisition-economics, assumptions-mapping, test-card, learning-card, gtm-motion, opportunity-space, demand-test]
related: []
created: 2026-06-20
last_used: 2026-06-20
---

# Market-economic perspective library

The fixed lenses `market-intel` applies to every idea (so they are never re-derived). Grounded in an adversarially-verified research pass (21 confirmed / 4 refuted), extended with established GTM/customer-research method (ADR-60). Apply; do not re-research.

1. **Competitive structure — Porter's Five Forces.** Analyze the industry *structure* (extended rivalry: rivals + buyers + suppliers + entrants + substitutes), not just direct rivals. Source: HBR 2008 (Porter). [high]
2. **Operating loop — Competitive Intelligence cycle.** plan → gather → analyze → disseminate → feedback; rerun, not rebuilt. Source: Wikipedia (Competitive Intelligence). [high]
3. **Demand / needs — Jobs-to-be-Done.** Make the customer's "job" the unit of analysis (not product, not demographic); express needs as measurable desired outcomes. Source: Strategyn/Ulwick. [high — originator source]
4. **Demand validation — The Mom Test.** Separate real purchase intent from polite/biased feedback; ask about the past and specifics, not opinions about the future. Source: momtestbook (Fitzpatrick), rooted in Blank's Customer Development. [high]
5. **Market sizing — TAM/SAM/SOM, bottom-up vs top-down.** Prefer bottom-up: TAM = ARPU × potential customers, summed across segments; cross-check top-down. Source: corroborated across 7+ sources. [high]
6. **Pricing — value-based + Van Westendorp.** Anchor on customer value, not cost; estimate the acceptable range with the four canonical Van Westendorp questions. Source: Simon-Kucher / Wikipedia. [high]
7. **Positioning — Dunford's five components.** Competitive alternatives, unique attributes, value+proof, target characteristics, market category (+ optional trend). The foundation; precedes GTM (may iterate with it). Source: Dunford, *Obviously Awesome*. [high]
8. **Purchase drivers — functional + emotional + social.** Purchase is multi-conditional: necessity & convenience (functional), desire & emotion (emotional), identity & belonging (social). Anchored in JTBD's job dimensions. **A tunable operating assumption (not verified):** the emotional/desire layer is stable on a ~10-year horizon. Source: JTBD (Christensen/Ulwick) for the dimensions; the 10yr horizon is a tunable parameter. [dims: high · horizon: owner-assumption]

## Customer-research method (ADD — produce the desire layer, don't assume it)
9. **Customer-research instrument — JTBD switch/timeline interview + Mom-Test question design.** Produce the desire / "who is this for" insight rather than asserting it. Map the **forces of progress** over the timeline of a real past switch — push of the situation, pull of the new way, anxiety of change, habit of the present — and design every question about the customer's past and specifics, never opinions about the future or pitches. Source: JTBD switch interview (Moesta/Klement, building on Christensen) + The Mom Test (Fitzpatrick). [JTBD + Mom Test high (grounded in ADR-59); the switch-interview variant — verify specifics in use]
10. **Needs-based segmentation.** Cut the market by job/need/desired-outcome, not demographics or firmographics; feeds `target-definition`'s persona and directly attacks the "who is this for" failure class. Source: JTBD outcome-based segmentation (Ulwick). [needs-based principle: high · the specific segmentation procedure — verify]

## GTM / outbound method (ADD — the operator's primary intent: sell, awareness, income)
11. **Awareness / demand generation — stages of awareness.** Plan for getting *noticed*, not just for channels: unaware → problem-aware → solution-aware → product-aware → most-aware; the message must meet the prospect at their stage. Source: Eugene Schwartz, *Breakthrough Advertising* (stages of awareness); AIDA as the funnel frame. [established]
12. **Channel selection — channel-fit + traction sweep.** Pick channels where the validated persona already is; sweep the full set of traction channels rather than defaulting to the familiar one — distribution is the solo founder's usual point of death. Source: *Traction* / Bullseye framework (Weinberg–Mares). [established; verify specifics in use]
13. **Acquisition economics — CAC / LTV / payback.** A coarse sanity ratio that *gates* channel viability: rough CAC vs. lifetime value and the payback period; if it does not close, the channel is not viable regardless of fit. Source: established unit-economics practice. [established]
14. **GTM-motion selection — keyed to ACV / buyer / time-to-value.** <$5K ACV → PLG (self-serve, individual buyer); $5–25K → hybrid PLG+SLG; $25K+ → sales-led (multi-stakeholder). CAC sanity: PLG ≈ $100–500 vs sales-led $5K–50K. Time-to-value is the PLG binary (aha in the first session); hybrid is the 2026 default. `market-intel` confirms the specific motion per idea. Source: practitioner-convergent (digitalapplied / kalungi / momentumnexus). [**practitioner-convergent · medium** — not academic; carry the caveat]

## Experiment & test method (ADD — ADR-62: validate, don't just decide)
15. **Assumptions map — importance × evidence.** Map every load-bearing assumption on two axes: importance ("if wrong, the idea fails") × evidence ("have / none"). **Test the top-right (high-importance, no-evidence) first** — that is where uncertainty is most expensive. Lives in `assumption-risk-register.md`; worked one-per-pass. Source: Strategyzer assumptions-mapping. [high]
16. **Test Card — every test is falsifiable.** A test names four things: *hypothesis* (what must be true) · *method* · *metric* · *success threshold*. A test with no metric/threshold is not a test. Source: Strategyzer test-card. [high]
17. **Learning Card — convert results to decisions.** After a test: *hypothesis tested · observation · insight · action.* The persistent experiment history; lives in `decisions.md`, written at `decision-review`. Source: Strategyzer learning-card. [high]
18. **Demand tests — cheapest ways to test real intent.** Smoke test / fake-door / landing-page (measure click-through / sign-up / pre-order against a threshold) — concrete cheapest-test methods for the Test Card. Source: kromatic. [secondary]
19. **Opportunity space before solution (Torres OST).** Name the 2–3 top customer NEEDS (opportunity layer) before committing to one solution (keystone); hold 2–3 solution options before converging. The opportunity layer sits above the solution layer. Source: producttalk OST. [high]

## Temporal classes (decay-aware reuse)
- **Volatile** (market size, competitors, prices, trends, channels): short half-life → carries its `date pulled`, confidence decays with age, re-validated when STALE. Volatile evidence stays **per-idea in `sources.md`**; `market-intel` re-runs `deep-research` on any stale, still-load-bearing volatile claim each pass.
- **Durable** (desire / emotion / motivation — the *why* of purchase): long half-life (~10yr, owner's operating assumption — tunable, not a verified fact). Durable insight is the **only** class promoted to your long-term memory store.
- **The mechanism is code-free.** The promotion gate (durable-only → long-term store; volatile → re-validate in `sources.md`) is what keeps memory from accumulating stale facts. A hard auto-expiry is an optional later extension (add a `valid_to`/`decay_class` field to your ingest path plus a GC runner) — not required for this behavior.

## Do NOT cite as fact (failed verification)
- "Timing is the #1 startup success factor" / "Timing 42%…" (Bill Gross) — REFUTED. Timing/"why-now" is a *qualitative* prompt only; no verified quantitative framework yet (open slot: market-readiness / adoption-curve).
- "Ten canonical pricing models" — REFUTED. Use #6.
- Evidence-based management "three evidence sources" — REFUTED. Use the four-source CIPD model (scientific literature, organizational data, professional expertise, stakeholder values).

## Open slots (flagged, not yet grounded)
- A durable "why-now" / market-timing framework.
- (Resolved) GTM-motion taxonomy → lens 14, keyed to ACV/buyer/time-to-value at practitioner-convergent confidence with the caveat (ADR-62).
