---
status: v2
date: 2026-06-10
scope: Standing criteria for fleet-wide harness review (structure + token efficiency + agent management) and improvement
audience: Mir Harness operators + fleet families (template-portable)
origin: 2026-06-10 fleet-wide re-validation (tasks/reports/harness-token-efficiency-revalidation-2026-06-10.md); v2 adds §C fleet-wide review method per user directive
---

# Harness Review & Improvement Criteria

Three parts: **A. Structure-review criteria** (how to audit one repo), **B. Improvement criteria** (when/how to change), **C. Fleet-wide review method** (how to run a full review across mir-self + template + all active repos). Post-Fable-5 direction: the harness optimizes for context intelligence, token efficiency, accurate operation, and clear intent capture — NOT for maximal restriction. Workflow, TDD, review, verification, sealed-repo protection, and cross-repo write safety are non-negotiable invariants.

## A. Structure-Review Criteria (run per re-validation)

### A1. Score rubric (per surface, 0–100)
- injection-necessity 40 / duplication-free 25 / size-vs-function 20 / deterministic-backing 15.
- Report composite per repo class: mir-self / template / fleet.
- Six report axes: token efficiency, context accuracy, workflow preservation, deterministic-verification coverage, repo/fleet safety, maintainability.

### A2. Before/after measurement procedure (no estimates in final reports)
1. BEFORE: `wc -c` every surface to be touched; live-run SessionStart hooks (`CLAUDE_PROJECT_DIR=<repo> bash .claude/hooks/session-start.sh | wc -c`).
2. AFTER: identical commands; record deltas in the evidence-sink report (§measured table).
3. Token estimate convention: bytes/4 (Latin), bytes/3 (Korean-dense). Label which.
4. Sub-agent measurements: UNIFORM per-item values across repos = fabrication signal (lesson) — re-measure ≥2 items directly before integrating.

### A3. Hook verification standard (ALL hooks, individually)
- For each file in `.claude/hooks/`: wiring (settings.json / settings.local.json / sub-dispatch from another hook / intentional-manual), verification method (executed, dispatch-path read, behavior probe), idle injection cost, status.
- "Orphan" verdicts require checking sub-dispatch (`grep <name> .claude/hooks/*.sh`) and ADR-51 allow-lists first.
- Behavior-probe new guards from the REAL enforcement point when possible (a guard that blocks the auditor's own probe is positive evidence).
- launchd/cron: `launchctl list | grep <prefix>` exit codes; nonzero → reproduce the exact plist command manually; phantom-flag class (plist args the CLI rejects) is a known recurring failure.

### A4. Context-injection review
- Classify every prose rule: (a) duplicate-of-L2 (hook/verifier already enforces) → cut to ≤3 lines + pointer; (b) mechanizable → convert to script/hook then slim; (c) judgment/proactive → KEEP INJECTED (output-time rules silently die if moved on-demand); (d) stale → fix or delete.
- Always-injected realistic ceiling ≈ −25%; code-session tier ≈ −60% (2026-06-10 measured).
- Generated blocks (mir:profile / mir:generated markers) are single-SoT; hand prose duplicating them is class (a).

### A5. Token budget standard
- Fixed per-session injection target: ≤ ~9K tok (mir-self class), ≤ ~8K (template adopters), family CLAUDE.md ≤ 12KB.
- SessionStart stdout hard cap 10,240B (UTF-8-safe truncation) — fleet-wide invariant since Wave 3.
- Ledger budgets via `config/doc-size-guard.json` (deterministic WARN at session start): plan.md 800 lines, tdd.json 20,000 lines, lessons.md 600 lines. Exceed → run archiver, never hand-trim.
- Whole-file reads of ledgers are the top historical waste (2026-06-09 audit: read/grep ≈ 90% of original tokens) — prefer ranged reads; keep ledgers under budget so whole-reads stay cheap when they happen.

### A6. Contract-pin awareness
- Literal-string contract tests (tests/test_harness_contracts*.py, scripts/verify_template_applied_state.py ROLE_POLICY_SNIPPETS) pin prose. Any wording dedupe MUST update pins in the same change, and pins must target the surviving single-SoT text.
- Baseline isolation: when classifying a failure as pre-existing, the control must cover ALL repos the test touches (mir-self stash does NOT control template-side state — 2026-06-10 e2e misclassification case).

## B. Improvement Criteria (when changing the harness)

### B1. Script/hook conversion rule
- Repeated deterministic judgments move from LLM prose to script/hook/test/guard. Block messages must self-describe the violated rule (reactive teaching at zero steady-state token cost).
- NEVER convert: proactive output-time behavioral rules (verify-before-report, no-fabricated-excuse, reply-tool discipline) — these only work injected.
- Token saving never outranks verification power. If a cut weakens TDD/review/verification/safety wording, keep the prose.

### B2. Risk tiers and wave separation
- Low (apply same session): advisory-surface dedupe with pins updated, config budgets, generated-surface re-render via the real renderer, verified launchd arg repair.
- Medium (separate wave, design + co-ship requirements): ledger archival touching contract-referenced data (pinned-id protection mandatory), prose splits that need a pointer-hook co-ship (F8 bluebricks class), enforcement-hook logic changes.
- High (user approval required): role-policy semantic changes, profile_compiler full `--apply` (writes 13 artifacts; `--target` is IGNORED in apply mode — lesson), anything touching sealed-5.

### B3. Repo/fleet write safety
- mir-self code paths (tools/, src/, scripts/): delegated Codex lane only (hook-enforced).
- Other family repos: Bash channel only, fleet-admin elevation recorded in tasks/plan.md BEFORE write (target_repos/surfaces/reason/verification), local commit per repo, NO push without explicit user approval.
- Sealed-5: untouched without user override; external push now hard-BLOCKED by pre-tool-use guard (F9).
- Fleet apply scripts: dry-run first, per-repo verification (`bash -n`, live-run bounds, label checks), auto-rollback on verification failure, idempotency proven by re-run.

### B4. Pre-push checklist (every repo, every push)
1. `git status` + `git diff --stat` reviewed; only intended files staged (explicit path-list staging).
2. Leak scan: absolute private paths, family slugs, emails, tokens/secrets → 0 hits (template pushes especially).
3. Tests: full suite run directly, EXIT/summary line read (no `; echo` masking); failures classified new-vs-pre-existing with a valid baseline control (B/A6).
4. Remote + branch verified against the dual-repo topology (mir-self → `private` remote; template → public origin; families → no push by default).
5. Generated surfaces regenerated by their real generators (never hand-edited inside markers).

### B5. Evidence discipline
- Every claim in a final report traces to a measured number or an executed command output.
- Evidence sink: tasks/reports/<topic>-<date>.md with §measured-before/after.
- Lessons → memory DB (`uv run mir memory insert --predicate lesson ...`), not new always-injected prose.

## C. Fleet-Wide Review Method (mir-self + template + all active repos)

### C1. Scope matrix
| Repo class | Members (SoT: config/fleet-harness-state.json `families`) | Review depth | Write policy during review |
|---|---|---|---|
| mir-self | <repo-root> | full (all 3 pillars + full suite) | normal lanes (code via Codex) |
| template | <template-repo> | full + sanitize + parity | Bash channel; push only after B4 |
| active families | your families | all 3 pillars, read-only first; fixes via recorded waves | Bash channel + elevation record; local commit, NO push without approval |
| sealed-5 | sealed repos | read-only observation only | UNTOUCHED (push hard-blocked by hook) |

### C2. Three review pillars (run all three per repo class)
**P1 Structure** — hooks wiring per A3 (incl. sub-dispatch + manual-trigger allow-lists), generated surfaces (markers intact, regenerated by real generators), `tools/harness_consistency` self-check (R1–R17) per repo, applied-state verifier (template↔mir-self), launchd/cron exit codes, settings.json permission rules valid.
**P2 Token efficiency** — A1 rubric + A2 measurements + A5 budgets per repo; fixed-injection table (CLAUDE.md / AGENTS.md / SessionStart stdout / skills+agents descriptions); ledger sizes vs doc-size-guard budgets.
**P3 Agent management** — catalog ↔ disk consistency: `python scripts/verify_repo_agent_management.py` (active_agents/active_skills refs resolve; family-specific externals registered), `python -m tools.fleet_skill_sync` (deployed skills = LATEST vs canonical), R17 agent_surface_contract findings, profile drift (`family=` labels, role-policy generated blocks vs `.mir/repo-profile.toml` — render-compare, do NOT full-apply), sub-agent contract regression tests green.

### C3. Standard execution recipe (per design-process 5-step)
1. **Step 1**: capture design_goals; pull prior reports + lessons (`uv run mir memory query <topic>`); snapshot BEFORE measurements (A2).
2. **Step 2 — cold sub-agents (≥3, parallel)**: (a) mir-self inventory+measure, (b) template parity+sanitize+measure, (c) fleet scan (one agent per ~10 repos), (d) optional mechanism-classification. Sub-agent outputs are claims, not facts: cross-check per A2-4 (uniform values, git states, stdout sizes — re-measure ≥2 directly).
3. **Step 3**: integrate into per-surface scorecard + risk-tiered improvement features (B2).
4. **Step 4**: fresh codex-final-reviewer instance per round; converge per design-process §4 (2–3 rounds, circuit breaker).
5. **Step 5**: execute in waves — Wave 1 advisory-direct, Wave 2 Codex lanes (code), Wave 3+ fleet Bash-channel (elevation recorded BEFORE write, dry-run → apply → per-repo verify → auto-rollback → idempotency re-run). AFTER measurements into the evidence sink; full suite + classification of any failure (A6 baseline-control validity).
6. Close: lessons → DB, projections re-rendered, criteria doc updated if the method itself changed, backups refreshed (`python -m tools.backup_collector collect-fleet`) when the wave touched family repos.

### C4. Deterministic verifier command set (run per review; zero-LLM-token)
> Note: several entries below (`tools.harness_consistency`, `tools.fleet_skill_sync`, `mir doc-guard`, `verify_template_applied_state.py`) belong to the full Mir harness and are NOT wired into this template's minimal CLI subset — run them from the full harness, or skip on a fresh clone.
```
uv run python -m tools.harness_consistency run            # mir-self self-check R1–R17
uv run python scripts/verify_repo_agent_management.py     # catalog ↔ profiles ↔ disk
uv run python -m tools.fleet_skill_sync                   # deployed skills vs canonical
uv run python scripts/verify_template_applied_state.py --template <T> --mir-self <M> --format json
uv run mir doc-guard --config config/doc-size-guard.json --project-dir <repo>
uv run pytest -q                                          # full suite, read summary line directly
launchctl list | grep com.mir                             # cron exit codes
```

### C5. Cadence
- Deterministic scans: weekly (existing Monday fleet scan) + per-session doc-guard — zero LLM tokens.
- Full 3-pillar fleet review: user-triggered (this document is the entry point); do not auto-fire.
- Re-entry rule: a new full review starts from THIS document + the latest evidence-sink report — do not re-derive the method.
