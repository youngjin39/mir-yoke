---
phase: 3
title: Memory & Context
status: consolidated-v1
depends_on: phase-1-start-harness
---

# Phase 3 -- Memory & Context

> **Purpose**: Bind memory, documentation, and reading order to a single source of truth (SoT), and inject only relevant fragments into the prompt.

## 0.5 Design Goals (R9 anchor)

**3-axis contribution**:
- **Axis I (self-harness hardening)**: 8-layer context model + memory_entry schema + cache stability
- **Axis II (public template sync)**: template memory_entry schema identical (SQLite store + sliding window N table)
- **Axis III (fleet central management)**: family memory lifecycle monitoring + cross-family memory bleed prevention

**Inter-phase contract**:
- **Input** (consumes): phase-1 (required_reads + task_subtype) + phase-2 (memory path hook)
- **Output** (provides): injected context + memory_entry mutation (status/valid_until) -> phase-4 task_state.memory_refs

## 1. Source-of-Truth Separation

| Domain | Role | Principle |
|---|---|---|
| Global Memory DB | Global facts and recurring rules | Canonical store for global facts |
| Personal Memory | Personal preferences and progress state | Canonical store for personal info |
| `memory-map.md` | Location and selection rule guide | **Map is not territory** |
| `docs/` | Design rationale and decision records | Must not substitute for memory |
| CLAUDE.md / AGENTS.md | Operating rules | Paired with code enforcement |

If `memory-map.md` holds fact summaries, it is contaminated. It must only point to locations; body content stays in the SoT.

## 2. 8-Layer Context Model

Claude Code context loading priority (lower = higher priority).

1. System prompt
2. Tool definitions
3. Global CLAUDE.md (`~/.claude/CLAUDE.md`)
4. Project CLAUDE.md (repo root)
5. `CLAUDE.local.md` (gitignored, personal override)
6. Subdirectory CLAUDE.md (`@import` or auto-load)
7. Conversation history
8. User message

Which layer holds operating rules determines whether enforcement is possible.

## 3. Selective Injection Rules

### Upfront injection
- Current goal
- Danger zones and prohibitions
- Recent decisions (active entries in `docs/decisions/`)
- Required verification procedures

### On-demand injection
- Long logs
- Relevant design documents
- Task-specific historical records
- External reference documents

### Absolute prohibitions
- Dumping entire memory into context
- Replicating the same fact in multiple locations (map + global + personal simultaneously)
- Injecting both a location guide and the full original text together

### 3-1. Cross-SoT deduplication for same `id` (added in R7-B-I4)

The `memory_entry` schema requires that entries sharing the same `id` across different `sot` values (global / personal / project) do not duplicate `body` content. Since this cannot be enforced at the schema level, it is an operational requirement.

- **At insert time**: `add_entry()` searches for existing entries with the same `id` in other SoTs; if body similarity exceeds threshold (Levenshtein < 10% or first-200-char hash matches), the insert is rejected.
- **Monthly cadence**: During memory diet cadence, run cross-SoT body duplication detector.
- **Manual audit**: User invokes `/memory-audit` skill for a full cross-SoT reference report.

## 4. Memory Lifetime Fields

Each memory entry carries the following fields.

```yaml
memory_entry:
  id: <slug>                         # kebab/snake-case, human-readable identifier
  type: user | feedback | project | reference | incident
  body: <content>
  status: active | deprecated | superseded | critical | expired
  superseded_by: <other_id>          # required if status == superseded
  valid_until: <date>                # optional; expires automatically
  tags: [<string>]
  owner: <user | agent | "shared">
  sot: global | personal | project
  created: <date>
  updated: <date>
  linked: [<other_id>]
```

Full definition in `docs/templates/_schema/memory_entry.schema.json`. The YAML above is a summary.

Without lifetime fields, memory lives forever. Eternal memory produces stale decisions. `status: critical` is a GC-exempt signal for phase-8.

### 4-1. `valid_until` automatic GC trigger (added in R7-B-W5)

Defines when entries past their `valid_until` are transitioned to `status: expired`.

| Trigger | When | Action |
|---|---|---|
| **Session start hook** | Immediately after each Claude/Codex session start | Checks `valid_until` for all entries; expired ones -> `status: expired`. Once per session. |
| **Pre-edit hook (memory path)** | Before reading/writing a memory entry | Checks that entry's `valid_until`. If expired: warn on read, require update on write. |
| **Daily cron** | UTC 00:00 daily | Full batch sweep + advisory log generation. |
| **Manual `/memory-gc` skill** | User explicit invocation | Immediate sweep + report output. |

**Phase 8 connection**: This section handles **automatic transition** (marking status=expired); phase-8 handles **physical deletion/archiving** (purging expired entries). The two stages are separated -- entries remain in expired state for 1 week before GC archives or deletes them.

**Current implementation**: All 4 triggers above are **not yet implemented**. Planned for introduction in P2 phase of the feature matrix.

## 5. Contamination Signals

- The same fact repeated in slightly different wording
- Conflict between an outdated description and current state
- A map document that also holds fact summaries
- The model cannot distinguish location guides from original content
- Entries past `valid_until` continuing to be injected

Contamination detected -> use phase-8 garbage collection cadence to recover.

## 6. Cache Stability

Rules to preserve prompt cache hit rate.

- Do not modify CLAUDE.md mid-session (defer to next session)
- Keep system prompt, tool definitions, and reading order fixed for the duration of a session
- Avoid cache-invalidating patterns (re-reading same file, immediately re-calling large tool output)

## 7. `/compact` Criteria

When context grows too large during a session, compress with `/compact`.

| Threshold | Action |
|---|---|
| Context 30-40% full | `/compact` recommended (proactive) |
| Near 200k tokens | `/compact` strongly recommended |
| After compaction | Re-apply selective injection rules (section 3) |

`/compact` reduces only conversation history. It does not touch SoTs.

## 8. Sliding Window Prompt

For long sessions, assemble prompts using a sliding window to prevent unlimited accumulation.

- Keep only the most recent N turns (N value by task type -- see table below)
- Summarize earlier turns as decision-log one-liners
- Migrate key decisions to memory SoT

### 8-1. N value by task subtype (added in R7-B-W4, corrected in R9)

The `task_subtype` in this table is a sub-classification of phase-1's 4-way `task_type` (`code_execution|research_planning|review|ops`) used exclusively for sliding window N lookup.

Mapping:
- `code` / `autonomous_loop` -> `task_type=code_execution`
- `design` / `audit` / `chat` / `clarify` -> `task_type=research_planning`
- `review` -> `task_type=review`
- `incident_response` -> `task_type=ops`

| task_subtype | N (turns) | Reason |
|---|---|---|
| `code` (writing/editing code) | 30 | TDD cycle has 3-4 tool calls per turn; maintains 7-8 cycles |
| `audit` / `review` | 20 | Needs finding accumulation + cross-reference; lighter than code |
| `design` (5-step design process) | 40 | 5 steps + 2-3 iterations + subagent result integration |
| `chat` / `clarify` | 10 | Short decisions; migrate to memory immediately |
| `incident_response` | 50 | Must trace all tool calls across CONTAIN->ERADICATE->RECOVER->POSTMORTEM |
| `autonomous_loop` | 25 | Maintains auto-reply turns within retry budget; migrate on budget exhaustion |

**N determination**: start-harness classifies task_type + task_subtype and looks up this table, recording the result in `task_state.sliding_window_n`.

**When N is exceeded**: Oldest turns are converted to one-line decision-log summaries. Decisions and artifacts from converted turns are migrated to memory SoT.

## 9. CLAUDE.md Writing Principles

### 4 Principles
1. **Short** -- 100 lines recommended (200 is the limit; split beyond that)
2. **Only what does not change** -- changing items belong in code and tests
3. **Compass** -- what exists where, and what must not be done
4. **Decision values** -- do not include items under active discussion

### High-ROI workflow
1. Failure occurs
2. Extract the cause as a one-line rule
3. Add as a CLAUDE.md candidate (draft comment)
4. Promote to permanent rule after 1 week of validation

### Anti-patterns
- Encyclopedia mode
- Including unresolved items
- Repeating the same content
- Copy-pasting full external source material

## 10. `@import` Splitting

When CLAUDE.md exceeds 80-100 lines, split with `@import`.

```markdown
@import .claude/rules/architecture.md
@import .claude/rules/codex-handoff.md
```

Saving as `AGENTS.md` causes Codex to auto-load the same file.

## 11. Memory Update Cadence

- After each decision -- new ADR in `docs/decisions/`
- At each phase completion -- handoff note
- Monthly -- run `/revise-claude-md` or `/claude-md-improver` for diet
- Monthly -- check memory lifetimes (purge entries past `valid_until`)

## 12. Application Status

| Item | Status | Location |
|---|---|---|
| SoT separation | partial | Global wiki + memory-map.md landed; personal SoT code path pending |
| 8-Layer model | landed (automatic) | Claude Code built-in feature |
| Selective injection rules | landed | `session-start.sh` + `scripts/build_session_upfront_context.py` auto-injects 4 upfront items |
| Memory lifetime fields | landed | `memory_entry.schema.json` + `store.py` lifetime/GC paths landed |
| Cache stability | landed | CLAUDE.md static + cache monitoring |
| `/compact` 30-40% threshold | landed (advisory) | `tools/fleet_observe/measure/context.py` emits estimated token facts + recommend/urgent booleans |
| Sliding window prompt | landed (policy + retrieval wire-up) | `task_state.sliding_window_n` schema + `store.recall_recent()` / `recall_for_task_state()` |
| CLAUDE.md 4 principles | landed | This repo's CLAUDE.md ~80 lines |
| `@import` splitting | partial | Self-harness uses single file |
| Monthly cadence | advisory | Reminder only |

## 13. Exit Criterion

memory-map.md / global / personal SoT separation complete. CLAUDE.md recommended under 100 lines (200-line limit). On new task entry, all 4 upfront injection items (current goal / danger zones / recent decisions / required verification) are measurably auto-injected.

## 14. Next Step

[Phase 4 -- State Machine](phase-4-state-machine.md)
