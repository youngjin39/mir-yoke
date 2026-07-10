# Bootstrap — turn this template into your project

Two ways to set up: **hand it to an AI agent** (recommended) or do it manually.

---

## Option A — Agent-guided (recommended)

Clone, open the repo in Claude Code **or** Codex CLI, and tell the agent:

> Read `BOOTSTRAP.md` and set up this repo as a **<project-type>** project for **<one-line purpose>**.

The agent then runs the procedure below. It is written to be executed by an agent, not just read.

### Step 1 — Interview (ask, then wait)

Ask the user, as a short numbered list, and wait for real answers:

1. **Project slug + one-line purpose** (e.g. `acme-api` — "internal billing API").
2. **Project type** — one of: `code_app` (app/service), `content_workspace` (docs/content), `infra_runtime` (infra/runtime/library), `hybrid_pipeline` (data/ML pipeline).
3. **Primary language / stack** (e.g. Python, TypeScript, Go, Flutter).
4. **Extra reviewers** — recommend the specialists for their type (table below); let them opt out of any.
5. **Codex too?** — will they also run Codex CLI (delegated code/TDD/review lane), or Claude-only?

### Step 2 — Configure (from the answers)

**a. Per-repo registry.** Create `config/repos/<slug>.json` from an existing entry's shape:
- `slug`, `display_name`, `registry_path` (this repo's absolute path), `repository_type` = the chosen type.
- `active_agents`: always `["main-orchestrator", "executor-agent", "codex-final-reviewer", "quality-agent"]` + `fleet-doc-steward` if they manage docs.
- `agent_overrides.add_specialists`: the specialists for the type (table below), minus opt-outs.
- `active_skills`: default `["design", "verify", "testing", "code-review", "bluebricks", "commit"]`; add `ui-design` for UI work, `governance` if managing CLAUDE.md/AGENTS.md, `knowledge` for a wiki.

**Specialists by project type:**

| Project type | Recommended specialists |
|---|---|
| `code_app` | cwe-auditor, dep-auditor, ui-reviewer |
| `content_workspace` | ontology-validator |
| `infra_runtime` | runtime-contract-reviewer |
| `hybrid_pipeline` | cwe-auditor, dep-auditor, pipeline-validator |

**b. Identity.** Fill `.mir/repo-profile.toml` — replace every placeholder (slug, display name, type). `setup.sh` warns while placeholders remain.

**c. Codex lane.** If they use Codex: `cp .mcp.json.example .mcp.json` and set the `codex` command (binary path) + `CODEX_HOME`. If Claude-only: set `config/sub-agent-policy.json` `"mode": "unrestricted"` (otherwise `force_codex` will BLOCK delegation with no Codex backend).

**d. Role policy.** Adjust the role-policy table in `CLAUDE.md` (and the `AGENTS.md` mirror) for the project — usually the defaults are fine; only change if they want a non-standard main/delegation split.

**e. Remove template-only content — ASK FIRST.** Offer to delete what the user does not need: `examples/`, `docs/harness-engineering/` (the template's own build history), template-specific ADRs. Keep `.claude/`, `.codex/`, `.ai-harness/`, `config/`, `tools/`, `src/`, hooks — those ARE the harness.

### Step 3 — Run setup

```bash
./setup.sh   # idempotent: makes hooks executable, seeds tasks/tdd.json + tasks/plan.md + .mir/repo-profile.toml
```

### Step 4 — First plan + prove the gates

- Verify the registry: `python3 scripts/verify_repo_agent_management.py`.
- Write the first real `tasks/plan.md` entry for the user's actual first task.
- Prove a gate fires: try to `Edit` a file under `src/`/`tools/` **without** a `tasks/tdd.json` entry — the pre-tool-use hook should block it. That block means the harness is live.

### Step 5 — Report

Summarize: project type, agents/skills enabled, Codex wired (y/n), what was removed, and the first suggested task. Do not commit unless asked.

---

## Option B — Manual

1. `git clone <this-repo> my-project && cd my-project`
2. `./setup.sh`
3. `cp .mcp.json.example .mcp.json` and set your codex command (skip if Claude-only; then set `sub-agent-policy.json` mode `unrestricted`).
4. Create `config/repos/<slug>.json` (copy an entry's shape; pick `active_agents`, specialists by type from the table above, `active_skills`).
5. Fill `.mir/repo-profile.toml` (no placeholders left).
6. `python3 scripts/verify_repo_agent_management.py` to confirm the registry is consistent.
7. Open `claude .` or `codex`. See `README.md` → "Using the harness — the loop".

Optional global rules: merge `global-rules/CLAUDE.global.md` / `AGENTS.global.md` into your own `~/.claude/CLAUDE.md` / `~/.codex/AGENTS.md`.
