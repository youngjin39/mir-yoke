---
phase: 8
title: Garbage Collection
status: consolidated-v1
depends_on: phase-7-fleet-expansion
---

# Phase 8 -- Automated Garbage Collection

> **Purpose**: Automatically detect and archive unused/duplicate/dead code, stale memory, and deprecated catalog entries. Systemically solve the problem of harnesses growing heavier over time.

## 0.5 Design Goals (R9 anchor)

**3-axis contribution**:
- **Axis I (self-harness hardening)**: GC cadence (monthly diet + memory lifetime cleanup + archive lifecycle)
- **Axis II (public template sync)**: template GC procedure (per-family archive standard lifecycle + deletion rules)
- **Axis III (fleet central management)**: fleet GC orchestration (your-harness manages N-family archive timing + prevents cross-family GC scheduling conflicts)

**Inter-phase contract**:
- **Input** (consumes): phase-3 (memory entry status/valid_until) + phase-6 (usage metrics) + phase-7 (per-family adoption)
- **Output** (provides): archive artifact + deletion log + CLAUDE.md diet -> phase cycle reset + phase-11 drift detection basis

## 1. Last of the 4 Pillars

Phase 0 section 2 listed 4 pillars. This is the last to be applied, but the most essential.

> Automated Garbage Collection -- automatically clean duplicate code, dead code, architecture violations, and unused catalog entries.

Relying on manual cleanup means it will not get done. Systematize with 3 stages: cadence + detect + archive.

## 2. Detection Targets

| Domain | Targets |
|---|---|
| Code | dead function / duplicate block / unused import |
| Catalog | agents / skills with 0 usage |
| Memory | entries past `valid_until` / superseded entries not reflected |
| Documentation | conflicting decision values / stale external references |
| Hook | 0-fire hooks (requires false negative verification) |
| Family | families where rollout is stalled |

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

Unused detection -> do not delete immediately. Route through archive.

```text
active -> unused (N days) -> archive candidate -> archived -> (if needed) revived | purged
```

| Stage | Action | Threshold |
|---|---|---|
| Mark unused | fleet_observe advisory WARN | **N = 30 days** -- based on last call/reference timestamp (code: import grep, catalog: active_agents reference, memory: last inject) |
| Archive candidate | tag applied, grace period | **7 days** -- operator can contest the unused decision |
| Archived | moved to `archive/` directory, removed from registry | (immediate -- right after 7-day grace period ends) |
| Revived | return to active when use resumes | (unlimited -- possible from any stage) |
| Purged | permanent deletion from archive after 6 months | **180 days** -- from archived entry time |

**Threshold rationale**: Concrete values (N=30, grace=7, purge=180) defined to prevent operators from being unable to determine archive candidate transition timing. Changes require an ADR.

**Cadence section 3 alignment**: This section thresholds are in days. Section 3 cadence ("weekly unused stats / monthly memory lifetime") is the trigger for threshold detection.

## 5. CLAUDE.md Diet

Monthly cadence.

### Automated tools
- `/revise-claude-md` (official Anthropic plugin)
- `/claude-md-improver`

### Checklist
- Keep to 100-200 lines
- Only decision values (remove items still under discussion)
- Only things that do not change (move changing items to code and tests)
- Remove duplicates (detect same fact in multiple 8-layer locations)
- Remove external citation body text (move to Appendix)

## 6. Memory Lifetime Cleanup

Uses the lifetime fields from [Phase 3 section 4](phase-3-memory-context.md).

**Dependency note**: This section functions only after Phase 3 lifetime field schema (`memory_entry.schema.json`) + code store implementation is landed. If Phase 3 is not landed, this section is entirely inactive. Therefore Phase 8 entry prerequisite = Phase 3 done.

1. `status: deprecated` entries -> exclude from injection immediately
2. `status: superseded` entries -> verify `superseded_by` is reachable
3. Entries past `valid_until` -> archive candidates
4. Same fact in multiple locations -> archive all except SoT
5. `status: critical` entries -> GC exempt (Phase 3 section 4 critical field)
6. Memory not directly edited by the operator is updated automatically by LLM/hook responsibility

## 7. Catalog Consistency

Advisory from `fleet_observe` and `scripts/verify_repo_agent_management.py`.

Checks:
- Agent definition exists but not referenced in any family `active_agents` -> 0 usage
- Skill definition exists but no agent calls it -> 0 usage
- Multiple agents / skills with the same function -> duplicate candidate
- Dangling references in external catalog -> patch immediately

## 8. Hook False Negative Verification

A 0-fire hook has two possibilities:

1. There really are no violations -> working correctly
2. Fire condition is wrong and actual violations are not detected -> false negative

Verify quarterly with false-negative-tester subagent. Inject intentional violation cases -> confirm hook fires.

## 9. ADR Active vs Superseded

ADRs in `docs/decisions/` also have a lifecycle.

- New ADR changes decision of existing ADR -> existing ADR frontmatter `status: superseded` + `superseded_by`
- Unexecuted ADR -> `status: deferred` (specify re-review date)
- Discarded ADR -> move to archive directory

## 10. Automation Tool Catalog

| Tool | Role |
|---|---|
| `fleet_observe/archive/detector.py` | Detect unused components |
| `scripts/verify_repo_agent_management.py` | Catalog consistency advisory |
| `scripts/verify_codex_sync.py` | Public template sanitize verification |
| `/revise-claude-md` | CLAUDE.md diet |
| `/claude-md-improver` | Same |
| false-negative-tester subagent | Hook fire verification (scripted, `.claude/agents/false-negative-tester.md`) |
| enforcement-validator subagent | Rule self-verification |
| cross-project-impact-audit | Cross-family change impact |

## 11. Prohibitions

- Immediate deletion (skipping archive lifecycle)
- Relying only on manual cleanup
- Trusting hooks without false negative verification
- Assuming unused = unnecessary (sometimes operator intent check required)
- Leaving CLAUDE.md diet on human cadence only (cadence reminder is automatic, execution is LLM)

## 12. Application Status

| Item | Status | Location |
|---|---|---|
| 4-pillar GC | landed | fleet-inventory-catalog-axis-extension ADR |
| 6-area detection targets | partial | code/catalog landed; actual canary stale hook archive evidence exists; cadence repeat closeout / doc stale / ADR lifecycle standardization pending |
| Cadence | partial | some automatic cadence; some manual reminder |
| Archive Lifecycle | landed | `archive/` catalog + detector.py |
| CLAUDE.md diet | partial | manual cadence only |
| Memory lifetime cleanup | partial | phase-3 lifetime field schema/store/GC path landed; phase-level cadence/evidence organization remaining |
| Catalog consistency advisory | landed | verify_repo_agent_management.py |
| Hook false negative verification | partial | false-negative-tester agent landed; deny-list sweep evidence acquired; repeat cadence accumulation pending |
| ADR active/superseded | partial | frontmatter consistency incomplete |

**Gaps**: Repeat hook false-negative cadence closeout + ADR lifecycle standardization + memory GC cadence evidence organization.

## 13. Exit Criterion

Automatic items in section 3 cadence (per-commit linter / per-phase catalog consistency) are operating, and monthly cadence reminder fires and executes for 1+ cycles. The active -> unused -> archived flow in the archive lifecycle is verified on 1+ unused components.

## 14. Conclusion

When this phase completes, all 4 pillars from [Phase 0](phase-0-foundations.md) are operational. When a new family is introduced, restart from Phase 0.

Appendix: [Appendix A -- Source Mapping, Deprecated Items, Contradiction Resolution](appendix-a-sources.md)
