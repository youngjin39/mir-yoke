---
phase: 0
title: Foundations
status: consolidated-v1
---

# Phase 0 — Foundations

> **Purpose**: Fix the philosophy, principles, and terminology that subsequent phases will share. No code, no hooks yet — only consensus.

## 0.5 Design Goals (R9 anchor)

> Connection of this phase to the [3-axis fleet goals](applications/fleet-catalog.md). When adding new phases or cherry-picking for a family, the `design` skill (R9-T11) mandates `design_goals` as required input.

**3-axis contribution**:
- **Axis I (your-harness strengthening)**: Fix 4 pillars, 5 layers, HOW NOT, 9 terminology as sticky baseline for all phases in your-harness
- **Axis II (Public template sync)**: Template adopters are obligated to pass the same consensus procedure (§11 Exit Criterion) — blocks terminology drift
- **Axis III (Fleet central management / back-propagation)**: N families are blocked from entering phase-1+ without phase-0 consensus (SE-meta self-stop entry point)

**Inter-phase contract**:
- **Input** (consumed): User request + external OSS inspiration + MEMORY (`project_*` / `feedback_*`)
- **Output** (provided): 4 pillars + 5 layers + 9 terminology + HOW NOT list + Decisions vs Sunset table → phase-1 entry foundation

## 1. Governing Variables

The variables that determine harness quality are not prompts — they are the following 4 axes:

1. **Context Hygiene** — What is read and what is not read
2. **Execution Path Separation** — Whether code tasks and non-code tasks are run in the same flow
3. **Enforcement Mechanism** — Whether important rules are code rather than prose
4. **State Source of Truth** — Whether a single fact lives in exactly one place

If these four axes break, no prompt can recover them.

## 2. 4 Pillars (Pachaar citation + learning notes refinement)

| Pillar | Definition | Phase flow mapping |
|---|---|---|
| Machine-Readable Context | Documents, structures, and conventions that AI reads | Phase 3 |
| Systematic Enforcement | Embedding rules as code-level enforcement | Phase 2 |
| Tool Boundaries | Limiting the domain that tools can reach | Phase 2, Phase 4 |
| Automated Garbage Collection | Automatic cleanup of unused, duplicate, and dead code | Phase 8 |

## 3. 5-Layer Responsibility Separation

| Layer | Responsibility | What must not be here |
|---|---|---|
| Harness | Classification, routing, validation checkpoints | Domain knowledge source text |
| Docs | Explanation, rationale, decision records | Enforcement rules themselves |
| Skills | Encapsulation of repeatable procedures | Single source of truth for global policy |
| Hooks/Scripts | Enforcement, automated validation, blocking | Verbose explanations |
| Memory | State, facts, preferences | Duplicate guidance documents |

Sub-agents and MCP are auxiliary executors of these 5 layers, not layers themselves.

## 4. HOW NOT Priority

When describing a module, the 5 questions to answer — **HOW NOT is highest priority**:

1. **WHAT** — What does it do
2. **HOW** — How does it do it
3. **HOW NOT** — How can it break ← most important
4. **WHERE** — Where is it called from
5. **WHY** — Why is it designed this way

Reason: AI causes incidents not when it doesn't know "ways it can work" but when it doesn't know "ways it must never work".

## 5. Compass not Encyclopedia

AI-Ready documentation is a compass, not an encyclopedia.

- Does not document all knowledge.
- Shows where things can be found.
- Makes decisions and prohibition lines clear.
- Only records what doesn't change (what changes goes into code and tests).

## 6. 4 Task Classifications

Every request falls into one of the following. Starting without classification means failure.

| task_type | Definition |
|---|---|
| code_execution | Includes actual file modification, creation, or deletion |
| research_planning | Investigation, comparison, design, planning (code absent or secondary) |
| review | Examination of defects, omissions, risks in existing artifacts |
| ops | Environment checks, logs, state diagnosis, runtime |

## 7. Core Prohibition Lines

Patterns **prohibited** across this entire consolidated document:

- Reporting completion without verification
- Dumping all memory source text into the prompt
- Duplicating the same fact across multiple locations
- Running code tasks and investigation tasks in the same flow
- Having "don't do this" text without a technical block
- Finishing work with only self-assessment (Worker Isolation violation)

## 8. Decisions vs Sunset

The following are decision values assumed by all phases in this consolidated document. For comparison with sunset options, see [Appendix A §2](appendix-a-sources.md).

| Item | Decision value | Sunset option |
|---|---|---|
| Implementation language | Python | Rust migration |
| Memory infrastructure | sqlite-vec + oMLX bge-m3 | No embeddings / Langfuse external |
| Execution agent | Claude + Codex dual | Single agent |
| Directory root | `.claude/` + `.ai-harness/` distributed | `.harness/` single root |
| MVP strategy | Full deployment + per-family evolution | Gradual 12-family introduction / MVP split |
| Discord | Claude Code plugin delegation | Custom adapter direct implementation |

## 9. Terminology Fixed

- **family** — One repository unit managed by the harness (your-harness itself + N external = total N+1)
- **harness** — Bundle of control plane code + rules + hooks. Not a tool belt the AI carries, but an exoskeleton that constrains the AI
- **executor lane / review lane** — Separate execution paths for code writing/testing vs verification/review
- **phase** (conceptual) — The phases in this consolidated document (§2 table)
- **phase** (implementation) — The P0-F ~ P14 ledger in `tasks/phase.json`. The two meanings are different ([Appendix A §3](appendix-a-sources.md))

## 10. Application Status

| Item | Status |
|---|---|
| 4 pillars | landed (distributed implementation across Phase 2/3/8) |
| 5-layer separation | landed (CLAUDE.md Hook Policy Boundary) |
| 4 task classifications | landed (orchestration preset mapping) |
| HOW NOT priority | partial land (failure-patterns.md absorbs some) |
| Compass not Encyclopedia | partial land (memory-map.md absorbs some) |
| Decisions vs Sunset table | landed (this document + Appendix A) |

## 11. Exit Criterion

Terminology from §9 and decision table from §8 agreed with user. Ready to create family profile JSON (`config/repos/<name>.json`) for new families.

## 12. Next Step

Proceed to [Phase 1 — Start Harness](phase-1-start-harness.md).
