# 04 — Output rules (spec-first, optimised for agent consumption)

## Principles

| # | Principle | Why |
|---|---|---|
| A-1 | `spec/` YAML is the single source of truth. Markdown is derived on request | The same structure in Markdown tables costs far more tokens than YAML, and two copies drift |
| A-2 | Read the index first, then load only the shards needed | An order of magnitude less context than loading everything |
| A-3 | Split files rather than growing them | A large file cannot be queried in part, so every read becomes a full read |
| A-4 | Reference by id instead of copying the same fact | Copies always diverge |
| A-5 | Every item carries a fixed-form, greppable anchor id | Search and back-tracing must work without tooling for neutrality to hold |
| A-6 | File and field names stay tool-neutral | No IDE-, CLI-, or MCP-specific syntax in the spec |

## Where output goes

| Condition | Location |
|---|---|
| A code repository exists | `spec/` at the repository root (default) |
| No code repository | `spec/` in the working output folder |
| A human-readable document was explicitly requested | Derived into `docs/architecture/` (§Derived output) |

Tell the user the choice in one line.

## Tree structure

```
spec/
  STATE.md                session entry front page. derived            — §Session lifecycle
  index.yaml              routing index. read first and written first
  meta.yaml               mode / domain / system boundary / basis
  graph.yaml              ★ the single store of every relation          — §Graph
  feat/<FEAT-id>.yaml     feature attributes plus lattice coverage      — §Features
  req/<group>.yaml        requirement attributes (no relations)
  uc/<UC-id>.yaml         use case plus scenarios (seven-axis results)
  iface/<IF-id>.yaml      external interface plus data contract
  mod/<MOD-id>.yaml       module responsibility, provided/required
  views/features.md       feature matrix. derived                       — §Projections
  views/runtime.yaml      run-time structure (C&C)          — 05 §Runtime
  views/deployment.yaml   nodes, artifacts, communication paths
  views/data.yaml         persistent model, consistency, evolution — 05 §Data
  concepts/<name>.yaml    crosscutting concepts             — 05 §Crosscutting
  decisions/ADR-<n>.yaml  architecture decisions plus rationale — 05 §ADR
  tasks.yaml              units of implementation
  checks.yaml             executable checks for structural constraints
  glossary.yaml           terms, synonyms, forbidden phrasing
  gaps.yaml               TBD / GAP / DRIFT / RISK / unrecovered
```

Do not create a file for something that does not exist. Empty shells only cost tokens.

---

## Graph — the single store of relations

**Node files carry attributes only. Every relation lives in `graph.yaml`.** Writing the same relation
on both nodes guarantees divergence (A-4, X-13).

```yaml
# spec/graph.yaml
edges:
  - [FEAT-001, has_req,        FR-001]
  - [UC-002,   refines,        FR-001]
  - [FR-001,   realized_by,    MOD-AUTH]
  - [MOD-AUTH, exposes,        IF-001]
  - [MOD-AUTH, implemented_in, "src/auth/token.py"]
  - [FR-001,   verified_by,    "tests/test_auth.py::test_login"]
  - [MOD-AUTH, governed_by,    error-handling]
  - [MOD-AUTH, decided_by,     ADR-004]
  - [GAP-003,  blocks,         FR-007]
  - [CONFLICT-001, affects,    FR-012]
```

One relation per line. A single `rg "FR-001" spec/graph.yaml` answers in both directions.

### Node types

| Prefix | Target |
|---|---|
| `FEAT-` | Feature. The unit the user recognises |
| `FR-` `QR-` `IR-` `CR-` | Functional / quality / interface / constraint requirement |
| `UC-` `IF-` `IT-` | Use case / interface / interface item |
| `MOD-` `RC-` `CN-` `SR-` `DS-` | Module / execution unit / connector / shared resource / store |
| `ADR-` `TASK-` `CHK-` `GAP-` `CONFLICT-` | Decision / task / check / gap / conflict |
| (name) | Crosscutting concept |
| (path) | Code and test files. `path` or `path::test_name` |

Numbers are zero-padded to three digits. **Once assigned, an id is never reused or reassigned** —
code anchors would silently point at something else.

### Where each node is defined

Every id an edge names must be defined somewhere (G-20). Definition sites are fixed by type.

| Node | Definition site |
|---|---|
| `FEAT-` | `feat/<id>.yaml` `id` |
| `FR-` `QR-` `IR-` `CR-` | `req/<group>.yaml` `requirements[].id` |
| `UC-` | `uc/<id>.yaml` `id` |
| `IF-` | `iface/<id>.yaml` `id`; `IT-` is `items[].id` in that file |
| `MOD-` | `mod/<id>.yaml` `id` |
| `RC-` `CN-` `SR-` | `views/runtime.yaml` `components[]`, `connectors[]`, `shared_resources[]` |
| `DS-` | `views/data.yaml` `stores[].id` |
| `ADR-` | `decisions/ADR-<n>.yaml` `id` |
| `TASK-` `CHK-` `GAP-` `CONFLICT-` | The item `id` in `tasks.yaml`, `checks.yaml`, `gaps.yaml` |
| Crosscutting concept | `concepts/<name>.yaml` `id` |
| Code and test paths | No definition file. Checked by existence (G-17) |

The types defined inside view files (`RC-` `CN-` `SR-` `DS-`) are easy to miss. An integrity check
must read the views too.

### Body nodes and attachment nodes

This determines what the orphan check (G-20) covers. Without the distinction, checks and gaps all
register as orphans and the gate fails itself.

| Kind | Nodes | Orphan check | Basis |
|---|---|---|---|
| **Body** | `FEAT-` `FR-|QR-|IR-|CR-` `UC-` `IF-` `MOD-` `RC-` `DS-` | **Covered** — no edge means dead spec | The relation vocabulary points at these types |
| **Contained** | `IT-` (inside IF) · `CN-` `SR-` (inside runtime) | Exempt — the parent being in the graph is enough | No relation in the vocabulary points at them |
| **Attachment** | `ADR-` `TASK-` `CHK-` `GAP-` `CONFLICT-` | Exempt — existing in its own file is enough | These are records **about** the system, not the system |

The test is single: **a type is a body node when the vocabulary has an edge pointing at it.**
`persists_to` reaches `DS-` and `runs_on` reaches `RC-`, so both are body nodes. Nothing points at
`IT-`, `CN-`, or `SR-`, so they live only inside their container.

An attachment node still gets an edge when a relation exists. The absence of one is not a defect.
Example: a `CHK-` that verifies graph integrity enforces no particular spec element, so it has no edge.

### `gaps.yaml` items and the graph

| kind | Graph edge | Why |
|---|---|---|
| `TBD`, `GAP` (blocking) | `blocks` to the target | What is blocked must be answerable by traversal |
| `DRIFT` (`CONFLICT-`) | `affects` to the target | The blast radius of a conflict must be traversable |
| `RISK`, `ISSUE`, `unrecovered` | No edge. Linked by `refs` only | These do not block progress |

`refs` is for people and search; it is not traversed.

### Relation vocabulary (fixed; extension requires an ADR)

| Edge | from → to | Meaning |
|---|---|---|
| `has_req` | FEAT → REQ | Requirements composing the feature |
| `refines` | UC → REQ | The use case elaborates the requirement |
| `realized_by` | REQ → MOD | The implementing module |
| `exposes` | MOD → IF | The interface the module provides |
| `runs_on` | MOD → RC | Run-time placement |
| `persists_to` | MOD → DS | Store used |
| `implemented_in` | MOD → path | Code location |
| `verified_by` | REQ → test | The test verifying the acceptance criteria |
| `governed_by` | MOD → concept | The crosscutting concept it follows |
| `decided_by` | MOD/IF → ADR | The decision behind it |
| `drives` | QR → ADR | The quality requirement that forced the decision |
| `depends_on` | MOD→MOD, TASK→TASK | Dependency. **Ordering only, not scheduling** |
| `blocks` | GAP → * | A gap holding progress |
| `affects` | CONFLICT → * | What a conflict touches |
| `constrains` | CR → * | What a constraint binds |
| `enforces` | CHK → rule/gate | The executable check |
| `supersedes` | ADR → ADR | Decision replacement |

### A conflict is a node

A clash between requirements, or between spec and code, is a **graph node**, not a line in
`gaps.yaml`. Only then can "what does this conflict affect" be answered by traversal.

```yaml
# gaps.yaml
gaps:
  - id: CONFLICT-001
    kind: DRIFT
    between: [FR-012, "src/booking/limit.py:34"]
    detail: "required 3s vs code 5s"
    authority_check: "same level — cannot auto-resolve"
    need: "confirm which is correct"
    blocking: true
```

Then leave the edge `[CONFLICT-001, affects, FR-012]`.

---

## Projections (derived)

The graph is strong for traversal and **weak as a reading entry point**. Learning "what features
exist" from 300 edges means reading all of them and grouping. Projections solve that.

| Projection | Question answered | Produced |
|---|---|---|
| `STATE.md` | What is the current state | On graph change |
| `views/features.md` | What features exist | On graph change |
| Impact view | What does changing X affect | Computed per query, not stored |
| Coverage view | What is unfinished | Computed per query |

**A projection is derived. Never edit it. Fix the graph and regenerate.**

`views/features.md`:

```
| FEAT | Feature | Status | Module | Reqs | UC | Code | Tests | L1 | L2 | L4 |
|---|---|---|---|---|---|---|---|---|---|---|
| FEAT-001 | Create booking | done | MOD-BOOKING | 3 | 1 | 2 | 2 | 12/12 | 7/7 | 10/10 |
```

Name, status, and coverage come from `feat/<FEAT-id>.yaml`; the link counts are counted from the
graph. Do not list ids — query the graph for detail (A-4). Both inputs are required to regenerate
this table.

---

## Session lifecycle

For a new session to grasp the whole software, **both an entry and an exit protocol** are needed.
With only an entry protocol there is nothing left by the previous session to enter.

### Entry — `spec/STATE.md`

A front page at a fixed path. Because it is a **file** rather than a harness hook, it behaves the
same under Claude, Codex, and environments with no hooks at all.

```markdown
# SPEC STATE
features: 18 (done 12 / building 4 / planned 2)
requirements: 47 (ready 39 / incomplete 6 / blocked 2)
gaps: 3 (blocking 1)
updated: 2026-07-29

## Reading order
1. spec/index.yaml
2. spec/views/features.md
3. The target feature's node shards plus the matching graph.yaml edges

## Currently blocked
- CONFLICT-001 blocks FR-012 — timeout value needs confirmation
```

Keep it under 40 lines. When a list grows, keep the top items and point at `gaps.yaml` for the rest.

### Exit — update at session end

A session that changed features, requirements, or code updates **the graph, then the affected
projections, then `STATE.md`**, in that order, before it ends. A session that changed nothing writes
nothing.

This is skill discipline, not a hook. It does not alter the harness's SessionEnd behaviour.

### L2 load priority

Do not open everything at once. Open in order of blast radius.

1. The target feature's nodes
2. That node's direct edges
3. The owning module's crosscutting concepts
4. Only then, second-order dependencies

If the budget runs out, stop at that point in the order rather than truncating arbitrarily.

## index.yaml

The first file an agent reads. Keep it under 40 lines.

```yaml
spec_version: 1
generated_from: ["<source>"]
mode: F            # F | R | S | D
domain: SERVICE    # 05 §Domain differences
counts:
  features: {total: 18, done: 12, building: 4, planned: 2}
  requirements: {total: 28, ready: 23, incomplete: 3, blocked: 2}
  use_cases: 9
  interfaces: 6
  modules: 7
  tasks: {total: 31, todo: 31}
  gaps: 7
shards:
  feat: [FEAT-001.yaml, FEAT-002.yaml]
  req: [auth.yaml, dispatch.yaml, audit.yaml]
  uc: [UC-001.yaml, UC-002.yaml]
  iface: [IF-001.yaml]
  mod: [MOD-AUTH.yaml, MOD-CORE.yaml]
  views: [runtime.yaml, deployment.yaml]
  concepts: [error-handling.yaml, logging.yaml]
  decisions: [ADR-001.yaml]
entry_points:
  "what gets built": tasks.yaml
  "why this structure": decisions/
  "what is blocked": gaps.yaml
```

## meta.yaml

```yaml
mode: F
mode_evidence: "requirements document only, no source tree"
domain: SERVICE
domain_evidence: "HTTP handlers, ORM, queue in use"
system_boundary: "<the system boundary in one sentence>"
quality_model: "ISO/IEC 25010:2023"
```

## feat/<FEAT-id>.yaml

The unit of management is the feature. Its **attributes** live here; what it connects to lives in the
graph. Projections (`views/features.md`, `STATE.md`) are regenerated from this file plus the graph,
so without it they cannot be rebuilt.

```yaml
id: FEAT-001
name: "Create booking"
summary: "<one line, from the user's point of view>"
status: done                    # planned | building | done | deprecated
owner_module: MOD-BOOKING       # primary owner; actual allocation is realized_by in the graph
coverage:                       # per-feature aggregate of 00 §Coverage report
  l1: {total: 12, filled: 9, derived: 1, na: 2, tbd: 0}
  l2: {total: 7,  filled: 5, derived: 0, na: 2, tbd: 0}
  l4: {total: 10, filled: 10, derived: 0, na: 0, tbd: 0}
updated: "2026-07-29"
```

`owner_module` is a primary-owner marker, not an allocation relation. Allocation is `realized_by` in
the graph, and where the two disagree the graph wins.

## req/<group>.yaml

```yaml
requirements:
  - id: FR-001
    type: functional            # functional | interface | quality | constraint
    statement: "<refined statement>"
    origin: "<original text or file:line>"
    actor: "<actor>"
    trigger: "<initiating event>"
    preconditions: ["..."]
    postconditions: ["..."]
    acceptance:
      - {given: "...", when: "...", then: "..."}
    data_contract:
      - {name: "...", direction: I, type: "...", format: "...", unit: "...",
         range: "...", nullable: false}
    errors:
      - {condition: "...", behavior: "..."}
    verification: unit          # unit | integration | e2e | measurement | inspection
    authority: feature          # system | platform | feature — precedence on conflict
    status: ready               # ready | incomplete | blocked
    confidence: high            # MODE-R: high | medium | low
    evidence: ["src/auth.py:42"]   # MODE-R only
    assumptions: ["..."]           # when inference was used
```

When `status` is not `ready`, record **only the id** in `gaps.yaml`. Do not copy the content (A-4).

### Authority levels — resolving conflicts

When requirements clash, state the precedence so the user is not asked every time.

| Value | Meaning | Example |
|---|---|---|
| `system` | System-wide rule. Strongest | Security policy, legal and regulatory constraints, safety requirements |
| `platform` | Platform or shared-foundation rule | Authentication scheme, logging convention, data retention |
| `feature` | An individual feature's requirement. Weakest | Screen behaviour, individual business rules |

Resolution rules:
1. Across levels, the higher one wins. Leave the lower as `blocked` with the winning id in its reason.
2. **At the same level, do not resolve automatically.** Record it in `gaps.yaml` as `kind: DRIFT` and ask.
3. When the resolution affects structure, record it as an ADR (05 §ADR).

## uc/<UC-id>.yaml

```yaml
id: UC-002
name: "<verb plus core result>"
actors: {primary: "<actor>", secondary: []}
preconditions:
  - {title: "...", description: "...", on_unmet: "..."}
postconditions:
  - {title: "...", description: "...", on_unmet: "..."}
basic_flow:                     # exactly one
  - {no: 1, description: "..."}   # first step's subject is the actor, second is the system
sweep:                          # all seven axes. never left blank
  A: [{scenario: "...", kind: exceptional, ends: return}]   # kind: optional|exceptional
  B: [{scenario: "...", kind: optional, ends: terminate}]
  C: []
  D: {na: "no device contact"}
  E: []
  F: []
  G: []
```

Relations (`refines`, `realized_by`) go in `graph.yaml`. Do not write them here.

## iface/<IF-id>.yaml

```yaml
id: IF-001
name: "<named from the external entity's point of view>"
role: "<core function>"
spec: "<protocol, format, invocation style>"
version: "1.0"
compatibility: "<backward-compatibility policy, deprecation conditions>"
quality: {performance: "...", availability: "...", reliability: "...", security: "..."}
items:
  - id: IT-001
    name: ElevatorArrived        # noun form. no direction words
    io: O                        # I | O
    kind: event                  # command | data | event
    type: "..."
    format: "..."
    unit: "..."
    range: "..."
    precision: "..."
    tolerance: "..."
```

## mod/<MOD-id>.yaml

```yaml
id: MOD-AUTH
responsibility: "<one reason to change>"   # SRP
provided: [{name: "...", operations: ["..."]}]
stability: {fan_in: 2, fan_out: 1, i: 0.33}
```

Dependencies (`depends_on`), allocation (reverse `realized_by`), code location (`implemented_in`),
applied concepts (`governed_by`), and interfaces (`exposes`) all live in `graph.yaml`. Do not write
them here. `stability` is counted from the graph's `depends_on` edges, so recount it when the graph
changes.

## tasks.yaml

Requirements and design alone do not start an implementation. State the units of work.

```yaml
tasks:
  - id: TASK-001
    goal: "<what works once this is done>"
    touches: ["src/auth/token.py"]
    done_when:
      command: "<verification command>"      # acceptance links are the graph's covers edges
    status: todo                  # todo | doing | done | blocked
```

The owning module (`realized_by`), the requirements covered (via `has_req`), and ordering
(`depends_on`) all live in `graph.yaml` (G-22). Do not add a separate sequence number either.

Task size criteria — split when any one is broken:

| Criterion | Value |
|---|---|
| Completion judgement | `done_when` must be decidable in one go. "Partly done" means it is too big |
| Scope | `touches` does not cross a module boundary |
| Coverage | No more than three requirements attached in the graph |
| Parallelism | Tasks touching the same file are serialised with a `depends_on` edge |

An under-specified task (goal at the level of "implement it", no completion condition) is itself a
defect. The L4 lattice catches it.

## checks.yaml

Record a structural constraint as an executable check, not a sentence. Without one, the constraint
does not hold.

```yaml
checks:
  - id: CHK-001
    rule: "the module dependency graph must have no cycle"      # ADP
    command: "<cycle detection command>"
    on_fail: "record a GAP and stop"
  - id: CHK-002
    rule: "a lower layer must not depend on an upper layer"
    command: "<dependency direction check command>"
```

Which gate a check enforces goes in the graph as an `enforces` edge (G-22).

Name a tool that actually exists in the target repository. If none does, leave
`command: "[TBD: confirm tooling]"` and do not invent one. **A check whose command is `[TBD]` does
not satisfy G-16** — it is named but not executable, so record that constraint in `gaps.yaml`.

## gaps.yaml

```yaml
gaps:
  - id: GAP-001
    kind: TBD          # TBD | GAP | DRIFT | RISK | ISSUE | unrecovered
    refs: [FR-007]     # ids only. never copy content
    need: "<what must be confirmed to close it>"
    blocking: true
```

`RISK` holds architectural risk and technical debt. Record `severity` and `mitigation` with it.

## glossary.yaml

```yaml
terms:
  - term: "call request"
    definition: "..."
    aliases: ["call", "request"]
    forbidden: ["ping"]      # phrasing not to use in output or code
```

## Code anchors and integrity checks

Node types and the relation vocabulary are in §Graph. This section covers only code binding and checks.

**Code binding** — leave comment anchors in implementation **and test** files. Only the comment
syntax differs by language; the form is the same.

```
# @spec FR-001 MOD-AUTH          implementation file
# @spec FR-001                   the test verifying that acceptance criterion
```

Anchors pair with the graph's `implemented_in` and `verified_by` edges. An acceptance criterion
without an anchor is an unverified requirement and returns to ARR-8 incomplete.

Injecting anchors modifies code. Do not do it without the user's approval.

**Integrity checks** — all decidable by text search and simple traversal. No external tooling.

| Check | What a violation means | Action |
|---|---|---|
| Undefined node reference | An edge names a non-existent id | Fix immediately |
| Orphan node | A **body** node appears in no edge | Dead spec. Delete or connect |
| Missing mandatory edge | A REQ without `realized_by`, a FEAT without `has_req` | ARR-7 shortfall |
| Missing verification | `status: ready` with no `verified_by` | Return to ARR-8 incomplete |
| Module cycle | A cycle in `depends_on` | ADP violation. MODE-R may record `ISSUE` |
| Unimplemented | `realized_by` exists but no `implemented_in` | Move to `tasks.yaml` |
| Anchor without spec | A code `@spec` id absent from the graph | Record a `CONFLICT-` and ask |
| Module boundary violation | An anchor's `MOD-` id in a file outside that module's `implemented_in` | Record a `CONFLICT-` |
| Value mismatch | Spec figure vs code constant | Record a `CONFLICT-` |
| Stale projection | `views/features.md` or `STATE.md` differs from a fresh projection | Regenerate |

Never settle which side is correct on your own. In a repository without anchors the anchor-based
checks cannot run; report that plainly and limit the comparison to items with explicit evidence.

## Token budget

When a limit is exceeded, split the shard rather than trimming content.

| File | Limit |
|---|---|
| `STATE.md` | 40 lines |
| `index.yaml` | 40 lines |
| `meta.yaml` | 20 lines |
| `graph.yaml` | No limit. One edge per line, read by partial query |
| `feat/<FEAT-id>.yaml` | 30 lines |
| `req/<group>.yaml` | 12 requirements or 200 lines |
| `uc/<UC-id>.yaml` | 120 lines |
| `mod/<MOD-id>.yaml` | 60 lines |
| `concepts/<name>.yaml` | 60 lines |
| `decisions/ADR-<n>.yaml` | 40 lines |

## Impact analysis (MODE-D / MODE-Q)

Answered by reverse graph traversal.

| Query | Traversal |
|---|---|
| What does changing X affect | Reverse BFS from X over `realized_by⁻¹`, `has_req⁻¹`, `depends_on⁻¹` |
| What requirement is this code | The file's `@spec` anchor → `implemented_in⁻¹` → REQ → `has_req⁻¹` → FEAT |
| Is this feature verified | FEAT → `has_req` → REQ → presence of `verified_by` |
| What is blocked | All `blocks` and `affects` edges |

Increment procedure:

1. Process the new requirements through F1–F6.
2. Build the impact set by the traversal above: features, modules, interfaces, tasks, tests.
3. If an interface changed, update `version` and `compatibility` and add its consumer modules to the
   impact set.
4. Re-judge the `status` of affected items. Anything whose allocation (ARR-7) changed returns to
   `incomplete`.
5. Record conflicts as `CONFLICT-` nodes, leave the `affects` edge, and ask.
6. Update in order: graph, then projections, then `STATE.md`.

**Re-running is not regeneration.** When a `spec/` tree already exists, amend the graph incrementally
and keep the ids. Do not renumber — code anchors would silently point elsewhere.

## Derived output (only on request)

Generate Markdown into `docs/architecture/`. Use these table headers verbatim.

```
ID | Requirement | ARR-1 | ARR-2 | ARR-3 | ARR-4 | ARR-5 | ARR-6 | ARR-7 | ARR-8 | status
ReqID | Type | UC | Scenario | Interface / Item | Module | Acceptance | status
Title | Description | Behaviour when the condition is not met
No | Description
Name | Role | Interface specification | Quality characteristics
Item name | Type (I/O) | Role | Characteristics
```

A derived artifact is a snapshot of its moment. Make corrections in `spec/` and regenerate. Never
edit the derived copy directly.

## Diagrams

Generate text-based diagrams without assuming any tool is installed. Element names must match the
spec's ids and names exactly.

| Target | Notation | Note |
|---|---|---|
| Context model | Mermaid `classDiagram` | Supports `<<system>>` and other stereotypes natively |
| Module dependency | Mermaid `flowchart` | On finding a cycle, annotate that edge with `ISSUE` |
| Sequence | Mermaid `sequenceDiagram` | At least one basic and one representative exceptional flow for major use cases |
| Deployment | Mermaid `flowchart` | Nodes, artifacts, communication paths |
| Use case diagram | PlantUML preferred | **Mermaid does not officially support use case diagrams.** Use PlantUML, or approximate with `flowchart` and say that it is an approximation |

A diagram is derived from the spec. Never create an element that exists only in the diagram.
