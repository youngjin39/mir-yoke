# 03 — Reverse recovery playbook (MODE-R / MODE-S / MODE-D)

## MODE-R in detail

### R1 static survey — map the terrain before reading code

What to collect:

| Target | Content |
|---|---|
| Entry points | main/entry/handler/route/task/ISR/CLI commands/scheduler registrations |
| External boundary | Network calls, file I/O, database access, device access, IPC, environment variables |
| Configuration | config/env/manifest/build files — timeouts, retries, pool sizes, ports |
| Dependencies | Package manifests, link targets, external SDKs |
| Tests | Test names carry intent and are a first-class clue for recovering requirements |
| Document remnants | README, comments, ADRs, issue links |

Prohibited: do not read whole files indiscriminately. Narrow inward from boundaries and entry points.

### Generated files are not recovery material

Recovering requirements from build or codegen output specifies the artifact instead of the source.
Read only canonical files, and exclude generated ones from `implemented_in` anchors as well.

| Signal | Examples |
|---|---|
| Extension or suffix convention | `*.g.dart` `*.freezed.dart` `*_pb2.py` `*.generated.*` `*.min.js` |
| Header marking | `GENERATED`, `DO NOT EDIT`, `@generated` |
| Repository declaration | The target's Profile `generated_paths`, `.gitignore`, build configuration |
| Directory | `build/` `dist/` `node_modules/` `.dart_tool/` `__pycache__/` |

Where a canonical file and its generated pair exist (`model.dart` and `model.g.dart`), take only the
canonical one as a node. If the generation rule itself is a design decision, record it as a
crosscutting concept or an ADR.

### R2 boundary recovery — deriving external entities

Rules:
- Something the code **calls** — this system is the client — the end without the arrow
- The sender of a request the code **receives** — this system is the server — the end with the arrow
- Device access (registers, drivers, ports) — input/output/I-O device
- A standard device a person operates directly (PC, phone) — the entity is the **user**, not the device
- A module wrapping a low-level protocol is identified as a gateway

Attach evidence to every entity: `file path:line number`

### R3 function recovery — deriving use cases

Candidate sources: public API endpoints, CLI commands, event handlers, periodic tasks, state machine
transitions. Merge and split from the user's point of view (01 §5.4).

Caution: one function is not one use case. An internal function is not a use case.

### R4 quality and constraint recovery

Raise the implicit quality requirements embedded in the code into explicit ones.

| Code signal | Raised to |
|---|---|
| Timeout values | Performance efficiency (Time Behaviour) |
| Retry / circuit breaker | Reliability (Fault Tolerance, Recoverability) |
| Pool / buffer / queue sizes | Performance efficiency (Capacity, Resource Utilization) |
| Authentication, encryption, authorisation | Security |
| Periods, deadlines, watchdogs | Performance efficiency plus Reliability (EMBEDDED) |
| Logs, audit trails | Security (Accountability) |
| Version pinning, platform branches | Constraints / Compatibility |

For each item record the current value **and** the basis for judging whether that value is a
requirement or an accident. When it cannot be judged, mark `confidence: low` and attach
`[TBD: confirm intent]`.

### R5 model reconstruction

Extract the module dependency model from the actual import/include relations. When a cycle is found,
record it as `ISSUE` rather than removing it. Reverse recovery records what is; improvement comes
after.

### R6 evidence binding

Attach all three to every recovered item (the same fields as the 04 schema).

| Field | Value |
|---|---|
| `evidence` | `file path:line number` (may be several) |
| `confidence` | `high` (stated in code) / `medium` (inferred) / `low` (circumstantial) |
| `assumptions` | Assumptions used in the inference (omit when none) |

Any item with `confidence: low` is also recorded in `gaps.yaml` as `kind: TBD` so it is visibly
awaiting confirmation.

For a recovered module, link its code location with an `implemented_in` edge in the graph, and with
the user's approval leave `@spec <id>` comment anchors in that code. Anchors are what make later
MODE-S drift detection possible.

### The absolute rule of MODE-R

Never create a requirement because it "seems likely" when the code does not confirm it. Record every
area that could not be recovered in `gaps.yaml` as `kind: unrecovered`.

---

## MODE-S in detail (comparison)

Compare the requirement set REQ against the recovered set IMPL and classify into four quadrants.

| Quadrant | Meaning | Action |
|---|---|---|
| REQ ∩ IMPL | Implemented | Also check the acceptance criteria match |
| REQ − IMPL | Not implemented | Emit as work in `tasks.yaml` |
| IMPL − REQ | Undocumented behaviour | Ask whether it is intended (`gaps.yaml` kind: TBD) |
| Value mismatch | Required 3s vs code 5s | Record as `kind: DRIFT` and ask which is correct |

Never settle either side as correct on your own.

### Anchor-based comparison (works without tooling)

When the code carries `@spec` anchors, the comparison runs on text search alone.

| Check | Method | Verdict |
|---|---|---|
| Allocated but unimplemented | `realized_by` exists but no `implemented_in` anchor | REQ − IMPL |
| Anchor without spec | A code anchor names an id absent from the spec | IMPL − REQ |
| Module boundary violation | An anchor's `MOD-` id appears in a file outside that module's `implemented_in` | Record a `CONFLICT-` |

In a repository without anchors this check cannot run. Report that plainly and restrict the
comparison to items with explicit evidence.

---

## MODE-D in detail (increment)

1. Process the new requirements through the MODE-F pipeline (F1–F6).
2. Follow 04 §Impact analysis for the blast radius and the re-judgement procedure.
3. Record conflicts with existing requirements as `kind: DRIFT` and ask.
