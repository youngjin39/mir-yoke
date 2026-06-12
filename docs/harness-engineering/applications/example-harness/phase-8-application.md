---
phase: 8
title: Garbage Collection Application
status: done
family: your-harness (SE-meta)
blueprint: ../../phase-8-garbage-collection.md
---

# Phase 8 — Garbage Collection Application (example-harness)

## 1. Blueprint Reference

[`../../phase-8-garbage-collection.md`](../../phase-8-garbage-collection.md) full. Key sections: §3 Cadence, §4 Archive Lifecycle, §5 CLAUDE.md diet, §6 memory lifetime cleanup.

**Related Supplementary Documents**: When writing the ADR candidate 38 (GC-lifecycle, R9 renumbered: previous ADR-27 = R9 newly added Back-Propagation conflict) for this phase, apply the 5-step + iteration requirement from [`../design-process.md`](../design-process.md).

## 2. Current State (pre-measurement)

| Item | Blueprint Location | your-harness State |
|---|---|---|
| 4-pillar GC | §1 | land — ADR-11 fleet-inventory-catalog-axis-extension |
| 6 detection target areas | §2 | partial land — code/catalog landed, cadence reminder + monthly log evidence landed, hook FN deny-list sweep evidence (10 FN-OK synthetic cases) exists, actual canary stale hook archive evidence 1 instance secured |
| Cadence | §3 | partial land — `scripts/refresh_phase8_cadence.py` landed + `tasks/checklist.md` 2026-05 cycle executed + `tasks/log/cadence-2026-05.md` recorded, recurring cadence closeout is follow-up |
| Archive Lifecycle | §4 | land — `archive/` catalog + `tools/fleet_observe/archive/detector.py` |
| CLAUDE.md diet | §5 | partial land — manual cadence only |
| Memory lifetime cleanup | §6 | partial land — `gc_scan()` + `memory_gc_runner.py` + daily plist present, cadence evidence is follow-up |
| Catalog alignment advisory | §7 | land — `scripts/verify_repo_agent_management.py` |
| Hook FN verification | §8 | partial land — false-negative-tester agent/codex mirror + deny-list sweep evidence (10 FN-OK synthetic cases) present, recurring cadence/log closeout is follow-up |
| ADR active/superseded | §9 | partial land — frontmatter consistency absent |

**Gap**: No exit-criterion-level blockers. Additional cadence hardening and ADR lifecycle standardization may remain as follow-up improvement items, but are not phase exit blockers.

## 3. Application Work Steps

| Step | Work | Dependency | Estimate |
|---|---|---|---|
| 8-1 | Memory lifetime cleanup cronjob — archive entries past `valid_until` | Phase 3 (3-1, 3-2) | 3h |
| 8-2 | false-negative sweep closeout — re-run synthetic deny-list cases + organize hook fire evidence/log | – | 2h |
| 8-3 | ADR lifecycle frontmatter standardization — `status: active \| superseded \| deferred \| archived` + `superseded_by` field | – | 4h |
| 8-4 | Backfill existing ADR-01~26 frontmatter | 8-3 | 2h |
| 8-5 | CLAUDE.md diet cadence closeout — organize checklist/log execution evidence based on landed reminder path | – | 1h |
| 8-6 | Document stale detection — auto-detect stale external citations/dependencies in `docs/` (cited but file not found, link rot) | – | 4h |

## 4. Files to Modify

| Path | Type |
|---|---|
| `scripts/memory_gc_runner.py` | landed (GC dry-run / confirm CLI) |
| `.claude/agents/false-negative-tester.md` | landed |
| `.codex/agents/false-negative-tester.toml` | landed (mirror) |
| `docs/templates/_schema/adr.schema.json` | create (ADR frontmatter standard) |
| `docs/decisions/adr-*.md` (all) | edit (frontmatter backfill) |
| `scripts/refresh_phase8_cadence.py` | landed (monthly cadence reminder evidence path) |
| `tools/fleet_observe/measure/doc_stale.py` | create |
| `docs/decisions/adr-27-gc-lifecycle-2026-MM-DD.md` | create |

## 5. Verification Procedure

Blueprint §13 Exit Criterion: "Automatic items from §3 cadence (per-commit linter / per-phase catalog alignment) are operating. Monthly cadence reminder fires + executes at least 1 cycle. Archive lifecycle active → unused → archived flow measured on at least 1 unused component."

Verification methods:
1. Intentionally add 1 unused agent → fleet_observe detects unused → confirm archive lifecycle entry
2. false-negative-tester re-runs synthetic deny-list cases → verify hook fire and cadence log supplementation
3. Confirm ADR-01 frontmatter specifies `status: active` or appropriate status
4. Confirm diet reminder auto-added to `tasks/checklist.md` on 1st of month (or cadence expiry)

## 6. Cross-repo Propagation Exceptions

| Case | Rule |
|---|---|
| code_app / SE-product | enforced — auto detector + archive lifecycle applied identically |
| hybrid_pipeline | warn — auto detector fires, archive requires user confirm |
| content_app | warn — privacy consideration, anonymize or user confirm on archive |
| Family uses own GC | your-harness detector inactive, but catalog alignment enforced only |
| Family refuses CLAUDE.md diet cadence | warn cadence reminder, no forced block (personal SE-product family) |

[`../exceptions.md`](../exceptions.md) §3 Phase 8 row consistent.

**Specific Exceptions**:
- `example-infra` (code_app) → entirely enforced
- `example-notes` / `example-game` (SE-product) → entirely enforced, but product assets (images etc.) exempt from GC
- `example-content` (hybrid_pipeline) → content itself exempt from GC, metadata detection only
- `example-personal` (SE-product personal) → user confirm required on GC, anonymize log

## 7. SE-meta self-stop Check

Can your-harness detect its own unused components? → ✓ archive detector already running.
Can your-harness diet its own CLAUDE.md? → ✓ user cadence reminder + LLM execution.
Can false-negative-tester detect false negatives in your-harness hooks? → ✓ evidence exists (10 FN-OK synthetic deny-list cases), but recurring cadence cycle accumulation is follow-up.

**Potential Violation Risk**:
- If memory lifetime cleanup automatically archives critical decision entries, decision loss. Therefore Phase 3 ADR-23's `status: critical` field explicitly marks GC-exempt entries.
- If false-negative-tester actually blocks operational hooks, production impact. Therefore run only in separate sandbox environment.

## 8. Work Status

- **Status**: done (archive lifecycle, cadence evidence, memory GC runner, false-negative sweep evidence, and phase-7 dependency all aligned)
- **Completion Date**: 2026-05-29
- **Verification Evidence**: `tools/fleet_observe/tests/test_archive.py::test_stale_hook_lifecycle_active_threshold_to_archived`, actual canary archive at `.claude/hooks/archive/phase8-stale-canary.sh`, archive detector advisory digest, `tasks/checklist.md` 2026-05 cadence cycle, `tasks/log/cadence-2026-05.md`, `scripts/refresh_phase8_cadence.py`
- **Revert Reason**: –

## 9. Conclusion

When this phase reaches done, all entries in the [`example-harness/README.md`](README.md) ledger table are done. SE-meta dogfooding complete. Next work:

- **other-families/** directory creation (application design for each fleet family)
- **prompt-templates/** directory creation (LLM prompts for each phase)

This work proceeds per [`../README.md`](../README.md) §8 S3 onwards, upon explicit user instruction.
