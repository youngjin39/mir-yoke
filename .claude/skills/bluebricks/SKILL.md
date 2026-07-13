---
name: bluebricks
description: "Proportional guidance for code writing, analysis, debugging, refactoring, architecture review, repository exploration, dependency analysis, and bluebricks-based development.\n\nTrigger: code, debug, refactor, architecture, module, repository, PR review, bluebrick, dependency"
---

# AI-Ready Bluebricks Development

## Use When
- The task involves program development or codebase analysis.
- The task touches multiple files, boundaries, or hidden project rules.
- The task needs architecture, dependency, hazard, or validation awareness.

Do not use this skill for pure writing, research, summaries, or other non-code tasks.

## Required Reads
Before non-trivial code work, read:
- `.ai-harness/development-ai-rules.md`
- `.ai-harness/bluebricks.md`
- `.ai-harness/tdd-matrix.md`
- `.ai-harness/deny-list.yaml`
- `.ai-harness/failure-patterns.md` when repeated mistakes or hazards may matter

## Workflow
1. Define the exact task boundary.
2. Identify the affected module or bluebrick.
3. Answer WHAT / HOW / HOW NOT / WHERE / WHY for the relevant boundary.
4. Decide whether the work is local, cross-module, or orchestration-level.
5. Decide whether direct execution or delegation is cheaper and safer for this scope.
6. Follow the Ponytail ladder before adding code: remove unnecessary work, reuse project code, use built-ins, justify a dependency, and write minimum custom code last.
7. For non-trivial logic, run the smallest check that can fail for the changed behavior.
8. Use `tasks/tdd.json` and the full matrix only for broad, high-risk, release, restartable, or explicitly ledger-driven work.
9. Record a newly discovered hazard only when it is reusable and non-obvious.

## Bluebrick Checklist
For each affected bluebrick, identify:
- purpose
- public interface
- internal rules
- non-obvious hazards
- dependencies
- downstream users
- composition relationship
- orchestration flow
- validation method

## Context Hygiene
- One session = one task.
- Avoid repeated file reads when the file has not changed.
- Do not dump huge logs or whole diffs into context.
- Use bounded output and targeted commands.
- Scope reads/searches: `rg`/`grep` skip huge non-source artifacts (`*.sqlite*`, session/rollout logs, `.git`, `.venv`, `node_modules`) and avoid `--hidden`/`--no-ignore` on large trees; read large generated/data files by slice (`jq`/`grep`/ranged), not whole — override when the logs/data are the target.

## Sub-agent Policy
Use sub-agent for:
- broad codebase search
- PR review
- security review
- performance investigation
- multi-file dependency analysis
- test failure investigation
- architecture comparison

Do not use sub-agent for:
- single grep
- reading one known file
- small local edits
- small diff review

## Safe Modification Rules
- Preserve architecture boundaries.
- Do not silently expand scope.
- Do not edit generated files unless generation is the task.
- Do not edit merged migration files; create a new one.
- Do not remove legacy fields without dependency checks.

## Validation Order
1. the smallest behavior-specific check
2. ledger commands when a ledger is used
3. affected-boundary lint, typecheck, build, or integration checks
4. full test suite only for broad, shared, or release risk

Executed relevant evidence is the primary proof. Independent review is proportional to uncertainty and risk.

## Final Response
When finishing, report:
1. summary
2. changed files
3. validation performed
4. risks or assumptions
5. newly discovered AI-ready rules, if any
