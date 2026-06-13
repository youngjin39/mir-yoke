---
description: Audit whether a design serves its original purpose via independent subagents (does not touch code)
---

# /audit-design-fit

Audit whether the **design itself** serves the repository's stated purpose. This command does not check code against design; it questions whether the design, even if perfectly implemented, would deliver the purpose. All audit work runs in role-isolated subagents.

## Inputs to load

- Purpose / mission statement: repository `CLAUDE.md`, root `README.md`, PRD if present.
- Design document(s): `$ARGUMENTS` path, else most recent design under `docs/decisions/`, `docs/design/`, `tasks/plan*.md`, `ARCHITECTURE.md`.
- Any user-recorded constraints in repo memory or ADRs.

If purpose or design is ambiguous, ask the user once for clarification before dispatching.

## Mandatory subagent dispatch

Run three independent passes; spawn all three in a **single message with multiple Agent tool calls** to run concurrently. None of them edits files.

Pass 1 — minimum-viable-requirements derivation:
- Subagent: `Plan`.
- Brief: "Cold derivation. Given the stated purpose `<purpose summary + path>`, enumerate the minimum capabilities, invariants, and constraints the system must satisfy to honour that purpose. Do not read the design. Produce a requirements list with rationale."

Pass 2 — design-vs-purpose cross-check:
- Subagent: `codex-final-reviewer` (Codex CLI, read-only, cold context).
- Brief: "Cold review. Read `<design path>` and `<purpose source>`. Identify: capabilities the design omits relative to the purpose, capabilities the design adds beyond the purpose, design choices that are misaligned with the purpose's spirit, and unstated assumptions. Cite design section refs."

Pass 3 — over-engineering and missing-core-path audit:
- Subagent: `general-purpose`.
- Brief: "Cold audit of `<design path>`. Flag speculative scope, premature flexibility, abstractions without two concrete consumers, and any core happy-path that the design under-specifies. Do not propose new design — only flag."

## Synthesis

After all passes return:
1. Cross-reference Pass 1's derived requirements against Pass 2's coverage report. Any requirement in Pass 1 missing from the design becomes a BLOCKER candidate.
2. Combine Pass 2 and Pass 3 to identify the bias direction: under-coverage vs over-engineering. Surface both lists explicitly.
3. Classify each finding as BLOCKER / WARN / NIT against the purpose, not against the design.

## Corrective edits (design doc only)

If the audit recommends design changes:
1. Draft an edit set as `before → after` snippets keyed to design sections.
2. Dispatch a **fresh** subagent (`executor-agent` or `general-purpose`, not used in any audit pass) to apply the edit set to the design doc.
3. Do not change code. If the audit's logical conclusion is "code must change," the user must invoke `/develop-from-design` or `/verify-against-spec` afterwards — this command stays out of code.

## Independent re-audit

After edits land, dispatch a newly spawned `codex-final-reviewer` (not used in Pass 2 or anywhere else above) to re-audit the revised design against the purpose. Verdict required.

## Completion criteria (continue until ALL hold)

- Every Pass 1 requirement is covered by the design, or explicitly deferred with user acknowledgement.
- Pass 2 reports zero BLOCKER misalignment after the edit set lands.
- Pass 3's flagged over-engineering items are either removed from the design or acknowledged with a one-line rationale.
- The independent re-audit returns a clean verdict.

## Halt conditions

- Purpose statement is contradictory or absent → stop, ask the user to define purpose before continuing.
- A finding requires choosing between two purpose readings → stop, surface both readings.
- Edits would require deleting design that's already implemented in code → stop, the user must decide whether to deprecate or refactor; this command does not touch code.

## Output to user

Final report, in the user's working language, contains:
- Purpose source(s) used.
- Pass 1 derived requirements (short list).
- Pass 2 misalignment findings.
- Pass 3 over-engineering and under-specification flags.
- Edits applied to the design doc (diff summary).
- Independent re-audit verdict.
- Open questions or halts.
