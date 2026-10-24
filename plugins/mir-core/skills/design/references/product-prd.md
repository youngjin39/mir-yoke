# Optional product-focused PRD recipe

Inspired by Q00/ouroboros at 5520a3e. Content re-checked at 7783d9f on 2026-10-24.

Use when the owner asks for product requirements. Reuse the current intent cursor
and elicitation rules; a PRD request does not authorize implementation or delivery.

1. Identify the target user, unmet problem, current workaround and evidence that it
   matters. Separate observed needs, owner choices and untested product assumptions.
   In brownfield work, inspect relevant existing journeys and constraints without
   treating current behavior as proof of desired intent.
2. Clarify the desired user outcome, why now, stakeholders and decision owner. Ask
   only unresolved consequential questions; do not turn technical tuning into an
   owner interview. Keep unanswered decisions visible with their effect on scope.
3. Define in-scope journeys and non-goals, including actors, entry conditions,
   successful outcome, failure/exception paths and data or permission constraints.
   Rank essential outcomes and identify dependencies and rollout assumptions.
4. Propose success measures with baseline, target, measurement source and time window
   where evidence supports them; otherwise mark each missing value open. Separate
   business success from acceptance criteria for observable product behavior.
5. Produce a compact PRD: problem and evidence; users and journeys; goals/non-goals;
   prioritized requirements with stable identifiers; acceptance examples; success
   measures; constraints, risks, dependencies and unresolved owner decisions.
6. Review each requirement against a user need and each acceptance example against
   a requirement. Preserve disagreements and product trade-offs for Main; a reviewer
   opinion is advisory. Hand settled intent to spec-architect only when requested.

Do not add a second planning system, mandatory interview engine or model-score gate.
