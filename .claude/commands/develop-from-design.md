---
description: Harness-style development from a design — small slices: implement -> independent review -> fix, looped until complete
---

# /develop-from-design

Develop the repository from an approved design through a **harness-style slice loop**. Every implementation, every review, and every fix runs in a dedicated subagent. The orchestrating main session (Claude main or Codex main) does no direct code edits by default.

## Preconditions (verify before starting)

- An approved design document exists at the path resolved from `$ARGUMENTS` or, if unspecified, the most recent doc under `docs/decisions/`, `docs/design/`, or `tasks/plan*.md`. Read it end-to-end.
- The repository defines a verification strategy (tests, lints, type-checks). If `tasks/tdd.json` or an equivalent ledger exists, load it.
- The repository's role policy (`CLAUDE.md`, `AGENTS.md`) does not forbid Codex execution for the touched scope. If it does, stop and request an explicit override.

State the design path, verification command set, and execution-lane policy before slicing.

## Slicing

Decompose the design into the smallest meaningful slices. Constraints:
- A slice owns at most one logical concern.
- A slice never bundles path/rename mutations with new logic — split those into separate slices, path-mutation first.
- Each slice has a precise file list and an a-priori verification command (test name, lint scope, or behaviour check).

Emit the slice plan to the user before executing.

## Per-slice loop (repeat until all slices done)

For each slice in order:

1. **Implementation subagent** — `executor-agent` (Codex execution lane).
   - Brief: "Cold execution. Implement slice `<id>` exactly as specified. Files: `<list>`. Verification: `<command>`. Do not modify files outside the listed scope. Do not refactor adjacent code."
   - On completion: collect the changed file list and verification result.

2. **Slice review subagent** — fresh `codex-final-reviewer` (cold context, did not run implementation).
   - Brief: "Cold review. Audit the changes for slice `<id>` against the design section `<ref>`. Check: design conformance, regression risk, hidden coupling, path/import integrity, error handling appropriateness, scope discipline. Classify BLOCKER / WARN / NIT. Report only — do not edit."

3. **Repair subagent** (only if BLOCKER or WARN-to-fix) — `executor-agent`, fresh dispatch.
   - Brief: "Apply this exact fix set for slice `<id>`. Do not touch files outside the listed scope. Re-run verification: `<command>`."

4. **Independent re-verification subagent** — a **newly spawned** `codex-final-reviewer`, distinct from step 2.
   - Brief: "Cold re-verification of slice `<id>` after repair. Confirm BLOCKER/WARN items are resolved and no new regressions appear. Verdict: pass / fail with reasons."

A slice is complete only when step 4 returns pass.

## Path-mutation discipline

When a slice renames, moves, or introduces a new path:
- The implementation brief must include the full updated reference graph (callers, imports, configs, scripts).
- The review subagent must verify caller and config integrity, not only the moved file.
- If a downstream reference cannot be reached without expanding scope, stop and ask the user before continuing.

## Completion criteria (continue until ALL hold)

- Every planned slice has completed step 4 with verdict pass.
- The full verification suite (or repository-equivalent) runs clean on the integrated branch.
- No slice expanded its file scope beyond what was planned.
- An end-of-run independent audit subagent (`codex-final-reviewer`, cold) reports zero remaining design gap.

## Halt conditions

- Implementation fails verification 3 times on the same slice → stop, surface root cause, do not start a 4th attempt.
- Reviewer demands changes that require redesign → stop, surface to user; do not redesign mid-loop.
- Slice scope cannot be honoured without touching unrelated files → stop, ask before expanding.
- Codex execution lane returns sandbox or permission errors → stop, surface; do not silently downgrade tools.

## Output to user

Final report, in the user's working language, contains:
- Design path and slice plan.
- Per-slice status table: implementation outcome, review verdict, repair count, final independent verdict.
- Aggregate diff scope (files touched).
- Full-suite verification result.
- Halts or open questions.
