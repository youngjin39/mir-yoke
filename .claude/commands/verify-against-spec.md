---
description: 구현이 설계·요구사항·목적과 일치하는지 다축 서브에이전트 독립 검증 (완료까지)
---

# /verify-against-spec

Verify that the current implementation matches the design, the requirements, and the repository's stated purpose. Detect missing implementations, design/code conflicts, regression risk, hidden dependencies, and broken path references. All inspection and repair happens through **role-isolated subagents**; the orchestrating Claude session synthesises only.

## Inputs to load before dispatch

- Design document(s): `$ARGUMENTS` path, else most recent under `docs/decisions/`, `docs/design/`, `tasks/plan*.md`, `ARCHITECTURE.md`.
- Requirements / PRD if present.
- Repository purpose: `CLAUDE.md`, `README.md`, root `AGENTS.md`.
- Recent changes window: branch diff vs `main`, plus the last N commits relevant to the scope.

If any source is missing, ask the user (single short text question) which to use as the authoritative reference. Do not silently assume.

## Mandatory parallel verification axes

Spawn the following subagents in a **single message with multiple Agent tool calls** so they run concurrently. Each subagent receives only its own slice — no shared context with the others.

Axis A — design coverage:
- Subagent: `general-purpose`.
- Brief: "Cold audit. Compare `<design path>` to current code under `<scope>`. Enumerate items declared in the design that are missing, partial, or inconsistent in code. Cite file:line for each finding."

Axis B — conflict and regression:
- Subagent: `codex-final-reviewer` (Codex CLI, read-only).
- Brief: "Cold review. Audit `<scope>` for internal conflicts, contract violations, regression risk, and silent failure modes. Cross-check against `<design path>`."

Axis C — reference and path integrity:
- Subagent: `Explore`.
- Brief: "Verify that every import path, config reference, script invocation, and relative path under `<scope>` resolves correctly. Surface dangling references and rename ghosts."

Axis D — hidden dependencies and edge cases:
- Subagent: `general-purpose` (distinct invocation from Axis A).
- Brief: "Cold audit. Enumerate hidden dependencies (env vars, files-on-disk, network endpoints, ordering assumptions, time/clock assumptions) and edge cases that `<scope>` does not handle. Cite evidence."

Launch all four concurrently.

## Synthesis

After all axes return:
1. Merge findings. Deduplicate. Classify each as BLOCKER / WARN / NIT.
2. Surface cross-axis conflicts (axes disagree on the same item) explicitly to the user.
3. Group findings by minimal repair unit; do not batch unrelated fixes.

## Repair loop (only if findings require code change)

Per repair group:
1. Dispatch `executor-agent` with a narrow brief — only the files and the precise fix list. No adjacent cleanup.
2. After repair, dispatch a **freshly spawned** `codex-final-reviewer` (distinct from Axis B) to re-verify that the specific findings are resolved and no new regressions surfaced.
3. If path/import/config references moved, the re-verification subagent must confirm caller integrity.

## Completion criteria (continue until ALL hold)

- Every Axis A coverage gap is either implemented and independently re-verified, or explicitly acknowledged as out-of-scope by the user.
- Zero unresolved BLOCKER across all axes.
- Every WARN is resolved or annotated with a one-line rationale.
- A final cold `codex-final-reviewer` (not used in any earlier pass) confirms the integrated state.
- The full verification suite passes (or repository-equivalent — pytest, ruff, tsc, etc.).

## Halt conditions

- Design and requirements contradict each other → stop, surface to user.
- A repair would require redesign → stop, do not redesign inside this command.
- 3 consecutive repair attempts fail on the same finding → stop, report root cause.
- Repair would expand scope beyond the verified axes → stop, ask before expanding.

## Output to user

Final report, in Korean, contains:
- Authoritative references used.
- Per-axis top findings.
- Conflicts surfaced between axes.
- Repair history table (finding → executor → re-verifier → verdict).
- Verification suite result.
- Open questions and halts.
