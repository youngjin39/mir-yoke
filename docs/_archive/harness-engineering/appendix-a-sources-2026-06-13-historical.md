---
phase: appendix
title: Sources, Sunset Items, Conflicts
status: consolidated-v1
---

# Appendix A — Original Mapping · Archived Items · Conflict Resolution

## 1. Original 16-document mapping

How each file from the source reference directory was absorbed into the current conceptual phase flow.

| Original file | Absorbed into phase / section |
|---|---|
| `README.md` | Phase 0 §9 terminology, this README §2 reading order |
| `01-project-charter.md` | Phase 0 entire |
| `02-start-harness-agent.md` | Phase 1 entire |
| `03-system-architecture.md` | Phase 0 §3 5-layer |
| `04-routing-policy.md` | Phase 1 §3-§7 |
| `05-enforcement-policy.md` | Phase 2 entire |
| `06-memory-context-policy.md` | Phase 3 §1-§5 |
| `07-subagent-policy.md` | Phase 5 §1-§9 |
| `08-implementation-roadmap.md` | This README §2 + each phase's "next steps" |
| `09-file-blueprint.md` | Phase 0 §3 + Phase 4 §10 |
| `claude-code-harness-design.md` | Phase 4 (state machine + 5 schema), Phase 6 (observability), Phase 2 (enforcement concepts) |
| `harness-rewrite-agent-classification.md` | Phase 7 §1 6-Type classification, §2 inheritance graph, §3 SE-meta self-stop, §4 dogfooding, §6 porting procedure (type-specific required skills list §5 not absorbed, ADR candidate 14 reference) |
| `study-notes.md` | Phase 0 §2 4 pillars, Phase 5 §5 Worker Isolation, Phase 6 §2 8 metrics |
| `improvement-proposals.md` | Phase 2 §5 Circuit Breaker, Phase 4 §7 interrupt atomicity |
| `gpt-alternative-design.md` | Phase 4 (13-state SM, 5 schema, retry_budget), Phase 3 §4 lifetime fields |
| `engineering-basics.md` | Source for nearly all phases. Phase 0 §4 HOW NOT, Phase 3 §2 8-layer / §9 CLAUDE.md, Phase 6 §3 cadence, Phase 8 §3 cadence + §5 diet |

## 2. Archived items

Items not adopted into this consolidated doc's decisions.

| # | Archived item | Source | Adopted alternative |
|---|---|---|---|
| 1 | Rust migration | study-notes.md L240 | Python |
| 2 | Langfuse integration | engineering-basics.md L155-158 | Custom fleet_observe 7-axis |
| 3 | `.harness/` single root directory | gpt-alternative-design.md | `.claude/` + `.ai-harness/` distributed |
| 4 | Single-agent assumption | gpt-alternative-design.md | Claude+Codex dual-track |
| 5 | MVP split / incremental family onboarding | engineering-basics.md L93 et al. | Full deployment + per-family evolution |
| 6 | Direct Discord adapter implementation | study-notes.md section | Claude Code plugin delegation |
| 7 | Delete brainstorming/writing-plans/verification skills from starter | study-notes.md L222-228 | Evolved to different skill system (design / verify / bluebricks) |
| 8 | No embedding (map alone sufficient) | engineering-basics.md L126 | sqlite-vec + bge-m3 embeddings |
| 9 | UI/Workflow Layer first-class separation (approval cards, diff visibility, interrupt/resume UI) | claude-code-harness-design.md §7.5, §8.1, §9 | Not currently applicable — CLI environment + Discord plugin delegation. Approval object itself absorbed into Phase 4 `approval.schema.json`; UI flow adoption decision deferred (ADR candidate 12) |

## 3. Conceptual phases vs implementation phases mapping

This consolidated doc's **conceptual phases** and the harness body's **implementation phases** are different axes.

| Conceptual (this doc) | Implementation (harness `tasks/phase.json`) |
|---|---|
| Phase 0 Foundations | No separate ledger; distributed across CLAUDE.md / ADRs |
| Phase 1 Start Harness | P0-A ~ P0-K (orchestrator + main entry) |
| Phase 2 Enforcement | P0-D pre-tool-use hook, pre-commit-verification, tdd-guard |
| Phase 3 Memory & Context | P10/P14 (sqlite-vec memory + harness generator) |
| Phase 4 State Machine | P0-F (`tasks/phase.json` ledger) + 13-state SM + `tool_contract.py` + `structured_error.py` |
| Phase 5 Subagents | ADR-08 cancelled, ADR-09 landed (executor-agent) |
| Phase 6 Observability | P10~P14 fleet_observe 7-axis |
| Phase 7 Fleet Expansion | Phase 4 hybrid_pipeline director specialization, fleet family rollout |
| Phase 8 Garbage Collection | ADR-11 catalog axis extension + archive lifecycle |
| Phase 9 Fleet Catalog | `config/fleet-harness-state.json` (family rows) + schema + `harness_drift.py` all landed |
| Phase 10 Rollout Share Pipeline | `scripts/sanitize_for_template.py` + `share_dispatcher.py` landed |
| Phase 11 Back-Propagation | `tools/fleet_observe/harness_drift.py` landed |
| Phase 12 Template Lifecycle | `tools/fleet_observe/template_health.py` + `scripts/sanitize_for_template.py` landed |
| Phase 13 Applied-State Closure | `applications/template-repo/current-state.md` live snapshot + verifier cross-check closeout |
| Phase 14 Completion Consistency | Conceptual closure lane only; no per-family rollout expansion and no new `enabled_phases` obligation |

This consolidated doc is "how it should be built" (blueprint); `tasks/phase.json` is "the order in which it was actually built" (ledger). Misalignment between the two is not a problem.

## 4. Conflict resolution

Conflicts between original documents and this consolidated doc's resolution.

| # | Conflict | Decision | Rationale |
|---|---|---|---|
| 1 | CLAUDE.md length 100 lines vs 200 lines | **100 lines recommended, 200 lines limit** | Anthropic official 4 principles + ~80 line operational measurement |
| 2 | Hook strength gradual (warn→suggest→block) vs immediate block | **Gradual is default, dangerous commands are exception** | Development flow protection + safety first (Phase 2 §4) |
| 3 | Embedding needed vs not needed | **Needed** | sqlite-vec + bge-m3 adopted |
| 4 | Self-evaluation vs new AI verification | **New lane / new session mandatory** | Worker Isolation principle (Phase 5 §8) |
| 5 | `/compact` 30-40% vs 200k tokens | **30-40% proactive, 200k strongly recommended** | Both thresholds valid, stage-based triggers (Phase 3 §7) |
| 6 | Plan repetition 4-5 times vs 3-5 times | **3-5 times** | Both within acceptable range, shorter adopted |
| 7 | `.agents/skills/` separate vs AGENTS.md single | **AGENTS.md single is default** | Auto-sync sufficient (Phase 3 §10) |
| 8 | Subagent introduction timing (v2 vs v1) | **Immediately after Phase 4 operational** | v2 approach was premature; v1 and this consolidated doc are a compromise |

## 5. Items in original sources not absorbed into this consolidated doc

Items present in source but intentionally excluded.

| Item | Source | Exclusion reason |
|---|---|---|
| Bluebricks 9-field detail | engineering-basics.md §8 | Delegated to separate skill definition |
| Global skill installation | engineering-basics.md §3 | Operational detail, out of scope |
| Codex CLI details (`/fork`, `/goal`, `really?`, `$harness`) | engineering-basics.md Codex section | CLI operations manual domain (separate doc candidate) |
| Pachaar 6-element body quotation | engineering-basics.md L20-28 | Memory SoT |
| External repo introductions (superpowers / Archon / OpenHarness etc.) | engineering-basics.md multiple locations | External reference SoT |
| AI developer maturity 4-stage model | engineering-basics.md | Self-classification tool, orthogonal to phase flow |

## 6. Future ADR candidates

Unimplemented gaps identified during this consolidation → ADR candidates.

| ADR candidate (confirmed number) | Domain | Priority | Status |
|---|---|---|---|
| ADR-21 (LANDED 2026-05-23) — family_type schema | Phase 7 | – | landed |
| ADR-22 (LANDED 2026-05-23) — sealed family policy | Phase 7 | – | landed |
| ADR-23 (LANDED 2026-05-23) — 10 active family dogfooding exemption | Phase 7 | – | landed |
| ADR-24 — 13-State SM introduction | Phase 4 | high (largest gap) | pending (after code lands) |
| ADR-25 (R9 land 2026-05-23) — Fleet Catalog (central management + non-forced) | Phase 9 | high | landed (accepted) |
| ADR-26 (R9 land 2026-05-23) — Rollout Share Pipeline (3-stage opt-in) | Phase 10 | high | landed (accepted) |
| ADR-27 (R9 land 2026-05-23) — Back-Propagation (5 sync directions) | Phase 11 | medium | landed (accepted) |
| ADR-28 — `run_state` / `tool_event` / `approval` JSON schemas | Phase 4 | high | landed (R4 phase-4 §3) |
| ADR-29 — Tool contract mandatory fields (idempotency / precondition / structured error) | Phase 4 | high | pending |
| ADR-30 — Memory lifetime fields (`status` / `superseded_by` / `valid_until`) | Phase 3 | medium | schema landed, code pending |
| ADR-31 — Sliding Window Prompt automation | Phase 3 | medium | pending |
| ADR-32 — Security & Compliance phase separation decision | (new Phase 15) | low | trigger pending (R7-C-I3) |
| ADR-33 (R9 design land) — design-complete-gate hook (`design-doc + grep evidence` enforcement) | (design-process) | medium | design land — hook code R11 |
| ADR-39 (R10 land 2026-05-23) — Template Applied-State Charter | your-harness-roles + phase-12 | high | landed (accepted) |
| ADR-40 (R10 land 2026-05-23) — Your-Harness Template-Maintainer Charter (Role B) | your-harness-roles + phase-12 | high | landed (accepted) |
| ADR-41 (R10 design land) — `verify_self_stop.py` hook (SE-meta self-stop runtime gate) | your-harness-roles §6 + fleet-catalog §1-bis | high | design land — hook code R11 |
| ADR-42 (R10-R5 design land) — `verify_template_applied_state.py` (ADR-39 charter enforcement tool) | adr-39 + adr-40 + template_health.py | high | design land — code R11 |
| (former ADR candidate 12) — UI/Workflow Layer explicit decision | Phase 4·6 | low | deferred (CLI environment + Discord delegation makes practical value low) |
| (former ADR candidate 13) — Phase flow exit condition standardization | all phases | medium | deferred |
| (former ADR candidate 14) — Type-specific required skill formal registration | Phase 7 | medium | deferred |
| Circuit Breaker quantification (`retry_budget`) | Phase 2 | medium | pending |
| Suggest strength level introduction (3rd level) | Phase 2 | low | pending |
| 6-Type classification naming + inheritance graph | Phase 7 | medium | landed |
| SE-meta self-stop automation | Phase 7 | high | pending |
| Hook False Negative verification (false-negative-tester) | Phase 8 | medium | pending |
| `report_contract` standardization | Phase 6 | medium | pending |

## 7. Plan number → actual ADR mapping (Planning-number reconciliation)

ADR-24/28-32 recorded as `pending` in §6 were later landed under different numbers or folded.

| Plan number (§6 table) | Actual landing | Notes |
|---|---|---|
| ADR-24 — 13-State SM introduction | **ADR-44** (landed) | Code: `tools/run_orchestrator/state_machine.py` |
| ADR-28 — `run_state`/`tool_event`/`approval` schema | **Phase-4 R4** (landed) | `tool_contract.py`, `structured_error.py` |
| ADR-29 — Tool contract mandatory fields | **folded into ADR-44** | No separate ADR number; absorbed into ADR-44 scope |
| ADR-30 — Memory lifetime fields | **folded** | Schema landed; no separate runtime ADR |
| ADR-31 — Sliding Window Prompt automation | **folded** | Scope reduced; separate ADR deemed unnecessary |
| ADR-32 — Security & Compliance phase | **folded** | Trigger not met; deferred and closed |

The `pending` entries in §6 are planning-time records; the above mapping is the actual landing result.

## 9. Change history

- 2026-05-22: Initial mapping + 8 archived items + 8 conflict resolutions + 11 ADR candidates.
- 2026-05-22 (post codex-final-reviewer R1): Added archived #9 (UI/Workflow Layer), improved rewrite-classification mapping, added ADR candidates 12·13·14. Fixed phase-1 §10 location error (config/orchestration-presets → CLAUDE.md §Orchestration Presets). Removed phase-4 §6 retry_budget yaml duplication.
- 2026-05-23 R9: Added phase-9/10/11 rows to §3 phase mapping table (Fleet Catalog / Rollout Share Pipeline / Back-Propagation). Fully renumbered §6 ADR candidate table (ADR-21~33 confirmed + former candidates 12/13/14 separated as deferred). Updated 9-state SM → 13-state SM throughout (R9 Slice B drift fix).
- 2026-05-27 R31: Generalized §1 phase count expressions to match current conceptual flow. Added phase-13/14 closure lane rows to §3 phase mapping table; explicitly stated phase-14 is not a per-family rollout expansion.
- 2026-06-08: Added §7 plan-number → actual ADR mapping (ADR-24→44, ADR-28→Phase-4 R4, ADR-29/30/31/32→folded).
