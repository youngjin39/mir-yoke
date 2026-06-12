---
status: design-v1
date: 2026-05-20
scope: multi-subagent design process with mandatory iteration — the standard design lane for harness engineering work
audience: your-harness control plane
---

# Design Process

> **Purpose**: Define the multi-subagent design process that applies to all harness engineering work. Iteration is mandatory — a single design pass is insufficient for any non-trivial harness change.

## 0. Design Goals Capture — 5 Mandatory Fields

Before beginning any design, the main agent must capture:

| Field | Description |
|---|---|
| `goal` | What outcome is this design achieving? (1-2 sentences) |
| `scope` | Which files, phases, or families are in scope? |
| `constraints` | What must not change? What are the hard limits? |
| `success_criteria` | How will we verify the design was implemented correctly? |
| `design_goals` | 3-axis contribution: Axis I (your-harness), Axis II (template), Axis III (fleet) |

The `design_goals` field is mandatory for any phase-related design (R9-T11 contract). If the task does not map to a specific phase, use the relevant domain axes.

## 1. Standard 5-Step Design Process

```text
Step 1: Goal capture      — fill §0 mandatory fields
Step 2: Research          — grep existing code, read schemas, survey physical state
Step 3: Draft design      — propose approach with explicit assumptions
Step 4: Iteration         — challenge draft with subagent analysis, resolve conflicts
Step 5: Finalize          — produce execution brief (DispatchBrief or equivalent)
```

**Step 2 is non-negotiable.** Never propose a new module, CLI command, hook, or configuration field without first grepping the codebase to confirm it does not already exist.

## 2. Iteration Requirements

### Minimum Iteration Rounds

| Task Classification | Minimum Rounds |
|---|---|
| tiny | 1 (single review pass sufficient) |
| normal | 2 (initial + at least 1 challenge pass) |
| heavy | 3 (initial + challenge + synthesis) |
| fleet-wide / policy | 3+ (mandatory parallel subagent analysis) |

A "round" is: draft produced → subagent challenges it → draft revised. Cosmetic rewording does not count as a round.

### When to Stop Iterating

Stop when:
1. All constraints from §0 are satisfied by the design
2. No outstanding unresolved conflicts between subagent analyses
3. Success criteria are mechanically testable (not subjective)
4. The execution lane can implement the design without needing to invent new decisions

Do not stop early because the design "looks good". Stop when it is verifiably complete.

## 3. Subagent Utilization Matrix

| Design Step | Recommended Subagents | Role |
|---|---|---|
| Step 2 (Research) | Explore, general-purpose | Parallel codebase search across multiple surfaces |
| Step 3 (Draft) | Plan | Architecture + step-by-step implementation plan |
| Step 4 (Iteration) | quality-agent, codex-final-reviewer | Independent challenge and gap identification |
| Step 5 (Finalize) | executor-agent | Verify brief is unambiguous and implementable |

For fleet-wide or policy changes, add:
- `fleet-doc-steward`: governance drift detection
- `cwe-auditor`: security pattern scan
- `runtime-contract-reviewer`: exception class and contract protection check

## 4. Anti-Patterns

The following design behaviors are explicitly prohibited:

| Anti-Pattern | Why Prohibited |
|---|---|
| Surface review only | Reading file names and section headings without reading actual code produces wrong assumptions about existing state |
| Single-pass design | One draft without challenge fails to surface conflicts, gaps, or constraint violations |
| Fabricated module list | Proposing new modules/CLIs without grepping first leads to duplicate implementations |
| Scope creep in brief | Adding features not in the original goal — the execution lane will implement everything in the brief |
| Subjective success criteria | "Looks better" or "feels cleaner" cannot be mechanically verified |
| Skipping `design_goals` | Phase-related designs without 3-axis goals lose connection to fleet-wide purpose |
| Delegating understanding | Writing "based on your findings, implement X" in a DispatchBrief — the main agent must synthesize before dispatching |
| Ignoring physical state | Designing changes to files that have already been changed since last read |

## 5. SE-meta Self-Stop for Design Phase

For your-harness (SE-meta family type):

> **Design self-stop**: If during the research step (Step 2) the main agent discovers that the proposed design would require modifying hook enforcement, pre-commit gates, or the verification contract — escalate to user before proceeding to Step 3. Do not draft a design for hook/enforcement changes without explicit user framing.

This prevents designs that appear bounded from growing into enforcement changes mid-execution.

## 6. Meta-Verification Table

After the design process completes, verify the design output against these criteria before dispatching:

| ID | Check | Pass Criterion |
|---|---|---|
| R1 | `design_goals` 3-axis contribution captured | All 3 axes filled (or explicitly N/A with reason) |
| R2 | No fabricated modules — grep evidence | At least 1 codebase read confirming physical state of proposed surfaces |
| R3 | Minimum iteration rounds completed | Round count meets the task classification minimum |
| R4 | Success criteria are mechanically testable | No criterion requires subjective judgment |
| R5 | All constraints satisfied | Each constraint from §0 is addressed in the design |
| R6 | DispatchBrief is self-contained | Execution lane can implement without needing to infer decisions |

### Subagent IDs for Meta-Verification

The following subagent types are used for R1–R6 verification passes:

- `Plan` (a-plan-*): architecture and step-by-step plan review
- `quality-agent` (a-quality-*): code quality and gap identification
- `codex-final-reviewer` (a-reviewer-*): final review before dispatch
- `Explore` (a-explore-*): targeted codebase search for R2 evidence
- `executor-agent` (a-exec-*): brief clarity check for R6

Note: subagent IDs follow the format `a-<type>-<session-suffix>`. They are session-scoped identifiers, not persistent.

## 7. Application State

| Item | Status |
|---|---|
| §0 mandatory fields — enforcement | advisory (meta-verification R1 catches violations) |
| Minimum iteration round requirement | advisory |
| Subagent utilization matrix | documented |
| SE-meta design self-stop | advisory (hook does not block design-phase actions) |
| Meta-verification table R1–R6 | operational |

## 8. Exit Criterion

The design process is complete when:
1. §0 mandatory fields are filled
2. Minimum iteration rounds are complete
3. Meta-verification R1–R6 all pass (or exceptions documented)
4. DispatchBrief produced and ready for execution lane
