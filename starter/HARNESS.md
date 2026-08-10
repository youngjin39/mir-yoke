# {{PROJECT_NAME}} Harness Contract

Replace every double-brace placeholder before treating this file as active project guidance.
Keep it short and repository-specific. Add optional machinery only after a real need appears.

## Outcome and completion

- Purpose: {{PROJECT_PURPOSE}}.
- Finish work when {{COMPLETION_CRITERIA}} and the smallest relevant checks pass.
- Report changed scope, verification evidence, assumptions, and remaining risks.

## Current state sources

- Read existing repository and path-scoped instructions before acting.
- Treat code, configuration, tests, CI, and current Git state as evidence of reality, not hidden
  intent.
- Architecture references: {{ARCHITECTURE_PATHS_OR_NONE}}.
- Primary implementation paths: {{IMPLEMENTATION_PATHS}}.
- Primary documentation or content paths: {{CONTENT_PATHS_OR_NONE}}.

## Authority and safety

- Read, review, and status requests are non-mutating.
- Change requests authorize only the named repository scope and relevant verification.
- Ask before destructive actions, credential access, external writes or messages, protected-scope
  mutation, commits, pushes, or material scope expansion.
- Protected paths: {{PROTECTED_PATHS_OR_NONE}}.
- Generated paths: {{GENERATED_PATHS_OR_NONE}}; edit their source and regenerate.
- Preserve unrelated local changes and never erase work merely to make a check pass.

## Work style

- Inspect before editing and state assumptions that affect the result.
- Prefer the smallest change that satisfies the request.
- Reuse project behavior and built-ins before adding dependencies or custom machinery.
- Direct work is valid for bounded tasks. Add planning, delegation, TDD structure, or independent
  review only when the task's risk or uncertainty justifies it.
- Do not turn optional template material into a project requirement without evidence and owner
  agreement.

## Verification

- Primary check: `{{PRIMARY_CHECK}}`.
- Additional check for {{BOUNDARY}}: `{{ADDITIONAL_CHECK_OR_NONE}}`.
- Run the smallest check that can fail for changed non-trivial behavior.
- A missing, skipped, or unreadable required check is not a pass.
