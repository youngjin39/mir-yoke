# claude-codex-harness

**An enforcement-first harness template for the Claude Code + Codex CLI pair.**

A reusable starting point for teams who want their AI coding assistants to follow rules — not
just hope they do. Hooks block destructive shell, gate code-path edits behind a TDD ledger, and
run the same verification on both Claude Code and Codex CLI.

If you have ever asked an AI to "be careful" and watched it overwrite a config file anyway, this
is the answer: replace politely-worded prompts with executable guards.

---

## What this is

A directory layout + hook scripts + rule documents you copy into a new (or existing) repository
so that Claude Code and Codex CLI behave like team members under the same playbook.

What you get out of the box:

- **12-agent topology (all active by default)** — main-orchestrator (Claude), executor-agent
  (Codex), codex-final-reviewer (Codex), quality-agent (Claude), fleet-doc-steward (governance),
  plus 7 specialists active out of the box: CWE auditor, dependency auditor, UI reviewer,
  pipeline validator, ontology validator, runtime-contract reviewer, template-sync validator.
  Each agent declares its execution backend in frontmatter so the orchestrator knows exactly
  which CLI subprocess to use. Trim per-family by editing `active_agents` in
  `config/repos/<slug>.json` when a project does not need a specialist.
- **11-skill library** — design, verify, code-review, testing, ui-design, governance, knowledge,
  automation, efficiency, bluebricks, commit. Skills load on demand when the request matches a
  trigger keyword. No token cost when unused.
- **Per-family JSON registry** — `config/repo-agent-management.json` catalogs agents and skills.
  When you fork and add repositories, each family gets its own `config/repos/<slug>.json` with
  per-family agent topology, skill pack, and specialist overrides.
- **Pre-tool-use guard** — denies destructive shell patterns and protected paths before the tool runs.
- **Post-edit checks** — flag debug statements and credential leaks immediately after every Edit/Write.
- **Composite TDD ledger** — implementation edits are blocked unless `tasks/tdd.json` has a planning
  entry covering the file.
- **Pre-commit verification** — the planning entry's verification commands must pass before the
  commit lands.
- **Session lifecycle** — auto-loaded plan/lessons/memory at session start, auto-saved snapshots
  at session end, auto-handoff at compact.
- **Dual CLI parity** — the same hooks fire from both Claude Code (`.claude/settings.json`) and
  Codex CLI (`.codex/hooks.json`). The wire format is shared, so you author once.
- **Sub-agent execution policy (force_codex)** — a global `config/sub-agent-policy.json` switch
  governs which backend the delegated sub-agents use. Under `force_codex` (the default), a Claude
  `Agent`/`Task` sub-agent spawn is **hard-blocked at the PreToolUse hook**, so delegated work is
  forced to the Codex lane; flip to `unrestricted` / `select` / `per_project` when you want a
  different backend. A deterministic (no-LLM) monitor surfaces any Claude-sub usage.
- **Priority-ordered model/effort routing** — the same `config/sub-agent-policy.json` carries a
  `routing` block: a global `model_rank` / `effort_rank` plus per-TDD-category routes
  (single `{model, reasoning_effort}` or an ordered `prefer` list). Model/effort strings are
  free pass-through — no hardcoded model names, so a new model generation needs zero code change.
  `mir policy resolve --category <cat>` resolves the route so BOTH a Claude main
  (`mcp__codex__codex`) and a Codex main (native `spawn_agent`) route their direct codex calls the
  same way; `mir_executor … --dispatch` resolves it internally. Values are deployment-owned via a
  `MIR_SUB_AGENT_POLICY` global overlay.
- **Git-diff merge gate for delegated execution** — `mir_executor … --dispatch` runs the Codex
  sub-agent in a throwaway git worktree and merges its edits back **only after a deterministic
  gate**: a real `git diff` (an empty diff is a failure) plus a re-run of the change's verification
  commands. The sub-agent's self-reported success is never trusted — the filesystem is.

What this is **not**: a runtime, a framework, or a service. There is no daemon. There is no SaaS.
The harness is just files in your repo. If you delete the directory, your project goes back to
behaving like it did before.

---

## Why dual CLI?

Claude Code and Codex CLI overlap in capability but differ in token budget, scoping, and review
style. Most non-trivial work benefits from using both. Whichever CLI you **open** becomes the
control-plane main (requirements, planning, design, orchestration, judgment); delegated sub-agent
execution stays Codex-centered (code writing, TDD, review). The two mains share one contract — the
rules, hooks, memory, and architecture apply identically no matter which CLI you launched. This
template assumes you will run both — and pins the rules so they cannot drift apart.

The hook events shared by both CLIs — `PreToolUse`, `PostToolUse`, `PreCompact`,
`SessionStart`, `Stop`, `PermissionRequest` — get the same script. Claude Code's additional
events (`TaskCreated`, `TaskCompleted`, `StopFailure`) get Claude-only enforcement.

---

## Quick start (5 minutes)

```bash
# 1. Clone or copy the template into your repo.
git clone https://github.com/youngjin39/claude-codex-harness.git my-project
cd my-project

# 2. Run the setup script.
./setup.sh

# 3. Open the project in Claude Code.
claude .

# 4. Or in Codex CLI.
codex
```

The setup script:
- Makes the hook scripts executable
- Creates starter `tasks/plan.md` and an empty `tasks/tdd.json` if absent
- Initializes `.mir/repo-profile.toml` and runs the placeholder guard
- Prints a post-clone checklist of next steps

Both CLIs will pick up the hooks on next launch. No daemon, no background process.

---

## Using the harness — the loop

For any non-trivial change the harness expects this loop (the gates enforce most of it):

1. **Design first.** Trigger the `design` skill (or just describe the change). For harness / ADR /
   architecture work this is a hard gate before code; capture `user_intent` + design goals up front.
2. **Plan the TDD.** Add a `change` entry to `tasks/tdd.json` for the files you'll touch, with the
   verification command(s). Implementation edits stay blocked until this entry exists.
3. **Delegate the code.** Under `force_codex` the main orchestrates but does **not** edit production
   code inline — it routes edits to the Codex lane (`mir_executor … --dispatch`), and the worktree
   + merge gate verify the result by `git diff`.
4. **Verify.** The pre-commit hook re-runs the ledger's verification commands; a commit whose `pass`
   entry does not actually pass is blocked. Run the full suite yourself before pushing.
5. **Close out.** `session-closeout` records intent + a handoff so the next session — or the *other*
   CLI — resumes with full context. Intent survives compaction and context resets.

Recall memory on demand instead of re-reading everything:

```bash
uv run mir memory query <keyword>     # full-text recall over .mir/memory.db
uv run mir context pull "<query>"     # on-demand context (top-k snippets)
```

---

## Agent topology (12 agents)

### Universal tier (always active)

| Agent | Backend | Role | Purpose |
|---|---|---|---|
| `main-orchestrator` | Claude | control_plane | Entry point, task classification, orchestration |
| `executor-agent` | Codex | execution | Codex-lane code writing and TDD execution |
| `codex-final-reviewer` | Codex | review | Final design-vs-code consistency check (read-only) |
| `quality-agent` | Claude | review | Fallback quality review, tie-break synthesis (read-only) |

### Governance tier

| Agent | Backend | Role | Purpose |
|---|---|---|---|
| `fleet-doc-steward` | Claude | governance | CLAUDE.md / AGENTS.md central governance |

### Specialist tier (opt-in by family)

| Agent | Backend | Scope | Purpose |
|---|---|---|---|
| `cwe-auditor` | Claude | code_app, hybrid_pipeline | CWE-pattern static security scan |
| `dep-auditor` | Claude | code_app, hybrid_pipeline | Dependency drift and license audit |
| `ui-reviewer` | Claude | code_app | UI component and accessibility review |
| `pipeline-validator` | Codex | hybrid_pipeline | Data pipeline schema validation |
| `ontology-validator` | Claude | content_workspace | Content taxonomy and ontology check |
| `runtime-contract-reviewer` | Claude | infra_runtime | Exception class and public API contract check |
| `template-sync-validator` | Claude | template_transitional | Public template sync sanitize validation |

The `execution_backend` field in each agent's frontmatter is the single declarative surface that
tells the orchestrator whether to dispatch via the MCP-backed Codex lane or a direct Claude agent
session. The agent loader (`tools/agent_loader`) validates this frontmatter on demand.

**Dispatch rule (ADR-09)**: Any agent declaring `execution_backend: codex` must be dispatched
via Codex MCP (`mcp__codex__codex` or `mir_executor --dispatch`), NOT via Claude's direct Agent
tool or raw `codex exec`. Violation logs are written to `tasks/log/dispatch-log.jsonl`.

---

## Skill library (11 groups)

| Skill | Trigger keywords | Absorbs legacy slugs |
|---|---|---|
| `design` | design, brainstorm, architecture, plan, interview | brainstorming, writing-plans, deep-interview, + more |
| `verify` | verify, done check, proof, spec check, audit | verification, verify-against-spec, self-audit, review-code |
| `code-review` | review, PR, quality, merge check | — |
| `testing` | test, TDD, unit test, integration test | — |
| `ui-design` | UI, UX, interface, wireframe, component spec | ux-ui-design |
| `governance` | CLAUDE.md, AGENTS.md, fleet governance, project doctor | fleet-instruction-doc-ops, project-doctor, + more |
| `knowledge` | knowledge, wiki, ingest, knowledge graph | knowledge-ingest, knowledge-lint |
| `automation` | runner, long-running, background, monitor, browser | runner, browser-automation |
| `efficiency` | token efficiency, AI readiness, cost analysis | improve-token-efficiency, ai-readiness-cartography |
| `bluebricks` | code, debug, refactor, architecture, module | ai-ready-bluebricks-development |
| `commit` | commit, git, save changes | git-commit |

Skills load only when triggered. Body lives at `.claude/skills/<name>/SKILL.md`.

---

## Per-family JSON pattern

The registry uses a per-family JSON split (ADR-15 v3.7):

```
config/
  repo-agent-management.json   # root catalog (agents, skills, templates)
  repo-agent-management.schema.json
  repos/                       # one file per family (empty in template)
    <your-repo>.json           # per-family entry (add when you fork)
```

Each per-family file declares:
- `active_agents` — which agents are enabled (subset of catalog)
- `active_skills` — which skill groups are enabled
- `agent_overrides.add_specialists` — opt-in specialists beyond the template default
- `agent_overrides.scope_patterns_overrides` — per-specialist file-scope narrowing
- `orchestration_profile` — standard / bounded / minimal

To validate the registry:

```bash
python3 scripts/verify_repo_agent_management.py
```

---

## Project layout

```
.
├── CLAUDE.md                   # Claude Code workspace rules (orchestration, role policy, gates)
├── AGENTS.md                   # Codex CLI mirror — same rules, Codex-flavored
├── ARCHITECTURE.md             # component map — Conductor / Engine / Worker layers
├── setup.sh                    # one-command bootstrap
├── README.md                   # (this file)
├── LICENSE                     # MIT
├── CONTRIBUTING.md             # how to extend the template
│
├── .claude/                    # Claude Code surface
│   ├── settings.json           #   hook + permission config (9 hook surfaces)
│   ├── hooks/                  #   shell scripts (PreToolUse, PostToolUse, ...)
│   ├── skills/                 #   11 trigger-loaded skill groups
│   └── agents/                 #   12 sub-agent personas
│
├── .codex/                     # Codex CLI surface
│   ├── hooks.json              #   6-trigger mirror of .claude/settings.json
│   └── agents/                 #   12 .toml mirrors of .claude/agents/*.md
│
├── .ai-harness/                # the rules (CLI-agnostic)
│   ├── common-ai-rules.md      #   loaded on every task
│   ├── development-ai-rules.md #   loaded on code tasks
│   ├── deny-list.yaml          #   destructive patterns the hook blocks
│   ├── tdd-matrix.md           #   the 12-category TDD ledger spec
│   ├── session-closeout.md     #   end-of-session checklist
│   └── failure-patterns.md     #   recurring AI mistakes worth pinning
│
├── config/                     # agent-management registry
│   ├── repo-agent-management.json        # root catalog
│   ├── repo-agent-management.schema.json # JSONSchema
│   └── repos/                  #   per-family entries (empty in template)
│
├── tools/                      # harness tooling
│   ├── catalog_loader.py       #   ADR-15 v3.7 per-family catalog aggregator
│   ├── agent_loader/           #   ADR-09 frontmatter parser + validator
│   └── profile_compiler/       #   role-policy compiler stub (extend for your fleet)
│
├── scripts/
│   └── verify_repo_agent_management.py  # registry verifier
│
├── tasks/                      # the working ledger
│   ├── plan.md                 #   current phase summary
│   ├── tdd.json                #   composite TDD ledger (the gate)
│   ├── change_log.md           #   what changed and why
│   ├── lessons.md              #   patterns promoted to rules
│   ├── sessions/               #   session snapshots
│   └── handoffs/               #   inter-session handoffs
│
├── docs/                       # prose memory + generated md projections
│   ├── memory-map.md           #   keyword → file index (generated from .mir/memory.db)
│   └── decisions/              #   ADRs
│
├── .mir/                       # canonical memory DB (.mir/memory.db, gitignored)
│
└── examples/                   # short walk-throughs
```

---

## How the gates work

### Pre-tool-use (input-stage)
Before Claude Code or Codex CLI runs `Bash`, `Edit`, `Write`, or `apply_patch`, the hook reads
the deny-list and:
- **blocks** patterns marked `severity: block` (e.g. `rm -rf /`, `git push --force`)
- **warns** on `severity: warn`
- exits 0 otherwise

Code paths (`tools/`, `src/`, `lib/`) additionally require an active Codex session; direct
Claude Edit/Write to those paths is blocked.

### Post-edit-check
After every Edit/Write, the hook scans the changed file for debug statements (`console.log`,
`print(` in non-test code) and credential-shaped strings (AWS keys, JWTs, etc.). Flags are
surfaced to the agent so it has a chance to clean up before commit.

### TDD-guard
Implementation files (anything under `src/`, `app/`, or `lib/` ending in `.py`/`.ts`/`.go`/…)
are blocked from editing unless `tasks/tdd.json` contains a `change` entry whose `targets` list
includes the file. Planning is required *before* coding.

### Pre-commit verification
On `git commit`, the hook walks the changed files, finds the matching ledger entry, and runs its
`categories.*.command` strings. If any test marked `pass` does not actually pass, the commit is
blocked.

The ledger has 12 categories — `unit`, `integration`, `e2e`, `browser`, `edge`, `architecture`,
`availability`, `load`, `soak`, `security`, `compatibility`, `transaction_locking`. Each is either
`pass` (with a runnable command), `covered_existing`, or `not_applicable` (with a written reason).

---

## Sub-agent execution policy & delegated execution

The harness runs on one split: **the opened CLI is the control-plane main (orchestration only);
the sub-agents that do the heavy, context-hungry work — code edits, TDD, review, verification —
run as delegated executors.** A single global setting decides which backend those sub-agents use,
and a hook makes the choice enforceable rather than advisory.

### The policy switch — `config/sub-agent-policy.json`

```json
{ "mode": "force_codex", "per_project": {} }
```

| mode | behavior |
|---|---|
| `force_codex` *(default)* | Claude `Agent`/`Task` sub-agent spawns are **hard-blocked**; all delegated work routes to the Codex lane. |
| `select` | honors an explicit per-call backend request (`--execution-backend`). |
| `per_project` | per-repo override keyed by slug. |
| `unrestricted` | no sub-agent constraint. |

A home-server overlay env (`MIR_SUB_AGENT_POLICY=/path/to.json`) changes the mode without editing
the repo file; the resolver fails closed to `force_codex` on any error. The overlay shallow-merges
over the repo file, so a `routing`-only overlay changes routing while leaving each repo's `mode`
intact.

### Model/effort routing — priority schema

The same file's optional `routing` block decides which model + reasoning effort each delegated
codex call uses, per TDD category:

```json
{
  "mode": "force_codex",
  "routing": {
    "model_rank":  ["<top-model>", "<mid-model>", "<small-model>"],
    "effort_rank": ["xhigh", "high", "medium", "low"],
    "default": { "model": null, "reasoning_effort": null },
    "by_category": {
      "unit":         { "model": "<small-model>", "reasoning_effort": "low" },
      "architecture": { "prefer": [
          { "model": "<top-model>", "reasoning_effort": "xhigh" },
          { "model": "<mid-model>", "reasoning_effort": "high" } ] }
    }
  }
}
```

- `model_rank` / `effort_rank` — global priority order (highest → lowest). Free strings; fill with
  your provider's actual model ids so a new model generation needs no code change.
- `by_category.<cat>` — either a single `{model, reasoning_effort}` or an ordered `prefer` list
  (`prefer[0]` is the primary route). `default` applies when a category has no route; `null` = the
  codex default.

Resolve a route from anywhere:

```bash
uv run mir policy resolve --category architecture   # -> {"model": "...", "reasoning_effort": "..."}
```

`mir_executor … --dispatch` resolves this internally. For **direct** codex calls — a Claude main's
`mcp__codex__codex` or a Codex main's native `spawn_agent` — the main resolves the route with
`mir policy resolve` and passes `model` (+ `config.model_reasoning_effort`) to the call, so both
CLIs route identically. (This is advisory: hooks do not inject routing, and codex→codex native
calls cannot be hook-intercepted, so resolution is uniform on both paths.)

### The gate — `.claude/hooks/sub-agent-policy-gate.sh`

Wired as a PreToolUse hook matching `^(Agent|Task)$`. When the mode is `force_codex` and a Claude
`Agent`/`Task` spawn is attempted, the hook prints a route-to-Codex message and **exits 2**
(blocked). It is slug-free and family-invariant, so the same file deploys to every repo.

```bash
# under force_codex, allow a one-off Claude sub-agent (e.g. an independent cross-model review):
MIR_R3_FALLBACK=1 <your command>
# or relax the policy entirely:
$EDITOR config/sub-agent-policy.json   # set "mode": "unrestricted"
```

### Delegated execution is a verified Codex worktree — `mir_executor --dispatch`

Delegated code work never edits your main tree directly:

```bash
uv run python -m tools.mir_executor execute --background --dispatch \
  --change-id <ledger-id> --category <tdd-category> --repo-root . \
  --codex-args 'exec --sandbox workspace-write "<task or DispatchBrief ref>"' \
  --allow-path tools/ --allow-path tests/ \
  --verify-cmd "uv run pytest tests/ -q"
```

1. a fresh git **worktree** is cut from HEAD;
2. the Codex sub-agent edits there;
3. the **deterministic merge gate** runs — `git diff` (empty diff → fail), an allowlist check, and
   a re-run of the `--verify-cmd` commands;
4. only an approved gate merges the edits back. The sub-agent's stdout / `result.json` is **never**
   the approval input.

This is "trust the filesystem, not the self-report" made executable, and it is the same path the
`executor-agent` (Codex) uses.

### Self-recognition — the monitor

A deterministic, LLM-free scanner (`stall_watchdog`) reads the session transcript and reports, via
`agent-check`, whether any Claude `Agent`/`Task` sub-agent ran while the policy was `force_codex`
— so the operating main can notice and self-correct:

```bash
uv run python -m tools.stall_watchdog.cli agent-check   # look for the CLAUDE_SUB_DISPATCH row
```

The active policy mode is also injected into the session-start context, so the main always knows
which backend it must use.

---

## Customizing for your project

### 1. Add your family repository

Create `config/repos/my-repo.json`:

```json
{
  "slug": "my-repo",
  "display_name": "My Repo",
  "registry_path": "/path/to/my-repo",
  "profile_slug": "my-repo",
  "repository_type": "code_app",
  "rollout_class": "immediate_migrate",
  "overlay_archetype": "code_app",
  "status": "active",
  "management_template_id": "code_app",
  "management_mode": "harness-managed",
  "profile_source": {"kind": "live-profile", "path": ".mir/repo-profile.toml"},
  "managed_domains": [
    "central_ownership_contract",
    "repository_overlay",
    "generation_verification_pipeline",
    "operating_contract",
    "harness_structure",
    "harness_format",
    "agent_management"
  ],
  "fleet_management": {
    "active_target": true,
    "control_repo": false,
    "runtime_contract_exception": false,
    "diet_mode": "normal"
  },
  "exception_review": {
    "requires_repo_specific_runtime_review": false,
    "protected_categories": []
  },
  "evidence_trace": {
    "source_documents": [],
    "open_questions": [],
    "assumptions": []
  },
  "notes": [],
  "active_agents": ["main-orchestrator", "executor-agent", "codex-final-reviewer", "quality-agent"],
  "active_skills": ["design", "verify", "testing", "code-review", "bluebricks"]
}
```

### 2. Adjust the deny-list

Edit `.ai-harness/deny-list.yaml` — add or remove patterns the pre-tool-use hook blocks. Each
entry has `id`, `pattern` (regex), `severity` (`block` / `warn`), and `reason`.

### 3. Set your role policy

Edit `CLAUDE.md` (the role policy table) and `AGENTS.md` (the Codex-side mirror).
Run `python3 scripts/verify_repo_agent_management.py` to confirm the registry is consistent.

---

## Comparison

This template is opinionated about one specific thing: **enforcement**. It exists because
advisory rules in markdown — "please don't push to main", "remember to write tests" — are read
by AI agents the same way humans read EULAs. Rules need to be code that runs, not text that gets
glanced at.

### The unique slice

Specifically, this template is the only one in the comparison table that:

1. **Wires both Claude Code and Codex CLI to the same hook scripts**, so when you fix a deny-list
   pattern it fixes both CLIs without a copy.
2. **Gates implementation edits behind a typed TDD ledger** (`tasks/tdd.json`), not a free-form
   list. The 12-category matrix is the contract.
3. **Carries a 12-agent catalog with declared execution backends** so the orchestrator knows at
   dispatch time whether to use `claude` or the MCP-backed Codex lane — no runtime guessing.
4. **Treats hook bypass attempts (e.g. `--no-verify`) as deny-list patterns themselves**, so the
   gate cannot be lifted by inviting the agent to lift it.
5. **Ships in a form you can rip out**. There is no runtime, no service, no schema migration.
   Delete `.claude/`, `.codex/`, `.ai-harness/`, `config/`, `tools/` and your repo behaves like
   a normal repo again.

### When this template fits well

- A repo where you run both Claude Code and Codex CLI and want them to stay coherent.
- A team where "please don't" notes have failed before.
- A project that can express its TDD plan in 12 categories before each change.
- A solo developer who wants the Saturday-morning AI-edit session to not destroy Friday-night's work.

### When this template is the wrong fit

- You need a single-agent setup with no enforcement (use Claude Code default).
- You want a managed multi-agent platform (use Archon, autoGPT family, etc.).
- Your project does not have a TDD culture and cannot adopt one — the gates here will fight you
  the whole way.
- You need cross-language hooks beyond shell (the hook scripts are bash).

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Issues and PRs welcome — particularly adding new
deny-list patterns, new skills, and new examples. Avoid implementation-specific code; this is a
template, not a runtime.

## License

MIT — see [LICENSE](LICENSE). Use it, fork it, strip it for parts.
