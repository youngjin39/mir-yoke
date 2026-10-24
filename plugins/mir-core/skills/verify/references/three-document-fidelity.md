# Optional three-document fidelity audit

Inspired by fn-opt/dryforge at f5aa6d7.

Use for consequential work that already has handoff, spec and plan documents.
Use their actual repository-owned paths and authority; do not require these
artifacts universally or generate a second document set just to run this checklist.

- **Intent preservation:** compare handoff to spec for dropped, weakened or altered
  goals, boundaries, invariants and accepted trade-offs. Cite both documents and the
  original decision evidence where available; mark missing evidence unknown.
- **Spec-over-plan precedence:** the spec defines the result; the plan defines the
  route. Surface disagreements and bring the plan into line with the governing spec
  within current authority; do not rewrite intent to fit an implementation shortcut.
- **Completeness:** map requirements to plan steps and their verification evidence;
  identify uncovered requirements and steps with no requirement, including negative
  constraints. A heading mentioning a requirement is not proof of its preservation.
- **Non-reconstructible intent:** preserve owner-only choices, reasons, exclusions and
  authority limits in the handoff. A future executor must not infer them from code.
  Unsettled intent stays unresolved until the authorized decision-maker answers.

For a fresh perspective, suggest an independent fresh reviewer who did not author
these documents to audit intent and omissions, using pinned documents and available
source evidence. Reuse an authorized reviewer; absence is an unperformed advisory
check, not permission to create an agent or fabricate a result. Give the Main cited
findings and unknowns as advisory evidence, alongside deterministic test results.

This checklist is never an LLM acceptance gate. Neither author agreement nor a
reviewer's verdict substitutes for required deterministic checks or owner decisions.

## Optional artifact-only executability review

Main may ask an already-authorized fresh reviewer with no dialogue context to read
only the finished repository-owned handoff, spec and plan, plus explicitly linked
documents available in that artifact set. Ask: could an executor carry out the work
from these documents alone, without guessing intent, authority, dependencies or
acceptance checks? Check whether references resolve, steps have preconditions and
expected outcomes, and unresolved choices have an owner and an explicit stop point.
Return executable, executable with listed gaps, or not executable, citing each
missing instruction and its consequence. Do not fill gaps from conversation memory.
This artifact-only judgment is advisory; Main adjudicates repairs and required
checks. An unavailable reviewer is unperformed evidence, never an LLM hard gate.
