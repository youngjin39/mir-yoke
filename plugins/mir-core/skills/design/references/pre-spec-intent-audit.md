# Pre-spec intent audit

Inspired by fn-opt/dryforge at f5aa6d7.

This optional advisory recipe supports Main before specification freeze. Use an
independent reviewer only when authorized; this adds no automatic review gate.

1. Give the reviewer the scoped dialogue, intent authority, any draft specification
   and complete Decision Surface, including every disposition and its evidence.
   Include confirmed, derived, assumed, open, conflict, tunable and inapplicable
   items rather than selecting only disputed choices.
2. Compare each disposition against the dialogue and stated goals. Challenge an
   unsupported confirmation, derivation or exclusion; identify omitted decisions
   whose answers could change behavior, scope, authority or verification.
   Distinguish missing evidence from disagreement with an explicit owner choice.
3. Return concise findings with the affected decision, supporting passage or missing
   evidence, likely consequence, and a proposed correction or owner question.
   Main brings findings and unresolved questions to the owner before freeze;
   reviewer agreement cannot substitute for the owner's decision.
4. After the owner responds, update the affected dispositions and specification.
   Main may request one bounded re-check of those decisions and their dependencies.
   Record remaining uncertainty explicitly; do not turn the re-check into an
   indefinite review loop, numerical threshold or mandatory LLM approval gate.
