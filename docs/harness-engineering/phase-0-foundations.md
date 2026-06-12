---
phase: 0
title: Foundations
status: consolidated-v1
---

# Phase 0 — Foundations

> **Purpose**: Fix the philosophy, principles, and terminology shared by all subsequent phases. No code or hooks yet. Only agreement.

## 0.5 Design Goals (R9 anchor)

> This phase's connection to the [3-axis fleet goals](applications/fleet-catalog.md). When adding a new phase or cherry-picking for a family, the `design` skill (R9-T11) requires `design_goals` as a mandatory input.

**3-axis contribution**:
- **Axis I (your-harness hardening)**: 4 pillars · 5 layers · HOW NOT · 9 terminology entries as a sticky baseline for all phases in your harness
- **Axis II (public template sync)**: template adopters must pass the same agreement procedure (§11 Exit Criterion) — prevents terminology drift
- **Axis III (fleet central governance / back-propagation)**: fleet families may not enter phase-1+ without a phase-0 agreement (SE-meta self-stop entry point)

**Inter-phase contract**:
- **Input** (consumes): user request + external OSS inspiration + MEMORY (`project_*` / `feedback_*`)
- **Output** (provides): 4 pillars + 5 layers + 9 terms + HOW NOT list + decisions-vs-archived table → foundation for phase-1 entry

## 1. Governing Variables

The variables that determine harness quality are not prompts — they are these 4 axes:

1. **Context hygiene** — what is read and what is not
2. **Execution path separation** — code work and non-code work are not routed through the same flow
3. **Enforcement mechanism** — critical rules are expressed in code, not prose
4. **State single source of truth** — each fact lives in exactly one place

If any of these four axes breaks, no prompt can recover the situation.

## 2. 4 Pillars (Pachaar reference + refined study notes)

| Pillar | Definition | Phase mapping |
|---|---|---|
| Machine-Readable Context | Documents, structures, and conventions that AI can read | Phase 3 |
| Systematic Enforcement | Embedding rules as code | Phase 2 |
| Tool Boundaries | Restricting the areas tools can reach | Phase 2, Phase 4 |
| Automated Garbage Collection | Auto-cleaning unused, duplicate, or dead code | Phase 8 |

## 3. 5-Layer Responsibility Separation

| Layer | Responsibility | Must NOT contain |
|---|---|---|
| Harness | Classification · routing · verification checkpoints | Domain knowledge verbatim |
| Docs | Explanation · rationale · decision records | Enforcement rules themselves |
| Skills | Encapsulation of repeated procedures | Global policy source of truth |
| Hooks/Scripts | Enforcement · automated verification · blocking | Verbose explanations |
| Memory | State · facts · preferences | Duplicate guidance documents |

Sub-agents and MCP are auxiliary executors within these 5 layers, not layers themselves.

## 4. HOW NOT Priority

When describing a module, there are 5 questions to answer — **HOW NOT is highest priority**:

1. **WHAT** — what does it do
2. **HOW** — how does it do it
3. **HOW NOT** — how does it break ← most important
4. **WHERE** — where is it called from
5. **WHY** — why is it designed this way

Reason: AI causes incidents not when it doesn't know "ways it can do something" but when it doesn't know "ways it must never do something."

## 5. Compass not Encyclopedia

AI-ready documentation is a compass, not an encyclopedia.

- Do not write down all knowledge.
- Tell the reader where to find what.
- State decisions and prohibited lines clearly.
- Write only what does not change (changing things belong in code and tests).

## 6. 4 Task Classifications

Every request is classified into one of the following. Starting without classification is failure.

| task_type | Definition |
|---|---|
| code_execution | Involves actual file modification, creation, or deletion |
| research_planning | Investigation, comparison, design, planning (no code or code is secondary) |
| review | Examining existing artifacts for defects, gaps, or risks |
| ops | Environment inspection, logs, status diagnosis, runtime operations |

## 7. Core Prohibitions

Patterns that are **prohibited** throughout this entire document set:

- Reporting completion without verification
- Dumping all memory verbatim into the prompt
- Replicating the same fact in multiple places
- Routing code work and research work through the same flow
- Placing only a "do not do this" statement without a technical block
- Ending work based on self-assessment alone (violates Worker Isolation)

## 8. Decisions vs Archived

The following are decision values that all phases in this document set assume. Comparison with archived alternatives: see [Appendix A §2](appendix-a-sources.md).

| Item | Decision value | Archived alternative |
|---|---|---|
| Implementation language | Python | Rust migration |
| Memory infrastructure | sqlite-vec + oMLX bge-m3 | No embeddings / Langfuse outsourced |
| Execution agent | Claude+Codex dual | Single agent |
| Directory root | `.claude/` + `.ai-harness/` distributed | Single `.harness/` root |
| MVP strategy | Full rollout + per-family evolution | Gradual incremental introduction / MVP split |
| Discord | Claude Code plugin delegation | Direct custom adapter implementation |

## 9. Terminology

- **family** — one repository unit managed by the harness (your-harness self + all fleet families)
- **harness** — the bundle of control plane code + rules + hooks. Not a tool belt AI carries; an exoskeleton that constrains AI
- **executor lane / review lane** — separated execution paths for code writing/testing vs. verification/review
- **phase** (concept) — the N stages in this document set (§2 table above)
- **phase** (implementation) — the P0-F ~ P14 ledger in `tasks/phase.json`. The two meanings are different ([Appendix A §3](appendix-a-sources.md))

## 10. Application State

| Item | Status |
|---|---|
| 4 pillars | land (distributed across Phase 2/3/8) |
| 5-layer separation | land (CLAUDE.md Hook Policy Boundary) |
| 4 task classifications | land (orchestration preset mapping) |
| HOW NOT priority | partial land (failure-patterns.md absorbs some) |
| Compass not Encyclopedia | partial land (memory-map.md absorbs some) |
| Decisions vs archived table | land (this document + Appendix A) |

## 11. Exit Criterion

Terminology in §9 and decisions table in §8 agreed with user. New family profile JSON (`config/repos/<name>.json`) can be written.

## 12. Next Steps

Proceed to [Phase 1 — Start Harness](phase-1-start-harness.md).
