# Changelog

All notable changes to `mir-yoke` will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) from `v0.1.0` onward.

Pre-`v0.1.0` entries (below) used date-format headings (`## 2026.05.x`) and are kept for historical reference. All future entries use the `## [vN.M.X] — YYYY-MM-DD — title` format.

## [0.6.0] — 2026-06-28 — Sub-agent execution policy (force_codex) + delegated-execution gate

Added the `force_codex` sub-agent execution policy to the template:

- `config/sub-agent-policy.json` global switch (`force_codex` / `select` / `per_project` /
  `unrestricted`) with a `MIR_SUB_AGENT_POLICY` home-server overlay, fail-closed to `force_codex`.
- `.claude/hooks/sub-agent-policy-gate.sh` — a slug-free, family-invariant PreToolUse hook that
  hard-blocks Claude `Agent`/`Task` sub-agent spawns under `force_codex` (`exit 2`), with a
  `MIR_R3_FALLBACK=1` escape, wired via a new `^(Agent|Task)$` settings entry.
- README: new "Sub-agent execution policy & delegated execution" section + a "Using the harness —
  the loop" usage guide.

## [0.5.0] — 2026-06-13 — Template completeness release

Closed the template completeness gap: a fresh `git clone` now yields an
immediately applicable harness with the full docs/harness-engineering set,
a post-clone setup checklist, and all missing harness components.

### Added

- `docs/harness-engineering/`: ported 62 files from prompt_DEV 2026-06-11 baseline
  (phases 0–14, applications, appendix, mir-roles, active-agents gap, context-surface
  reduction, phase-N-baseline stubs, sanitize-glossary). Total: 79 tracked files.
- `## Template Purpose` section in `CLAUDE.md` — post-clone instructions and
  component inventory (sanitized from prompt_DEV a052747).
- `setup.sh`: placeholder guard — warns while `slug = "your-harness"` or
  `display_name = "Your Harness"` remain in `.mir/repo-profile.toml`, or while
  `family= "your-harness"` remains in `session-start.sh`. Post-clone checklist
  banner (8-step path to working harness).
- `.mir/repo-profile.toml`: auto-created by setup.sh on first run (placeholder values).
- `.mir-preserve.toml`: lists preserved dirs/sections so fleet rollout skips template
  harness-engineering + decision docs.
- `.mir/boundary.md`: generic allowed/blocked policy for this template.
- `.claude/skills/memory-gc/SKILL.md`: GC scan skill (user-triggered only).
- `.claude/hooks/_lib/invocation_log.sh`: phase-6 usage telemetry helper.
- `.claude/hooks/_lib/tier_dispatch.sh`: tier-routing helper (block/suggest/warn).

### Changed

- `CHANGELOG.md` and `VERSION`: bumped to 0.5.0 per ADR-40 release procedure.
- Phase docs (phase-0 through phase-12 + README): editorial English wording rewrites
  (no structural changes).

### Sanitize gate

All content under `docs/harness-engineering/` passes the sanitize gate (0 sensitive
hits), including `applications/template-repo/sanitize-glossary.md`, whose mapping
table uses placeholder forms (e.g. `/Users/<real-username>/`) on both sides.

## [0.4.0] — 2026-05-25 — Applied-state baseline completion

Raised the public template working tree to an applied-state baseline that
satisfies the template verifier.

### Added

- `docs/harness-engineering/phase-0-baseline.md` through
  `phase-12-baseline.md`
- `docs/templates/_schema/design_doc.schema.json`
- `docs/templates/_schema/fleet_harness_state.schema.json`
- `docs/templates/_schema/family_config.schema.json`
- `docs/templates/_schema/report_contract.schema.json`
- `docs/templates/_schema/tdd.schema.json`
- `docs/templates/_schema/mir_agent_self_health.schema.json`
- concise ADR parity stubs for missing baseline decision numbers required by
  the applied-state verifier

### Changed

- Sanitized schema descriptions to keep the public template English-only.
- `verify_template_applied_state.py` now passes against the working tree.

### Notes

- This release is recorded in the workspace before a follow-up commit/tag.

## [0.3.0] — 2026-05-24 — Phase-4 state machine modules

Synced the phase-4 state machine implementation.

### Added

- `tools/run_orchestrator/state_machine.py` — 13-state SM (`RunState`
  StrEnum: IDLE/DISCOVER/PLAN/NEED_APPROVAL/ACT/VERIFY/REPORT/DONE/REPLAN/
  BLOCKED/CANCELLING/ROLLBACK/INTERRUPTED) + `RUN_TRANSITIONS` table.
- `tools/run_orchestrator/run_orchestrator.py` — `run_state.json` driver
  (init_run + transition + get_current_state + record_tool_event) with
  ULID generation + atomic write + jsonschema validation.
- `tools/run_orchestrator/approval_gate.py` — Discord-delegated approval
  (request_approval + parse_reply + apply_decision). Zero network calls.
- `tools/hooks/validate_tool_contract.py` — pre-tool-use hook validator
  (env-gated by `MIR_TOOL_CONTRACT_REQUIRED` or `MIR_TOOL_CONTRACT_LOG`).
- `src/mir/core/engine/structured_error.py` — `StructuredError` frozen
  dataclass + `ErrorType` StrEnum (7 members) for unified error format.
- `src/mir/core/engine/tool_contract.py` — `ToolContract` 4-field obligatory
  metadata (idempotency_key, precondition, dry_run, side_effect_summary).
- `src/mir/core/engine/interrupt_handler.py` — git stash-based atomic
  rollback for ACT→CANCELLING→ROLLBACK→INTERRUPTED transitions.

### Changed

- `docs/templates/_schema/run_state.schema.json` — added `session_id` +
  `current_step_id` (optional ULID per phase-4 5-tier execution unit spec).
- `docs/templates/_schema/tool_event.schema.json` — added `turn_id`
  (REQUIRED ULID) + `step_id` (optional).
- `docs/templates/_schema/task_state.schema.json` — added
  `origin_session_id` (optional ULID).
- `docs/templates/_schema/approval.schema.json` — added DENIED/DELAYED to
  status enum + auto_policy oneOf + discord_chat_id / denial_reason /
  delay_reason fields.

### Notes

- Phase-4 state machine is opt-in via `python -m tools.run_orchestrator --use-13-state`.
- Default `cli.py` behavior remains 7-state (backward compat per ADR-44).
- Tool contract validation is OFF by default; activate via
  `.claude/settings.json` env `MIR_TOOL_CONTRACT_REQUIRED=1` (enforce) or
  `MIR_TOOL_CONTRACT_LOG=1` (advisory only).
- This release consolidates the phase-4 state-machine work.
- 0 Korean leakage across all synced surfaces.

## [0.2.0] — 2026-05-24 — R17 fleet rollout hook sync

Synced upstream the source harness repo hook updates from the R17 fleet phase rollout.

### Changed

- `.claude/hooks/mir-stop.sh` — updated to match upstream R17 baseline.
- `.claude/hooks/pre-commit-verification.sh` — updated to match upstream R17 baseline.
- `.claude/hooks/pre-tool-use.sh` — updated to match upstream R17 baseline (includes phase-2 enforcement domain pinning + code-path config helper).
- `.claude/hooks/session-start.sh` — updated to match upstream R17 baseline.
- `.claude/hooks/stop-failure-audit.sh` — updated to match upstream R17 baseline.
- `.claude/hooks/tdd-task-created.sh` / `tdd-task-completed.sh` — updated to match upstream R17 baseline.

### Added

- `.claude/hooks/lib/code-path-config.py` — helper for per-family enforced code-path resolution + ADR-23 dogfooding exemption check.

### Notes

- 0 Korean leakage verified across all synced hook surfaces.
- Synced hooks are versioned in the source repo; backups are not included in the template.
- This release consolidates the R17 hook sync.

## [0.1.0] — 2026-05-23 — PROMOTE-R5a (schemas + light ADR)

Initial semver release. First sanitized promotion of upstream harness-engineering work to the public template.

### Added

- `VERSION` (`0.1.0`) — initial semver version artifact (per ADR-40 §Versioning Policy).
- `MIGRATION.md` skeleton — empty migration log, ready for first MAJOR bump.
- `docs/templates/_schema/` — 13 R5-era schemas (all 0-Korean, English-clean):
  - `adr.schema.json`
  - `agent_frontmatter.schema.json` (re-promote — previously already present)
  - `approval.schema.json`
  - `arch.schema.json`
  - `memory_entry.schema.json`
  - `phase.schema.json`
  - `prd.schema.json`
  - `review-rounds.schema.json`
  - `run_state.schema.json`
  - `s4_input.schema.json`
  - `skill.schema.json`
  - `task_state.schema.json`
  - `tool_event.schema.json`
- `docs/decisions/adr-18-orchestrator-runtime-guard.md` — sanitized v4 (R3/R4 audit absorbed). Korean memory quotation (4 lines) translated to English. Naming convention aligned with template (no date suffix).

### Changed

- `CHANGELOG.md` format migrated to [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) (`## [vN.M.X] — YYYY-MM-DD — title`). Pre-`0.1.0` entries below preserved verbatim.

### Deprecated

- (none)

### Removed

- (none)

### Fixed

- (none)

### Security

- (none)

### Notes for adopters

- PROMOTE-R5a deliberately ships **schemas + 1 light ADR + versioning artifacts only**. The Korean-heavy `docs/harness-engineering/` directory (24 docs × 70-180 Korean lines each) is deferred to a follow-up round once an LLM-assisted sanitize pipeline (`scripts/sanitize_for_template.py`, upstream R11) is available. Hand-translating 24 docs accurately exceeds a single-round budget.
- See upstream [`docs/harness-engineering/applications/template-repo/current-state.md`](https://github.com/youngjin39/mir-yoke/blob/main/) (placeholder link; doc lives upstream until R11 promote) for the full physical-vs-design gap snapshot.
- New JSON Schemas are all `additionalProperties: false` (Draft 2020-12). Validate your family configs with `python -m jsonschema -i config/repos/<name>.json docs/templates/_schema/<schema>.json`.

---

## Pre-0.1.0 (date-format entries, historical reference)

## 2026.05.2 — fleet governance + sub-agent definitions + pattern catalogue

- Added `docs/governance/principles.md` — six fleet-governance principles
  (autonomy / direct-management / skills+tools / per-repo recording /
  catalogue cross-pollination / unused-component archive).
- Added `docs/governance/fleet-observation.md` — public design summary
  of the Facts/Checks/Scorecards 3-layer inspection pipeline, bucket
  decision matrix, S2 autonomous-fix safety net, S3 advisory handoff,
  and S4 import wave rollout (canary → wave 1 → rollback).
- Added four reference sub-agent definitions under `.claude/agents/`:
  `executor-agent` (Codex execution lane), `quality-agent` (Claude
  fallback review), `codex-final-reviewer` (Codex primary review),
  `fleet-doc-steward` (CLAUDE.md / AGENTS.md drift governance).
- Seeded `docs/patterns/` catalogue with three transplant-ready
  reference patterns + auto-generated `INDEX.md`:
  `bounded-review-plane.md` (curriculum / docs workspaces),
  `app-product-flutter.md` (Flutter app product),
  `content-workspace.md` (narrative / score authoring).

## 2026.05.1 — content expansion

- Expanded README comparison section into a 7-row matrix (vs Claude Code default, Codex CLI default, superpowers, Archon, OpenHarness, claude-code-skills, hand-rolled CLAUDE.md). Names the unique slice this template fills.
- Added 3 examples: `examples/fix-bug/`, `examples/refactor/`, `examples/multi-round-review/` — the last is an anonymized walkthrough of a real multi-round adversarial review that landed a 500-LOC change in 3 rounds.
- Added 3 skills: `deep-interview` (ambiguity gate), `git-commit` (commit hygiene + safety rules), `project-doctor` (health check / drift report).

## 2026.05 — initial public release

- Dual-CLI harness: Claude Code + Codex CLI, identical hook scripts on the 8 shared events.
- 5 hook scripts: `pre-tool-use`, `post-edit-check`, `session-start`, `session-end`, `pre-compact`, plus the `tdd-guard` helper.
- 5 built-in skills: `design`, `writing-plans`, `testing`, `code-review`, `verification`.
- `.ai-harness/` rule set: common rules, development rules, deny-list, TDD matrix, session closeout, failure patterns.
- `tasks/` + `docs/` working ledger.
- Worked example: `examples/add-feature/`.
