---
name: code-review
description: "Code review and quality check. Trigger: code review, pull request review, quality check, merge check, post-completion. Architecture review routes to bluebricks."
context: fork
allowed-tools: Read, Grep, Glob, Bash
---

# Code Review

## Review policy

- Review the bounded diff directly; use an independent reviewer when uncertainty, blast radius, or self-approval risk justifies it.
- Primary correctness evidence is the smallest executed check that can fail for the changed behavior.
- Findings require a verified file and line citation. A plausible pattern without source evidence is not a finding.

## Workflow

1. Read the user request, the current task plan when present, and `git diff` to pin the intended scope and protected boundaries.
2. Identify changed behavior, its callers and consumers, persistent-state boundaries, permission changes, and platform assumptions.
3. Inspect each changed file for correctness, error handling, security, naming, duplication, unnecessary complexity, transaction safety, and source-of-truth drift.
4. Run or inspect the smallest relevant verification. Record missing tools or unrunnable checks as unevaluated, never as passes.
5. Re-read every cited line before including the finding. Remove pattern matches that do not reproduce in context.
6. Classify findings as P0 (critical), P1 (high), or P2 (low), and assign one scope status: `fix-now`, `reroute`, `escalate`, `user-confirm`, or `false-positive`.
7. Give every P0 a concrete alternative and recommendation. If no alternative exists, state the technical reason.
8. Report findings first; finish with counts, verification evidence, residual risks, and a `Sound` or `Changes requested` verdict.

## Trivial documentation pass

A direct single-pass review is sufficient only when the diff is at most ten lines, changes no executable or structured-data file, changes no instruction/harness/task/config/schema surface, and cannot affect behavior. State that classification explicitly; ambiguity means the normal workflow applies.

## Finding format

| File:Line | Severity | Finding | Evidence | Scope status | Alternative | Recommendation |
|---|---|---|---|---|---|---|
| `path:line` | P0/P1/P2 | Concrete defect | Verified source and impact | fix-now/reroute/escalate/user-confirm | Specific alternative | Preferred action and reason |

## Review checklist

- Errors and rejected inputs preserve the documented runtime contract.
- Inputs cannot cross command, path, SQL, template, or credential boundaries unsafely.
- Multi-step writes are atomic or have an explicit recovery path.
- Public interfaces, schemas, generated files, and their consumers stay in sync.
- The change does not silently widen permissions or external-write authority.
- New behavior has proportionate regression evidence.
- The diff contains no unrelated cleanup or pre-existing user work.

## Banned verdict language

Do not substitute confidence phrases such as “looks good,” “should be fine,” or “probably OK” for evidence.
