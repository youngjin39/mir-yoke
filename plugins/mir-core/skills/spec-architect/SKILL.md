---
name: spec-architect
description: "Turns requirements or existing code into a machine-readable spec tree under spec/. Finds missing requirements with a four-layer lattice, reports coverage as counts, and links requirements to modules to code as a graph.\n\nTrigger: requirements completeness, clarify requirements, write a spec, generate architecture docs, recover requirements from code, legacy analysis, traceability matrix, spec-driven development, spec-code drift\n\nDeciding the design direction is the design skill's job. This skill turns settled intent into an implementable spec structure.\n\nDo NOT use for: writing or refactoring code, writing tests, CI/CD setup, general project management."
---

# spec-architect

Purpose: start from stated requirements and produce an implementation blueprint that is **complete
and unambiguous**. "Nothing is missing" is proven by the coverage of a four-layer completeness
lattice (00). A completeness claim without counts is not permitted.

The primary consumer of the output is an AI agent, not a person. The `spec/` YAML tree is the single
source of truth; human-readable Markdown is derived only when explicitly requested.

## Contract

| Item | Content |
|---|---|
| Input | Natural-language requirements / a requirements document / an existing source repository / any mix |
| Output | A machine-readable `spec/` tree (index plus shards) — see 04 |
| Guarantee 1 | Nothing missing — the four lattices are traversed exhaustively and coverage is reported as counts. Unresolved cells surface as questions |
| Guarantee 2 | No ambiguity — zero forbidden words, every criterion quantified |
| Guarantee 3 | Implementable — every requirement passes the eight AI-Ready gate items, or its failure is visible in `status` and `gaps.yaml` |
| Binding | Every item carries a greppable anchor id. Code carries `@spec <id>` comments pointing back |
| Neutrality | Files and text search only. No dependency on a particular CLI, IDE, or MCP |

What it does not do: write code, invent requirements, or settle a stakeholder's intent by guessing.

## Use When

Turning requirements into something implementable / recovering architecture from an existing
repository / checking requirements against code / tracing the blast radius of a new requirement /
checking a single requirement sentence for ambiguity or gaps.

## When NOT to Use

| Request | Delegate to |
|---|---|
| Writing, refactoring, or debugging code | `bluebricks` |
| Writing or running tests | `testing` |
| Code review, merge checks | `code-review` |
| Verifying outputs, checking evidence | `verify` |
| Direction still open, alternatives to compare | `design` (return here once settled) |
| UI flows, wireframes | `ui-design` |
| Harness documents and policy | `governance` |

If the deliverable is code, this is the wrong skill. If the deliverable is an implementable spec,
this is the right one.

## Reference routing

Read only what is needed. Do not preload everything.

| Situation | File |
|---|---|
| Running the omission checks (L1 and L4 lattices, coverage report) | [`references/00-completeness.md`](references/00-completeness.md) |
| Requirement classification, refinement, modelling rules | [`references/01-methodology.md`](references/01-methodology.md) |
| Judging a requirement's implementability | [`references/02-ai-ready-gate.md`](references/02-ai-ready-gate.md) |
| MODE-R / MODE-S reverse recovery and comparison | [`references/03-reverse-recovery.md`](references/03-reverse-recovery.md) |
| Output tree, schemas, anchors, token budgets | [`references/04-artifacts.md`](references/04-artifacts.md) |
| Architecture views (runtime, data, crosscutting, ADR) and domain differences | [`references/05-views.md`](references/05-views.md) |
| A single sentence check was requested | 01 §5.2 only |

## A0 INTAKE — mode

State the mode and its basis in one line in the first response.
Example: "MODE-R — a source tree exists but there is no requirements document."

| Condition | Mode | Meaning |
|---|---|---|
| Only a query, an overview, or an impact question | MODE-Q (Query) | Read-only. See §Session entry and exit |
| Requirements only, no code | MODE-F (Forward) | Requirements to spec |
| Code only, no requirements document | MODE-R (Reverse) | Code to recovered spec |
| Both present | MODE-S (Sync) | Comparison and drift analysis |
| An existing spec plus new requirements | MODE-D (Delta) | Increment plus impact analysis |

**If a `spec/` tree already exists, do not regenerate it with MODE-F.** Handle it as an increment
under MODE-D or MODE-S and keep the existing ids. Renumbering makes code anchors point silently at
something else.

## Triage

The lattices and gates are not an entry toll. Apply them in proportion to the change.

| Size | Application |
|---|---|
| Tiny | Skip L1. Check only the axes the change touches, and report coverage for those axes |
| Normal | Full L1–L4, gates, graph update |
| Heavy | Normal plus reverse-recovery evidence binding, and independent review when the impact warrants it |

## A0 INTAKE — domain

State the basis for the judgement. When it cannot be determined, use GENERIC and apply no
domain-specific rules. Do not assert a domain by guessing. Per-domain differences are in
05 §Domain differences.

| Domain | Detection signals |
|---|---|
| EMBEDDED | GPIO, I2C, SPI, UART, CAN, RTOS, ISR, firmware, sensors, actuators, motors, periodic tasks, watchdog, MISRA, hardware registers, C/C++ builds |
| SERVICE | HTTP, REST, gRPC, databases, ORM, queues, caches, containers, k8s, load balancers, auth tokens, microservices |
| APP | UI frameworks, screen transitions, event handlers, local storage, push notifications |
| DATA/ML | Pipelines, training, inference, model artifacts, features, batch jobs, datasets |
| AI_SYSTEM | LLM APIs, prompt templates, embeddings, vector stores, agent loops, tool calls, context assembly, eval sets, guardrails, token cost |
| HYBRID | Two or more of the above coexist meaningfully |

## Pipeline

The step order is fixed. Do not enter a later step without the earlier output. If only one step is
requested, run that step but reconstruct the prior output from the input first and then apply that
step's gate.

```
A0 INTAKE   Collect input; determine mode, domain, size; state the system boundary in one sentence
F0 INTENT   If intent is unsettled, run the design skill's Intent Extraction.
            If the input is settled (an approved design document, an existing spec, an explicit
            instruction), skip it and record that it was skipped.

MODE-F                          MODE-R
F1 Atomise                      R1 Static survey
F2 Classify                     R2 Boundary recovery
F3 Refine for clarity           R3 Function recovery
F4 Elicit omissions  <- L1+L3   R4 Quality and constraint recovery
F5 Model                        R5 Model reconstruction
F6 Scenario completeness <- L2  R6 Evidence binding

Convergence
C1 GATE      Judge the eight ARR items per requirement
C2 Views     module / runtime / deployment / data / concepts            (05)
C3 Design completeness <- L4                                            (00)
C4 Binding   requirement <-> UC <-> interface <-> module <-> acceptance <-> code and test anchors
C5 Output    spec/ tree plus index.yaml                                 (04)
C6 Tasks     tasks.yaml — units of implementation                       (04)
C7 Verify    Gates plus the four-layer coverage report; shortfalls to gaps.yaml   (00)
```

L2 (the seven axes) needs use cases to exist. Do not run it before modelling (F5).

| Step | Rule |
|---|---|
| F1 | Split sentences carrying several meanings. Conjunctions and multiple verbs are the signal. An atom is one verifiable statement. Preserve the original; keep the refined form in a separate field |
| F2 / F3 | 01 §5.1 / §5.2 |
| F4 | 00 §L1 (missing functionality itself) plus 01 §6.1 (the nine quality characteristics) |
| F5 | 01 §5.3, §5.4, §5.6, §5.7 |
| F6 | 00 §L2 then 01 §5.5 (seven axes) plus 01 §6.2–6.3 (QA scenarios, constraints) |
| R1–R6 | 03 in full |
| MODE-S | 03 §Four-quadrant comparison plus `@spec` anchor drift |
| MODE-D | 04 §Impact analysis (reverse graph traversal) |

## The completeness lattice — the backbone of this skill

Each layer catches a different class of omission. One layer does not substitute for another. Rules
and judgements are in 00.

| Layer | Omission caught | When |
|---|---|---|
| L1 elicitation | The requirement or feature **itself** is absent (entity x lifecycle, actor x permission, state x event, forward vs reverse, 0/1/N boundaries, operational functions, time, data lifetime) | F4 |
| L2 scenario | Paths **inside** a use case (seven axes) | F6 |
| L3 quality | Non-functional requirements (ISO/IEC 25010:2023, nine characteristics) | F4 |
| L4 implementation | Holes in the blueprint itself | C3 |

What the lattice produces is **questions, not requirements**. Filling a blank by guessing violates
X-1. Every cell closes as `filled` / `derived` plus its basis / `na` plus a reason / `tbd` plus a
question.
**Attempt derivation before asking.** If the answer follows from existing requirements, code, or
concepts, close it as `derived` and record the basis. Question count is not a quality metric
(00 §derived).

Do not report completeness while unresolved cells remain. Report the four-layer coverage as counts
(00 §Coverage report).

## AI-Ready Gate

A requirement is `status: ready` only when all eight items hold. Full criteria are in 02.

| ID | Item | Criterion |
|---|---|---|
| ARR-1 | Identity | Has a unique id, linked to its origin (original text, stakeholder, or code location) |
| ARR-2 | Singularity | States exactly one thing |
| ARR-3 | Unambiguity | No forbidden words; the criterion is quantified |
| ARR-4 | Acceptance | At least one verifiable criterion in given/when/then form |
| ARR-5 | Data contract | Every input and output item has a name, direction, type, format, unit, and valid range |
| ARR-6 | Exceptions | Behaviour on failure, invalid input, timeout, and resource exhaustion is stated |
| ARR-7 | Allocation | A responsible module is named (or the id of one to be created) |
| ARR-8 | Verification | The means of checking is named (test kind or measurement method) |

`status`: `ready` / `incomplete` / `blocked`. Always report the pass rate as counts, for example
"ready 23 / incomplete 5 / blocked 2".

## L2 — the seven-axis scenario lattice

Give every use case exactly one basic scenario, then apply all seven axes to each step to derive
alternative scenarios. An axis that does not apply is closed as `n/a` plus a reason. No axis is left
blank. Detail is in 01 §5.5.

| Axis | Check |
|---|---|
| A. Input validity | Invalid / out of range / malformed / absent |
| B. Resource availability | No target / insufficient / occupied / over limit |
| C. External response | Rejection / error code / no response (timeout) / disconnection |
| D. Device state | Not operating / stuck / faulty / consumable exhausted |
| E. User choice | Cancel / abort / retry / choose another |
| F. Time | Longer than expected / earlier than expected / duplicated |
| G. Permission and policy | Authentication failure / not authorised / policy violation |

## Output rules (summary; full text in 04)

- The default output is a `spec/` tree. **All relations live in `spec/graph.yaml`; node files carry
  attributes only.** Never write the same relation in two places.
- Fixed anchor ids: `FEAT-` `FR-` `QR-` `IR-` `CR-` `UC-` `IF-` `IT-` `MOD-` `RC-` `DS-` `ADR-`
  `CN-` `SR-` `TASK-` `CHK-` `GAP-` `CONFLICT-`, zero-padded to three digits. **Never reuse or
  reassign an id.**
- The relation vocabulary is fixed (04 §Graph). No ad-hoc additions; extend it through an ADR.
- Leave `@spec <id>` comments in code and tests so the graph reaches the code. Injecting anchors
  modifies code, so do it only after the user approves.
- The feature matrix (`views/features.md`) and `STATE.md` are **projections of the graph**. Never
  edit them directly; fix the graph and regenerate. The same holds for derived Markdown.
- Repeated records go in YAML; only small decision tables go in Markdown tables.
- Tell the user in one line where the output was placed.

## Session entry and exit

**Entry** — a new session reads in this order. Do not load everything.

| Order | Read | Yields |
|---|---|---|
| 1 | `spec/STATE.md` | Feature counts, status, what is blocked, the reading order |
| 2 | `spec/index.yaml` plus `spec/views/features.md` | The full feature list and its links |
| 3 | The target feature's node shards plus the matching `graph.yaml` edges | Detail and blast radius |

Open step 3 in order of blast radius: the target node, then its direct edges, then its module's
crosscutting concepts, then second-order dependencies. If the budget runs out, stop at that point in
the order rather than truncating arbitrarily.

**Exit** — a session that changed features, requirements, or code updates `graph.yaml`, then the
affected projections, then `STATE.md`, before it ends. A session that changed nothing writes nothing.

**MODE-Q queries** are answered by graph traversal (04 §Impact analysis).

## Verification gates

Apply on every run. Record every shortfall in `gaps.yaml` as `GAP-nn` and tell the user. After three
consecutive failures, stop and return the additional information needed.

| ID | Judgement |
|---|---|
| G-1 | Every requirement is classified into one of the four types. Zero unclassified |
| G-2 | Zero forbidden words in **output fields** such as refined statements and acceptance criteria. The preserved original (`origin`) is out of scope |
| G-3 | External entity set = actor set minus {Timer, Gateway}. Gateway and Timer are out-of-scope actors |
| G-4 | Every input and output item in a flow of events exists in the external interface items. An unused item is not a violation; record an `n/a` reason |
| G-5 | Every use case has exactly one basic scenario |
| G-6 | Every use case shows all seven axes applied (including `n/a` plus a reason) |
| G-7 | Every scenario records preconditions, postconditions, and the behaviour when they do not hold |
| G-8 | All nine ISO 25010:2023 characteristics judged (required, or `n/a` plus a reason) |
| G-9 | Every quality requirement's response measure is quantified and carries a unit |
| G-10 | Every use case is allocated to at least one module |
| G-11 | No cycle in the module dependency graph (MODE-R may record one as `ISSUE`) |
| G-12 | Every requirement belongs to at least one feature (`has_req`). Zero orphaned requirements |
| G-13 | The AI-Ready gate result is reported with summary counts |
| G-14 | In MODE-R, every recovered item carries `evidence` and `confidence` |
| G-15 | `index.yaml` matches the actual shard list and counts |
| G-16 | Every structural constraint has a `checks.yaml` entry whose `command` is not `[TBD]`. If it is, record it in `gaps.yaml` |
| G-17 | Where an allocated module has code, it is bound by `@spec` anchors (MODE-R/S/D) |
| G-18 | Four-layer coverage is reported as counts, and every `tbd` cell is recorded in `gaps.yaml` |
| G-19 | Requirement conflicts are resolved by authority level or exposed as a `CONFLICT-` node |
| G-20 | Graph integrity: zero undefined references, zero orphaned **body** nodes, zero missing mandatory edges (04 §Body and attachment) |
| G-21 | `STATE.md` and `views/features.md` match a fresh projection of the graph |
| G-22 | No relation fields in node files. Relations exist only in `graph.yaml` |

## Failure handling

| Situation | Action |
|---|---|
| Read failure | Report the failing path verbatim and separate that area as `unrecovered`. Do not fill it by guessing |
| Insufficient information | `[TBD: needs confirmation - <what>]` plus `status: incomplete`. Record the id in `gaps.yaml` |
| Conflict | Do not settle either side. Mark it `DRIFT` and ask |
| Gate failure | Expose every `GAP-nn`. After three consecutive failures, stop and return the list of information needed |
| Mode undeterminable | Ask once what kind of input this is. In a remote channel, ask with a numbered list |
| Output tree bloating | When a 04 §Token budget limit is exceeded, split the shard. Do not grow the file |

## Guardrails

- X-1 Never invent a requirement, figure, stakeholder, or interface name. Leave what is unsettled as
  `[TBD: needs confirmation - <what>]` and expose it in the output.
- X-2 In MODE-R, never create a requirement that the code does not confirm.
- X-3 During the requirements stage, do not state design decisions such as modules, components,
  classes, or database schemas.
- X-4 Never quietly edit the user's original text. Preserve it and put the refined form in a
  separate field.
- X-5 Never conceal a gate failure. Do not report it as PASS.
- X-6 Do not draw the system's internal components in a context model.
- X-7 Do not decompose use cases from a developer's point of view.
- X-8 Do not draw bidirectional arrows or undirected associations.
- X-9 Do not write only the basic scenario and omit the alternatives.
- X-10 Do not produce a quality requirement without a quantified basis.
- X-11 Do not report completion without confirming that the files were actually created.
- X-12 Do not put internal paths, tool names, or session identifiers in the output.
- X-13 Never copy the same fact into two files. Reference by id. Relations go only in `graph.yaml`.
- X-14 Do not put tool- or platform-specific syntax or paths in the spec.
- X-15 Never reuse or renumber an id that has already been assigned.
- X-16 Never edit a projection directly (`STATE.md`, `views/*`, derived Markdown).
- X-17 Do not redefine intent extraction or the questioning protocol here. The `design` skill owns them.
- No unapproved transmission: do not send output to an external repository, a remote channel, or an
  external service.
- Do not modify code files. Injecting `@spec` anchors happens only as a separate, user-approved request.
