# Changelog

All notable changes to `claude-codex-harness` will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) from `v0.1.0` onward.

Pre-`v0.1.0` entries (below) used date-format headings (`## 2026.05.x`) and are kept for historical reference. All future entries use the `## [vN.M.X] — YYYY-MM-DD — title` format.

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

Synced upstream Mir R18+R20+R21 phase-4 state machine implementation.

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
- This release tracks upstream Mir R18 (`393ce52`) + R20 (`be8873f`) + R21 (`c4b8388`).
- 0 Korean leakage across all synced surfaces.

## [0.2.0] — 2026-05-24 — R17 fleet rollout hook sync

Synced upstream Mir-self hook updates from the R17 fleet phase rollout.

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
- All synced hooks have backup files in upstream Mir under `<hook>.r17-backup-2026-05-24` (not included in template).
- This release tracks upstream Mir R17 (commits `be420d0`~`76b9d57`).

## [0.1.0] — 2026-05-23 — PROMOTE-R5a (schemas + light ADR)

Initial semver release. First sanitized promote of upstream Mir-self harness-engineering work to the public template (rounds R5 through R10-R3 backlog is tracked at [`tasks/role_b_backlog.md`](https://github.com/youngjin39/claude-codex-harness/blob/main/tasks/role_b_backlog.md) in the upstream repo).

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
- See upstream [`docs/harness-engineering/applications/template-repo/current-state.md`](https://github.com/youngjin39/claude-codex-harness/blob/main/) (placeholder link; doc lives upstream until R11 promote) for the full physical-vs-design gap snapshot.
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
