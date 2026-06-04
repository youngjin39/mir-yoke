---
status: accepted
---

# ADR-15 — Catalog (multi-agent + skill) (sanitized summary)

Status: accepted (upstream)

Sanitized summary of the upstream ADR. Captures the catalog structure
that public-template fork users will encounter.

## Catalog surface

`config/repo-agent-management.json` is the central manifest. It carries:
- `catalog.agents` — declarative inventory of every agent, keyed by
  slug, with role / model / status / scope_patterns / execution_backend.
- `catalog.skills` — same shape for skill groups.
- `repositories[]` OR `repositories_dir` — per-family entries.
  The template uses `repositories_dir: "config/repos"` and ships an
  empty `config/repos/` directory. Forks populate it.
- `change_log[]` — append-only audit trail.

The schema at `config/repo-agent-management.schema.json` constrains the
manifest shape; `additionalProperties: false` is enforced.

## L1 catalog vs L3 family override

Each family's `repositories[i].active_agents` lists which catalog
agents are active for that family. Slugs outside `active_agents` are
disk-deployed but advisory only — `main-orchestrator.md` Active Agent
Resolution pre-dispatch step refuses to dispatch them without an
explicit recorded override.

Family-private agents (slugs not in `catalog.agents`) live in the
family's local `.claude/agents/` and are referenced via the family's
local `.mir/harness-config.json` `active_agents` list rather than the
central manifest.

## Skill groups

11 skill groups are listed under `catalog.skills`. The legacy 12-skill
catalog from earlier revisions is absorbed into the 11 groups via the
`absorbs:` frontmatter field on each SKILL.md.

## See also

- `tools/catalog_loader.py` — loads the aggregated catalog dict.
- `scripts/verify_repo_agent_management.py` — runs the R1–R13 audit
  checks (drift, alignment, dispatch log, family consistency).
- `docs/decisions/adr-17-scope-pattern-routing.md` (if shipped) for
  the scope-pattern dispatch filter design.
