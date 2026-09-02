---
phase: 1
title: Start Harness Application
status: done
family: your-harness (SE-meta)
blueprint: ../../phase-1-start-harness.md
---

# Phase 1 — Start Harness Application (example-harness)

## 1. Blueprint Reference

[`../../phase-1-start-harness.md`](../../phase-1-start-harness.md) in full. In particular §3 five-element declaration, §4 classification decision rules, §7 routing failure conditions.

**Related reinforcement docs**: When writing ADR-21 (risk-level taxonomy) for this phase, apply the 5-step + 2~3 iteration requirement from [`../design-process.md`](../design-process.md).

## 2. Current State (Pre-measurement)

| Item | Blueprint location | your-harness state |
|---|---|---|
| Four task classifications | §4 | landed (`CLAUDE.md` §Orchestration Presets) |
| Five-element declaration | §3 | landed — `task_state.schema.json` 5-element fields + `start-harness-verifier.sh` block hook (ARCHIVED 2026-06-04, commit 02dff45 — ADR-44 R21 fallout; see ADR-51) |
| Routing failure detection | §7 | landed — `scripts/verify_routing.py` |
| Executor / review lane separation | §8 | landed (Codex execution lane + codex-final-reviewer, ADR-09) |
| Start-harness single entry point | §1 | landed (main-orchestrator) |

**Gap assessment**: Mechanical verification gaps resolved as of R29-T06. `risk-level-classifier.sh`, `start-harness-verifier.sh` (both ARCHIVED 2026-06-04, commit 02dff45 — ADR-44 R21 fallout; see ADR-51), `verify_routing.py`, `tests/test_phase1_hooks.py` all landed.

## 3. Application Work Steps

| Step | Work | Dependency | Estimate |
|---|---|---|---|
| 1-1 | Define `risk_level` — specify judgment criteria for low / medium / high (`docs/decisions/` new ADR) | – | 2h |
| 1-2 | Make five-element declaration mandatory at main-orchestrator start (output 5-element yaml block after Korean response) | 1-1 | 1h |
| 1-3 | Five-element omission detection hook — `.claude/hooks/post-tool-use.sh` or new `session-start-validator.sh` | 1-2 | 2h |
| 1-4 | Progressive enforcement — 3 intensity levels from Phase 2 §4 (warn → suggest → block) | 1-3 | 1 week (observation) |

## 4. Files to Change

| Path | Type |
|---|---|
| `docs/decisions/adr-21-risk-level-taxonomy-2026-MM-DD.md` | create (ADR) |
| `.claude/agents/main-orchestrator.toml` | edit (five-element declaration required) |
| `.codex/agents/main-orchestrator.toml` | edit (codex mirror) |
| `.claude/hooks/session-start-validator.sh` | create (five-element omission detection) |
| `CLAUDE.md` §Orchestration Presets | edit (add five-element declaration requirement) |
| `tasks/checklist.md` | edit (add cadence reminder) |

## 5. Verification Procedure

Blueprint §11 Exit Criterion: "For 3 sample requests (code / research / review), verify five-element declaration is output without omission, and routing to the correct flow for each classification is confirmed."

Verification method:
1. Intentional five-element omission → hook blocks (in warn → suggest → block intensity order)
2. Run samples for 3 task types → verify routing consistency
3. Measure five-element appearance frequency with `tools/fleet_observe/measure/agent.py`

## 6. Cross-Repo Propagation Exceptions

| Case | Rule |
|---|---|
| code_app family (example-infra etc.) | enforced — five-element declaration required |
| SE-product family (example-notes etc.) | enforced — five-element declaration required |
| hybrid_pipeline family (example-content etc.) | warn — only `risk_level` required, rest advisory |
| SE-product personal family (example-personal etc.) | off — start-harness itself not applied (personal context, automation not appropriate) |

Consistent with [`../exceptions.md`](../exceptions.md) §3 Phase 1 row.

**Specific exceptions**:
- Family A's main-orchestrator already has its own five-element variant (e.g., uses `category` instead of `task_type`) → your-harness's five-element names are not forced. Only your-harness catalog mapping is required.
- Family B uses direct execution flow without a start-harness single entry point → opt-out allowed. Must be specified in `enabled_phases`.

## 7. SE-meta Self-Stop Check

Can your-harness apply the five-element declaration requirement hook to itself? → After work ✓ possible.
Does your-harness's circuit breaker block itself when its own hook's failure case (intentional omission) occurs? → After work ✓ intended.

**Potential violation risk**: If the five-element hook is too strict and blocks your-harness's own day-to-day work, that is a self-stop. Therefore §3-4's three-intensity progressive enforcement is mandatory (warn 1 week → suggest 1 week → block).

## 8. Work Status

- **Status**: done
- **Completion date**: 2026-05-25
- **Verification evidence**: `.venv/bin/python -m pytest tests/test_phase1_hooks.py -q` → `13 passed` (updated 2026-06-04: now 5 passed — two hook test classes removed in commit 02dff45); `.claude/hooks/risk-level-classifier.sh` (ARCHIVED 2026-06-04); `.claude/hooks/start-harness-verifier.sh` (ARCHIVED 2026-06-04); `scripts/verify_routing.py`
- **Revert reason**: –

## 9. Next Steps

Proceed to [Phase 2 Application](phase-2-application.md).
