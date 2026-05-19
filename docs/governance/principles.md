# Fleet Governance Principles

Six operating principles for managing a fleet of repositories with this harness.
These principles are what a meta-harness applies when it manages many child
repositories; a single-repo user can treat them as opt-in guidance.

## Principle 1 — Harness structure stays autonomous

The meta-harness organises only the **common, reusable** harness structure.
Each child repository is the authority on its own `.claude/hooks/`,
`.claude/agents/`, `.claude/skills/`, and `.codex/` layout.

The meta-harness's job is to **catalogue and curate**, not to force
uniformity. One repository's hook should be portable to another repository
on demand, not pushed in by surprise.

Concretely:
- Hook structure mutations are routed to advisory only (never autonomous fix),
  even when the repository declares itself fully managed.
- The repository's own `.mir/repo-profile.toml` (or equivalent local profile)
  is the source of truth for its rollout class, archetype, and Codex role.

## Principle 2 — Direct management for context efficiency, agents, and migration

The meta-harness directly manages, with an AI-score impact gate:

- Token efficiency (prompt cache shape, hit rate)
- Context efficiency (`CLAUDE.md`, `AGENTS.md` size, section split)
- Multi-agent structure
- Migration state (rollout class transitions)

The applied changes must be **low impact** — document tidying, section
splitting, frontmatter alignment. Functional changes that alter the
repository's behaviour are out of scope.

## Principle 3 — Direct management for skills and tools

Principle 2 extends to:
- Skills (`.claude/skills/<id>/SKILL.md`)
- Tools (the project-local `tools/` package and `.mcp.json` registration)

The meta-harness measures their presence, names, and frontmatter compatibility;
it does not author skill or tool internals.

## Principle 4 — Per-repository hook + harness recording is portable

For every child repository the meta-harness records the local harness
structure and hooks in a fingerprint form (SHA + content state). The
recording is shaped so that:
- A different repository can opt to **adopt** that hook or harness
  configuration without re-engineering it from scratch.
- A brand-new project can bootstrap a known-good baseline.

The recording layer is what makes principle 5 (cross-pollination) practical.

## Principle 5 — Full catalogue, opt-in cross-pollination

Every repository's agents, skills, tools, hooks, and harness structure are
indexed in a single fleet catalogue. The catalogue is queryable so that:
- A user can pick a pattern from repository A and adopt it in repository B.
- The catalogue records the provenance (source repository, license,
  adoption notes).
- A canary / wave rollout flow keeps the import bounded — try once on
  a single recipient before fanning out.

## Principle 6 — Unused-component detection and archive

The catalogue is paired with a usage telemetry axis so that:
- Hooks, agents, skills, and tools that have not been invoked beyond a
  configurable threshold (default: 30 days) surface as **archive
  candidates** — advisory only.
- Archiving requires explicit user confirmation; autonomous archive is
  forbidden. The archive destination is `.claude/{agents,skills,hooks}/
  archive/` per kind.

This keeps each repository's runtime narrow without losing the historical
record.

## Practical guarantees

- **Principle 1 invariant**: the autonomous-fix lane never mutates files
  whose check id is prefixed `HARNESS.HOOKS.` or `HARNESS.SETTINGS.` —
  those are routed to advisory.
- **Principle 2 invariant**: only the three score slots (`ai_readiness`,
  `token_efficiency`, `context_efficiency`) are tracked; new measurement
  axes do not create new score slots — they extend the fact namespace.
- **Principle 6 invariant**: archive operations refuse without an explicit
  `--confirm` flag, regardless of repository management mode.
