---
phase: 5
title: Subagents Application
status: done
family: your-harness (SE-meta)
blueprint: ../../phase-5-subagents.md
priority: P9 (nearly complete)
---

# Phase 5 — Subagents Application (example-harness)

> **Priority P9**. The most mature area for your-harness. Almost no gaps.

## 1. Blueprint Reference

[`../../phase-5-subagents.md`](../../phase-5-subagents.md) full.

**Related Supplementary Documents**: [`../design-process.md`](../design-process.md) §5 subagent matrix + §6-2 role-split patterns integrate directly with this phase's resource cap and fork_context policy. The default cap for this phase = 4, and only when design parallel analysis and independent verification must be maintained simultaneously does the `temporary_cap` mechanism raise it to 6 (design-process §5 end).

## 2. Current State (pre-measurement)

| Item | Blueprint Location | your-harness State |
|---|---|---|
| 3 allowed roles + extensions | §3 | land — executor-agent / codex-final-reviewer / quality-agent / cwe-auditor / runtime-contract-reviewer / template-sync-validator / dep-auditor / pipeline-validator / ontology-validator / ui-reviewer / fleet-doc-steward |
| Handoff contracts | §4 | land — per agent definition |
| Worker Isolation 4-step | §5 | land — Claude+Codex role policy (`docs/decisions/claude-codex-role-policy-2026-05-02.md`) |
| fork_context policy | §6 | land — `CLAUDE.md` Subagent Resource Management |
| Resource cap = 4 | §7 | land — `CLAUDE.md` same section |
| Self-assessment avoidance | §8 | land — Codex execution lane enforced |
| Activation timing | §10 | land (already in use, ADR-09) |

**Gap**: no substantive unimplemented gaps beyond closeout evidence cleanup.

## 3. Application Work Steps

| Step | Work | Dependency | Estimate |
|---|---|---|---|
| 5-1 | Audit existing handoff contracts against [`../../phase-5-subagents.md`](../../phase-5-subagents.md) §4 checklist — supplement missing fields (time/token budget) | – | 2h |
| 5-2 | fork_context policy alignment verification — confirm each agent's fork_context setting matches §6 table | – | 1h |
| 5-3 | Resource cap = 4 baseline alignment — align concurrent spawn policy and advisory recording rules with `CLAUDE.md`/runbook | – | 2h |

## 4. Files to Modify

| Path | Type |
|---|---|
| `.claude/agents/*.toml` (15+ files) | edit (supplement handoff contract fields as needed) |
| `.codex/agents/*.toml` | edit (mirror) |
| `.claude/hooks/pre-spawn-validator.sh` | optional future work (if runtime enforcement is needed) |
| `CLAUDE.md` §Subagent Resource Management | edit (cap = 4 default + temporary cap recording rules) |

## 5. Verification Procedure

Blueprint §12 Exit Criterion: "1 code task measured completing all 4 Worker Isolation steps. Self-assessment avoidance confirmed."

Verification methods:
1. Dummy code task → measure whether all 4 steps pass: Claude plans → Codex writes → Codex verifies → Claude merges
2. Check fleet_observe logs for cases where same lane performs both writing and verification simultaneously
3. Confirm policy recording/degraded mode remains when 5+ concurrent spawns attempted

## 6. Cross-repo Propagation Exceptions

| Case | Rule |
|---|---|
| code_app | enforced — Worker Isolation 4-step mandatory |
| SE-product | warn — 4-step recommended, but 2-step allowed for simple tasks (Claude write + Claude verify in different session) |
| hybrid_pipeline | warn — spawn reviewer when content task needs one, single lane if off-day |
| content_app | off — personal/content tasks: user is reviewer |
| Family has own review framework | your-harness codex-final-reviewer not enforced, but advisory verification that review lane is a separate lane |

[`../exceptions.md`](../exceptions.md) §3 Phase 5 row consistent.

**Specific Exceptions**:
- `example-infra` → same as your-harness
- `example-notes` → code work enforced, content work warn
- `example-content` → cost vs. value review needed for Claude+Codex 4-step for content work. User decision.
- `example-personal` → entirely off

## 7. SE-meta self-stop Check

your-harness itself already operates with Worker Isolation. Minimal new application in this phase.

**Potential Violation Risk**:
- Cap = 4 default fits multiple parallel audits better, but should not be read as unlimited expansion. Therefore §3-3 policy stays in the form "default cap = 4, can raise to 6 via temporary_cap when needed."

## 8. Work Status

- **Status**: done
- **Completion Date**: 2026-05-25
- **Verification Evidence**: ADR-09 role policy + active subagent management policy + current session real subagent use demonstrates Worker Isolation operation
- **Revert Reason**: –

## 9. Next Steps

Proceed to [Phase 6 Observability](phase-6-application.md).
