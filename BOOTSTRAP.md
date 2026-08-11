# Agent-Guided Adoption

Mir Yoke provides two supported entrypoints. Neither is a provider-side installer. The minimum
adoption path does not require a specification tree merely to begin.

## Existing repository: Minimal Starter

Use `starter/` as reference material. The active agent first records the target root, Git status,
existing instructions, purpose, stack, generated and protected paths, external boundaries, and real
verification commands. Preserve repository-owned files and merge only missing rules.

The Starter adoption is complete when the local contract describes the actual project, no
placeholder remains, every named path and command is real or explicitly absent, the selected check
passes, and the final diff contains only the accepted harness changes.

## Empty repository: Project Agent Kit

For one explicit empty directory, use the short prompt in the root README. The active agent reads
[`recipes/project-agent-kit/`](recipes/project-agent-kit/) and creates a purpose-specific agent
foundation. The supported outcome includes:

- preserved project intent and a local harness contract;
- Claude and Codex entrypoints;
- a repository-unique code-review skill and read-only reviewer;
- generated Claude-to-Codex parity;
- real lint, build, and test commands behind a tracked Git pre-commit hook; and
- one verified local initial commit with no remote or push.

The agent stops at `READY_FOR_DEVELOPMENT_PLANNING`. The recipe does not authorize a development
plan, product feature, API, UI, deployment, remote, push, or release.

## Unsupported target state

Do not run the Project Agent Kit flow when the target contains files, is inside another Git
worktree, lacks required Git identity or toolchain, or contains a consequential unresolved product
decision. Use Starter comparison for an existing repository or return the exact blocker before
mutation.

The retained setup, bootstrap, memory, executor, hook, and specification implementations are
reference or maintainer evidence. Their presence never makes them part of either supported adoption
flow.
