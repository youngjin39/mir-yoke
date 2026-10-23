# Advisory consensus for disputed reviews

Inspired by ADR-58 item 1.

Use only for disputed high-impact reviews where a bounded second perspective can
clarify evidence. Set the disputed claim, source revision, evidence and review budget
before starting; do not turn routine review into a standing panel or voting loop.

Reuse existing reviewers in three roles; add no new packaged agents:

- **Advocate:** state the strongest evidence-supported case for the proposed change,
  naming the requirement it meets and the limits of that evidence.
- **Adversarial reviewer:** challenge that case with concrete counterexamples,
  boundary failures or missing checks; distinguish hypotheses from verified defects.
- **Judge:** compare both cases against the same requirement and source evidence;
  give an advisory verdict with reasons, unresolved disagreements and next checks.

Keep authorship and role independence explicit. If independent reviewers are not
available or authorized, report the limitation; a single author's role-play is not
independent consensus. No majority vote or confidence score establishes correctness.

Record the compact result in the existing review evidence, optionally in an already
supported review-rounds field. Do not impose a schema or a new evidence ledger.
The judge's verdict is advisory; deterministic checks remain the only hard blockers.
The panel grants no approval, merge, escalation, dispatch or execution authority.
Unresolved policy choices go to the owner through the Main; the panel cannot decide
owner intent or waive deterministic failures.
