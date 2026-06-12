---
title: "Context-Surface Reduction — Fleet-Application Design"
keywords: [context-surface, token-budget, session-overhead, CLAUDE-md, AGENTS-md, session-start, memory-index, eager-context, fleet-apply, dedup]
created: "2026-06-03"
last_used: "2026-06-07"
type: harness-engineering
---
# Context-Surface Reduction — Fleet-Application Design

- Date: 2026-06-03
- Status: design (reference implementation landed on example-harness; fleet rollout is a separate user-directed pass)
- Related: `docs/references/ecc-context-budget.md`, context budget audit (prior fleet Phase A/B), `docs/harness-adoption-blueprint.md`

## 1. Purpose

Reduce the **per-session always-on context surface** — the bytes injected into every Claude/Codex session regardless of task — across the fleet, using the example-harness pilot of 2026-06-03 as the reference implementation. Target: bring eager context to ≤ the project's own stated budget (`session overhead < 5% of the 200K window`, ~10K tokens) **without losing any load-bearing rule**.

## 2. Background — eager vs lazy context

Every session **eagerly** loads, regardless of task:
- `CLAUDE.md` + `AGENTS.md` (full text),
- the SessionStart hook payload (`.claude/hooks/session-start.sh` — plan/lessons/memory-map/handoff slices),
- the agent's `MEMORY.md` index.

Skill and agent **bodies are lazy** (only `name` + `trigger`/`description` surface until invoked). Adding skills/agents therefore does **not** grow the eager surface beyond ~1 index line each.

> Consequence: the lever is the always-on **prose** (`CLAUDE.md`/`AGENTS.md`) + injected slices + the memory index — **not** the count of skills/agents. "Many agents/skills" is not the bloat source; long instruction prose and a fat memory index are.

## 3. Reference pilot result (illustrative numbers)

| Surface | Before | After | Delta |
|---|---:|---:|---|
| `MEMORY.md` (agent memory, injected) | ~18K B | ~7K B | −62% (two-tier) |
| SessionStart stdout | ~14K B | ~11K B | −20% |
| `CLAUDE.md` | ~10K B | ~9K B | −9% |
| `AGENTS.md` (regenerated) | ~10K B | ~10K B | −9% |
| **Claude-session eager total** (MEMORY + session-start + CLAUDE) | **~42K B** | **~27K B** | **−36% (~10.6K → ~6.7K tok)** |

Zero new test regressions (full suite: only pre-existing environmental baseline failures remained).

## 4. Portable changes (apply per repo)

### 4.1 `CLAUDE.md` intra-file dedup
- State role policy **once**: keep the generated `mir:profile:role-policy` block as the source of truth; delete hand-authored prose that merely duplicates it; keep only the non-duplicated deltas (e.g. "record overrides", "long-term changes update the ADR + this file + regressions together").
- Merge overlapping sections (e.g. fold `Surgical Change Rules` into `Principles`).
- Compress verbose `Workflow` bullets when an `Orchestration Presets` table already encodes the routing.
- Delete closing "Principle/restatement" paragraphs that re-explain the preceding bullets.
- **Constraint:** never edit inside generated markers (`mir:generated`, `mir:profile:*`).

### 4.2 `AGENTS.md`
- `AGENTS.md` body mirrors `CLAUDE.md` (+ a small Codex header) and must be **regenerated** from `CLAUDE.md` via `scripts/generate_codex_derivatives.sh` — never hand-edited.
- Both files must stay **self-contained for their runtime** (Codex does not read `CLAUDE.md`). **Do not merge them.** Trimming the `CLAUDE.md` source automatically shrinks `AGENTS.md` on regeneration.

### 4.3 SessionStart injection trim (`.claude/hooks/session-start.sh`)
- Reduce the `plan.md` head (e.g. `head -c 4000` → `head -c 1200`): the live override / active-step lives in the first ~1.2 KB; the rest is completed-history noise already summarized in the upfront-context `current_goal`.
- Drop static doc preambles from injected slices (e.g. the `lessons.md` Promotion-Rule header) — inject only the live / `mir:generated` content.
- The `memory-map` injection block is the **largest single block** and duplicates the recall index — dropping it is the biggest win, **but it may be test-pinned** (see §6).
- Keep: upfront-context, latest-session snippet, latest-runner snippet, and the stderr enforcement block (not part of the context window).

### 4.4 Agent memory index two-tier (per-agent `MEMORY.md`)
- Split the always-injected `MEMORY.md` into:
  - **HOT** (stays injected): behavioral rules applied every session + current-state / topology facts you must not get wrong.
  - **COLD** (moves to a non-injected `MEMORY-archive.md`): early-design narrative, settled ADRs, infra/install trivia, situational discipline, incidents, references, consolidated history.
- All memory **files stay on disk**; only the injected index is slimmed (cold entries remain recallable by reading the archive or the individual file).
- **Verify no entry lost:** indexed-entry count before == hot + cold after.

## 5. Fleet-application procedure (per family repo)

1. **Measure baseline:** `wc -c CLAUDE.md AGENTS.md`; `bash .claude/hooks/session-start.sh </dev/null 2>/dev/null | wc -c`; `MEMORY.md` size. Record.
2. **Establish the test baseline first:** run the **full** suite to capture known-failing tests (so "no new regression" is meaningful). The pre-commit hook is **not** the full suite (see §7).
3. Apply §4.1 `CLAUDE.md` dedup (surgical; lose no rule).
4. Regenerate `AGENTS.md` (§4.2); run `scripts/verify_codex_sync.py`.
5. Apply §4.3 session-start trim.
6. Apply §4.4 memory two-tier (the agent's own `MEMORY.md`).
7. **Verify:** re-measure; re-run the **full** suite → only the pre-existing baseline failures (no new). Confirm `verify_codex_sync.py` clean.
8. Commit in logical commits (English, structured trailer). Do **not** push without instruction.

## 6. Test-pin caveat (load-bearing)

Some always-on content is asserted by tests as **required injection**. On the reference pilot this blocked the two largest cuts:
- `CLAUDE.md` role-policy bullets — pinned by exact-string asserts in harness contract tests.
- SessionStart `memory-map` block — pinned by a test asserting the memory-map header is included in session start output.

The executor **must not weaken these tests** to make a cut. Realizing those reductions requires a **deliberate, separate decision** to update the test ("is this content still a required injection?"). **Each repo's pin set differs — discover it by running the suite, not by assuming.** This is why the reference pilot landed −36% rather than the theoretical −55%.

## 7. Verification discipline (lessons — apply fleet-wide)

- **Full suite, not the pre-commit hook.** The pre-commit hook runs lint + TDD ledger + a changed-file test scope, **not** the full suite; schema/contract regressions slip through it.
- **Do not trust exit 0 / self-report.** A `cmd > log 2>&1; echo EXIT=$?` wrapper makes a background job's reported exit `0` even when pytest fails — always read the `EXIT=` / pytest summary line. Re-verify delegated commits independently (git log, tree status, re-measure sizes), not the agent's word.
- **No-loss memory split.** Confirm the indexed-entry count is unchanged across the hot/cold split.
- **Delete/move safety.** "0 external importer" ≠ dead — also check CLI entry points (`__main__.py`), deployment records, and config references; quote shell globs (`grep --include='*.py'`, not bare) or the shell aborts before grep runs and yields a false "none".

## 8. Constraints & explicitly non-portable items

**Non-portable (reference implementation only) — excluded from fleet rollout:**
- daemon / cron policy enforcement (reference implementation automation infra),
- per-profile apply-state revert (single profile's data),
- memory archive tools (the bundled fleet copies need a **separate user-directed** retirement under the DB-distribution model),
- `anthropic` → optional dependency (only repos that ship a sanitize-llm tool).

**Constraints:**
- Cross-repo write requires an explicit, recorded grant (the default boundary forbids writing into other family repos).
- Sealed-repo families must not be pushed externally.
- The sandbox shell may have limited launchd capabilities — changes that require loading must run in the user's real login terminal.
- Each repo's `CLAUDE.md`/`AGENTS.md` content and test pins differ — apply **surgically per repo**, never blanket-overwrite.

## 9. Applicability matrix

All managed family repos carry `CLAUDE.md` + `AGENTS.md` + a SessionStart injection ⇒ §4.1–4.3 apply to every repo. §4.4 (memory two-tier) applies per-agent (each agent's own `MEMORY.md`). Expected per-repo reduction scales with current bloat; the reference pilot achieved −36%.

## 10. Status & next

- **Reference implementation:** example-harness pilot, verified zero new regressions.
- **This document is the spec for fleet rollout.** Rollout execution is a separate, user-directed pass requiring a cross-repo write grant and a per-repo design/verify cycle, consistent with the prior Context Budget Audit Phase A/B fleet rollout.
- Recommended rollout order: highest-bloat repos first (measure §5.1 across the fleet to rank), one repo per slice with full-suite verification, never blanket edits.
