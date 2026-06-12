---
status: design-v1
date: 2026-05-25
scope: external family repositories operational verification and score-improvement preparation
audience: your-harness control plane
---

# External Repo Operational Verification Phase

> Purpose: define the ordered phase queue, pre-check gates, abort rules, and score-review shape before sequential operational verification starts across external family repositories.

## 1. Scope

Included targets:

1. `example-notes`
2. `example-app`
3. `example-brand`
4. `example-game`
5. `example-personal`
6. `example-video`
7. `example-content`
8. `example-story`
9. `example-stock`
10. `example-learning`
11. `example-infra`
12. `example-service` (hermes)
13. `example-service` (openclaw)
14. `example-service` (router-control)

Excluded from this phase:

- `your-harness` — self host, already handled by separate example-harness application docs
- `template-harness` — public template, structural verification only
- `claude-starter` — sealed reference template, not the next active external target

## 2. Decision

External repository work proceeds in ordered waves, not ad hoc.

Each repository must complete one verification phase before any repo-local fix wave starts:

1. path and dirt check
2. repository-local verifier discovery
3. current operational verification run
4. current AI score snapshot capture
5. bounded fix-seam selection
6. post-fix re-verification and score re-check

This document is the reusable preparation layer for that sequence.

## 3. Queue By Phase

### Phase A — application-first, low-control-plane risk

Run first because they are active product or content surfaces and do not sit on the infra/control-plane edge.

1. `example-notes`
2. `example-app`
3. `example-brand`
4. `example-game`
5. `example-personal`
6. `example-video`
7. `example-content`
8. `example-story`

### Phase B — partial-adoption or learning-workspace follow-up

Run after Phase A because they either have known partial adoption or a narrower learning-workspace operating model.

9. `example-stock`
10. `example-learning`

### Phase C — infra/runtime or higher blast-radius repos

Run later because verifier drift or fixes are more likely to touch runtime, infra, or shared control surfaces.

11. `example-infra`
12. `example-service` (hermes)
13. `example-service` (openclaw)

### Phase D — sealed or effectively suspended tail

Run only after the earlier phases are clean or when explicitly reactivated.

14. `example-service` (router-control)

## 4. Standard Pre-Check

Before touching any external repository:

1. Confirm the repository path from `config/repos/<slug>.json`.
2. Run `git status --short` in the target repository and record existing dirt.
3. Identify available local gates:
   - `scripts/verify_context_paths.py`
   - `scripts/verify_codex_sync.py`
   - repo-native test entrypoint
   - family-specific verifier or score script if present
4. Capture the current your-harness fleet score from `config/fleet-harness-state.json`.
5. Do not select a fix seam until the first verification pass is complete.

## 5. Abort Rules

Abort the repository wave before writes when:

- repository path cannot be resolved from `config/repos/<slug>.json`
- working tree dirt overlaps the candidate fix surface
- no local verification command can be identified and the repo is not explicitly bootstrap-only
- the fix would widen from harness verification into unrelated product behavior
- a sealed repository requires broad rewrites rather than a bounded operational fix

Abort after verification and do not write when:

- the failure is only an environmental dependency absence with no repository defect
- the candidate improvement would need cross-repository policy change first
- the local score cannot be measured and there is no structural substitute to improve

## 6. Review Record Shape

Each repository review note should capture:

1. repository path
2. baseline git dirt snapshot
3. verification commands run
4. pass/fail summary
5. baseline AI score
6. top score drag factors
7. chosen bounded fix seam
8. post-fix verification result
9. post-fix AI score or reason why score remains unmeasurable

## 7. Target Matrix

| Order | Slug | Phase | Family Type | Sealed | Baseline AI Score | Baseline Gate Surface | Primary Caution |
|---|---|---|---|---:|---:|---|---|
| 1 | `example-notes` | A | `code_app` | no | 50 | `verify_context_paths`, `verify_codex_sync`, `pubspec.yaml` | Flutter repo; keep fixes bounded to harness or verifier drift first |
| 2 | `example-app` | A | `SE-product` | no | 48 | `verify_context_paths`, `verify_codex_sync`, `pubspec.yaml` | Flutter repo with preserved history; avoid widening into reader product behavior |
| 3 | `example-brand` | A | `code_app` | no | 68 | no common harness gate discovered yet | bootstrap-style discovery first; do not assume shared verifier layout |
| 4 | `example-game` | A | `code_app` | no | 48 | `verify_context_paths`, `verify_codex_sync`, `pubspec.yaml` | Flutter repo; verify analyzer/test entrypoints before edits |
| 5 | `example-personal` | A | `SE-product` | no | 54 | `verify_context_paths`, `verify_codex_sync` | content/personal workspace shape; expect structural rather than runtime score improvements |
| 6 | `example-video` | A | `hybrid_pipeline` | no | 53 | `verify_context_paths`, `verify_codex_sync` | avoid widening into media pipeline runtime unless verification directly points there |
| 7 | `example-content` | A | `hybrid_pipeline` | no | 50 | `verify_context_paths`, `verify_codex_sync` | content pipeline repo; keep first fixes in harness/verifier layer |
| 8 | `example-story` | A | `hybrid_pipeline` | no | 39 | `verify_context_paths`, `verify_codex_sync` | lowest baseline score; likely highest payoff but still keep first slice bounded |
| 9 | `example-stock` | B | `hybrid_pipeline` | yes | 56 | `verify_context_paths`, `verify_codex_sync` | sealed; only bounded operational fixes allowed |
| 10 | `example-learning` | B | `SE-product` | yes | 50 | `verify_context_paths`, `verify_codex_sync` | learning workspace; local score scripts exist, but keep scope repo-local |
| 11 | `example-infra` | C | `code_app` | no | 61 | `verify_context_paths`, `verify_codex_sync` | infra-adjacent runtime; avoid operational fixes that widen into deploy wiring |
| 12 | `example-service` (hermes) | C | `code_app` | no | 58 | `verify_context_paths`, `verify_codex_sync` | infra/runtime repo; expect env-specific verification constraints |
| 13 | `example-service` (openclaw) | C | `code_app` | yes | 58 | `verify_context_paths`, `verify_codex_sync` | sealed and infra/runtime flavored; late-wave only |
| 14 | `example-service` (router-control) | D | `code_app` | yes | 61 | `verify_context_paths`, `verify_codex_sync`, `package.json` | sealed and effectively suspended; verify only if explicitly reactivated |

## 8. Score Handling Rule

Score review follows this order:

1. Prefer repository-local measurable score if the repo already ships a score script.
2. If local score is not measurable, use the your-harness fleet snapshot in `config/fleet-harness-state.json` as the baseline observation.
3. If neither exists, record the repo as `structural-only` and improve verification shape first.

Current known exception:

- `example-learning` has a local score path under `.claude/skills/ai-readiness-cartography/scripts/score.py`.
- `example-brand` currently requires verifier and score-surface discovery before any score-improvement work can be planned.

## 9. Exit Criterion

This preparation phase is complete when:

1. every next external target is ordered into a phase queue
2. every target has a resolved repository path
3. every target has a baseline gate surface or an explicit discovery warning
4. sealed and deferred repositories are explicitly marked
5. the control plane can start repository-by-repository verification without inventing new rules mid-run

## 10. Next Step

Start with `example-notes` as Wave 1.

For each wave:

1. run baseline operational verification
2. capture baseline AI score
3. choose one bounded improvement seam
4. re-run verification
5. record score delta or measurement limitation
