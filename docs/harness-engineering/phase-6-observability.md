---
phase: 6
title: Observability
status: consolidated-v1
depends_on: phase-4-state-machine
---

# Phase 6 -- Observability & Auto-correction

> **Purpose**: No measurement, no evaluation; no evaluation, no improvement. The harness improves itself with 12 metrics + an autonomous reply loop.

## 0.5 Design Goals (R9 anchor)

**3-axis contribution**:
- **Axis I (self-harness hardening)**: 12-metric measurement + fleet_observe 7-axis + autonomous reply loop
- **Axis II (public template sync)**: identical template measurement schema + families must report using same axes
- **Axis III (fleet central management)**: fleet observability rollup (aggregate N-family 7-axis data, visualize drift comparisons -> phase-11 back-propagation input)

**Inter-phase contract**:
- **Input** (consumes): phase-4 (tool_event log + run_state transitions) + phase-5 (subagent dispatch log)
- **Output** (provides): report_contract output + autonomous reply trigger + 12-metric dashboard -> phase-7 fleet-wide comparison + phase-11 drift detection

## 1. Principle

> Measure to evaluate; evaluate to improve.

Also:

> When AI breaks a rule, do not just fix the prompt -- **fix the system so that failure is structurally impossible to repeat**.

## 2. 12 Measurement Metrics

This table is the single source of truth for this phase. The 4 standard LLM harness metrics (Cost / Latency / Approval rate / Error rate) are explicitly included.

| # | Metric | Meaning | Category |
|---|---|---|---|
| 1 | Context size trend | Token usage per turn | context |
| 2 | Tool call count | Average calls per turn / distribution | tool |
| 3 | Repeated read pattern | Same file read N times | pattern |
| 4 | Giant output occurrence | Single tool result > threshold | tool |
| 5 | Subagent spawn count | Spawns per task | pattern |
| 6 | `/compact` timing | Turns until trigger | context |
| 7 | Post-failure retry pattern | Same error repeating N times | pattern |
| 8 | Cache hit estimate | Cache breakpoint hit rate | context |
| 9 | **Cost** | Cumulative LLM cost per task (USD) -- provider x model x token | resource |
| 10 | **Latency** | Tool call wall-clock distribution (P50 / P95 / P99) | resource |
| 11 | **Approval rate** | NEED_APPROVAL -> APPROVED ratio (user consent alignment for auto_policy=required) | governance |
| 12 | **Error rate** | `tool_event.result in [error, denied, timeout]` ratio | governance |

**fleet_observe 7-axis mapping**: The 7 axes in `tools/fleet_observe/measure/*` (agent / context / harness / skill / token / archive / advisory) cover a subset of these 12 metrics. Metrics not covered by axes (Cost, Latency quantification, etc.) require new `fleet_observe/measure/cost.py` + `latency.py` (future work).

**OTel compatibility**: Metrics 9-12 (resource + governance) map directly to OpenTelemetry GenAI Semantic Conventions (`gen_ai.usage.input_tokens` / `gen_ai.usage.output_tokens` / `gen_ai.client.operation.duration`). The `provider`/`model`/`operation` fields in `tool_event.schema.json` provide this mapping foundation.

## 3. Measure -> Fix -> Automate Cadence

3-stage evolution model.

### Measurement stage
- Session log analysis (above 12 metrics)
- Cost / latency / tool chain tracking
- Sources: self-hosted metrics, fleet_observe

### Fix stage (manual)
- Prefix stabilization (cache stability)
- CLAUDE.md diet
- Deny-list additions
- Output cap introduction
- Session / subagent criteria tightening

### Automation stage (Hook transitions)
- PreToolUse -- subagent routing before large file reads
- PostToolUse -- `/compact` suggestion after context size check
- SessionStart -- stale memory cleanup
- PreWrite (TDD) -- block writes without tests
- PreCommit -- lint / build / test
- Before PR creation -- AI review

Once a rule transitions from manual to automated, it is no longer left to human action.

## 4. Autonomous Reply Loop

Failure occurs -> system autonomously replies with error to AI worker -> fix -> re-execute. Auto-correction Loop.

```text
ACT -> tool error -> structured error (phase-4 section 5)
  -> orchestrator catches -> constructs feedback message
  -> sends to AI worker -> AI proposes fix
  -> loop until retry_budget exceeded (phase-2 section 5)
```

Loop exit conditions:
- Success -> VERIFY -> REPORT
- retry_budget exceeded -> BLOCKED -> user intervention
- Same error repeating (Circuit Breaker) -> INTERRUPTED

## 5. 5 Cost-Waste Patterns (diagnosis and remediation)

| Pattern | Diagnosis | Remedy |
|---|---|---|
| Context Bloat | 8-layer layers 3-6 are overloaded | CLAUDE.md diet, `@import` splitting |
| Giant Tool Outputs | Single tool result > 10k tokens | head/tail/grep cap, page splitting |
| Poor Cache Utilization | Cache miss on same reads | Do not modify CLAUDE.md mid-session |
| Duplicate Tools | Multiple registrations of same-function tools | Tool catalog cleanup |
| Subagent Overuse | Spawns per task > N | Review [Phase 5](phase-5-subagents.md) section 2 usage conditions |

## 6. Observability Tool Candidates

| Tool | Role | Adoption |
|---|---|---|
| Langfuse | Token / cost / latency / tool chain + LLM-as-judge | Not adopted (self-built) |
| fleet_observe | 7-axis measurement + family advisory | landed |
| Self-hosted metric (`tools/fleet_observe/measure/*`) | Per-axis measurement | landed |
| OpenTelemetry GenAI Semantic Conventions | Standard schema for provider/model/operation/token/error + distributed tracing | Schema-only adoption under review |

External SaaS dependency avoided; self-built measurement infrastructure adopted. However the design principles of this phase apply universally.

**OTel schema adoption rationale**: Maintain self-hosted fleet_observe infrastructure but make schema OTel GenAI conventions compatible. Prevents schema mismatch when external families integrate their own observability tools (Langfuse, Datadog, Honeycomb, etc.).

## 7. Measurable Catalog

Axes measured by `fleet_observe`:

1. agent
2. context
3. harness
4. skill
5. token
6. archive
7. advisory log

Each axis absorbs a subset of the 12 metrics from section 2.

## 8. Meta-feedback

Patterns discovered in the fix stage feed back into:

- Recurring failures -> add to `failure-patterns.md` -> memory SoT
- Repeated hook evasion -> strengthen enforcement ([Phase 2](phase-2-enforcement.md))
- Context bloat -> CLAUDE.md diet cadence ([Phase 3 section 11](phase-3-memory-context.md))
- Unused component detection -> [Phase 8 Garbage Collection](phase-8-garbage-collection.md)

## 9. Report Contract

Standard format for `report_contract` (declared by start-harness).

```yaml
report_contract: concise_report_v1
fields:
  - changed_files: [<path>]
  - verification: {checks: [...], result: pass|fail}
  - risks: [<one-line>]
  - next_steps: [<one-line>]
  - artifacts: [<path>]
```

Beyond `concise_report_v1`, task_type-specific contracts are possible: `audit_report_v1`, `research_report_v1`, etc.

## 9a. Evaluation Harness

Where the 12 metrics measure system metrics, **output quality assessment** is handled by a separate evaluation harness.

### Components

| Component | Definition |
|---|---|
| **Golden Dataset** | Version-controlled set of standard input + expected output pairs |
| **Scoring Rubric** | Evaluation axes: accuracy, fidelity, safety, format compliance, etc. |
| **CI Gate** | Automatic evaluation before PR merge; blocks on regression |
| **Regression Test Pool** | Production failures automatically flow back as new test cases |

### Evaluation axes (rubric example)

| Axis | low (0) | medium (1) | high (2) |
|---|---|---|---|
| Accuracy | Many factual errors | Some errors | No errors |
| Fidelity | User requirements unmet | Partially met | Fully met |
| Safety | Many risky patterns | Some risk | No risk |
| Format compliance | Contract violated | Partially compliant | Fully compliant |

Each axis 0-2 points x 4 axes = 0-8 points. 6+ = PASS.

### Application Status

- Golden dataset formal definition: **not yet implemented**
- Scoring rubric codification: **not yet implemented**
- CI gate automatic evaluation: **not yet implemented**
- Regression test pool feedback: partial (absorbed by `failure-patterns.md`)

## 10. Prohibitions

- Claiming "performance improved" without measurement
- Only fixing prompts without fixing the system
- Autonomous reply loop without Circuit Breaker
- Report free-form (no contract)
- Uncritical dependence on external SaaS observability tools

## 11. Application Status

| Item | Status | Location |
|---|---|---|
| 12-metric measurement | partial | fleet_observe 7-axis + usage telemetry pattern facts landed; cache hit quantification and OTel/resource metrics pending |
| Measure -> fix -> automate cadence | landed | fleet-governance-advisory architecture decision record |
| Autonomous reply loop | partial | `run_state.retry_count`-based retry_budget detection + VERIFY->BLOCKED seam landed; broader loop hardening pending |
| 5 cost-waste pattern diagnosis | partial | fleet_observe advisory |
| Meta-feedback | landed | failure-patterns + ADR cycle |
| report_contract | partial | active_task declaration + validator + CLI report closeout path landed |
| Evaluation Harness | partial | 6-slice audit pattern landed; golden dataset/rubric/CI gate not yet implemented |
| OTel GenAI schema compatibility | not yet implemented | fleet_observe schema lacks OTel mapping |

## 12. Exit Criterion

At least 5 of the 12 metrics (context / tool call / repeated read / giant output / retry pattern) are automatically measured and at least 1 advisory report generated. The autonomous reply loop operates up to retry_budget limit on an intentional verification failure case, then enters BLOCKED.

## 13. Next Step

[Phase 7 -- Fleet Expansion](phase-7-fleet-expansion.md)
