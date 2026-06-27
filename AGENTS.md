<!-- GENERATED FILE: edit CLAUDE.md and rerun scripts/generate_codex_derivatives.sh -->

# Codex Project Instructions


## Source Of Truth
- Edit `CLAUDE.md`, `.claude/agents/*`, `.claude/skills/*`.
- Do not hand-edit `AGENTS.md`, `.codex/`, or `.agents/`.

## Startup
- Read the startup context files required by the local Claude workflow before acting.
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
  - Simple non-code (1-2 steps) -> execute directly -> self-check -> done.
  - Development-changing request -> design first.
  - Simple or bounded development -> short harness-structured design -> executor-agent -> codex-final-reviewer -> verify.
  - Complex, repo-wide, or ambiguous development -> full design-process pipeline.
  - Complex (3+ steps) -> design -> executor-agent -> codex-final-reviewer -> verify.
- Treat code, tests, repository structure, phases, ADRs, skills, agents, template sync, fleet rollout/share, policy docs, and generated surfaces as development-changing.
- When ambiguous, classify upward and keep the refined execution brief in `tasks/plan.md` or a `DispatchBrief`.

## Codex Hook-Mirror Obligations
- [Codex] `SessionStart`: read startup context manually before acting (`tasks/plan.md`, `tasks/lessons.md`, `docs/memory-map.md`, and required local workflow docs).
- [Codex] `PreCompact`: before compaction, manually create a handoff document in `tasks/handoffs/` mirroring the PreCompact contract.
- [Codex] `PostToolUse`: after edits, manually review for debug leftovers and credential leaks.
- [Codex] `SessionEnd`: at session end, manually create a session snapshot in `tasks/sessions/` mirroring the SessionEnd contract.
- [Codex] `UserPromptSubmit`: for substantial prompts, run `uv run mir context pull "<query>"` for memory retrieval.
- [Codex] `TaskCreated` / `TaskCompleted`: keep `tasks/tdd.json` current; TDD ledger closure is enforced at pre-merge by `.claude/hooks/pre-merge-gate.sh`.

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
- Code-writing, debugging, refactoring, architecture review, repository exploration, and test generation must load `bluebricks` first.
- Code-development safeguards live in `.ai-harness/development-ai-rules.md`, `.ai-harness/bluebricks.md`, `.ai-harness/tdd-matrix.md`, `.ai-harness/deny-list.yaml`, and `.ai-harness/failure-patterns.md`.
- Code-development proof rule: design first, then maintain `tasks/tdd.json`, then implementation, then executed TDD evidence as the primary proof of correctness.

## Project Structure
- Root control files: `CLAUDE.md`, `AGENTS.md`, `.mcp.json` (optional — add if your project uses MCP servers), `setup.sh`, `README.md`
- Harness rules: `.ai-harness/`
- Runtime source: `.claude/`
- Working state: `tasks/`
- Long-term memory: `.mir/memory.db` (canonical DB); `docs/` holds prose + generated md projections

## Workflow
- 0 specificity signals: load `design` skill (interview subtype).
- Simple non-code work: execute directly + self-check.
- Before development-changing execution, classify the task as `tiny`, `normal`, or `heavy`.
- Development-changing work defaults to a harness-structured design pass first, even when the request is specific.
- `tiny` tasks may execute without a formal phase or slice when the overhead would outweigh the value, but they still need a clear verification step.
- `normal` and `heavy` tasks should prefer explicit phases or bounded slices before execution.
- Simple code task: short `design` pass → Codex execution + TDD + review.
- Complex 3+ step work: `design` → Codex execution lane → Codex review lane → `verify`.
- Harness docs, phases, ADRs, skills, agents, template sync, fleet rollout/share, repo-wide policy, and generated-surface changes must route through `design` before execution.
- Use `ui-design` before any real UI work.
- `automation` is the default for long-running or restartable work.
- Delegated, restartable, or 3+ step work should emit a persisted `DispatchBrief` or equivalent handoff artifact before the execution lane starts.
- Sub-agent contracts must stay pinned by regression tests.

## Continuation Loop Protocol
- Applies to BOTH mains: whichever CLI is opened, Claude or Codex, follows the same file-backed continuation loop.
- Cursor of record: `tasks/plan.md` formal `Step N:` lines; do not create a second cursor in `run_state.json`.
- Each runnable step carries bounded machine refs: `brief=<path>` and `tdd=<change_id>#<category>`.
- Move 1: read the cursor with `uv run mir loop next --json`.
- Move 2: select exactly one non-DONE/non-CLOSED step from the first active task section.
- Move 3: execute ONE bounded step through the delegated Codex lane or `scripts/loop_driver.sh`.
- Move 4: update `tasks/tdd.json` evidence for that step's declared category.
- Move 5: rewrite only that cursor line to `DONE`, `FAILED | attempts=K`, or `BLOCKED | reason=...`.
- Move 6: stop after the one bounded step; the next pass must re-read the file cursor.
- `FAILED` retries are finite; after the configured attempt cap, mark `BLOCKED` and return control.
- `BLOCKED` means no fabricated continuation: a main agent or user must revise the plan or brief.
- `COMPLETE` means all machine steps in the active section are `DONE` or `CLOSED`.
- Non-LLM automation may drive the loop, but it must not bypass hooks, TDD gates, or verification.
- `tools/run_orchestrator` remains observer-only; it is not the continuation executor.


## Subagent Resource Management
- **Subagent-first**: investigation / extraction / verification / multi-file work → delegate to sub-agents and orchestrate (no broad inline read / extract / audit / survey). The main agent fans out and synthesizes; it does not read everything itself. Detail in `main-orchestrator`.
- Default live subagent cap = 4. Raise it only when Claude/Codex lanes are clearly independent and the current lane is healthy.
- Design-process work may raise the live cap to 4 without separate user approval when Step 2 parallel analysis and Step 4 independent verification both need coverage; record the temporary cap in `tasks/plan.md` or the active handoff note.
- Prefer `fork_context: false` for bounded harness docs, config, or verifier work. Use `fork_context: true` only for broad role-policy review, runtime-contract review, or independent final verification.
- Close completed, timed-out, or errored subagents before the next wave so experiments do not leave stale lanes open.
- If `spawn_agent` returns capacity or thread-limit errors, stop parallel expansion, reduce ownership to one harness surface per subagent, retry one subagent at a time, and record degraded mode in the active plan or handoff.

## Hook Policy Boundary
- **Enforcement domain** — Hook-strict:
  - `tools/`, `src/`, `lib/` code paths: Claude direct Edit/Write is blocked by `.claude/hooks/pre-tool-use.sh`. Changes must go through the Codex execution lane.
  - Pre-commit lint / typecheck / test (`pre-commit-verification.sh`): auto-enforced on code changes.
  - TDD ledger (`tdd-guard.sh`): implementation-before-test pattern is blocked.
- **Advisory domain** — Hook-loose / non-enforced:
  - `.claude/agents/`, `.claude/skills/`, `config/repo-agent-management.json`, `docs/`, `tasks/`: direct edits allowed. Verifier (`scripts/verify_repo_agent_management.py`) emits advisory WARN/INFO only.
  - Monthly catalog review cadence: no cron, no auto-fire. fleet-doc-steward surfaces reminders to `tasks/checklist.md`.
- **Principle**: Core design (catalog / skill / agent / orchestration) must not depend on hooks for correctness. Hooks add (a) TDD enforcement on code surfaces, (b) Codex execution lane routing, and (c) verification automation. Hook enforcement must not leak into core design execution.

## Runtime Role Policy
- Full contract: §Role Policy (Template Profile) below (generated block — single SoT for parity/delegation/Codex-first defaults).
- Record every runtime override in `tasks/plan.md` or the active handoff note. Long-term policy changes must update `docs/decisions/role-policy.md`, this file, and its regressions together.

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
| Codex allowed modes | code, review, tdd |
| Codex blocked modes | none |
| Review scope | tools/, tests/ |
| TDD scope | scripts/** |

**Claude main** and **Codex main** share the same default main-agent contract: requirements clarification, architecture, design approval, orchestration, planning, dispatch, exception handling, verification synthesis, and final merge judgment.

**Delegated sub-agents** are the default execution plane for the repository modes listed under `codex_allowed_modes`. That delegated work may include implementation, code modification, composite TDD execution, deterministic verification, and code review within the profile's review and TDD scope.

**Codex** is the default backend for delegated backend-capable execution work. The repository-level `main_role=control_plane` / `delegated_execution=codex_first` / `codex_backend_role=code_tdd_review_plane` fields describe the default backend ownership model, not a different main-agent contract by runtime.

A runtime role swap requires an explicit recorded override in the active plan or handoff note.

### Orchestration-Only Main (ADR-63, 2026-06-28)

The control_plane main (whichever CLI is opened) does ORCHESTRATION ONLY: read, analyze, design/decide, dispatch, plan.md cursor rewrites (ADR-60 R5 Move 5), verification synthesis, and user communication.
ALL editing, authoring, code changes, config, and cross-repo writes route to the Codex delegated lane — regardless of domain (advisory or code-path). This extends codex_first beyond the tools/src/scripts hard gate to the full advisory domain.
Enforcement: policy/discipline (advisory tier, per ADR-51/52) — no new runtime hook.
Exception: the plan.md Step N cursor line and the active handoff note may be written by the main (orchestration-state bookkeeping it must own).

<!-- template:profile:role-policy:end -->
