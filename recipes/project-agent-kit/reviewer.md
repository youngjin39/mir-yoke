# Project-Specific Reviewer Contract

Create a repository specialization rather than duplicating a common provider skill.

## Canonical sources

- `.claude/skills/<project-slug>-code-review/SKILL.md`
- `.claude/agents/<project-slug>-code-reviewer.md`

The skill uses exactly the `name` and `description` frontmatter fields and records only
project-specific paths, risks, architecture references, and the `scripts/verify.sh` command. Keep it
concise and self-contained. The slug `<project-slug>-code-review` must be repository-unique.

The agent slug is `<project-slug>-code-reviewer`. It must be an evidence-first reviewer, not an
executor. Its Claude frontmatter includes the exact allowlist `tools: Read, Glob, Grep` plus
`disallowedTools: Write, Edit`. Do not grant Bash, Agent, Skill, MCP, browser, or external-service
tools. The main agent or Git hook runs lint, build, and test; the reviewer inspects their recorded
evidence and never fixes its own findings.

## Generated surfaces

Provide a one-way Claude-to-Codex generator at
`scripts/generate_agent_derivatives.py`, owned by the target repository. It generates:

- `.agents/skills/<project-slug>-code-review/SKILL.md`; and
- `.codex/agents/<project-slug>-code-reviewer.toml`.

The Codex agent must contain `sandbox_mode = "read-only"`. Generated files name their canonical
Claude source and are never hand-edited. The generator provides a parity check mode, is idempotent,
checks both the skill and agent outputs, and fails when either generated surface is stale.

## Review behavior

The reviewer must:

1. read `PROJECT.md`, `HARNESS.md`, the requested change, and the bounded diff;
2. inspect affected callers, consumers, state, permissions, and generated surfaces;
3. cite verified file and line evidence for each finding;
4. classify findings by severity and separate blockers from optional improvements;
5. treat missing or failed verification as unevaluated, never as a pass; and
6. return `Sound` or `Changes requested` without modifying the repository.
