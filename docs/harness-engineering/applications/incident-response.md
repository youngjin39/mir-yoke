---
status: design-v1
date: 2026-05-23
scope: incident response runbook
audience: your-harness operators (your-harness self + fleet families)
---

# Incident Response Runbook

> **Purpose**: Standard response procedure for incidents occurring during autonomous operation and fleet family rollout. **Pre-condition (DETECT) → 4-phase response (CONTAIN → ERADICATE → RECOVER → POSTMORTEM)**. DETECT is the pre-trigger phase handled by the 6 user-intervention triggers (R8 supplement) in [`autonomous-execution.md`](autonomous-execution.md) §6. This document defines the 4-phase response that follows.

## 1. Definitions

Scope of "incident" covered by this document.

| Type | Definition | Example |
|---|---|---|
| **stall** | Task makes no progress (idle / hang) | MIR-STALL-001 21-minute idle |
| **runaway** | Autonomous operation exceeds intended scope | Unbounded ACT loop outside retry_budget |
| **bad output** | Measurable output quality degradation | Evaluation harness score below threshold |
| **enforcement bypass** | Hook fails to block an intended action | False negative |
| **security incident** | Injection / poisoning / data leak | Indirect injection from WebFetch passing through |
| **family contamination** | Change in family A affects family B | Cross-pollination safeguard failure |

## 2. Pre-condition + 4-Phase Response

```text
[Pre-condition]
DETECT  (6 triggers from autonomous-execution.md §6 — pre-fire, R8 supplement)
  ↓
[4-Phase Response]
CONTAIN (immediate isolation / spread prevention)
  ↓
ERADICATE (root cause removal)
  ↓
RECOVER (return to normal state + verification)
  ↓
POSTMORTEM (record / feedback / prevention)
```

DETECT is the pre-trigger phase handled by [`autonomous-execution.md`](autonomous-execution.md) §6. The 4-phase response in §2 follows that. Standard procedure for each phase.

### 2-1. DETECT
The 6 triggers (R8 supplement) in [`autonomous-execution.md`](autonomous-execution.md) §6 constitute the detect phase.

- retry_budget exceeded → BLOCKED
- SE-meta self-stop violation → INTERRUPTED
- risk_level high + NEED_APPROVAL → waiting for user confirm
- Circuit Breaker (same error N times) → BLOCKED
- Interrupt (Ctrl-C, kill) → CANCELLING

Additional R4 triggers:
- evaluation harness score below threshold (Phase 6 §9a)
- prompt injection validator fires (Phase 2 §3-4)
- critical category in fleet_observe advisory log

### 2-2. CONTAIN
**Goal**: Prevent spread / additional damage. Within 5 minutes.

Standard actions:
1. Stop ACT of active run (CANCELLING → ROLLBACK)
2. Temporarily disable or downgrade related hook intensity (block → warn)
3. Block new task entry (start-harness forces NEED_APPROVAL)
4. User notification (Discord or advisory log)
5. Confirm scope of impact — your-harness only? family A only? family A+B?

For family contamination, additionally:
- Activate cross-pollination safeguard ([`template-cherrypick.md`](template-cherrypick.md) §9)
- Temporarily disable `enabled_phases` for affected families

### 2-3. ERADICATE
**Goal**: Remove root cause. "System fix" not "prompt fix" ([`../phase-6-observability.md`](../phase-6-observability.md) §1).

Standard actions:
1. Read structured_error ([`../phase-4-state-machine.md`](../phase-4-state-machine.md) §5) type / recoverable / details_ref carefully
2. Review the preceding N events in fleet_observe advisory log
3. Classify root cause:
   - Hook gap → reinforce Phase 2 enforcement
   - Memory contamination → Phase 8 GC + Phase 3 lifecycle cleanup
   - Tool contract violation → Phase 4 schema reinforcement
   - Prompt injection → reinforce Phase 2 §3-4 validator
4. Write hot-fix or ADR
5. Apply mandatory [`design-process.md`](design-process.md) 5-step to the fix

### 2-4. RECOVER
**Goal**: Return to normal state + verification.

Standard actions:
1. Confirm ROLLBACK is complete (git worktree / diff snapshot / file checksum)
2. Restore hook intensity downgraded during CONTAIN
3. Remove block on new task entry
4. **Verification**: Attempt to reproduce the same scenario → confirm fix works
5. 1 week fleet_observe advisory observation
6. Declare normal operations

### 2-5. POSTMORTEM
**Goal**: Learning + prevention. Mandatory for all incidents.

#### Postmortem Template

```markdown
---
incident_id: INC-YYYYMMDD-XXX
status: resolved | reverted | ongoing
severity: critical | high | medium | low
detected_at: <iso>
contained_at: <iso>
eradicated_at: <iso>
recovered_at: <iso>
affected: your-harness | family-X | family-X+Y | fleet-wide
---

# INC-YYYYMMDD-XXX — <one-line summary>

## Timeline
- HH:MM detect: ...
- HH:MM contain: ...
- HH:MM eradicate: ...
- HH:MM recover: ...

## Root Cause
<systemic, not human error>

## What Worked
- ...

## What Didn't
- ...

## Action Items
- [ ] Hook/script change — location + ADR number
- [ ] Test case addition — feed into golden dataset
- [ ] Memory entry — register as `incident` type
- [ ] CLAUDE.md / failure-patterns.md update
- [ ] Add regression-guard subagent training data

## Tripwire Retrospective
- Which tripwire should have fired before this incident reached the detect phase?
- Why did it not fire?
- How to strengthen the fire condition going forward
```

#### Feedback Obligations
- Action item hook/script changes → new enforcement in [`../phase-2-enforcement.md`](../phase-2-enforcement.md)
- Test cases → regression test pool in [`../phase-6-observability.md`](../phase-6-observability.md) §9a evaluation harness
- Memory entry → `incident` type ([`../templates/_schema/memory_entry.schema.json`](../../templates/_schema/memory_entry.schema.json) R4 addition)

## 3. Severity Classification

| Severity | Definition | CONTAIN SLA | ERADICATE SLA | RECOVER SLA | Escalation |
|---|---|---|---|---|---|
| **critical** | your-harness or multiple families affected simultaneously + potential data loss | Immediate (< 5 min) | < 4 hours | < 24 hours | Immediate user notification, all autonomous operations halted |
| **high** | your-harness or 1 family affected + operational disruption | < 30 min | < 1 day | < 3 days | User notification, halt autonomous operations for affected family |
| **medium** | Affected but workarounds available | < 1 day | < 1 week | < 2 weeks | Advisory log only, user decision |
| **low** | No operational impact (info-level) | best-effort | best-effort | best-effort | Log only |

**R7-D-I2 new**: Previous table had only CONTAIN SLA. After applying design-process 5-step for ERADICATE, ERADICATE completion time + RECOVER 1-week advisory observation time are now explicit SLAs. SLA breach requires severity escalation.

### 3-1. Per-Family-Type SLA Differential (R8 supplement — Slice D WARN resolution)

The §3 table applied uniformly across family types — making "5-min CONTAIN" obligation ambiguous for stall/runaway in a personal SE-product family.

| family_type | SLA Application | Reason |
|---|---|---|
| SE-meta (your-harness, template-harness, claude-starter) | **§3 table as-is** + auto escalate to critical when your-harness itself is affected | self-stop obligation (phase-7 §3) |
| code_app (example-infra, example-service) | §3 table + high when multi-family pollination risk exists | shared infrastructure impact |
| SE-product (example-notes, example-game, example-app, example-brand) | §3 table as-is | potential user data impact |
| hybrid_pipeline (example-content, example-story, example-video, example-stock) | CONTAIN SLA 2x extended (creative work protection — interrupt burden is high) | Content work flow protection |
| SE-product personal (example-learning, example-personal) | **best-effort + user decision required** (auto critical/high escalation prohibited) | Personal domain — user autonomy |

**Sealed family incidents**: When applying this ledger, external git push blocking risks violating the sealed policy. CONTAIN phase requires immediate user notification + confirmation of no ADR-22 violation.

## 4. Sample Incident — MIR-STALL-001 (Reference)

Retrospective application of this runbook to the MEMORY `incident_mir_stall_001.md`.

| Phase | Execution in this incident |
|---|---|
| DETECT | User noticed 21-minute idle → discovered missing ADR-06 trigger |
| CONTAIN | (Not present at the time — user manual intervention) |
| ERADICATE | Introduced ADR-06 stall-detection + created stall_watchdog |
| RECOVER | 1-week advisory observation |
| POSTMORTEM | Recorded MEMORY `incident_mir_stall_001`, wrote ADR-06 |

Once this runbook is formalized at R4, future stall-type incidents will automatically go through this 4-phase process.

## 5. your-harness Application Priority

| Step | Work | Dependencies | Estimate |
|---|---|---|---|
| IR-1 | Formalize this runbook as ADR (ADR candidate 36 — R9 renumber: previous ADR-30 = memory lifetime conflict with appendix-a §6) | – | 2h |
| IR-2 | Formalize postmortem template + create `tasks/incidents/` directory | IR-1 | 1h |
| IR-3 | Apply `incident` type memory entry schema (memory_entry.schema.json R4 land) | Phase 3 | 1h |
| IR-4 | Automate connection of 5 DETECT triggers — fire trigger events in fleet_observe advisory_log | autonomous-execution AE-5 | 2h |
| IR-5 | CONTAIN intensity downgrade hook — `.claude/hooks/contain-mode.sh` | Phase 2 | 3h | land (R28-T05 2026-05-24) |
| IR-6 | Tripwire Retrospective automation — integrate with false-negative-tester subagent | Phase 8 | 4h |

Total estimate: 13h.

## 6. Per-Family Propagation Exceptions

| family type | Incident runbook application |
|---|---|
| SE-meta (your-harness) | enforced — all incidents follow this runbook |
| code_app | enforced — high infrastructure impact |
| SE-product | enforced — postmortem required |
| hybrid_pipeline | warn — formal postmortem only for severity high and above |
| SE-product personal | off — user's private domain, postmortem at user's discretion |

Family contamination incidents are enforced regardless of type.

## 7. Change History

- 2026-05-23: Initial draft. Incorporates R3 verification P3 recommendations. 4-phase response + postmortem template + severity classification.
