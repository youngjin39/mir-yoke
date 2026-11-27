---
name: code-review
description: "Diff and PR review, code quality and merge checks. Trigger: code review, pull request review, quality check, merge check, repository audit. Completion evidence and spec compliance route to verify; architecture analysis routes to bluebricks."
context: fork
allowed-tools: Read, Grep, Glob, Bash
---

# Code Review

Routing precedence: diff and PR review → code-review; completion evidence and spec compliance → verify; architecture analysis → bluebricks.

Audit precedence: code-quality, debt and risk audit of code → code-review; periodic multi-item repository checkup → repo-maintenance; instruction-document and registry governance → governance; AI-readiness review → efficiency.

## Review policy

- Review the bounded diff directly; use an independent reviewer when uncertainty, blast radius, or self-approval risk justifies it.
- Primary correctness evidence is the smallest executed check that can fail for the changed behavior.
- Findings require a verified file and line citation. A plausible pattern without source evidence is not a finding.

## Workflow

1. Read the user request, the current task plan or scenario card when present, and `git diff` to pin the intended scope, acceptance criteria, and protected boundaries.
2. Check behaviour scenarios first: missing rows for touched flows (entry point, failure or late result, lifecycle, concurrency, platform), unreachable rows, wrong expected outcomes, and mocks that disagree with their real producer. Identify changed behavior, its callers and consumers, persistent-state boundaries, permission changes, and platform assumptions.
3. Inspect each changed file for correctness, error handling, security, naming, duplication, unnecessary complexity, transaction safety, and source-of-truth drift.
4. Run or inspect the smallest relevant verification. Record missing tools or unrunnable checks as unevaluated, never as passes.
5. Re-read every cited line before including the finding. Remove pattern matches that do not reproduce in context.
6. Apply the severity rubric and assign one scope status: `fix-now`, `reroute`, `escalate`, `user-confirm`, or `false-positive`.
7. Report findings first; finish with counts, verification evidence, residual risks, and a `Sound` or `Changes requested` verdict.

## Trivial documentation pass

A direct single-pass review is sufficient only when the diff is at most ten lines, changes no executable or structured-data file, changes no instruction/harness/task/config/schema surface, and cannot affect behavior. State that classification explicitly; ambiguity means the normal workflow applies.

## Severity rubric

Use the acceptance criteria that govern the reviewed scenario, including any
recorded owner ruling or allowed deviation. Where parity governs, matching the
pinned reference satisfies that criterion. If the criterion is missing or the
applicable sources conflict without a governing ruling, report a scope question
without severity. Classify any independently demonstrated violation on its own.

Apply the highest severity supported by the observed effect.

| Severity | Observed effect |
|---|---|
| **P0** | Data loss, an effect on the wrong process or file, or a false red-to-green in normal use (the operation or gate reports success despite the underlying failure). |
| **P1** | A stated acceptance criterion is broken on a supported path. |
| **P2** | A bounded functional defect or evidence gap. |
| **P3** | A low-impact documentation or diagnostic defect with the expected outcome preserved. |

## Finding format

A defect states the concrete input, the wrong outcome and the violated
requirement. Put preferences in a separate suggestion list with status
`user-confirm`. Give every finding a stable ID in its first round (for example,
`R1-01`) and carry it forward even if the file line or severity changes.
On re-review, classify prior findings as **closed** when evidence shows the fix or
a governing ruling resolves them, and as **recurring** while they remain open
or if they reappear. Mark newly identified defects **new** and give them new IDs.
Report counts by status. For a fix, cite the executed check and observed result as
closure evidence. A fix to a finding gets rows for the flow it changes and is
reviewed again when it changes state or asynchronous behaviour. Repair ownership
and the round limit follow the `mir-lifecycle-hooks:runtime-continuity` default work method.
Keep the reviewer's submitted severity unchanged; the orchestrator records its ruling separately and cites the rubric clause when lowering or rejecting a finding.
Close a finding from reading only after its check has run; record the result.
For recurrence tracking, use `mir-core:repo-maintenance`'s `references/improvement-loop.md` when available.

| ID | File:Line | Severity | Scenario and finding | Evidence | Scope status | Smallest fix | Closure evidence |
|---|---|---|---|---|---|---|---|
| `R1-01` | `path:line` | P0/P1/P2/P3 | Input, wrong outcome, violated criterion | Verified source and impact | `fix-now` | Specific change | Check and result when fixed |

For P0, also record a concrete alternative and recommendation, or explain why no
alternative is viable.

## Review checklist

- Errors and rejected inputs preserve the documented runtime contract.
- Inputs cannot cross command, path, SQL, template, or credential boundaries unsafely.
- Multi-step writes are atomic or have an explicit recovery path.
- Public interfaces, schemas, generated files, and their consumers stay in sync.
- The change does not silently widen permissions or external-write authority.
- New behavior has proportionate regression evidence.
- Every scenario row has executed evidence or is reported open.
- The diff contains no unrelated cleanup or pre-existing user work.

## Banned verdict language

Do not substitute confidence phrases such as “looks good,” “should be fine,” or “probably OK” for evidence.

For a requested repository audit or manual shortcut review, use [audit and debt guidance](references/repository-audit-and-debt.md).

For disputed high-impact reviews, use the [advisory consensus panel](references/advisory-consensus.md).

For ordinary relevant diffs, apply the [bounded load, performance and lean checks](references/repository-audit-and-debt.md) to changed paths and callers.
