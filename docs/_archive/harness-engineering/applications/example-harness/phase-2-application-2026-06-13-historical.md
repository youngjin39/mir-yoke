---
phase: 2
title: Enforcement Application
status: done
family: your-harness (SE-meta)
blueprint: ../../phase-2-enforcement.md
---

# Phase 2 — Enforcement Application (example-harness)

## 1. Blueprint Reference

[`../../phase-2-enforcement.md`](../../phase-2-enforcement.md) in full. In particular §3 four enforcement bindings, §4 three intensity levels, §5 Circuit Breaker.

**Related reinforcement docs**: When writing ADR-22 (retry_budget) for this phase, apply the 5-step + iteration requirement from [`../design-process.md`](../design-process.md). The retry_budget quantitative value is directly related to the termination condition of the autonomous response loop in [`../autonomous-execution.md`](../autonomous-execution.md) §4.

## 2. Current State (Pre-measurement)

| Item | Blueprint location | your-harness state |
|---|---|---|
| pre-edit hook | §3-1 | landed — `.claude/hooks/pre-tool-use.sh` (your-harness BLOCK) |
| post-edit verify hook | §3-2 | landed — `pre-commit-verification.sh` |
| TDD ledger | §3-2 | landed — `tdd-guard.sh + tdd-matrix-guard.py` |
| Validator script | §3-3 | landed — `scripts/verify_*` |
| Prompt injection defense | §3-4 (R5 update) | landed — `prompt_injection_advisory.py` + `artifact_sanitizer.py` + `intent_verification.py` path for advisory/verification path operation |
| Deny-list | §3-5 (R5 update) | landed — `.ai-harness/deny-list.yaml` expanded high-risk patterns + hook enforcement |
| Three intensity levels | §4 | landed — warn / suggest / block all implemented as hook tiers |
| Circuit Breaker | §5 | landed — `src/your-harness/core/engine/circuit_breaker.py` + gateway wiring + regression tests |
| 7-layer Safety Layer | §7 | partially landed — only points 3 and 5 |
| Enforcement vs. Advisory separation | §8 | landed — Hook Policy Boundary |

**Gap assessment**: No implementation gaps against the phase closeout criteria. Prompt injection maintains an advisory-first operational policy, but the phase-2 exit criterion and the current blueprint's enforcement binding requirements are satisfied.

## 3. Application Work Steps

| Step | Work | Dependency | Estimate |
|---|---|---|---|
| 2-1 | Define `retry_budget` quantitatively + ADR (`adr-22-retry-budget-2026-MM-DD.md`) | – | 2h |
| 2-2 | Circuit Breaker implementation — counter + threshold-exceeded → BLOCKED in the main-orchestrator ACT → VERIFY loop | 2-1 | 4h |
| 2-3 | Add suggest intensity — add user confirm prompt branch to `.claude/hooks/pre-tool-use.sh` | – | 3h |
| 2-4 | Reinforce deny-list — add production DB / eval / exec / system shell / curl-to-bash patterns | – | 2h |
| 2-5 | Review 4 missing points (1·2·4·6) in 7-Layer Safety — introduce new hook where absent or make intentional shelved decision | – | 4h |

## 4. Files to Change

| Path | Type |
|---|---|
| `docs/decisions/adr-22-retry-budget-2026-MM-DD.md` | create |
| `src/your-harness/core/conductor/meta_mode.py` or main-orchestrator | edit (Circuit Breaker logic) |
| `tasks/phase.json` schema | edit (add `retry_count` field) |
| `.claude/hooks/pre-tool-use.sh` | edit (suggest intensity branch) |
| `.ai-harness/deny-list.yaml` | edit (5 → 12 patterns) |
| `.claude/hooks/pre-edit-confirm.sh` | create (for suggest intensity) |

## 5. Verification Procedure

Blueprint §11 Exit Criterion: "pre-edit hook blocks at least one attempted modification of a prohibited path, post-edit verify fires at least one failure report on intentional lint/test failure, deny-list blocks at least one dangerous command."

Verification method:
1. Intentionally attempt direct Edit of a prohibited path (`src/your-harness/core/`) → confirm BLOCK
2. Intentionally attempt to commit lint/test-failing code → confirm pre-commit-verification blocks
3. Intentionally attempt `git push --force` → confirm deny-list blocks
4. Intentionally exceed retry_budget (3 times same verify failure) → confirm BLOCKED entry

## 6. Cross-Repo Propagation Exceptions

| Case | Rule |
|---|---|
| code_app / SE-product code path | enforced — same application of your-harness's pre-edit hook + retry_budget |
| hybrid_pipeline code path | warn — hook fires only, no block (protects style workflow) |
| SE-product personal code path | off — `personal-context/` directory permanently exempt (exceptions §7) |
| External family uses its own pre-commit framework | your-harness hook deactivated + advisory log only |
| External family has different deny-list from your-harness | Family's deny-list takes precedence (user responsibility); your-harness deny-list serves as default |

**Specific exceptions**:
- `example-infra` (code_app) → same enforced as your-harness
- `example-notes` (SE-product) → same enforced as your-harness, but production DB pattern in deny-list reviewed against example-notes dev DB possibility and handled as option
- `example-content` (hybrid_pipeline) → warn on code path, enforced on memory path (dual strictness differential, exceptions §3 matrix)
- `example-personal` (SE-product personal) → entirely off, protects user personal context area

## 7. SE-meta Self-Stop Check

Can your-harness apply retry_budget to itself? → After work ✓ possible.
If your-harness's Circuit Breaker blocks its own work, that is a self-stop. Therefore the ADR in §3-1 must decide retry_budget conservatively (total 3 times, verify 2 times, patch conflict 1 time).

**Potential violation risks**:
- If the suggest intensity hook requests user confirm too frequently, it blocks the work flow → monitor firing frequency for 1 week then adjust
- If deny-list reinforcement causes false positives that block your-harness's own work, revert immediately

## 8. Work Status

- **Status**: done
- **Completion date**: 2026-05-25
- **Verification evidence**: `.venv/bin/python -m pytest tests/test_hook_scripts.py tests/test_circuit_breaker.py -q` → `32 passed`; `.venv/bin/python -m pytest tests/test_mcp_gateway.py tests/test_hook_tier_application.py -q` → `22 passed`
- **Revert reason**: –

## 9. Next Steps

Parallel-eligible: [Phase 3 Memory & Context](phase-3-application.md) or [Phase 4 State Machine](phase-4-application.md).
