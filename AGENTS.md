<!-- GENERATED FILE: edit CLAUDE.md and rerun scripts/generate_codex_derivatives.sh -->

# Codex Project Instructions


## Source Of Truth
- Edit `CLAUDE.md`, `.claude/agents/*`, `.claude/skills/*`.
- Do not hand-edit `AGENTS.md`, `.codex/`, or `.agents/`.

## Startup
- Read the compact repository identity and safety context, classify the task, and retrieve only relevant depth.
- Use generated Codex skills first.
- If derived files are stale, regenerate from Claude source.

- Skills: `bluebricks, code-review, commit, design, efficiency, governance, knowledge, memory-gc, automation, testing, ui-design, verify`

## Main-Agent Orchestration Contract
- The opened CLI (Claude or Codex) is the control_plane main; Codex main carries the same orchestration contract as Claude main.
- Full Startup Protocol, Ambiguity Gate, and Task Classification: `.codex/agents/main-orchestrator.toml` (generated mirror of `.claude/agents/main-orchestrator.md`) - adopt it as your session contract.
- Ambiguity Gate:
  - Specificity signals: file path, function name, numbered steps, or error message.
  - 0 specificity signals -> load `design` skill (interview subtype) and resolve ambiguity before execution.
  - `force:` prefix bypasses the ambiguity gate.
- Task Classification:
  - 0 specificity signals -> design interview -> ambiguity gating.
  - Tiny or bounded work -> execute directly -> smallest useful check -> done.
  - Normal work -> use a short design note only when a material choice exists; execute directly or delegate when useful.
  - Heavy, restartable, or cross-repo work -> persist a plan or `DispatchBrief`; use isolation or delegation when it reduces risk.
- Classify from uncertainty, blast radius, coordination, and reversibility, not step or file count.
- Source-of-truth, protected-scope, and fleet rollout boundaries still apply to harness and generated surfaces.

## Codex Hook-Mirror Obligations
- [Codex] `SessionStart`: read the compact repository profile and safety context. Do not automatically full-read `tasks/plan.md`, lessons, history, or unrelated workflow docs; retrieve them only after task classification.
- [Codex] `PreCompact`: before compaction, manually create a handoff document in `tasks/handoffs/` mirroring the PreCompact contract.
- [Codex] `PostToolUse`: after edits, manually review for debug leftovers and credential leaks.
- [Codex] `SessionEnd`: at session end, manually create a session snapshot in `tasks/sessions/` mirroring the SessionEnd contract.
- [Codex] `UserPromptSubmit`: for substantial prompts, run `uv run mir context pull "<query>" [--path <target>] [--risk low|normal|high]` for task-scoped retrieval.
- [Codex] `TaskCreated` / `TaskCompleted`: use `tasks/tdd.json` for broad or high-risk work; lifecycle hooks are advisory.

# Claude+Codex Harness Template — Opinionated Claude Code Starter

## Template Purpose

**This repo is the canonical harness engineering template.** `git clone` it when starting a new project to get a fully-configured harness structure immediately applicable.

- `docs/harness-engineering/` — complete harness engineering reference (phases 0-14, applications, runbooks). Covers every phase from scratch to fleet-grade operation.
- `.ai-harness/` — common AI execution rules, session closeout, TDD matrix, deny list, failure patterns, bluebricks.
- `.claude/hooks/` — session-start (context-core, doc-guard, profile enforcement), pre-tool-use Codex routing, TDD guard, stop audit.
- `.mir/repo-profile.toml` + `.mir-preserve.toml` + `.mir/boundary.md` — family profile files required by all active repos.
- `CLAUDE.md` + `AGENTS.md` — replace placeholder family/slug values and update profile block after clone.

**After clone**: (1) set `family=` in `.mir/repo-profile.toml` (setup.sh warns if placeholder remains), (2) replace `your-harness` slug in repo-profile.toml, (3) run `./setup.sh` to register hooks and create task files, (4) run `uv run mir migrate up` to initialize the memory store, (5) run `uv run python scripts/verify_context_paths.py` to verify harness path wiring.


## Required Reads
- `tasks/plan.md`
- `docs/decisions/role-policy.md`

**On-demand (do NOT full-read — already covered, token diet):** `tasks/lessons.md` is injected live every session start; `docs/memory-map.md` is a generated keyword index — reach it via `uv run mir memory query <keyword>`, not a full read.

## Memory (DB-canonical)
- Canonical store: `.mir/memory.db` (SQLite + FTS5 + sqlite-vec). `docs/memory-map.md` and `tasks/lessons.md` are **generated projections** — never hand-edit inside `mir:generated` markers.
- Bootstrap once after cloning: `uv run mir migrate up`. Recall: `uv run mir memory query <keyword>`. Full capture/render command suite: `uv run mir --help`.

## Build & Run
- Starter-only configuration. Update commands when a concrete code product is added.

## AI Development Harness
- Non-code tasks follow `.ai-harness/common-ai-rules.md` and `.ai-harness/session-closeout.md`.
- Use `bluebricks` for non-trivial codebase boundaries, debugging, refactoring, architecture review, or repository exploration; skip the load for an obvious tiny edit.
- Code-development safeguards live in `.ai-harness/development-ai-rules.md`, `.ai-harness/bluebricks.md`, `.ai-harness/tdd-matrix.md`, `.ai-harness/deny-list.yaml`, and `.ai-harness/failure-patterns.md`.
- Code-development proof rule: understand the affected boundary, make the smallest sufficient change, and run the smallest check that can fail for the changed behavior. Use a design artifact or `tasks/tdd.json` only when risk or restartability justifies it.

## Project Structure
- Root control files: `CLAUDE.md`, `AGENTS.md`, `.mcp.json` (optional — add if your project uses MCP servers), `setup.sh`, `README.md`
- Harness rules: `.ai-harness/`
- Runtime source: `.claude/`
- Working state: `tasks/`
- Long-term memory: `.mir/memory.db` (canonical DB); `docs/` holds prose + generated md projections

## Workflow
- 0 specificity signals: load `design` skill (interview subtype).
- Simple non-code work: execute directly + self-check.
- Bounded work with a clear route may execute directly with a focused check.
- Use a short design note only when a material choice exists; persist a plan or `DispatchBrief` for broad, restartable, protected, or cross-repo work when it adds recovery value.
- Use `ui-design` for material UI choices and `automation` when restartability is actually needed.
- Choose direct execution, delegation, TDD ledgers, review, worktrees, and full-suite verification in proportion to uncertainty, blast radius, reversibility, and coordination cost.
- Ponytail baseline: understand the real flow, then stop at the first sufficient rung—remove unnecessary work, reuse project code, use built-ins or the standard library, use a justified dependency, and write minimum custom code last.

## Continuation Loop Protocol
- Applies to BOTH mains: whichever CLI is opened, Claude or Codex, follows the same file-backed continuation loop.
- Cursor of record: `tasks/plan.md` formal `Step N:` lines; do not create a second cursor in `run_state.json`.
- Read the cursor with `uv run mir loop next --json` and select the next coherent non-DONE work unit.
- A step may carry `brief=<path>` or `tdd=<change_id>#<category>` when those artifacts are useful; they are not universal ceremony.
- Execute directly or through the delegated lane according to the task, record the selected evidence, and update only the cursor owned by the main.
- Complete one coherent, independently verifiable work unit before advancing the cursor.
- A failed step returns control without automatic retry. Retry only after a plausible transient cause or a materially changed brief or approach.
- `BLOCKED` means no fabricated continuation: a main agent or user must revise the plan or brief.
- `COMPLETE` means all machine steps in the active section are `DONE` or `CLOSED`.
- Non-LLM automation may drive the loop, but it must preserve hard safety boundaries and explicitly selected verification.
- `tools/run_orchestrator` remains observer-only; it is not the continuation executor.


## Subagent Resource Management
- Use sub-agents when parallelism, isolation, specialist context, or context economy justifies their coordination cost. Direct bounded work is valid.
- Default live subagent cap = 4. Raise it only when Claude/Codex lanes are clearly independent and the current lane is healthy.
- Design-process work may raise the live cap to 4 without separate user approval when Step 2 parallel analysis and Step 4 independent verification both need coverage; record the temporary cap in `tasks/plan.md` or the active handoff note.
- Prefer `fork_context: false` for bounded harness docs, config, or verifier work. Use `fork_context: true` only for broad role-policy review, runtime-contract review, or independent final verification.
- Close completed, timed-out, or errored subagents before the next wave so experiments do not leave stale lanes open.
- If `spawn_agent` returns capacity or thread-limit errors, stop parallel expansion, reduce ownership to one harness surface per subagent, retry one subagent at a time, and record degraded mode in the active plan or handoff.

### Sub-agent Routing
- Claude-main → Codex sub-agent: use Codex MCP (`mcp__codex__codex`; continue with `codex-reply`). Read-only investigation/review = `sandbox=read-only`; code-writing/mutating = `danger-full-access` (`workspace-write` forbidden).
- Codex-main → Codex sub-agent: use native `multi_agent_v1` (`tool_search` → `spawn_agent` → `wait_agent` → `close_agent`) for read-only breadth.
- Use `mir_executor --dispatch` for in-repo work when worktree isolation, restartability, or a deterministic merge gate is worth the overhead.
- **Codex sub-agent = lightweight mcp (ADR-67)**: slim base-instructions + `config{project_doc_max_bytes:0}` (blocks cwd AGENTS.md auto-load = token savings) · per-task `model`/`model_reasoning_effort` routing · `stall_timeout` watchdog + live progress monitoring · global policy `config/sub-agent-policy.json` · dispatch/execute = mcp-only (raw exec fallback removed).
- Raw `codex exec` = BANNED (ADR-69, owner order 2026-07-04). Claude→codex = MCP only (`mcp__codex__codex` / `tools/mir_executor/codex_mcp_client.py`); in-repo code = `mir_executor … --dispatch` (MCP backend); codex→codex = native `multi_agent_v1`. A missing preferred MCP lane is not a task blocker when a safe direct, native, or manual path remains; never use raw exec fallback.
- Obsolete raw-exec guards: timeout/stdin/perl-alarm hang guards for `codex exec` are no longer a live delegation contract under ADR-69. MCP transport owns call timeouts, stall progress, and cancellation through `tools/mir_executor/codex_mcp_client.py`.

## Hook Policy Boundary
- Hard blocks are limited to deterministic destructive operations, credential/privacy boundaries, protected paths or Git operations, real integration conflicts, raw `codex exec`, and explicitly selected failed verification.
- Code-path routing, TDD ledgers, pre-commit verification, review rounds, and session closeout are advisory or operator-selected. Bounded direct edits are valid.
- Core design must not depend on hooks for correctness. Hooks provide narrow safety enforcement and useful guidance, not universal workflow control.

## Runtime Role Policy
- Full contract: §Role Policy (Template Profile) below (generated block — single SoT for parity/delegation/Codex-first defaults).
- Record only material runtime role swaps in `tasks/plan.md` or the active handoff. Choosing bounded direct-main work is not a role swap.

## Language Protocol
- User-facing output: match your team's language convention.
- Internal docs, code, commits, and handoffs: English.
- Keep progress updates short and scannable.

## Surgical Change Rules
- Do not touch code outside the requested scope.
- Do not improve adjacent code or formatting without need.
- Do not refactor working code unless requested.
- Report dead code; do not delete it without instruction.
- No speculative abstractions or impossible-case error handling.

## Principles
- Default is no-action without evidence.
- Simplicity first.
- Fix root causes.
- Explicit prohibitions beat vague guidance.
- No filler.
- Terse by default for routine prose, but never at the cost of safety, exact technical strings, review contracts, user clarity, or directly answering the user.
- If the user asks for explanation or status, provide the minimum explanation or status needed to answer directly. Never answer with silence.

## Central Fleet Management (optional)
- This template can be enrolled in a central managed-fleet workflow, but public clones are standalone unless an operator opts in.
- A fleet manager should inspect the current harness structure before rollout changes, apply the minimum viable harness/agent patch directly, verify the repository, and maintain a rollout report.
- Keep source-of-truth edits in `CLAUDE.md`; do not hand-edit generated `AGENTS.md`.
- A deeper rollout can use `DispatchBrief` plus tiny, normal, and heavy triage. See `docs/harness-engineering/applications/dispatchbrief-defaults-2026-05-28.md`.
- Record rollout state in `tasks/reports/<repo-slug>_harness_rollout_<date>.md`.
- If a repository needs a narrower rollout than the fleet default, document the exception in the rollout report before deviating.

## Role Policy (Template Profile)

<!-- template:profile:role-policy:begin -->
<!-- This block is generated by the profile compiler when you register a family.
     Edit .mir/repo-profile.toml and rerun scripts/generate_codex_derivatives.sh to update. -->

### Template Harness — Role Policy

| Field | Value |
|---|---|
| Repository type | template_transitional |
| Rollout class | bootstrap_only |
| Main role (whichever CLI is opened) | control_plane |
| Delegated execution backend | codex_first |
| Codex backend role | code_tdd_review_plane |
| Codex default enabled | true |
| Delegation required tasks | adopter_wide_template_contract_or_bootstrap_change, release_review |
| Delegation recommended tasks | tools_or_src_implementation, tests, independent_review |
| Main-direct tasks | placeholder_or_profile_check, small_documentation_change, final_publish_judgment |
| Delegable implementation paths | tools/, src/, scripts/ |
| Delegation allowed capabilities | code, review, tdd |
| Delegation blocked capabilities | none |
| Review scope | tools/, tests/ |
| TDD scope | tools/, src/ |
| Main/operator-only runtime boundaries | none |
| Secret paths | .env, .env.* |
| Data sensitivity | low |
| Release window | anytime |
| External service boundaries | none |
| Required operational gates | none |

**Claude main** and **Codex main** share the same default main-agent contract: requirements clarification, architecture, design approval, orchestration, planning, dispatch, exception handling, verification synthesis, and final merge judgment.

**Delegated sub-agents** are the preferred execution option when isolation, parallelism, or restartability materially helps. Bounded direct-main edits are valid when they are the simpler path and retain the same safety and verification boundaries.

**The opened CLI (Claude or Codex) is the control_plane main.** `delegated_execution=codex_first` and `codex_backend_role=code_tdd_review_plane` describe the delegated backend preference, not a mandatory routing gate. The opened main may perform bounded work directly regardless of which CLI launched the session.

The task rows classify work, not agents. A required task must include the relevant delegated implementation, TDD, or independent-review slice; the main still owns scope and final judgment. Recommended tasks use delegation when its benefit exceeds coordination cost. Main-direct tasks should stay local unless a concrete reason justifies delegation.

Path and capability rows bound delegated work. Runtime, secret, data, and external-service rows do not grant delegated mutation authority; required operational gates and operator approval still apply. `protected_paths` retain repository-specific semantics and are not promoted to a universal no-write rule.

A material runtime role swap should be recorded in the active plan or handoff. Choosing a bounded direct-main edit is not a role swap.

### Proportional Main Execution

The control_plane main may read, analyze, design, edit, verify, and communicate directly for bounded work.
Prefer delegation for broad, parallel, isolated, or restartable work when its coordination cost is justified.
Keep destructive operations, credential boundaries, protected Git operations, and delegated plan-cursor ownership as hard safety gates.

<!-- template:profile:role-policy:end -->
