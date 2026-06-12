---
title: "Known Limitation: active_agents Dispatch Enforcement is Prompt-Only"
keywords: [active-agents, enforcement-gap, dispatch, prompt-only, hard-gate, deny-list, permissions, settings-json, specialist, deferred]
created: "2026-06-03"
last_used: "2026-06-07"
type: harness-engineering
---
# Known Limitation: `active_agents` Dispatch Enforcement is Prompt-Only

- Date: 2026-06-03
- Status: **known limitation** (hard-gate investigated, deferred for safety per conservative directive)
- Related: ADR-09 (declarative `active_agents` surface + dispatch-log), `.claude/agents/main-orchestrator.md` "Active Agent Resolution", `scripts/verify_repo_agent_management.py` (R8/R11 advisory), `docs/harness-engineering/context-surface-reduction-fleet-design-2026-06-03.md`

## The gap

`active_agents` (which catalog specialists a family may dispatch) is enforced **only** by:
- the orchestrator **prompt** convention (`main-orchestrator.md` "Active Agent Resolution" → abort dispatch with `routed_via: skipped_inactive`), and
- **post-hoc advisory audit** (`verify_repo_agent_management.py` R8/R11 emit WARN/INFO; R11 reads `tasks/log/dispatch-log.jsonl`, which is itself prompt-emitted, not runtime telemetry).

There is **no deterministic code gate**. This is the largest hole in the project's "enforcement, not advisory" thesis.

## Why naive hard-gates do not work (investigated 2026-06-03)

1. **No code dispatch path.** Specialists are spawned purely by the LLM main-orchestrator calling the host **Agent/Task tool** per prompt convention; no code function maps `agent_slug → spawn`. The dispatcher operates at `family_slug` granularity (whole Codex jobs) and carries no agent name — so the dispatcher is the **wrong layer** (nothing to gate there).
2. **A hook cannot gate by type.** Claude Code's Agent-tool `PreToolUse` payload does **not** expose a documented/stable `subagent_type` field, and there is no `SubagentStart`/`TaskCreated` lifecycle hook that carries the agent type. A `PreToolUse` hook with matcher `Agent` can block *all* sub-agent spawns but **cannot condition on type**.
3. **Permission-rule precedence is unverified.** The only viable native mechanism is Claude Code permission rules `Agent(<name>)`. But the allow-list shape `deny: ["Agent(*)"]` + `allow: ["Agent(<active>)"]` is **unconfirmed**: the docs state deny is absolute and first-match wins ("if a tool is denied at any level, no other level can allow it"), which implies a catch-all `Agent(*)` deny would also block the allowed names — contradicting the example given. This was not empirically resolved.

## Recommended (deferred) safe approach

- Use a **deny-LIST**, not a catch-all deny: generate `permissions.deny: ["Agent(<x>)"]` for each **catalog specialist** not in the family's **effective** `active_agents` (effective = `active_agents` ∪ `agent_overrides.add_specialists` − `agent_overrides.remove_specialists`). A scoped deny blocks that name; active names are simply not denied — this **sidesteps the allow-vs-deny precedence ambiguity**.
- **Safelist built-in / utility agents** (`general-purpose`, `Explore`, `claude-code-guide`, `statusline-setup`, etc.) — never deny these; gate **only** catalog specialists. (Denying an in-use built-in agent would lock out live tooling.)
- Generate the rules in the deploy path into a **managed block** of each repo's `.claude/settings.json`, sourced from the family's effective `active_agents`.
- **Prerequisite spike (isolated):** in a throwaway Claude Code invocation — **not** the live session — confirm (a) `deny: ["Agent(X)"]` actually blocks spawning `subagent_type=X`, and (b) the allow/deny precedence, before generating any rules.

## Why deferred

- Editing the **live session's** `settings.json` mid-run would immediately change the running agent's own permissions — a footgun that could lock out in-use built-in agents.
- The permission precedence is unverified; forcing the catch-all-deny shape risks blocking **all** agent spawns.
- The current state (prompt + post-hoc audit) is **benign in practice**.
- Per the conservative directive ("don't proceed with risky things; if a conflict is expected, approach conservatively"), the hard-gate is deferred to a deliberate, isolated-spike-backed pass rather than forced opportunistically.

## Acceptance

Until implemented, `active_agents` remains a **soft contract** (prompt + advisory audit). This is a documented, accepted known limitation — not an oversight. A future hard-gate must follow the deferred safe approach above (deny-list + built-in safelist + isolated precedence spike + managed settings block).
