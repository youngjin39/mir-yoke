---
phase: 6
title: Observability
status: consolidated-v1
depends_on: phase-4-state-machine
---

# Phase 6 — Observability & Auto-correction

> **Purpose**: No measurement means no evaluation; no evaluation means no improvement. 12 metrics + autonomous feedback loop for the harness to improve itself.

## 0.5 Design Goals (R9 anchor)

> This phase's connection to the [3-axis fleet goals](applications/fleet-catalog.md). When adding a new phase or cherry-picking for a family, the `design` skill (R9-T11) requires `design_goals` as a mandatory input.

**3-axis contribution**:
- **Axis I (your-harness hardening)**: 12 metric measurement (R7-C reinforcement) + fleet_observe 7-axis + autonomous feedback loop
- **Axis II (public template sync)**: identical template measurement schema + families must submit identical axis reports
- **Axis III (fleet central governance / back-propagation)**: fleet observability rollup (your-harness aggregates 7-axis results from all fleet families, compares drift visibility → phase-11 back-propagation input)

**Inter-phase contract**:
- **Input** (consumes): phase-4 (tool_event log + run_state transitions) + phase-5 (subagent dispatch log)
- **Output** (provides): report_contract output + autonomous feedback trigger + 12-metric dashboard → phase-7 fleet-wide comparison + phase-11 drift detection

## 1. Principle

> Without measurement, no evaluation; without evaluation, no improvement.

Also:

> When AI violates a rule, do not just edit the prompt — **fix the system so that particular failure is structurally unrepeatable**.

## 2. 12 Measurement Metrics (R7-C-W4 reinforcement: 8 → 12)

This §2 table is the single source of truth for this phase. The 4 standard LLM harness metrics (Cost / Latency / Approval rate / Error rate) — previously mentioned only in §3 prose — are explicitly added to the table.

| # | Metric | Meaning | Category |
|---|---|---|---|
| 1 | Context size trend | Token usage per turn | context |
| 2 | Tool call count | Average / distribution of calls per turn | tool |
| 3 | Repeated read pattern | Same file read N times | pattern |
| 4 | Giant output occurrence | Single tool result > threshold | tool |
| 5 | Subagent call count | Spawn count per task | pattern |
| 6 | `/compact` timing | Turn count until trigger | context |
| 7 | Retry pattern after failure | Same error repeated N times | pattern |
| 8 | Cache hit estimate | Cache breakpoint recovery rate | context |
| 9 | **Cost** (R7 new) | Cumulative LLM cost per task (USD) — provider × model × token | resource |
| 10 | **Latency** (R7 new) | Tool call wall-clock distribution (P50 / P95 / P99) | resource |
| 11 | **Approval rate** (R7 new) | NEED_APPROVAL → APPROVED ratio (auto_policy=required user consent consistency) | governance |
| 12 | **Error rate** (R7 new) | `tool_event.result in [error, denied, timeout]` ratio | governance |

**Mapping to fleet_observe 7-axis**: The 7 axes of `tools/fleet_observe/measure/*` (agent / context / harness / skill / token / archive / advisory) measure a portion of these 12 metrics. Metrics not covered by any axis (Cost/Latency quantification, etc.) require new `fleet_observe/measure/cost.py` + `latency.py` (R7-P3 follow-up).

**OTel compatibility**: Metrics 9–12 (resource + governance) directly map to OpenTelemetry GenAI Semantic Conventions' `gen_ai.usage.input_tokens` / `gen_ai.usage.output_tokens` / `gen_ai.client.operation.duration`. The R7-C-W5 fields (`provider`/`model`/`operation`) in `tool_event.schema.json` provide the basis for this mapping.

## 3. Measure → Correct → Automate Cadence

A 3-stage evolution model.

### Measurement Stage
- Session log analysis (12 metrics above)
- Cost / latency / tool chain tracking
- Sources: self-built metrics, fleet_observe

### Correction Stage (manual)
- Prefix pinning (cache stability)
- CLAUDE.md diet (trim)
- Deny-list additions
- Output cap introduction
- Session/subagent threshold tightening

### Automation Stage (hook transition)
- PreToolUse — route to subagent before large file reads
- PostToolUse — suggest `/compact` after context size check
- SessionStart — clean up stale memory
- PreWrite (TDD) — block when tests are absent
- PreCommit — lint / build / test
- Before PR creation — AI review

Rules moved from manual to automated are no longer left to human hands.

## 4. Autonomous Feedback Loop

Failure occurs → system autonomously sends error back to AI → fix → re-run. Auto-correction Loop.

```text
ACT → tool error → structured error ([phase-4-state-machine] §5)
  → orchestrator catches → constructs feedback message
  → sends to AI worker → AI proposes fix
  → loop until retry_budget exceeded ([phase-2-enforcement] §5)
```

Loop exit conditions:
- Success → VERIFY → REPORT
- retry_budget exceeded → BLOCKED → user intervention
- Same error repeated (Circuit Breaker) → INTERRUPTED

## 5. 5 Cost Waste Patterns (Diagnosis & Fix)

| Pattern | Diagnosis | Fix |
|---|---|---|
| Context Bloat | Layers 3–6 of the 8-layer model are oversized | CLAUDE.md diet, `@import` split |
| Giant Tool Outputs | Single tool result > 10k tokens | head/tail/grep cap, page split |
| Poor Cache Utilization | Cache miss on same reads | Prohibit mid-session CLAUDE.md modification |
| Duplicate Tools | Multiple registrations of same-function tools | Tool catalog cleanup |
| Subagent Overuse | Spawn count per task > N | Re-examine [[phase-5-subagents]] §2 usage conditions |

## 6. Observability Tool Candidates

| Tool | Role | Adoption |
|---|---|---|
| Langfuse | Token/cost/latency/tool chain + LLM-as-judge | Not adopted (self-built) |
| fleet_observe (your-harness) | 7-axis measurement + family advisory | land |
| Self-built metrics (`tools/fleet_observe/measure/*`) | per-axis measurement | land |
| **OpenTelemetry GenAI Semantic Conventions** | provider/model/operation/token/error standard schema + distributed tracing | **schema adoption only under review** (R4 new) |

External SaaS dependency avoided → self-built measurement infrastructure. The principles of this phase apply regardless.

**OTel schema adoption rationale (R4)**: Maintain self-built fleet_observe infrastructure but make **schema** OTel GenAI conventions compatible. Avoids schema mismatch when external families integrate with their own observability tools (Langfuse, Datadog, Honeycomb, etc.). Integration targets:
- Map `tool_event.schema.json` field names to OTel `gen_ai.*` namespace
- Express parent-child relationships for distributed tracing spans (Claude → Codex → subagent fan-out)
- Add `provider`/`model`/`operation` fields (currently absent in fleet_observe)

**Application strength**: schema compatibility only is mandatory; actual OTel collector/exporter adoption is optional. ADR candidate 37 (R9 renumbered: previously candidate 29 → 37, ADR-29 = tool contract mandatory fields conflict).

## 7. Measurable Catalog

Axes measured by `fleet_observe`:

1. agent
2. context
3. harness
4. skill
5. token
6. archive
7. advisory log

Each axis absorbs a portion of the 12 metrics in §2.

## 8. Meta-feedback

Patterns discovered during the correction stage feed back into:

- Recurring failures → add to `failure-patterns.md` → memory SoT
- Repeated hook avoidance → enforcement strengthening ([[phase-2-enforcement]])
- Context bloat → CLAUDE.md diet cadence ([[phase-3-memory-context]] §11)
- Unused component detection → [[phase-8-garbage-collection]]

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

In addition to `concise_report_v1`, task-type-specific contracts like `audit_report_v1` and `research_report_v1` are possible.

## 9a. Evaluation Harness (R4 new)

If the 12 metrics (§2) measure only system metrics, **artifact quality evaluation** is handled by a separate evaluation harness.

### Components

| Component | Definition |
|---|---|
| **Golden Dataset** | Version-controlled set of standard input + expected output pairs |
| **Scoring Rubric** | Evaluation axes: accuracy, fidelity, safety, format compliance, etc. |
| **CI Gate** | Automatic evaluation run before PR merge; blocks on regression |
| **Regression Test Pool** | Production failures automatically feed back as new test cases |

### Absorbing the 6-slice audit pattern

The 6-slice cold-context audit + R1~R5 reinforcement pattern (see MEMORY `feedback_six_slice_audit_pattern`) is already the conceptual prototype of an evaluation harness. This §9a formalizes that pattern.

- PARTIAL/PASS judgment from audit results → scoring rubric quantification
- R1~R5 recommendation application → regression test pool feedback
- Audit cadence (immediately after large land) → CI gate trigger

### Directory Structure

```
docs/harness-engineering/evaluation/        # R4 new candidate, next step after this ledger
  ├ README.md
  ├ golden-datasets/
  │   ├ phase-design.jsonl           # golden examples for phase design work
  │   ├ enforcement-policy.jsonl     # golden examples for enforcement decisions
  │   └ ...
  ├ rubrics/
  │   ├ design-quality.yaml          # design evaluation rubric
  │   └ code-quality.yaml
  └ runs/                            # accumulated evaluation run results
```

### Evaluation Axes (rubric example)

| Axis | low (0) | medium (1) | high (2) |
|---|---|---|---|
| Accuracy | many factual errors | some errors | no errors |
| Fidelity | user requirements unmet | partially met | fully met |
| Safety | many dangerous patterns | some risks | no risks |
| Format compliance | contract violation | partial compliance | full compliance |

Each axis 0–2 points × 4 axes = 0–8 points. 6 or above = PASS.

### Application State

- 6-slice audit pattern: land (in active operation)
- Golden dataset formalization: **not implemented** (R4 follow-up)
- Scoring rubric codification: **not implemented**
- CI gate automatic evaluation: **not implemented**
- Regression test pool feedback: partial land (`failure-patterns.md` absorbs some)

### External References

- Braintrust / LangSmith / OpenAI Evals — your-harness uses self-built (same stance as Langfuse deprecation)
- Towards Data Science 12-metric framework — reference for rubric design

## 10. Prohibitions

- Claiming "performance improved" without measurement
- Fixing only the prompt without fixing the system
- Autonomous feedback loop without Circuit Breaker
- Free-form reports (no contract)
- Uncritical reliance on external SaaS

## 11. Application State

| Item | Status | Location |
|---|---|---|
| 12 metric measurement | partial land | fleet_observe 7-axis + usage telemetry pattern facts land; cache hit quantitative facts and OTel/resource metrics are follow-up |
| Measure → correct → automate cadence | land | ADR-10 fleet-governance-advisory |
| Autonomous feedback loop | partial land | `run_state.retry_count`-based retry_budget detection + VERIFY→BLOCKED seam landed; broader loop hardening is follow-up |
| 5 cost waste pattern diagnosis | partial land | fleet_observe advisory |
| Langfuse | deprecated | self-built adopted |
| Meta-feedback | land | failure-patterns + ADR cycle |
| report_contract | partial land | active_task declaration + validator + CLI report closeout path land |
| **Evaluation Harness (§9a)** | partial land | 6-slice audit pattern land; golden dataset/rubric/CI gate not implemented |
| **OTel GenAI schema compatibility** (§6) | **not implemented** | fleet_observe schema itself has no OTel mapping |

**Gap**: report_contract enforcement across the full closeout lane, cache hit/resource metric expansion, autonomous feedback loop retry_budget quantification (linked with [[phase-2-enforcement]] §5), Evaluation Harness formalization, OTel schema compatibility.

## 12. Exit Criterion

At least 5 of the 12 metrics (context / tool call / repeated read / giant output / retry pattern) are automatically measured and at least 1 advisory report is generated. Autonomous feedback loop observed reaching retry_budget limit on an intentional verification failure case, then entering BLOCKED state.

## 13. Next Steps

Proceed to [Phase 7 — Fleet Expansion](phase-7-fleet-expansion.md).
