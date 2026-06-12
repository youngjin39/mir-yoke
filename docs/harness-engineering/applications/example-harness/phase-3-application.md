---
phase: 3
title: Memory & Context Application
status: done
family: your-harness (SE-meta)
blueprint: ../../phase-3-memory-context.md
---

# Phase 3 — Memory & Context Application (example-harness)

## 1. Blueprint Reference

[`../../phase-3-memory-context.md`](../../phase-3-memory-context.md) full. Key sections: §4 memory lifetime fields, §7 `/compact` criteria, §8 Sliding Window Prompt, §11 memory update cadence.

**Related Supplementary Documents**: When writing ADR-23 (memory-lifetime) for this phase, apply the 5-step + iteration requirement from [`../design-process.md`](../design-process.md).

## 2. Current State (pre-measurement)

| Item | Blueprint Location | your-harness State |
|---|---|---|
| SoT separation | §1 | partial for storage backend, sufficient for phase exit — global wiki + memory-map.md landed and `memory_entry.sot` schema exists, while explicit personal-store backend remains outside current closeout scope |
| 8-Layer context model | §2 | land (automatic, Claude Code feature) |
| Selective injection rules | §3 | land — `session-start.sh` + `scripts/build_session_upfront_context.py` auto-inject 4 upfront items |
| Memory lifetime fields | §4 | land — schema/store/GC path landed, `recall_for_task_state()` provides sliding-window retrieval wire-up point |
| Cache Stability | §6 | land |
| `/compact` 30~40% criteria | §7 | land (advisory) — `measure/context.py` generates compact recommendation facts |
| Sliding Window Prompt | §8 | land (policy + retrieval wire-up) — `task_state.sliding_window_n` + `store.recall_for_task_state()` |
| CLAUDE.md 4 principles | §9 | land (this repo ~80 lines) |
| `@import` split | §10 | partial land — your-harness single file |
| Monthly cadence | §11 | advisory — reminder only |

**Summary**: phase-3 is not about "reassembling every conversation frame with a new engine." The completion criterion is connecting SoT separation operational boundaries + upfront 4-item auto-injection + sliding-window retrieval policy + `/compact` advisory to your-harness. The explicit personal-store backend absence remains a blueprint residual item.

## 3. Application Work Steps

| Step | Work | Dependency | Estimate |
|---|---|---|---|
| 3-1 | Memory entry lifetime fields (`status` / `superseded_by` / `valid_until`) landed | – | done |
| 3-2 | sliding-window retrieval consumer (`recall_recent`, `recall_for_task_state`) landed | 3-1 | done |
| 3-3 | `/compact` advisory facts (`estimated_prompt_tokens`, `compact_recommended`, `compact_urgent`) landed | – | done |
| 3-4 | session-start upfront 4-item auto-injection helper landed | – | done |

## 4. Files to Modify

| Path | Type |
|---|---|
| `src/your_harness/core/engine/memory/store.py` | landed (lifetime fields + sliding-window consumer) |
| `tools/fleet_observe/measure/context.py` | landed (`/compact` advisory facts) |
| `scripts/build_session_upfront_context.py` | create (upfront 4-item synthesis) |
| `.claude/hooks/session-start.sh` | edit (phase-3 helper invoke) |
| `tests/test_build_session_upfront_context.py` | create |
| `tools/fleet_observe/tests/test_measure_context.py` | edit |
| `tests/test_hook_scripts.py` | edit |

## 5. Verification Procedure

Blueprint §13 Exit Criterion: "memory-map.md / global / personal SoT separation complete, CLAUDE.md within 100~200 lines, upfront 4-item auto-injection on new task entry."

Verification methods:
1. `tests/test_r25_integration.py` to confirm `sliding_window_n` retrieval wire-up
2. `tools/fleet_observe/tests/test_measure_context.py` to confirm compact advisory facts
3. `tests/test_hook_scripts.py` + `tests/test_build_session_upfront_context.py` to verify upfront 4 items appear on new session start
4. CLAUDE.md line count check (`wc -l` in 100~200 range)

## 6. Cross-repo Propagation Exceptions

| Case | Rule |
|---|---|
| All families | enforced — memory applies all phase-3 items (all 6 types) |
| Family uses its own memory store | your-harness sqlite-vec not enforced, but lifetime field equivalent is mandatory |
| Family memory contains PII | sliding window PII redact mandatory (special handling for personal SE-product family) |
| Family CLAUDE.md already exceeds 200 lines | warn — diet cadence reminder, no hard block |

[`../exceptions.md`](../exceptions.md) §3 Phase 3 row: all types enforced (memory has the strongest controls).

**Specific Exceptions**:
- `example-infra` (code_app) → memory lifetime fields enforced
- `example-personal` (SE-product personal) → sliding window PII redact required, `valid_until` conservative (1-year default)
- `example-content` (hybrid_pipeline) → memory applied normally, content itself is not memory

## 7. SE-meta self-stop Check

Can your-harness apply lifetime fields to its own memory? → After work ✓ yes.
Do your-harness existing memory entries (35+ entries in MEMORY.md) all remain `active` after backfill? → ✓ handled by §3-2 step default processing.

**Potential Violation Risk**:
- If sliding window retains only summaries of important decision entries, decision loss may occur. Therefore ADR-23 in §4 should explicitly mark sliding-window-exempt entries with an additional field like `status: critical`.
- If `/compact` auto-trigger is too aggressive, context shortage may occur. Therefore advisory only, no automatic execution.

## 8. Work Status

- **Status**: done
- **Completion Date**: 2026-05-25
- **Verification Evidence**: `.venv/bin/python -m pytest tests/test_build_session_upfront_context.py tools/fleet_observe/tests/test_measure_context.py tests/test_hook_scripts.py tests/test_r25_integration.py -q` → `39 passed`
- **Revert Reason**: –

## 9. Next Steps

Proceed to [Phase 4 State Machine](phase-4-application.md).
