---
phase: 8
title: Garbage Collection
status: consolidated-v1
depends_on: phase-7-fleet-expansion
---

# Phase 8 — Automated Garbage Collection

> **Purpose**: Automatically detect and archive unused, duplicate, dead code, stale memory, and deprecated catalog entries. Systemically solves the problem of the harness growing heavier over time.

## 0.5 Design Goals (R9 anchor)

> This phase's connection to the [3-axis fleet goals](applications/fleet-catalog.md). When adding a new phase or cherry-picking for a family, the `design` skill (R9-T11) requires `design_goals` as a mandatory input.

**3-axis contribution**:
- **Axis I (your-harness hardening)**: your-harness GC cadence (monthly diet + memory lifetime cleanup + archive lifecycle)
- **Axis II (public template sync)**: template GC procedure (per-family archive standard lifecycle + deletion rules)
- **Axis III (fleet central governance / back-propagation)**: fleet GC orchestration (your-harness manages archive timing for all fleet families + prevents cross-family GC schedule conflicts)

**Inter-phase contract**:
- **Input** (consumes): phase-3 (memory entry status/valid_until) + phase-6 (usage metrics) + phase-7 (per-family adoption)
- **Output** (provides): archive artifacts + deletion log + CLAUDE.md diet → phase cycle reset + phase-11 drift detection basis

## 1. Last of the 4 Pillars

The last of the 4 pillars from [[phase-0-foundations]] §2 to be applied, but the most core.

> Automated Garbage Collection — automatically clean up duplicate code, dead code, architectural violations, unused catalog items

Relying on manual cleanup means it ultimately won't happen. Systematize with 3 steps: cadence + detect + archive.

## 2. Detection Targets

| Area | Target |
|---|---|
| Code | dead function / duplicate block / unused import |
| Catalog | agent / skill with 0 calls |
| Memory | entry past `valid_until` / superseded not reflected |
| Docs | conflicting decision values / stale external citations |
| Hooks | 0-fire hooks (false negative verification required) |
| Family | rollout-abandoned family |

## 3. Cadence

| Frequency | Work |
|---|---|
| Every commit | linter / dead code detector (automatic) |
| Every phase completion | catalog consistency (fleet_observe) |
| Weekly | unused agent / skill usage statistics |
| Monthly | CLAUDE.md / AGENTS.md diet (`/revise-claude-md`) |
| Monthly | memory lifetime check (`valid_until`) |
| Quarterly | family rollout re-evaluation |
| Quarterly | ADR active vs superseded cleanup |

## 4. Archive Lifecycle

Unused detected → do NOT delete immediately. Route through archive.

```text
active → unused (N days) → archive candidate → archived → (if needed) revived | purged
```

| Stage | Action | Threshold (R7-C-W6 confirmed) |
|---|---|---|
| unused mark | fleet_observe advisory WARN | **N = 30 days** — based on last call/reference timestamp (code: import grep, catalog: active_agents reference, memory: last inject) |
| archive candidate | tag assigned, grace period | **7 days** — user can dispute unused determination |
| archived | moved to `archive/` directory, removed from registry | (immediate — right after 7-day grace period ends) |
| revived | return to active when use resumes | (no limit — possible from any stage) |
| purged | permanently deleted from archive after 6 months | **180 days** — from archived entry timestamp |

**Threshold rationale (R7-C-W6)**: Prior table only noted "(N days)" without specific values → operators couldn't determine when to transition to archive candidate. This R7 confirms N=30, grace=7, purge=180. Change requires an ADR.

**Consistency with §3 cadence table**: §4 thresholds are in days. §3 cadence ("weekly unused stats / monthly memory lifetime") is the detection trigger for these thresholds.

## 5. CLAUDE.md Diet

Monthly cadence.

### Automated Tools
- `/revise-claude-md` (official plugin)
- `/claude-md-improver`

### Checklist Items
- Keep under 100–200 lines
- Decision values only (remove items under discussion)
- Only what doesn't change (move changing items to code/tests)
- Remove duplicates (detect same fact at multiple locations across 8-layer model)
- Remove external citation body text (move to Appendix)

## 6. Memory Lifetime Cleanup

Uses lifetime fields from [[phase-3-memory-context]] §4.

**R4 dependency note**: This section only works after Phase 3's lifetime field schema ([`memory_entry.schema.json`](../templates/_schema/memory_entry.schema.json)) + code store implementation is landed. If Phase 3 is not landed, this entire section is inoperative. Therefore Phase 8 entry prerequisite = Phase 3 done.

1. `status: deprecated` entry → exclude from injection immediately
2. `status: superseded` entry → verify `superseded_by` is reachable
3. Entry past `valid_until` → archive candidate
4. Multiple locations for same fact → archive all but the SoT
5. `status: critical` entry → GC exempt (uses Phase 3 §4 critical field)
6. Memory not directly edited by user → automatically updated by LLM/hook responsibility

## 7. Catalog Consistency

Advisory from `fleet_observe` and `scripts/verify_repo_agent_management.py`.

Check items:
- Agent definition exists but not referenced in family's `active_agents` → 0 uses
- Skill definition exists but no agent calls it → 0 uses
- Multiple agents / skills with same functionality → duplicate candidates
- Dangling references in external catalog → patch immediately

## 8. Hook False Negative Verification

A 0-fire hook has two possibilities:

1. Genuinely no violations → working correctly
2. Fire condition is wrong and actual violations are not detected → false negative

Quarterly verification with false-negative-tester subagent. Inject intentional violation cases → confirm hook fires.

## 9. ADR Active vs Superseded

ADRs in `docs/decisions/` also have a lifecycle.

- New ADR changes a decision in an existing ADR → existing ADR frontmatter `status: superseded` + `superseded_by`
- Unexecuted ADR → `status: deferred` (specify review date)
- Abandoned ADR → move to archive directory

For ADR-01 through ADR-20 lifecycle status as of this consolidated document's writing (2026-05-22), refer to frontmatter in each file in `docs/decisions/`.

## 10. Automated Tool Catalog

| Tool | Role |
|---|---|
| `fleet_observe/archive/detector.py` | Unused component detection |
| `scripts/verify_repo_agent_management.py` | Catalog consistency advisory |
| `scripts/verify_codex_sync.py` | Public template sanitize verification |
| `/revise-claude-md` | CLAUDE.md diet |
| `/claude-md-improver` | Same |
| false-negative-tester subagent | Hook fire verification (scripted — R29-T09 land, `.claude/agents/false-negative-tester.md`) |
| enforcement-validator subagent | Rule self-verification |
| cross-project-impact-audit | Cross-family change impact |

## 11. Prohibitions

- Immediate deletion (skipping archive lifecycle)
- Relying only on manual cleanup
- Trusting hooks without false negative verification
- Simply assuming unused = unnecessary (may require user intent verification)
- Leaving CLAUDE.md diet to human cadence (cadence reminder only is automatic; execution is LLM)

## 12. Application State

| Item | Status | Location |
|---|---|---|
| 4-pillar GC | land | ADR-11 fleet-inventory-catalog-axis-extension |
| 6 detection areas | partial land | code/catalog land; 1 canary stale hook archive evidence exists; cadence repeat closeout / doc stale / ADR lifecycle standardization is follow-up |
| Cadence | partial land | some automatic cadence, some manual reminders |
| Archive lifecycle | land | `archive/` catalog + detector.py |
| CLAUDE.md diet | partial land | manual cadence only |
| Memory lifetime cleanup | partial land | [[phase-3-memory-context]] lifetime field schema/store/GC path landed; phase-level cadence/evidence cleanup is remaining |
| Catalog consistency advisory | land | verify_repo_agent_management.py |
| Hook FN verification | partial land | false-negative-tester agent land, deny-list sweep evidence (`10/10 FN-OK`) obtained; repeat cadence accumulation is follow-up |
| ADR active/superseded | partial land | frontmatter consistency absent |

**Gap**: Repeat hook FN cadence closeout + ADR lifecycle standardization + memory GC cadence evidence cleanup.

## 13. Exit Criterion

Automatic items from §3 cadence (per-commit linter / per-phase catalog consistency) are working, and monthly cadence reminder fires and is executed at least 1 cycle. Archive lifecycle's active → unused → archived flow is measured on at least 1 unused component.

## 14. Conclusion

When this phase is complete, all 4 pillars from [[phase-0-foundations]] are operational. When adopting a new family, start from Phase 0 again.

Appendix: [Appendix A — Source Mapping, Deprecated Options, Contradiction Resolution](appendix-a-sources.md)
