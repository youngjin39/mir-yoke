---
description: 설계를 분야별 서브에이전트로 세분화 분석·수정·재검토 (완료까지 반복)
---

# /analyze-design

Subdivide a design document and analyze each slice through **role-isolated subagents**. Modifications go to the design doc only — this command does not touch product code.

## Target resolution

Resolve the design target in this order:
1. If `$ARGUMENTS` names a path (ADR, PRD, RFC, design note) → use it.
2. Else search `docs/decisions/`, `docs/design/`, `tasks/plan*.md`, `ARCHITECTURE.md` for the most recently modified candidate and confirm with the user (single short text question).
3. Else ask the user for an explicit path.

Read the target end-to-end before dispatching. Do not paraphrase from memory.

## Slicing

Partition the design into independent slices. Use whichever of these axes apply to the document:
- Data model and persistence boundaries.
- Control flow / sequencing / lifecycle.
- External interfaces (CLI flags, MCP tools, HTTP, file artifacts).
- Failure modes and recovery.
- Security, permissions, sandbox boundaries.
- Performance and resource budgets.
- Migration and backward compatibility.
- Test strategy and verification gates.

State the chosen slices and which sections of the design each covers before dispatching.

## Mandatory parallel review

Spawn one subagent per slice in a **single message with multiple Agent tool calls** so they run concurrently. Default subagent type is `general-purpose`; use `Plan` for control-flow / sequencing slices, and `Explore` for slices that require wide-codebase cross-reference.

Per-slice brief template (fill in `<slice>`):
> Cold review. You have no prior context. Read `<design path>` and audit the `<slice>` portion only. Identify: hidden assumptions, internal contradictions, gaps vs the stated purpose, conflicts with neighbouring slices, edge cases not covered, and concrete edits to make. Output: findings list + proposed edits as `before → after` snippets. Do not modify any file.

Each subagent must remain in its slice — no cross-slice rewrites.

## Synthesis

After all slice subagents return:
1. Build a cross-slice conflict matrix. List pairs of slices whose findings collide.
2. Resolve each conflict by either choosing one side (with one-line rationale) or queuing a clarification for the user.
3. Build the consolidated edit set: deduplicated, ordered by dependency.

## Edit application (separate subagent)

Apply the edits through a **fresh** subagent that did not participate in any slice review:
- Subagent: `executor-agent` if the design lives under a Codex-managed scope, else `general-purpose`.
- Brief: "Apply this exact edit set to `<design path>`. Do not introduce edits beyond the supplied list. Preserve surrounding text."

## Independent re-review

Dispatch `codex-final-reviewer` (cold context, no participation in earlier passes) to re-audit the revised design end-to-end. Verdict required: clean, or list of remaining gaps/conflicts.

## Completion criteria (continue until ALL hold)

- Every slice has been reviewed by a dedicated subagent.
- All cross-slice conflicts are resolved or surfaced to the user.
- The consolidated edit set has been applied without scope expansion.
- The independent re-review reports zero unresolved gap/conflict, or every remaining item is explicitly acknowledged.

## Halt conditions

- The design contradicts the repository's stated purpose (per `CLAUDE.md` or PRD) → stop and surface before editing.
- A subagent's findings cannot be reconciled with the user's earlier decisions recorded in memory or ADRs → stop and ask.
- Edits would require code changes to remain coherent → stop, do not edit code in this command; the user can chain into `/develop-from-design` afterwards.

## Output to user

Final report, in Korean, contains:
- Design path and slice partition.
- Per-slice top findings (1–3 each).
- Conflict matrix and resolutions.
- Diff summary of edits applied to the design doc.
- Independent re-review verdict.
- Open questions, if any.
