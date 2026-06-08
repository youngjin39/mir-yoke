<!-- GENERATED FILE: edit CLAUDE.md and rerun scripts/generate_codex_derivatives.sh -->

# Codex Project Instructions


## Source Of Truth
- Edit `CLAUDE.md`, `.claude/agents/*`, `.claude/skills/*`.
- Do not hand-edit `AGENTS.md`, `.codex/`, or `.agents/`.

## Startup
- Read the startup context files required by the local Claude workflow before acting.
- Use generated Codex skills first.
- If derived files are stale, regenerate from Claude source.

- Skills: `bluebricks, code-review, commit, design, efficiency, governance, knowledge, automation, testing, ui-design, verify`

# Claude+Codex Harness Template — Opinionated Claude Code Starter

## Required Reads
- `tasks/plan.md`
- `tasks/lessons.md`
- `docs/memory-map.md`
- `docs/decisions/role-policy.md`

## Memory (DB-canonical)
- The canonical long-term memory store is `.mir/memory.db` (SQLite + FTS5 + sqlite-vec). `docs/memory-map.md` and `tasks/lessons.md` are **generated projections** of the DB, not hand-maintained indexes.
- Init / migrate: `uv run mir migrate up` (creates `.mir/memory.db`, applies pending migrations). Run this once after cloning.
- Recall: `uv run mir memory query <keyword>` (FTS5 keyword search).
- Capture a doc: add frontmatter, then `uv run mir memory ingest-md docs/<category>/<topic>.md` (deterministic, no LLM).
- Capture a lesson: `uv run mir memory insert --predicate lesson --subject <slug> --object "<rule>"`.
- Regenerate the md views: `uv run mir memory render --target memory-map --apply --output-path docs/memory-map.md` (and `--target lessons --output-path tasks/lessons.md`). Never hand-edit inside the `mir:generated` markers.

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

## Subagent Resource Management
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
- Main agent parity: Claude main and Codex main share the same defaults for requirements clarification, architecture, design approval, orchestration, planning, dispatch, exception handling, verification synthesis, and final merge judgment.
- Delegated sub-agents are the default execution plane for code writing, code modification, composite TDD execution, deterministic verification, code review, and bounded implementation research.
- Codex-first backend default: use Codex for delegated backend-capable execution work unless an explicit override or capability constraint is recorded.
- Runtime role override is conditional; main-agent parity remains the default contract.
- Record every runtime override in `tasks/plan.md` or the active handoff note.
- Project-level policy revision is a separate path.
- Long-term policy changes must update `docs/decisions/role-policy.md`, this file, and its regressions together.

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
| Claude role | control_plane |
| Codex role | code_tdd_review_plane |
| Codex default enabled | true |
| Codex allowed modes | code, review, tdd |
| Codex blocked modes | none |
| Review scope | tools/, tests/ |
| TDD scope | scripts/** |

**Claude main** and **Codex main** share the same default main-agent contract: requirements clarification, architecture, design approval, orchestration, planning, dispatch, exception handling, verification synthesis, and final merge judgment.

**Delegated sub-agents** are the default execution plane for the repository modes listed under `codex_allowed_modes`. That delegated work may include implementation, code modification, composite TDD execution, deterministic verification, and code review within the profile's review and TDD scope.

**Codex** is the default backend for delegated backend-capable execution work. The repository-level `claude_role=control_plane` / `codex_role=code_tdd_review_plane` fields describe the default backend ownership model, not a different main-agent contract by runtime.

A runtime role swap requires an explicit recorded override in the active plan or handoff note.

<!-- template:profile:role-policy:end -->
