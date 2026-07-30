# 05 — Architecture views and domain differences

Requirement rules are in 01. This document is needed only after C2 (view allocation).

## Stakeholders, concerns, views

Before building a view, record in `meta.yaml` whose concern it serves. Do not build a view with no
concern behind it.

```yaml
stakeholders:
  - who: "implementing agent"
    concerns: ["what to build in which file", "how completion is judged"]
    views: [mod/, tasks.yaml]
  - who: "operator"
    concerns: ["what happens, and how, during a failure"]
    views: [views/runtime.yaml, concepts/error-handling.yaml]
```

## Kinds of view

| View | Exists at | Output |
|---|---|---|
| Module | Development-time implementation elements | `mod/*.yaml` |
| Component & Connector | Run-time dynamic elements | `views/runtime.yaml` |
| Allocation | Implementation elements to artifacts to environment | `views/deployment.yaml` |
| Data | Persistent data structure and lifetime | `views/data.yaml` |

No single view expresses a whole architecture. Do not omit a view the domain requires.

---

## Module view — four steps, fixed order

| Step | Output | Core |
|---|---|---|
| 1 | Module dependency | Identify modules and dependencies. No cycles (ADP). Instability I = Fan-out/(Fan-in+Fan-out) |
| 2 | Module interface | Provided/Required. Split fat interfaces (ISP), minimal interfaces |
| 3 | Module interaction | Sequence. Must agree with the interface model (operation↔message, dependency↔message direction) |
| 4 | Module internal | Internal structure, data, algorithms |

Language mapping (C family): interface → header file / module → implementation file /
provided and required → `#include`

### Design principles (original definitions preserved)

- **SRP** A module should have one, and only one, reason to change.
- **OCP** Open for Extension: a module's behaviour must be extensible. Closed for Modification: a
  module's code must not be modified.
- **ISP** Clients should not be forced to depend upon interfaces that they do not use. Split a fat
  interface into several small, cohesive interfaces.
- **DIP** Depend on interfaces, not implementations.
- **CRP** A component is the unit of reuse. Classes reused together belong in one component.
- **CCP** A component is the unit of change. Classes that change together belong in one component.
- **REP** A component is the unit of release. Classes released together belong in one component.
- **ADP** A component must not depend on itself, directly or indirectly.
- **SDP** A component should depend on components more stable than itself.
- **SAP** A component should depend on components more abstract than itself.
- **Cohesion** Strength of functional relatedness of elements within a module.
- **Coupling** Degree of interdependence between two modules.

Layer principles
- Separation of concern: a layer exposes a cohesive set of services through a public interface.
- Acyclic downward dependency: a lower layer does not depend on an upper layer's functionality.
  Upward communication goes through callbacks.

Do not leave these as prose. Push each one down into an executable check in `checks.yaml` (04 §checks).

---

## Runtime view (C&C) — `views/runtime.yaml`

A static module structure cannot express concurrency, timing, or resource contention. Where the
domain requires those, this view is mandatory.

```yaml
components:                       # units of execution
  - id: RC-001
    name: "<process / thread / task / coroutine name>"
    kind: process                 # process | thread | task | isr | coroutine | job
    trigger: "<what starts it: request / period / interrupt / event>"
    period_ms: 100                # when periodic
    deadline_ms: 50               # when there is a deadline
    priority: 3                   # when priorities exist
connectors:
  - id: CN-001
    from: RC-001
    to: RC-002
    kind: queue                   # call | queue | topic | shared-memory | signal | stream
    sync: async                   # sync | async
    capacity: 128
    on_full: drop-oldest          # behaviour when saturated; [TBD] if undecided
    timeout_ms: 3000
    retry: {max: 3, backoff: exponential}
shared_resources:
  - id: SR-001
    what: "<shared state / device / file>"
    accessed_by: [RC-001, RC-002]
    protection: mutex             # mutex | semaphore | atomic | single-writer | none
    reentrant: false
states:                           # only for stateful execution units
  - component: RC-001
    states: ["idle", "running", "degraded"]
    transitions: [{from: idle, to: running, on: "<event>"}]
```

Which module runs on an execution unit lives in the graph as a `runs_on` edge (G-22).

Check items — close with `n/a` plus a reason where they do not apply:
- Does every shared resource name a protection mechanism
- Does every asynchronous connector define timeout, saturation behaviour, and retry (absence fails ARR-6)
- Does every periodic unit define its deadline and worst-case execution time
- Where priorities exist, has inversion been considered
- Does every stateful unit define its recovery and re-entry path

---

## Data view — `views/data.yaml`

```yaml
stores:
  - id: DS-001
    name: "<store>"
    kind: relational              # relational | document | kv | blob | stream | file
    owner: MOD-STORE              # the single module holding write authority
    entities:
      - name: "<entity>"
        key: "<identifier>"
        fields: [{name: "...", type: "...", unit: "...", nullable: false}]
        retention: "<retention period and deletion rule>"     # links to constraints
    consistency: strong           # strong | eventual | read-your-writes
    migration: "<schema evolution and backward-compatibility rule>"
lineage:                          # mandatory for DATA/ML and AI_SYSTEM
  - output: "<produced data>"
    from: ["<input, source>"]
    transform: "<processing stage id>"
```

Keep write authority to one module per store. If there are several, record the reason.

---

## Crosscutting concepts — `concepts/<name>.yaml`

Rules that span modules. Without these, each module implements things differently and conceptual
integrity collapses. **This is the first file an implementing AI agent should read.**

```yaml
id: error-handling
rule: "<the single rule every module follows>"
pattern: "<concrete form: exception hierarchy / return convention / error code scheme>"
forbidden: ["<prohibited form>"]
example: "<minimal example>"
```

The modules it applies to (`governed_by`) and the checks that enforce it (`enforces`) live in the
graph (G-22).

Minimum list — close with `n/a` plus a reason where inapplicable:

| Concept | What must be settled |
|---|---|
| error-handling | Error classification, propagation, user-facing form, where recovery belongs |
| logging | Level criteria, mandatory fields, masking sensitive data, correlation id |
| configuration | Source precedence, required vs optional, defaults, secret handling |
| persistence | Transaction boundaries, retry safety (idempotence), migration procedure |
| auth | Who authenticates, where authorisation is decided, token lifetime, failure response |
| resilience | Default timeout, retry, backoff; circuit conditions |
| observability | Minimum metric and trace set, correlation id propagation |
| naming | Naming rules, obligation to follow `glossary.yaml` |

---

## Architecture Decision Record — `decisions/ADR-<n>.yaml`

A structure without a recorded reason gets rearranged freely by the next agent. Record the decision
and why.

```yaml
id: ADR-001
title: "<the decision in one line>"
status: accepted                  # proposed | accepted | superseded
context: "<what the problem was>"
decision: "<what was chosen>"
alternatives:
  - {option: "<rejected option>", why_not: "<why>"}
consequences: {gains: ["..."], costs: ["..."]}
```

What it affects (reverse `decided_by`), the quality requirement that drove it (`drives`), the checks
that enforce it (`enforces`), and supersession (`supersedes`) live in the graph (G-22).

To reverse a decision, write a new ADR and mark the previous one `superseded`. Do not rewrite an
existing ADR.

---

## Quality requirement to tactic to trade-off

Connect the QA scenario (01 §6.2) to a structural decision. Without this link, a quality requirement
stays on paper.

```yaml
quality_bindings:
  - quality: QR-002               # "p95 response within 300ms"
    tactic: "<chosen tactic: cache / replicate / isolate / queue / precompute>"
    sensitivity: "<the point where this quality breaks if the value moves>"
    tradeoff: "<what was given up: consistency lag / memory / complexity>"
    measured_by: "<measurement method>"
```

Do not claim one tactic improves two qualities at once. Usually one is gained and one is lost.

---

## Infrastructure / allocation — `views/deployment.yaml`

Elements: node / execution environment / communication path / artifact placement.
Notation: multiplicity `{N}`, protocol labels stated.

| Model | Mapping |
|---|---|
| Install model | Module/Component to artifact |
| Deployment model | Artifact to node / execution environment |

---

## Domain differences

Adjust the mandatory views and checks by the domain judged. Under GENERIC, apply no specialised rules.

| Item | EMBEDDED | SERVICE | APP | DATA/ML | AI_SYSTEM |
|---|---|---|---|---|---|
| Context level | Software system context (devices mandatory) | System context | System context | System context | System context (models and external APIs as external systems) |
| Mandatory views | runtime, deployment | runtime, deployment, data | runtime | data, runtime | runtime, data, concepts |
| Priority qualities | Performance (time), reliability, **safety**, resources | Availability, scalability, security | Interaction capability, performance, compatibility | Correctness, throughput, reproducibility | Correctness, reproducibility, security, cost |
| Mandatory constraints | Timing, memory, power, safety level | SLA, concurrency, data retention | Platform, screen sizes, accessibility | Data quality, bias, explainability | Model and prompt version pinning, token budget, data boundary |
| Module mapping | Interface→header, module→implementation file | Service/package boundaries | Layer/feature modules | Pipeline stages | Layers: model, context, tools, orchestration, guardrails, observability |
| Extra checks | ISR safety, re-entrancy, priority inversion, watchdog | Idempotence, retry, backpressure | Offline behaviour, state restoration | Data lineage, drift | See §AI_SYSTEM below |

### AI_SYSTEM extra checks

Apply when the target system contains an LLM or agent. Do not confuse this with the skill itself —
here the **system being designed** is the AI system.

| Concern | What the spec must record |
|---|---|
| Non-determinism | Acceptance criteria that assume the same input may produce different output. Judgement criteria and tolerances rather than exact equality |
| Reproducibility | Model id and version, temperature and seed, prompt version, tool versions pinned. What, once fixed, makes a run reproducible |
| Evaluation | Location, size, and refresh cadence of the eval set; the passing bar; how regression is judged |
| Guardrails | Input validation and injection blocking, output filtering, what the user sees when something is blocked |
| Tool boundary | The list of tools the agent may call, and each one's permission scope and side effects |
| Context | What is loaded and when, the context budget, the rules for trimming or evicting on overflow |
| Cost | Token budget per request, the hidden cost of retries and self-consistency, behaviour on overrun |
| Observability | The minimum recorded in a trace (input hash, model, tokens, tool calls, judgement outcome) |
| Failure taxonomy | Behaviour for hallucination / tool failure / refusal / timeout, linked to seven-axis C, F, and G |

An acceptance criterion example — written to admit non-determinism:

```yaml
acceptance:
  - given: "eval set v3 (120 cases)"
    when: "run with the model pinned and temperature 0"
    then: "pass rate >= 92%, spread across 3 repeats <= 2 percentage points"
```
