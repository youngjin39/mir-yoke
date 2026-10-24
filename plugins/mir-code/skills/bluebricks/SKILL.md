---
name: bluebricks
description: "Proportional guidance for code writing, analysis, debugging, refactoring, architecture review, repository exploration, dependency analysis, and bluebricks-based development.\n\nTrigger: code, debug, refactor, architecture, module, repository, bluebrick, dependency"
---

# AI-Ready Bluebricks Development

Routing precedence: diff and PR review → code-review; completion evidence and spec compliance → verify; architecture analysis → bluebricks.
Architecture precedence: existing, as-built architecture analysis → bluebricks; unresolved architecture choices and new design → design.

## Use When
- The task involves program development or codebase analysis.
- The task touches multiple files, boundaries, or hidden project rules.
- The task needs architecture, dependency, hazard, or validation awareness.

Do not use this skill for pure writing, research, summaries, or other non-code tasks.

## Repository Context

Read the repository's own instruction, architecture, test, deny-list, and failure-pattern documents
when present and relevant. Common locations include `.ai-harness/`, `docs/`, and nested instruction
files, but their absence is valid and never a reason to invent or install a local harness. Follow the
actual repository contract instead of assuming Mir Yoke's maintainer layout.

Before asserting or using unfamiliar or version-sensitive API names, flags, package names, versions or commit identifiers, verify them against project code, installed interfaces or authoritative docs; leave unknowns explicit.
Inspired by drona23/claude-token-efficient at 0d30a6d.

For unresolved implementation, verification, or direct-dependency questions with a known anchor,
apply `mir-core:selective-relations` when that namespaced skill and maintained evidence are available.
Do not add relationship retrieval as a preflight to every code task. Otherwise use ordinary source search. The relation adapter and graph
are optional; use direct search when the answer location is already known or the question is outside
the supported declared relationships.

## Workflow

When identity, relation scope, lifecycle, evidence boundaries or an agent handoff affects the task, apply `mir-core:ontology` using the project-owned mapping.
1. Define the exact task boundary.
2. Identify the affected module or bluebrick.
   Before editing, enumerate callers, tests, fixtures, configs, exports and cross-cutting sites
   the change must reach. When adding to or removing from a collection, find tests or snapshots
   that hard-code its size or member set. For a bug, fix the root cause once in shared code,
   rather than patching one call site. Finish every reached site before reporting.
   Tiny local edits need only a quick search.
3. Answer WHAT / HOW / HOW NOT / WHERE / WHY for the relevant boundary.
4. Decide whether the work is local, cross-module, or orchestration-level.
5. Decide whether direct execution or delegation is cheaper and safer for this scope.
6. Follow the Ponytail ladder before adding code: remove unnecessary work, reuse project code, use built-ins, justify a dependency, and write minimum custom code last.
   When implementation deliberately introduces a known limitation, leave a `shortcut:` marker immediately with a ceiling and an observable upgrade trigger using the [existing recipe](../code-review/references/repository-audit-and-debt.md).
7. For non-trivial logic, run the smallest check that can fail for the changed behavior.
8. When the repository already owns `tasks/tdd.json`, use it and the full matrix only for broad,
   high-risk, release, restartable, or explicitly ledger-driven work. Otherwise use the
   repository's existing ledger, if any.
9. Record a newly discovered hazard only when it is reusable and non-obvious.
   After verifying a feature or fix, and only with write authority, re-read the governing
   intent (spec, plan, handoff or cursor). Update only existing durable docs affected by
   the change: architecture, business rules, security and engineering notes. Record
   intended behavior, not only code behavior; check for stale statements in both directions:
   changed behavior against docs and doc statements against the change. Escalate conflicting
   in-scope content instead of overwriting it. Create no new doc tree or layout; skip this
   for tiny local edits.

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
- Apply repository-declared structure principles when present. Otherwise preserve existing module
  boundaries, avoid unexplained hardcoding, identify transaction boundaries, and keep one source of
  truth. Report out-of-boundary violations instead of rewriting them.
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

When selecting a solution, apply the [expanded ladder and safeguards](references/sufficient-solution.md).

For authorized multi-task work, use the [bounded integration recipe](references/bounded-task-integration.md).

Inspired by DietrichGebert/ponytail at 09c434a.
Inspired by fn-opt/dryforge at f5aa6d7.
