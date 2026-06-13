---
description: Multi-pass review of authored code via independent subagents (bias-free, loop until complete)
---

# /review-code

Review authored code in this repository through **bias-free subagent dispatch**. The orchestrating Claude session MUST NOT review its own code; reviews and repairs are delegated to fresh subagents only.

## Scope resolution

Determine the review target in this order:
1. If `$ARGUMENTS` names a path, commit range, PR, or branch → use it.
2. Else if there are staged or uncommitted changes → use the working diff.
3. Else if the branch is ahead of `main` → use `git diff main...HEAD`.
4. Else ask the user for an explicit scope (single short text question — no picker UI).

State the resolved scope before dispatching.

## Mandatory subagent dispatch (no self-review)

Run **at least two independent review passes**, each in a separate subagent with no shared history.

Pass A — primary review (parallel-launchable):
- Subagent: `codex-final-reviewer` (Codex CLI, read-only).
- Brief: "Cold review. You have no context from prior conversation. Audit <scope> for correctness, design alignment, regression risk, hidden assumptions, security, and path/import integrity. Classify findings as BLOCKER / WARN / NIT. Report findings only — do not edit."

Pass B — secondary axis (parallel with A):
- Subagent: `quality-agent`.
- Brief: "Independent quality pass on <scope>. Focus on style/clarity, error handling appropriateness, test coverage gaps, and any failure modes Pass A is likely to miss. Same classification scheme. Do not coordinate with Pass A."

Launch A and B in a single message with two Agent tool calls so they run concurrently.

## Synthesis and repair loop

1. Merge findings from A + B. Deduplicate. Surface conflicts between the two reviews explicitly.
2. For every BLOCKER and every WARN you decide to fix, dispatch `executor-agent` (Codex execution lane) with a narrow, file-scoped repair brief. One repair batch per logical slice. Never include scope outside the original review target.
3. After a repair batch lands, dispatch a **freshly spawned** `codex-final-reviewer` subagent (not the same one as Pass A) to re-verify the repaired files. Cold context required — this is the anti-bias safeguard.

## Path-change safety

When repairs touch import paths, config paths, script invocation paths, or relative references:
- The repair brief MUST list every caller of the moved/renamed symbol/path.
- The re-verification subagent MUST confirm caller integrity, not just the changed file.

## Completion criteria (continue until ALL hold)

- Zero unresolved BLOCKER findings across all passes.
- Every WARN is either fixed and independently re-verified, or explicitly acknowledged with a one-line rationale.
- The most recent re-verification was performed by a subagent that did not participate in the repair.
- No scope leakage: the diff after repairs stays within the original review target unless the user expanded it.

## Halt conditions (stop and report — do not proceed)

- Same finding survives 3 repair attempts → stop, report root-cause hypothesis.
- Reviewer subagents disagree on a BLOCKER and cannot be reconciled → stop, surface both opinions to the user.
- Repair would require touching files outside the review scope → stop, ask the user before expanding.

## Output to user

Final report, in the user's working language, contains:
- Scope reviewed (resolved value).
- Findings table: severity, file:line, summary, status (fixed / acknowledged / deferred).
- Files changed by the repair loop.
- Independent re-verification result (subagent id + verdict).
- Any halts or open questions.
