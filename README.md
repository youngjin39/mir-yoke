# Mir Yoke

**An agent-guided, proportional harness-engineering template for Claude Code + Codex CLI.**

Mir Yoke is a public template and reference repository. It is not an agent runtime and has no
standing authority over a repository that adopts or consults it. Every adoption is an explicit,
repository-local owner choice.
It is not a universal installer; the supported automated bootstrap boundary is macOS, Linux, and
WSL, while the active agent adapts the baseline to the repository in front of it.

A reusable baseline for teams who want their AI coding assistants to share one operating contract.
The active agent reads the repository's current state and local instructions, then adapts only the
applicable template assets. Hooks block narrow deterministic hazards, while design, delegation,
TDD, review, and verification scale with the changed boundary.

If you have ever asked an AI to "be careful" and watched it overwrite a config file anyway, this
is the answer: replace politely-worded prompts with executable guards.

> [!WARNING]
> A full `git clone` of Mir Yoke is a provider/maintainer checkout, not a slim product repository.
> Product bootstrap first installs a copied Mir CLI outside the repository. Only Phase 2 finalize,
> after all readiness evidence passes, automatically quarantines the exact hash-matched provider
> payload and re-verifies the external CLI. A failed check rolls the move back and cannot produce a
> ready receipt. Do not implement product work during `restart_required` or while
> `R20 adopter_payload_boundary` still reports provider markers.

---

## What this is

A directory layout + hook scripts + rule documents installed through an explicit greenfield or
existing-repository adoption path so that Claude Code and Codex CLI share the same playbook.

What you get out of the box:

- **Profile-selected agent catalog** — each greenfield adopter retains only the agents declared by
  its capability pack: 5 for content workspaces, 7 for code applications or infrastructure, and
  11 for hybrid pipelines. The provider-only `template-sync-validator` remains available only to
  Mir Yoke/public-template maintainers and is removed from every adopter payload. Each retained
  agent declares its execution backend so the orchestrator can dispatch it consistently.
- **13-skill library in three global plugins** — `mir-core` always supplies architecture,
  `spec-architect`, governance, memory, and verification; `mir-code` and `mir-content` add the
  profile-specific code or no-code capabilities. Namespaces prevent project/global duplication.
- **Required portable memory** — every completed bootstrap proves a local SQLite+FTS5 index over
  tracked Markdown. Embeddings and vectors are optional; memory is not.
- **External-first storage profile** — an optional shared storage root keeps uv cache, managed
  Python downloads, and the global capability provider on the same external filesystem. Every
  product receives its own CLI tool namespace and keeps its project environment local; credentials
  stay in the user home.
- **Pinned capability source** — a trusted Git URL plus exact commit and tree hashes let later
  agents check for skill/agent updates without silently activating mutable remote instructions.
- **Per-repository JSON registry** — `config/repo-agent-management.json` catalogs agents and skills.
  A consumer may maintain one explicit `config/repos/<slug>.json` for its own agent topology,
  skill pack, and specialist overrides; Mir Yoke never discovers sibling repositories.
- **Pre-tool-use guard** — denies destructive shell patterns and protected paths before the tool runs.
- **Post-edit checks** — flag debug statements and credential leaks immediately after every Edit/Write.
- **Composite TDD ledger** — broad or high-risk work can record a typed verification matrix in
  `tasks/tdd.json`; bounded work can use the smallest relevant check directly.
- **Pre-commit verification** — explicitly selected verification commands must pass before the
  commit lands.
- **Session lifecycle** — startup loads compact repository identity and safety context, deeper
  history is retrieved on demand, and closeout refreshes one canonical handoff.
- **Dual CLI parity** — the same hooks fire from both Claude Code (`.claude/settings.json`) and
  Codex CLI (`.codex/hooks.json`). The wire format is shared, so you author once.
- **Sub-agent execution policy** — `config/sub-agent-policy.json` controls a delegated backend when
  delegation is useful. The template defaults to `unrestricted`; projects may explicitly select
  `force_codex`, `select`, or `per_project` for their own boundary.
- **Priority-ordered model/effort routing** — the same `config/sub-agent-policy.json` carries a
  `routing` block: a global `model_rank` / `effort_rank` plus per-TDD-category routes
  (single `{model, reasoning_effort}` or an ordered `prefer` list). Model/effort strings are
  free pass-through — no hardcoded model names, so a new model generation needs zero code change.
  `mir policy resolve --category <cat>` resolves the route so BOTH a Claude main
  (`mcp__codex__codex`) and a Codex main (native `spawn_agent`) route their direct codex calls the
  same way; `mir_executor … --dispatch` resolves it internally. Values are deployment-owned via a
  `MIR_SUB_AGENT_POLICY` global overlay.
- **Optional Git-diff merge gate for delegated execution** — `mir_executor … --dispatch` runs the Codex
  sub-agent in a throwaway git worktree and merges its edits back **only after a deterministic
  gate**: a real `git diff` (an empty diff is a failure) plus a re-run of the change's verification
  commands. The sub-agent's self-reported success is never trusted — the filesystem is.

What this is **not**: a runtime, a framework, or a service. There is no daemon. There is no SaaS.
The harness is just files in your repo. If you delete the directory, your project goes back to
behaving like it did before.

---

## Bootstrap a new product (agent-guided)

Clone a pinned Mir Yoke release with its Git ancestry into the intended product repository, detach
its push path from the provider, open it in Claude Code or Codex CLI, and say:

> Read `BOOTSTRAP.md` and bootstrap this repository as a **code_app** project for **"an internal
> billing API in Python"**. Do not begin product implementation until Phase 2 finalize reports a
> ready receipt and completes the adopter slim step.

On macOS, Linux, or WSL, the agent follows [`BOOTSTRAP.md`](BOOTSTRAP.md): it inspects the target,
selects a profile, runs the supported coordinator, installs a copied external CLI plus the pinned
global plugins, rewrites only exact release-matched provider contracts/tasks into product-owned
baselines, installs the exact provider commit with tracked production constraints under a
project-specific external runtime, builds the required memory index, and selects the project-local
agent pack. The machine-local receipt separately binds the installed executable
digest. After a runtime restart it performs the
mandatory initial
`design` → `spec-architect` structure pass, records pinned non-empty spec evidence, and verifies a
ready receipt. The last successful finalize action journals and moves the unchanged provider
payload into an ignored recovery quarantine, proves the remaining adopter tree with that external
CLI, and commits the transaction only after the ready receipt is durable.

Before the first setup, the agent renames the cloned provider remote and disables its push URL (or
uses a separately materialized local-only repository), then optionally adds the product-owned
`origin`. Setup rejects any effective push URL that still targets Mir Yoke before host or repository
mutation. It never changes Git remotes, commits, pushes, or rewrites history itself.

Native Windows is not an automated bootstrap target. `setup.ps1` exits without changing the
repository and directs the agent to WSL or to a manual, reference-only adaptation based on the
target repository's own contract. Mir Yoke does not claim readiness for that manual route.

Prefer to do it yourself? `BOOTSTRAP.md` has a manual checklist too, and the Quick start below is the
5-minute mechanical path.

---

## Why dual CLI?

Claude Code and Codex CLI overlap in capability but differ in token budget, scoping, and review
style. Most non-trivial work benefits from using both. Whichever CLI you **open** becomes the
control-plane main (requirements, planning, design, orchestration, judgment). When delegation is
selected, Codex is the preferred backend for code, TDD, and independent review. The two mains share one contract — the
rules, hooks, memory, and architecture apply identically no matter which CLI you launched. This
template assumes you will run both — and pins the rules so they cannot drift apart.

The hook events shared by both CLIs — `PreToolUse`, `PostToolUse`, `PreCompact`,
`SessionStart`, `Stop`, `PermissionRequest` — get the same script. Claude Code's additional
events (`SessionEnd`, `TaskCreated`, `TaskCompleted`, `StopFailure`) get Claude-only enforcement.

---

## Prerequisites

Project policy, hooks, permissions, orchestration, and agents are repository-local. Reusable common
skills are installed once as namespaced Claude/Codex plugins from the pinned Git provider; raw
same-name copies under user or project skill directories are rejected.

The **Codex delegation lane** (`executor-agent`, `codex-final-reviewer`, `mir_executor --dispatch`,
the `mcp__codex__codex` tool) additionally needs:

1. **Codex CLI** installed and logged in (`codex` on `PATH`). Claude Code remains supported and
   is required only when the adopter chooses to use the Claude runtime.
2. **Python 3.12+, Git, `uv`, and `jq`** for setup and hook JSON parsing. Setup installs Mir as a
   copied `uv tool`; afterward use `scripts/mir.sh` or `scripts/mir.ps1`.
3. **Bash** on macOS/Linux/WSL. On Windows, run the supported path inside WSL; native PowerShell
   bootstrap is guidance-only and makes no repository changes.
4. **The `codex` MCP server wired** so the `mcp__codex__codex` tool exists. This template does NOT
   ship a `.mcp.json` (it would carry machine-specific paths). Copy the example and adjust:

   ```bash
   cp .mcp.json.example .mcp.json
   # edit .mcp.json: set "command" to your codex binary ("codex" if on PATH, else an absolute
   # path) and CODEX_HOME if your Codex home is not ~/.codex
   ```

Optional: shared global coding rules (Think Before Coding / Simplicity First / Surgical Changes /
Goal-Driven Execution) live in [`global-rules/`](global-rules/) — merge them into your own global
`~/.claude/CLAUDE.md` and `~/.codex/AGENTS.md` if you want them applied across all your repos, not
just this one. They are optional; the project-local `CLAUDE.md` is self-sufficient without them.

The bootstrap does not claim `ready` until Codex CLI/desktop reports the selected plugins enabled
at the pinned hashes and a new Codex session records the expected skill catalog. Claude
installation and discovery remain visible status evidence but do not block activation. Codex IDE
extensions are outside this plugin-ready claim.

Existing repositories that already contain same-name raw skills should use the
[local plugin migration reference](docs/operations/global-plugin-migration.md) before activation.
Checks are limited to roots the user explicitly names; Mir Yoke does not discover or inventory
sibling repositories.

## Team use (required gates)

Per [ADR-72](docs/decisions/adr-72-dispatch-resilience.md), local pre-commit hooks, the TDD ledger,
and the merge gate are local evidence suitable for single-operator use only. Multi-contributor
adoption requires a server-side authoritative gate: protect the `main` branch, run tests and lint
again in CI on the server, and prohibit direct pushes to `main`. This is a mandatory adoption
prerequisite for team use.

---

## Maintainer checkout smoke test

The following checkout is suitable for evaluating or maintaining Mir Yoke itself. It is not a
product-adopter result, and the setup command must not be used to bypass the template Profile or
R20. Use the provider commands below only when the checkout will remain Mir Yoke itself. For a new
product, follow the two-phase bootstrap; do not change the Profile by hand or start product work
before its final slim result is ready.

```bash
# 1. Clone the provider/maintainer source for evaluation.
git clone https://github.com/youngjin39/mir-yoke.git mir-yoke
cd mir-yoke

# 2. Validate the maintainer checkout without changing its Profile.
uv sync
uv run python -m tools.harness_consistency run
uv run pytest -q tests/test_public_template_identity.py tests/test_template_asset_classification.py

# 3. Optionally wire the Codex MCP server for Mir Yoke maintenance.
cp .mcp.json.example .mcp.json   # then edit the codex command/CODEX_HOME

# 4. Open the maintainer checkout in Claude Code.
claude .

# 5. Or in Codex CLI.
codex
```

Product bootstrap profiles, storage options, the WSL route for Windows hosts, the final automatic
slim transaction, and existing-repository assessment are documented in `BOOTSTRAP.md`.

---

## Using the harness — the loop

Use the smallest sufficient loop for the change:

1. **Understand the boundary.** Use `design` when a material choice exists; tiny, clear work may
   proceed directly.
2. **Choose evidence.** Use `tasks/tdd.json` for broad or high-risk work. Otherwise identify the
   smallest check that can fail for the changed behavior.
3. **Choose execution.** Main may implement bounded work directly. Delegate when isolation,
   parallelism, specialist context, independent review, or restartability is worth the cost.
4. **Verify.** Run the selected check and add broader coverage only when the risk or release context
   warrants it. Failed explicitly required verification blocks a completion claim.
5. **Close out.** Refresh the canonical handoff with decisions, unresolved issues, next actions,
   changed files, verification, and key risks.

Recall memory on demand instead of re-reading everything:

```bash
./scripts/mir.sh memory query <keyword>     # full-text recall over .mir/memory.db
./scripts/mir.sh context pull "<query>"     # on-demand context (top-k snippets)
```

An already initialized repository may expose `.\scripts\mir.ps1` as a convenience launcher. Its
presence does not make native Windows an automated bootstrap or ready-receipt platform.

---

## Agent template catalog

### Universal starter tier

| Agent | Backend | Role | Purpose |
|---|---|---|---|
| `main-orchestrator` | Claude | control_plane | Entry point, task classification, orchestration |
| `executor-agent` | Codex | execution | Codex-lane code writing and TDD execution |
| `codex-final-reviewer` | Codex | review | Final design-vs-code consistency check (read-only) |
| `quality-agent` | Claude | review | Fallback quality review, tie-break synthesis (read-only) |

### Optional governance reference

| Agent | Backend | Role | Purpose |
|---|---|---|---|
| `fleet-doc-steward` | Claude | governance | Read-only, repository-local instruction-doc advice |

### Specialist tier (opt-in by family)

| Agent | Backend | Scope | Purpose |
|---|---|---|---|
| `cwe-auditor` | Claude | code_app, hybrid_pipeline | CWE-pattern static security scan |
| `dep-auditor` | Claude | code_app, hybrid_pipeline | Dependency drift and license audit |
| `ui-reviewer` | Claude | code_app | UI component and accessibility review |
| `pipeline-validator` | Codex | hybrid_pipeline | Data pipeline schema validation |
| `ontology-validator` | Claude | content_workspace | Content taxonomy and ontology check |
| `runtime-contract-reviewer` | Claude | infra_runtime | Exception class and public API contract check |
| `template-sync-validator` | Claude | public_template | Explicit, local template comparison validation |

The `execution_backend` field in each agent's frontmatter is the single declarative surface that
tells the orchestrator whether to dispatch via the MCP-backed Codex lane or a direct Claude agent
session. The agent loader (`tools/agent_loader`) validates this frontmatter on demand.

**Dispatch rule (ADR-09)**: Any agent declaring `execution_backend: codex` must be dispatched
via Codex MCP (`mcp__codex__codex` or `mir_executor --dispatch`), NOT via Claude's direct Agent
tool or raw `codex exec`. Violation logs are written to `tasks/log/dispatch-log.jsonl`.

---

## Skill library (13 groups)

| Skill | Trigger keywords | Absorbs legacy slugs |
|---|---|---|
| `design` | design, brainstorm, architecture, plan, interview | brainstorming, writing-plans, deep-interview, + more |
| `spec-architect` | requirements completeness, write a spec, architecture docs, traceability | — |
| `verify` | verify, done check, proof, spec check, audit | verification, verify-against-spec, self-audit, review-code |
| `code-review` | review, PR, quality, merge check | — |
| `testing` | test, TDD, unit test, integration test | — |
| `ui-design` | UI, UX, interface, wireframe, component spec | ux-ui-design |
| `governance` | CLAUDE.md, AGENTS.md, instruction governance, project doctor | instruction-doc ops, project-doctor, + more |
| `knowledge` | knowledge, wiki, ingest, knowledge graph | knowledge-ingest, knowledge-lint |
| `memory-gc` | memory GC (explicit user request only) | — |
| `automation` | runner, long-running, background, monitor, browser | runner, browser-automation |
| `efficiency` | token efficiency, AI readiness, cost analysis | improve-token-efficiency, ai-readiness-cartography |
| `bluebricks` | code, debug, refactor, architecture, module | ai-ready-bluebricks-development |
| `commit` | commit, git, save changes | git-commit |

Skills load only when triggered. Canonical bodies live under `plugins/<pack>/skills/<name>/SKILL.md`
and are installed through the Claude and Codex marketplace manifests.

---

## Per-repository JSON pattern

The registry uses a per-repository JSON split:

```
config/
  repo-agent-management.json   # root catalog (agents, skills, templates)
  repo-agent-management.schema.json
  repos/                       # explicit repository profiles
    <your-repo>.json           # local entry (add when you fork)
```

Each repository file declares:
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
├── setup.sh / setup.ps1        # supported Unix bootstrap / native-Windows guidance
├── README.md                   # (this file)
├── LICENSE                     # MIT
├── CONTRIBUTING.md             # how to extend the template
│
├── .claude/                    # Claude Code surface
│   ├── settings.json           #   hook + permission config (9 hook surfaces)
│   ├── hooks/                  #   shell scripts (PreToolUse, PostToolUse, ...)
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
│   ├── capability-sources.json #   trusted Git source + profile packs
│   ├── repo-agent-management.json        # root catalog
│   ├── repo-agent-management.schema.json # JSONSchema
│   └── repos/                  #   explicit repository profiles
│
├── tools/                      # harness tooling
│   ├── catalog_loader.py       #   explicit local profile loader
│   ├── agent_loader/           #   ADR-09 frontmatter parser + validator
│   └── harness_consistency/    #   template-local structural validators
│
├── scripts/
│   └── verify_repo_agent_management.py  # registry verifier
│
├── tasks/                      # the working ledger
│   ├── plan.md                 #   current phase summary
│   ├── tdd.json                #   composite TDD ledger (the gate)
│   ├── change_log.md           #   what changed and why
│   ├── lessons.md              #   patterns promoted to rules
│   ├── sessions/               #   Stop/StopFailure runtime audit logs
│   └── handoffs/               #   canonical inter-session handoff
│
├── plugins/                    # namespaced global mir-core/mir-code/mir-content skills
├── docs/                       # durable Markdown memory + generated projections
│   ├── memory-map.md           #   generated keyword → file index
│   └── decisions/              #   ADRs
│
├── .mir/                       # machine-local DB/receipt + tracked capability lock
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

The opened CLI is the control-plane Main. It may work directly or select delegated executors when
their isolation, parallelism, or independent context adds value. A project-owned setting chooses
the backend for work that is delegated.

### The policy switch — `config/sub-agent-policy.json`

```json
{ "mode": "unrestricted", "per_project": {} }
```

| mode | behavior |
|---|---|
| `force_codex` | Explicitly requires delegated work to use the Codex lane. |
| `select` | honors an explicit per-call backend request (`--execution-backend`). |
| `per_project` | per-repo override keyed by slug. |
| `unrestricted` *(default)* | No sub-agent backend constraint; Main still applies repository policy. |

A home-server overlay env (`MIR_SUB_AGENT_POLICY=<abs-path-to-policy.json>`) changes the mode without
editing the repo file. The overlay shallow-merges over the repo file, so a `routing`-only overlay
changes routing while leaving each repo's `mode` intact.

### Model/effort routing — priority schema

The same file's optional `routing` block decides which model + reasoning effort each delegated
codex call uses, per TDD category:

```json
{
  "mode": "unrestricted",
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
./scripts/mir.sh policy resolve --category architecture   # -> {"model": "...", "reasoning_effort": "..."}
```

`mir_executor … --dispatch` resolves this internally. For **direct** codex calls — a Claude main's
`mcp__codex__codex` or a Codex main's native `spawn_agent` — the main resolves the route with
`mir policy resolve` and passes `model` (+ `config.model_reasoning_effort`) to the call, so both
CLIs route identically. (This is advisory: hooks do not inject routing, and codex→codex native
calls cannot be hook-intercepted, so resolution is uniform on both paths.)

### The gate — `.claude/hooks/sub-agent-policy-gate.sh`

Wired as a PreToolUse hook matching `^(Agent|Task)$`. When a project explicitly selects
`force_codex` and a Claude
`Agent`/`Task` spawn is attempted, the hook prints a route-to-Codex message and **exits 2**
(blocked). It is repository-agnostic, so a consumer may explicitly adopt the same starter file
locally.

```bash
# under force_codex, allow a one-off Claude sub-agent (e.g. an independent cross-model review):
MIR_R3_FALLBACK=1 <your command>
# or relax the policy entirely:
$EDITOR config/sub-agent-policy.json   # set "mode": "unrestricted"
```

### Optional isolated delegation — `mir_executor --dispatch`

When isolated delegation is useful, run it in a verified worktree:

```bash
uv run python -m tools.mir_executor execute --background --dispatch \
  --change-id <ledger-id> --category <tdd-category> --repo-root . \
  --codex-args '<task or DispatchBrief ref>' \
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

Mir Yoke ships no watchdog or background monitor. A consumer may inspect its own task and runtime
evidence with explicit one-shot commands selected by that repository's local contract.

---

## Customizing for your project

### 1. Define your repository-local profile

Use `config/repos/example.json` as the canonical template for your repository entry:

```json
{
  "slug": "my-repo",
  "display_name": "My Repo",
  "registry_path": ".",
  "profile_slug": "my-repo",
  "repository_type": "code_app",
  "adoption_mode": "explicit_local",
  "overlay_archetype": "code_app",
  "status": "active",
  "management_template_id": "code_app",
  "management_mode": "self-maintained-template",
  "profile_source": {"kind": "live-profile", "path": ".mir/repo-profile.toml"},
  "managed_domains": [
    "repository_overlay",
    "generation_verification_pipeline",
    "operating_contract",
    "harness_structure",
    "harness_format",
    "agent_management"
  ],
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
  "active_skills": ["design", "spec-architect", "verify", "testing", "code-review", "bluebricks"]
}
```

### 2. Adjust the deny-list

Edit `.ai-harness/deny-list.yaml` — add or remove patterns the pre-tool-use hook blocks. Each
entry has `id`, `pattern` (regex), `severity` (`block` / `warn`), and `reason`.

### 3. Set your role policy

Edit `.mir/repo-profile.toml` for detailed role boundaries and keep only shared startup invariants
in `CLAUDE.md`. Then run `scripts/generate_codex_derivatives.sh`; `AGENTS.md` is generated and must
not be edited directly. Run `python3 scripts/verify_repo_agent_management.py` to confirm the
registry is consistent.

---

## Comparison

This template is opinionated about one specific thing: deterministic hazards should have executable
guards, while workflow choices should stay proportional to the task.

### The unique slice

Specifically, this template is the only one in the comparison table that:

1. **Wires both Claude Code and Codex CLI to the same hook scripts**, so when you fix a deny-list
   pattern it fixes both CLIs without a copy.
2. **Provides a typed TDD ledger** (`tasks/tdd.json`) for broad or high-risk work without forcing it
   onto every bounded edit.
3. **Carries a 12-agent catalog with declared execution backends** so the orchestrator knows at
   dispatch time whether to use `claude` or the MCP-backed Codex lane — no runtime guessing.
4. **Treats hook bypass attempts (e.g. `--no-verify`) as deny-list patterns themselves**, so the
   gate cannot be lifted by inviting the agent to lift it.
5. **Ships without a daemon or SaaS dependency.** The required memory engine is repository-local;
   tracked Markdown remains portable and the SQLite index can be rebuilt on every machine.

### When this template fits well

- A repo where you run both Claude Code and Codex CLI and want them to stay coherent.
- A team where "please don't" notes have failed before.
- A project that wants a structured TDD matrix for changes whose risk justifies one.
- A solo developer who wants the Saturday-morning AI-edit session to not destroy Friday-night's work.

### When this template is the wrong fit

- You need a single-agent setup with no enforcement (use Claude Code default).
- You want a managed multi-agent platform (use Archon, autoGPT family, etc.).
- You require native-Windows automation or a native-PowerShell ready receipt; use the supported WSL
  route or another harness designed for that runtime.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Issues and PRs welcome — particularly adding new
deny-list patterns, new skills, and new examples. Avoid implementation-specific code; this is a
template, not a runtime.

## License

MIT — see [LICENSE](LICENSE). Use it, fork it, strip it for parts.
