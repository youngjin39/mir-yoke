---
name: commit
description: "Git commit rules + structured trailer enforcement.\n\nTrigger: commit, git, save changes\n\nAbsorbs: git-commit"
---

# Commit

## Use When
- When creating a git commit.
- When staging and committing code changes.

## Absorbed legacy skills
- git-commit — Git commit rules + structured trailers.

## Workflow
1. Inspect `git status --short` and the relevant diff. Separate the requested change from pre-existing user work.
2. Run the smallest meaningful verification for the staged scope and record any check that could not run.
3. Stage only files owned by the current task and inspect the staged diff before committing.
4. Use an English `type(scope): summary` subject with a concise imperative summary.
5. Add `Constraint:` trailers for material boundaries, `Rejected:` for consequential alternatives, and `Not-tested:` when any relevant check was omitted.
6. Do not amend, force-push, or push unless the user explicitly authorized that operation.
