# Bluebricks

Bluebricks is the development model used in this repository.

A bluebrick is a module-level blueprint unit.
Multiple bluebricks are connected through composition and orchestration.

## Purpose

The purpose of bluebricks is to help AI agents understand the repository as a system of bounded design units, not as a pile of files.

## Bluebrick Template

```md
# Bluebrick: <name>

## Purpose
What this bluebrick is responsible for.

## Public Interface
APIs, functions, classes, events, configs, or files exposed to other bluebricks.

## Internal Rules
Implementation rules that must be preserved.

## Non-Obvious Hazards
Hidden patterns that can break build, runtime behavior, compatibility, or data.

## Dependencies
What this bluebrick depends on.

## Downstream Users
What depends on this bluebrick.

## Composition
How this bluebrick is combined with others.

## Orchestration
Who calls this bluebrick, in what order, and under what conditions.

## Validation
How to test or verify changes.
```

## Current Core Bluebricks

## Composite TDD Validation Rule

For every non-trivial code change, the affected bluebrick must define a composite TDD matrix in
`tasks/tdd.json`.

Each bluebrick validation pass must explicitly classify:

- `unit`
- `integration`
- `e2e`
- `browser`
- `edge`
- `architecture`
- `availability`
- `load`
- `soak`
- `security`
- `compatibility`
- `transaction_locking`

The category may be closed as `not_applicable`, but it may not be omitted.

### Bluebrick: Conductor

**Responsibility:** Accept external task requests, classify ingress mode, preserve an audit trail, and hand normal-mode work to Engine without leaking transport-specific concerns into execution code.

**Critical hazards:**
- Do not bypass `ConductorReporter` by returning raw exceptions to the caller.
- Do not turn `KeyboardInterrupt` or `SystemExit` into swallowed recoverable failures.

Full brick: docs/bluebricks/conductor.md

---

### Bluebrick: Engine

**Responsibility:** Compile drafted intent into an executable job, enforce policy and isolation gates, run the worker/reviewer loop, and own the execution-time control plane.

**Critical hazards:**
- Do not skip `target_files` root confinement or SHA pin checks.
- Do not move required tool or provider allowlist validation out of compile.

Full brick: docs/bluebricks/engine.md

---

### Bluebrick: Worker

**Responsibility:** Provide runtime-specific execution adapters for Claude Code, Codex, and future CLIs while keeping the Engine-facing contract stable.

**Critical hazards:**
- Do not make `dispatch` async; the async boundary is intentionally one layer higher.
- Do not leak secrets by widening the provider env allowlist casually.

Full brick: docs/bluebricks/worker.md

---

### Bluebrick: Harness Runtime

**Responsibility:** Define the durable human/agent operating contract: startup context, skills, hooks, generated Codex mirrors, deny-list enforcement, and session continuity.

**Critical hazards:**
- Do not patch `AGENTS.md`, `.agents/`, or `.codex/` by hand.
- Do not leave deny-list as documentation-only policy; hook enforcement must stay wired.

Full brick: docs/bluebricks/harness-runtime.md

---

## Agent Rule

Before making non-trivial code changes, identify the affected bluebrick and check:

- hazards
- dependencies
- downstream users
- validation method
