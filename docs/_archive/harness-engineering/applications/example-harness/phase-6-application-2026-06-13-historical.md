---
phase: 6
title: Observability Application
status: done
family: your-harness (SE-meta)
blueprint: ../../phase-6-observability.md
---

# Phase 6 — Observability Application (example-harness)

## 1. Blueprint Reference

[`../../phase-6-observability.md`](../../phase-6-observability.md) full. Key sections: §2 12 metrics, §3 measure→fix→automate cadence, §9 report_contract.

**Related Supplementary Documents**: [`../autonomous-execution.md`](../autonomous-execution.md) — the autonomous reply loop uses measurement results from this phase as input. The retry_budget quantification + report_contract standardization in this phase is required for autonomous operation termination condition verification.

## 2. Current State (pre-measurement)

| Item | Blueprint Location | your-harness State |
|---|---|---|
| 12 metric measurements | §2 | land for your-harness exit criterion — `fleet_observe` axis + usage telemetry pattern facts (`tool_call`, `repeat_read`, `giant_output`, `retry_pattern`) landed and live invocation-log producer coverage is now observable |
| Measure→fix→automate cadence | §3 | land — ADR-10 fleet-governance-advisory |
| Autonomous reply loop | §4 | partial land — `run_state.retry_count` based retry_budget detection + VERIFY→BLOCKED seam landed |
| 5 cost waste pattern diagnosis | §5 | partial land — `measure/usage.py` measures repeated read / giant output / retry pattern facts |
| Langfuse | §6 | discontinued — self-built approach adopted |
| Meta-feedback | §8 | land — failure-patterns + ADR cycle |
| `report_contract` | §9 | partial land — `active_task.report_contract` + CLI declaration + `post-task-validator` suggest-tier hook landed (post-task-validator ARCHIVED 2026-06-04, commit 02dff45 — never wired to TaskCompleted; see ADR-51) |

**Follow-up items**: cache-hit/resource metric expansion, broader report closeout wire-up hardening, OTel/evaluation harness formalization.

## 3. Application Work Steps

| Step | Work | Dependency | Estimate |
|---|---|---|---|
| 6-1 | `report_contract` standard definition — `concise_report_v1` / `audit_report_v1` / `research_report_v1` (`docs/templates/_schema/report.schema.json`) | – | 3h |
| 6-2 | report_contract verification closeout lane — contract verification in `run_orchestrator report --payload` path | 6-1 | 2h |
| 6-3 | Cache hit measurement — add `cache_hit.py` to `tools/fleet_observe/measure/` | – | 3h |
| 6-4 | 5 cost waste pattern automatic detection — threshold + advisory for each pattern | – | 4h |
| 6-5 | Autonomous reply loop quantification — integrate with Phase 2 retry_budget | 2-1 (Phase 2) | (handled in Phase 2) |

## 4. Files to Modify

| Path | Type |
|---|---|
| `docs/templates/_schema/run_state.schema.json` | edit (`report_contract`, `retry_count`) — (updated 2026-06-04: report_contract ported to run_state in ADR-44 R21; active_task.schema.json reference is stale) |
| `tools/run_orchestrator/cli.py` | edit (`--report-contract` start declaration) |
| `tools/run_orchestrator/orchestrator.py` | edit (run_state-backed retry_budget handling) |
| `.claude/hooks/post-task-validator.sh` | landed (suggest-tier report_contract verification) (ARCHIVED 2026-06-04, commit 02dff45 — never wired to TaskCompleted; see ADR-51) |
| `.claude/hooks/post-task-validator.py` | landed (ARCHIVED 2026-06-04, commit 02dff45 — never wired to TaskCompleted; see ADR-51) |
| `tools/fleet_observe/measure/usage.py` | edit (pattern facts) |

## 5. Verification Procedure

Blueprint §12 Exit Criterion: "Minimum 5 of 12 metrics automatically measured + 1 advisory report generated. Autonomous reply loop reaches retry_budget limit then enters BLOCKED on intentional verification failure case."

Verification methods:
1. Run fleet_observe runner once → confirm 5+ of 12 metrics measured
2. Attempt report_contract violation output → confirm `run_orchestrator report --payload` or post-task-validator suggest-tier blocks (historical — post-task-validator ARCHIVED 2026-06-04, commit 02dff45; this verification step is now unexecutable)
3. Intentional verification failure 3 times (retry_budget total_attempts) → confirm BLOCKED entry from VERIFY
4. Confirm repeated read / giant output / retry pattern fact measurements in usage telemetry

## 6. Cross-repo Propagation Exceptions

| Case | Rule |
|---|---|
| All families | enforced — observability is identical for all 6 types |
| Family refuses measurement (privacy) | personal context area only off, public area enforced |
| report_contract conflicts with family default reporting format | family contract can be additionally registered (`docs/templates/_schema/report.<family>.schema.json`) |
| Family LLM calls go through external SaaS (Langfuse etc.) | parallel with your-harness measurement allowed, but SoT is your-harness measurement |

[`../exceptions.md`](../exceptions.md) §3 Phase 6 row: all types enforced.

**Specific Exceptions**:
- All families → same enforced as your-harness
- `example-personal` (SE-product personal) → privacy-sensitive areas can be excluded from measurement, advisory log anonymize only

## 7. SE-meta self-stop Check

Can your-harness measure its own operations? → Already measuring itself via fleet_observe.
If report_contract blocks your-harness normal output, self-stop. Therefore §3-2 hook uses warn → suggest → block gradual introduction.

**Potential Violation Risk**:
- If cache hit measurement intercepts all tool calls via hook, performance degradation → design as sampling-based (10% sampling).

## 8. Work Status

- **Status**: done
- **Completion Date**: 2026-05-25
- **Verification Evidence**: `.venv/bin/python -m pytest tests/test_post_task_validator_hook.py tools/run_orchestrator/tests/test_cli.py tools/run_orchestrator/tests/test_orchestrator_intervention.py tools/fleet_observe/tests/test_measure_usage.py tests/test_report_contract_validator.py tests/test_hook_scripts.py -q` passed, `uv run python -m tools.fleet_observe refresh --family your-harness --allow-self` live run confirmed `usage.invocations_log.exists=True` and `hook.pre-tool-use.last_invoked_at` populated, `run_orchestrator report --payload` smoke pass
- **Revert Reason**: –

## 9. Next Steps

Proceed to [Phase 7 Fleet Expansion](phase-7-application.md).
