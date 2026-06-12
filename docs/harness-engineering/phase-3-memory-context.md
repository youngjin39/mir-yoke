---
phase: 3
title: Memory & Context
status: consolidated-v1
depends_on: phase-1-start-harness
---

# Phase 3 — Memory & Context

> **Purpose**: Bind memory, documents, and reading order to a single source of truth (SoT), and inject only the relevant fragments into each prompt.

## 0.5 Design Goals (R9 anchor)

> This phase's connection to the [3-axis fleet goals](applications/fleet-catalog.md). When adding a new phase or cherry-picking for a family, the `design` skill (R9-T11) requires `design_goals` as a mandatory input.

**3-axis contribution**:
- **Axis I (your-harness hardening)**: 8-layer context model + memory_entry schema + cache stability
- **Axis II (public template sync)**: template memory_entry schema identical (SQLite store + sliding window N table)
- **Axis III (fleet central governance / back-propagation)**: family memory lifecycle monitoring + cross-family memory bleed prevention

**Inter-phase contract**:
- **Input** (consumes): phase-1 (required_reads + task_subtype) + phase-2 (memory path hook)
- **Output** (provides): injected context + memory_entry mutate (status/valid_until) → phase-4 task_state.memory_refs

## 1. Source of Truth Separation

| Domain | Role | Principle |
|---|---|---|
| Global Memory DB | Global facts and recurring rules | Canonical store for global facts |
| Personal Memory | Personal preferences and progress state | Canonical store for personalized info |
| `memory-map.md` | Location and selection rule guide | **map ≠ territory** |
| `docs/` | Design, rationale, and decision records | Must not substitute for memory |
| CLAUDE.md / AGENTS.md | Operational rules | Paired with code enforcement |

If `memory-map.md` carries fact summaries, that is contamination. It announces locations; the full content lives in the SoT.

## 2. 8-Layer Context Model

Claude Code context loading priority (lower in the list = higher priority).

1. System prompt
2. Tool definitions
3. Global CLAUDE.md (`~/.claude/CLAUDE.md`)
4. Project CLAUDE.md (repo root)
5. `CLAUDE.local.md` (gitignored, personal override)
6. Subdirectory CLAUDE.md (`@import` or auto-loaded)
7. Conversation history
8. User message

Which layer holds operational rules determines whether enforcement is possible.

## 3. Selective Injection Rules

### Upfront injection
- Current goal
- Danger zones and prohibitions
- Recent decisions (`docs/decisions/` active items)
- Required verification procedures

### On-demand injection
- Long logs
- Related design documents
- Task-specific prior history
- External reference documents

### Absolute prohibitions
- Full memory dump
- Replicating the same fact across multiple locations (map + global + personal simultaneously)
- Co-injecting location guides and full content in excess

### 3-1. Same-`id` Multi-SoT Duplication Prevention (R7-B-I4)

[`memory_entry.schema.json`](../templates/_schema/memory_entry.schema.json) requires that when the same `id` exists across different `sot` values (global / personal / project), the `body` must not be duplicated (schema description), but this cannot be enforced at the schema level. Therefore it is an operational guide obligation.

- **At insert time**: `add_entry()` in `src/mir/core/engine/memory/store.py` searches for the same `id` in other SoTs → rejects if body similarity (Levenshtein < 10% or first 200-char hash match) (Phase 2 implementation)
- **Monthly cadence**: run cross-SoT body duplication detector during memory diet cadence (`fleet_observe/measure/memory.py` new axis)
- **Manual verification**: user calls `/memory-audit` skill → full cross-SoT reference report

This §3-1 is the cross-SoT application of the `feedback_no_duplicate_modules` memory. Multiple locations for the same fact cause stale decisions.

## 4. Memory Lifetime Fields

Each memory entry has the following fields.

```yaml
memory_entry:
  id: <slug>                         # kebab/snake-case (not ULID — human-readable identifier)
  type: user | feedback | project | reference | incident   # R4: incident type added
  body: <content>
  status: active | deprecated | superseded | critical | expired   # R4: critical (GC-exempt), expired (past valid_until)
  superseded_by: <other_id>          # required if status == superseded
  valid_until: <date>                # time-bound memory; auto-expires when date passes
  tags: [<string>]
  owner: <user | agent | "shared">
  sot: global | personal | project
  created: <date>
  updated: <date>
  linked: [<other_id>]
```

Full definition: [`docs/templates/_schema/memory_entry.schema.json`](../templates/_schema/memory_entry.schema.json) (R4). This YAML is a summary.

Without lifetime fields, memory lives forever. Immortal memory produces stale decisions. `status: critical` is the GC-exempt signal for [[phase-8-garbage-collection]].

### 4-1. `valid_until` Auto GC Trigger (R7-B-W5)

Trigger definition for transitioning expired `valid_until` entries to `status: expired`.

| Trigger | Timing | Action |
|---|---|---|
| **Session start hook** | Immediately after each Claude/Codex session start | Check all entries' `valid_until`; past entries → `status: expired`. One batch per session. |
| **Pre-edit hook (memory path)** | Immediately before memory entry read/write | Check that entry's `valid_until`. If past: expired warning on read, update obligation on write. |
| **Daily cron** (`.claude/hooks/memory-gc-daily.sh`, future) | Once per day at UTC 00:00 | Full entry batch sweep + advisory log generation. |
| **Manual `/memory-gc` skill** | Explicit user invocation | Immediate sweep + report output. |

**Connection to Phase 8 §6**: This §4-1 handles **auto-transition** (expired status marking); [[phase-8-garbage-collection]] §6 handles **physical deletion/archiving** (cleanup of expired entries). Two-stage separation — remain in expired state for 1 week, then GC archives or deletes.

**Current implementation status**: All 4 triggers in this §4-1 are **not implemented** (hook files absent). `valid_until` code absent in `src/mir/core/engine/memory/store.py`. Planned for Phase 2 stage ([applications/feature-matrix.md §8](applications/feature-matrix.md); ~6h estimate).

## 5. Duplication and Contamination Signals

- The same fact repeated in slightly different phrasing
- Stale description conflicting with current state
- Map document carrying fact summaries
- Model unable to distinguish location guide from full content
- Entries past `valid_until` continuing to be injected

When contamination signals appear → recover via [[phase-8-garbage-collection]] cadence cleanup.

## 6. Cache Stability

Rules to preserve prompt cache hit rate.

- Do not modify CLAUDE.md mid-session (defer to the next session if needed)
- System prompt, tool definitions, and reading order are fixed for the session duration
- Avoid cache-busting patterns (re-reading the same file after read, immediate re-call of large tool outputs)

## 7. `/compact` Threshold

When context grows large during a session, compress with `/compact`.

| Threshold | Action |
|---|---|
| Context at 30–40% | `/compact` recommended (proactive) |
| Approaching 200k tokens | `/compact` strongly recommended |
| After compression | Re-apply selective injection rules from §3 above |

`/compact` reduces only conversation history, not the SoT.

## 8. Sliding Window Prompt

Assemble prompts with a sliding window to prevent infinite accumulation in long sessions.

- Retain only the last N turns (N values per task type — table in this §8)
- Prior turns: summary only (decision log format)
- Key decisions: migrate to memory SoT

### 8-1. N Values by Task Type (R7-B-W4, R9 correction)

Previously "N = decided per task type" with no defined owner, timing, or concrete values. The following table is the source of truth.

**Terminology SoT (R9 correction)**: `task_subtype` in this table is a sub-classification of the 4-way `task_type` (`code_execution|research_planning|review|ops`) from [phase-1 §3](phase-1-start-harness.md) — an auxiliary enum for sliding window N lookup only. Mapping between the two enums:

- `code` / `autonomous_loop` → `task_type=code_execution`
- `design` / `audit` / `chat` / `clarify` → `task_type=research_planning`
- `review` → `task_type=review`
- `incident_response` → `task_type=ops`

| task_subtype | N (turns) | Rationale |
|---|---|---|
| `code` (code writing/modification) | 30 | TDD cycle's read/edit/test/verify 4 tool calls = 3–4 calls per turn → maintain 7–8 cycles |
| `audit` / `review` | 20 | finding accumulation + R1~Rn cross-reference needed, but lighter than code |
| `design` ([design-process.md](applications/design-process.md) §3 5-step) | 40 | 5-step + 2–3 iterations + sub-agent result integration needed; keep long |
| `chat` / `clarify` | 10 | Short decision-making; migrate decisions to memory immediately |
| `incident_response` ([incident-response.md](applications/incident-response.md)) | 50 | Must track all tool calls across 4 phases: CONTAIN→ERADICATE→RECOVER→POSTMORTEM |
| `autonomous_loop` ([autonomous-execution.md](applications/autonomous-execution.md)) | 25 | Maintain autonomous reply turns within retry_budget cycle; migrate to memory when budget exhausted |

**N decision owner**: start-harness looks up this table when classifying task_type + task_subtype and records the result in `task_state.sliding_window_n` field (to be introduced in the next task_state.schema.json update).

**N decision timing**: Decided once at task start. Changeable during work — dynamic adjustment within ±25% range based on tool call count / cache hit rate monitoring results.

**On N exceeded**: Oldest turns converted to summary (1-line decision log). Decisions and artifacts from converted turns migrated to memory SoT ([phase-8 §6 memory lifetime cleanup](phase-8-garbage-collection.md) cadence alignment).

## 9. CLAUDE.md Authoring Principles

### 4 Principles
1. **Short** — 100 lines recommended (200 lines is the limit; split beyond that)
2. **Only what doesn't change** — things that change go into code and tests
3. **Compass** — what is where, what must not be done
4. **Decided values** — no items still under discussion

### High-ROI Workflow
1. Failure occurs
2. Extract root cause as a one-line rule
3. Add CLAUDE.md candidate (`#` shorthand memo)
4. After 1 week of validation, promote to permanent rule

### Anti-patterns
- Encyclopedification
- Publishing undecided items
- Repeating the same content
- Copy-pasting external reference full text

## 10. `@import` Split

When CLAUDE.md exceeds 80–100 lines → split with `@import`.

```markdown
@import .claude/rules/architecture.md
@import .claude/rules/codex-handoff.md
```

Saved as `AGENTS.md`, Codex auto-loads the same file. (your-harness `AGENTS.md` ↔ `CLAUDE.md` auto-sync)

## 11. Memory Update Cadence

- Immediately after each decision — new ADR in `docs/decisions/`
- On each phase completion — handoff note
- Once monthly — `/revise-claude-md` or `/claude-md-improver` for diet
- Once monthly — memory lifetime check (cleanup of entries past `valid_until`)

## 12. Application State

| Item | Status | Location |
|---|---|---|
| SoT separation | **partial land** (R6 correction) | global wiki + memory-map.md landed. `memory_entry.sot = "personal"` schema definition landed; `src/mir/core/engine/memory/store.py` personal SoT code path absent — resolved when Phase 3 step 3-1 is applied |
| 8-layer model | land (automatic) | Claude Code native feature |
| Selective injection rules | land | `session-start.sh` + `scripts/build_session_upfront_context.py` auto-inject 4 upfront types (goal / danger / decisions / verification) |
| Memory lifetime fields | land | `memory_entry.schema.json` + `store.py` lifetime/GC path landed; `recall_for_task_state()` provides sliding_window_n wire-up point |
| Cache Stability | land | CLAUDE.md static + cache monitoring |
| `/compact` 30–40% threshold | land (advisory) | `tools/fleet_observe/measure/context.py` emits estimated token facts + recommend/urgent booleans |
| Sliding Window Prompt | land (policy + retrieval wire-up) | `task_state.sliding_window_n` schema + `store.recall_recent()` / `recall_for_task_state()` fix retrieval window; long history separated from `/compact` advisory |
| CLAUDE.md 4 principles | land | This repo's CLAUDE.md ~80 lines |
| `@import` split | partial land | your-harness is a single file |
| Monthly cadence | advisory | reminder only |

**Remaining note**: full prompt-frame assembler (`PrefixBuilder.assemble`) is a separate cache-layer implementation task. However, the Phase 3 exit criterion items — SoT separation, 4-type upfront auto-injection, sliding-window retrieval policy, `/compact` advisory — are satisfied by the current implementation.

## 13. Exit Criterion

memory-map.md / global / personal SoT separation complete; CLAUDE.md ≤100 lines recommended (≤200 limit); on new task entry, 4 upfront injection types (current goal / danger zones / recent decisions / required verification) confirmed auto-injected.

**R4 addition (Phase 8 dependency resolution)**: Memory lifetime fields (`status` / `superseded_by` / `valid_until`) schema definition ([`memory_entry.schema.json`](../templates/_schema/memory_entry.schema.json)) and code store application (`src/mir/core/engine/memory/store.py`) are in landed state. The remaining exit criterion is connecting this path to phase-level verification evidence and the sliding-window policy.

## 14. Next Steps

Proceed to [Phase 4 — State Machine](phase-4-state-machine.md).
