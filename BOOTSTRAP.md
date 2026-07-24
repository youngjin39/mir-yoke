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
6. **Vector search (optional)?** — recommend the embedding backend (Step 2 f): explain the effect first, then ask. Never install a server or model without explicit consent.

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

**d. Role policy.** Set project-specific role and boundary values in `.mir/repo-profile.toml`, keep
only shared startup invariants in `CLAUDE.md`, then run `scripts/generate_codex_derivatives.sh`.
`AGENTS.md` is generated and must not be edited directly.

**e. Remove template-only content — ASK FIRST.** Offer to delete what the user does not need: `examples/`, `docs/harness-engineering/` (the template's own build history), template-specific ADRs. Keep `.claude/`, `.codex/`, `.ai-harness/`, `config/`, `tools/`, `src/`, hooks — those ARE the harness.

**f. Embedding backend — RECOMMEND, EXPLAIN, then ASK. Never install without consent.**
Vector search is optional: without it the memory engine runs FTS5 keyword-only and is fully functional. Before touching anything, explain both outcomes to the user:

- **Enable now**: `mir context pull` gets hybrid vector + keyword retrieval, and the index never has vector gaps.
- **Enable later**: chunks indexed in the meantime carry no vectors and are **not auto-backfilled** — a full re-index is required when the model arrives.

Then ask whether to set it up. Installing a server or pulling a model always requires explicit user consent — this is a hard gate, not a default.

Recommended backends by platform — **recommendations, not restrictions**. Any OpenAI-compatible `/v1/embeddings` server works (the `omlx_http` backend name is historical):

| Platform | Recommended server | base_url | model |
|---|---|---|---|
| macOS (Apple Silicon) | oMLX | `http://127.0.0.1:8001/v1` | `bge-m3-mlx-fp16` |
| Windows / Linux | Ollama (`ollama pull bge-m3`) | `http://127.0.0.1:11434/v1` | `bge-m3` |
| Anything else | any OpenAI-compatible server | — | your choice |

The model is likewise a recommendation, not a restriction: bge-m3 (dim 1024) is the tested default, but any embedding model works as long as `dim` in `harness_a.toml` matches the model's output and the server returns L2-normalized vectors — the engine validates both and fails closed on mismatch. After filling `[memory.embedding]` (see `harness_a.toml.example`), verify with one test call (dimension = `dim`, L2 norm ≈ 1.0) before running `mir context sync`.

**New environment = fresh index.** When setting up on a new machine or runtime, propose starting fresh. Never copy a vector DB produced by a different runtime or quantization — the same model name under a different runtime is a different encoder fingerprint (`docs/architecture/embedding-index-lifecycle-shape.md`).

Day-2 operations (re-index, model change, rollback, evidence) live in `docs/operations/embedding-lifecycle-operations.md`.

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
6. Optional: enable vector search — configure `[memory.embedding]` in `harness_a.toml` (see `harness_a.toml.example` and Step 2 f for platform recommendations). Without it, retrieval is keyword-only; enabling later requires a re-index.
7. `python3 scripts/verify_repo_agent_management.py` to confirm the registry is consistent.
8. Open `claude .` or `codex`. See `README.md` → "Using the harness — the loop".

Optional global rules: merge `global-rules/CLAUDE.global.md` / `AGENTS.global.md` into your own `~/.claude/CLAUDE.md` / `~/.codex/AGENTS.md`.
