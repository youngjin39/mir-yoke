---
description: 메인에이전트 설계/오케스트레이션→cold 검토→delegated 실행→cold 평가 4단계 파이프라인 (단계마다 신규 서브에이전트, 편향 0)
---

# /role-split-pipeline

Run a full design → review → implementation → evaluation pipeline with **strict role isolation across subagents**. No single subagent performs more than one phase. Every review and every evaluation runs in a freshly spawned subagent with cold context — this is the anti-bias contract.

## Phase contract

| Phase | Owner | Subagent | Tool surface |
|---|---|---|---|
| 1. Design | Main agent (Claude main or Codex main) | `Plan` (or main session if user requests) | read + write design docs only |
| 2. Design review | Codex (cold) | `codex-final-reviewer` (instance A) | read-only |
| 3. Design repair | Main agent (Claude main or Codex main) | `Plan` or main session | design doc edits only |
| 4. Design re-review | Codex (cold) | `codex-final-reviewer` instance B — newly spawned, no shared history with A | read-only |
| 5. Implementation | Codex execution lane | `executor-agent` | code edits within design scope |
| 6. Implementation review | Codex (cold) | `codex-final-reviewer` instance C — newly spawned, distinct from A and B | read-only |
| 7. Code repair | Codex execution lane | `executor-agent` (instance distinct from phase 5) | code edits |
| 8. Final evaluation | Codex (cold) | `codex-final-reviewer` instance D — newly spawned, no shared history with any prior reviewer | read-only |

A single subagent NEVER occupies two phases. This is non-negotiable.

## Inputs

- Task or purpose statement: `$ARGUMENTS`. If absent, ask the user once for the goal.
- Repository context: `CLAUDE.md`, `AGENTS.md`, any role policy.
- Existing design docs and prior decisions in `docs/decisions/`.

State the resolved task and detected role policy before phase 1.

## Phase walkthrough

### Phase 1 — Design

Produce a design doc at `docs/design/<task-slug>.md` (or the repo's design home). Include: purpose, scope, non-goals, slice plan, verification strategy, path/rename inventory.

### Phase 2 — Design review

Dispatch `codex-final-reviewer` instance A with brief:
> Cold review. You have no prior context. Read `<design path>` and audit it against `<purpose source>`. Classify findings BLOCKER / WARN / NIT. Report only.

### Phase 3 — Design repair

If review returned BLOCKER or WARN-to-fix items, edit the design doc directly. **Do not** delegate repair to the reviewer.

### Phase 4 — Design re-review

Dispatch a newly spawned `codex-final-reviewer` (instance B). Brief: cold re-review of the revised design. Must return clean before proceeding to implementation.

### Phase 5 — Implementation

Dispatch `executor-agent` with the approved design's slice plan. Constraints already declared in `/develop-from-design` apply: one slice at a time, no path-rename bundling with logic, strict scope discipline.

### Phase 6 — Implementation review

Dispatch `codex-final-reviewer` instance C (cold, distinct from A and B). Brief: audit implementation against the approved design, with focus on design conformance, regression risk, path/import integrity, hidden coupling.

### Phase 7 — Code repair

If review found issues, dispatch `executor-agent` (a fresh instance, not the one from phase 5) with narrow file-scoped fixes.

### Phase 8 — Final evaluation

Dispatch `codex-final-reviewer` instance D (cold, distinct from A, B, C). Brief:
> Cold evaluation. Read the approved design at `<path>` and the implementation under `<scope>`. Verdict on: design conformance, purpose alignment, regression risk, scope discipline. This is the independent gate before completion.

## Iteration rules

- If any review/evaluation phase finds BLOCKERs, return to the appropriate repair phase, then re-spawn a **new** reviewer (do not reuse the previous reviewer instance). The reviewer instance counter increments on every reviewer dispatch.
- The orchestrating main session may not review its own design or implementation — only synthesise reviewer reports and dispatch repairs.

## Completion criteria (continue until ALL hold)

- Phase 4 (design re-review) returned clean.
- Phase 8 (final evaluation) returned clean.
- Every reviewer instance is distinct from every other reviewer instance (no subagent reuse across review phases).
- Repository's verification suite passes.
- No scope leakage outside the approved design.

## Halt conditions

- Same finding survives 3 repair cycles in any phase → stop, surface root cause.
- A reviewer instance reports that the design itself is wrong against the purpose → restart at phase 1 with the user, do not patch.
- Codex execution lane returns sandbox or policy errors → stop, surface; do not silently downgrade.
- User-specified role policy in `CLAUDE.md` forbids one of the phase owners → stop, ask user for an explicit override before deviating.

## Output to user

Final report, in Korean, contains:
- Resolved task and purpose source.
- Phase-by-phase log: reviewer instance id, verdict, repair count.
- Final evaluation verdict.
- Files changed (design docs + code) with diff scope summary.
- Open questions and halts.
