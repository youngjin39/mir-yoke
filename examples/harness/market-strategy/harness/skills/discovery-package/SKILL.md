---
name: discovery-package
description: "Orchestrate the full Discovery Package: run the owner interview, sequence the 7 role skills into the 7 sections, and keep the registers honest. The connective tissue of the harness's two engines (inward intent + outward intelligence).\n\nTrigger: discovery package, discovery, new idea, validate concept, product discovery, start discovery, GTM package\n\nRole: Lead orchestrator (assembles C-level / Market-Intel / Product Planner / Researcher / GTM / Critic)"
---

# Discovery Package

The harness's top-level orchestration skill. Produces and iterates the 7-section Discovery Package in `discovery/`. It does not replace the 7 role skills — it sequences them across the harness's two engines: the **inward / intent engine** (`c-level` decision support) and the **outward / intelligence engine** (`market-intel` evidence + memory).

## Use When
- A new product idea enters discovery, or an existing Discovery Package needs another iteration.
- The owner asks to "start discovery", "validate this concept", or "build the GTM package".

## First action — interview, do NOT research blind
Before any research, ask the owner four questions and write the answers into `discovery/discovery-package.md` §0:
1. The idea in 1–2 sentences.
2. What outcome = success.
3. Who they think it's for now (the assumed target).
4. What went wrong with targeting last time.

Then write the **Critic's strongest objection to the assumed target** before drafting anything else. Then run `c-level` (front): co-author the owner's intent read (they correct it) and name the **1–3 bets** the idea hinges on — these direct what the roles research.

## Re-entry (returning to an existing idea)
Before Step 1, run `decision-review`: read back the prior `decision-brief.md` + its target/founder pre-mortem + the named Test Card; record what the test actually returned into `decisions.md` as a **Learning Card** (hypothesis tested → observation → insight → action); **flip the tested assumption's `Evidence` cell** in `assumption-risk-register.md` (`none` → `have`) so `assumption-challenge` re-ranks and surfaces the next riskiest; record any **calibration delta** (a pattern in your own misjudgment) in a personal calibration log, if you maintain one. This closes the learning loop — the only mechanism that catches *systematic* mis-targeting.

## Workflow (sequence the roles — unified two-engine pass)
1. **§0 interview + C-level front** → capture verbatim; open with the Critic's objection; then run `c-level` (front): load your founder/operator profile, if you keep one, write the intent read + the 1–3 decision-agenda bets into §0.
2. **Gather (outward engine)** → run `market-intel`: recall your long-term memory store + `sources.md`, deep-search only the gap, run the customer-research method (JTBD switch interview + Mom-Test design) for the desire layer, apply the perspective library, capture provenance into `sources.md`, promote durable findings to your long-term memory store. `market-research` writes §3 from this; the C-level's scoring basis cells are populated from it.
3. **§2 target** first (it gates everything): run `target-definition` using needs-based segmentation → primary persona + anti-persona.
4. **§3 market** → run `market-research` → sizing + competitors from the gathered evidence; every number cites `discovery/sources.md`.
5. **§1 problem/opportunity** → synthesize from §2 + §3.
6. **§4 positioning** → run `positioning` (Dunford + the messaging-from-positioning bridge). Needs a validated §2 + the §3 gap.
7. **§5 GTM + §6 pricing** → run `gtm-plan`: stages-of-awareness + channel selection + GTM-motion (verify first) + CAC/LTV/payback sanity.
8. **§7 register** → run `assumption-challenge` continuously: it pulls every `ASSUMPTION` tag into `discovery/assumption-risk-register.md`, **maps on importance × evidence and surfaces the top-right (riskiest) assumption** for the C-level's Test Card, and issues the §2 sign-off (`validated` / `target-unvalidated`).
9. **C-level brief (back)** → run `c-level`: consume §1–§7 + the risk register, pick the single keystone decision (defaults to the target while `target-unvalidated`, go blocked), write `discovery/decision-brief.md` — opportunity space (2–3 needs), rank-flip headline, qualitative option matrix (hold 2–3 solution options where the keystone is a solution choice), best/worst, target pre-mortem, revenue path, founder-fit + founder pre-mortem, floored dissent, intent tension, recommendation + a **Test Card** (hypothesis/method/metric/threshold) on the riskiest assumption.
10. **Owner decision** → record each call + rationale + the **predicted** fields (confidence + the pre-mortem's "first thing that breaks") in `discovery/decisions.md`. Iterate.

Interaction model: one interview up front, then run to a **single review checkpoint at the brief** — not stop-for-input at every step.

## Invariants (enforce on every pass)
- Evidence over eloquence: no uncited fact. Each claim is `[cited]` (row in `sources.md`, with its domain-action) or `ASSUMPTION`.
- Challenge before agree: the package header stays `target-unvalidated` until the Critic signs off §2.
- Have a POV: the C-level forms and defends an opinion; it never dissolves into "it depends".
- Owner decides: the harness never finalizes a target/positioning/pricing call — it recommends; the owner's recorded decision closes it.
- Stay out of technical design: business/product-discovery artifacts only.

## Output
- A fully-linked, iterated `discovery/discovery-package.md` with `sources.md`, `assumption-risk-register.md`, `decisions.md`, and `decision-brief.md` kept in sync.
- Each iteration opens with the single highest-risk assumption and the Critic's current strongest objection.

## Related skills
`c-level`, `market-intel`, `target-definition`, `market-research`, `positioning`, `gtm-plan`, `assumption-challenge`.
