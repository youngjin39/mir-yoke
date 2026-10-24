# Recovery diagnosis and optional reframing

Inspired by Q00/ouroboros at 5520a3e. Content re-checked at 7783d9f on 2026-10-24.

This is report-only advice for Main-directed or user-reported stalls or repeated failure. Reuse the
[SPINNING report](spinning-report.md) and its declared attempt window; do not add
another detector, ledger, retry loop or threshold. Main chooses any next action.

## Failure vocabulary and evidence

Classify provisionally: validation (invalid input or unmet precondition), execution
(failed operation or timeout), system (resource or transport failure), semantic
(result misses the intended behavior). Mark an unknown cause Unknown. Suggest a
recovery class: correct input; investigate a transient condition; repair a structural
cause; clarify intent; or reframe the approach. A transient label does not prove a
retry is safe. Preserve completed work and identify side effects before proposing
resume, rollback or a changed attempt; none is automatically authorized here.

When an already-authorized shell check pipes output, use `set -o pipefail` where
supported and retain producer and filter exit statuses, stderr and original output.
A successful formatter or `tee` is not proof that its producer passed. If the shell
cannot preserve pipeline evidence, inspect stages separately and report that limit.

## Stagnation patterns and lenses

| Pattern | Evidence to report | Optional lens affinity |
| --- | --- | --- |
| SPINNING | Use the existing report and unchanged failure signature. | hacker |
| OSCILLATION | Attempts switch between alternatives without resolving the conflict. | simplifier, architect |
| NO_DRIFT | Changed attempts leave the declared outcome gap unchanged. | researcher, architect |
| DIMINISHING_RETURNS | Comparable attempts yield progressively smaller useful gains. | researcher, simplifier |

These are qualitative diagnoses, not model-score gates or universal numeric rules.
- **hacker:** suggest a small reversible probe that challenges a stuck implementation assumption.
- **researcher:** identify missing evidence and one check that could distinguish explanations.
- **simplifier:** remove incidental complexity while preserving requirements and safety.
- **architect:** reconsider a boundary or dependency when local changes keep conflicting.
- **contrarian:** challenge the goal or premise; potentially useful for all four patterns.

Return the observed pattern, evidence, uncertainty, an optional lens and a bounded
proposal to Main. Lenses are thinking prompts, not agents, automatic persona rotation,
model escalation or permission to execute a recovery.
