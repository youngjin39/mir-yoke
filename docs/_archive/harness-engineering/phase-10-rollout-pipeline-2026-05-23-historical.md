---
phase: 10
title: Rollout / Share Pipeline
status: design-v1
depends_on: [phase-7, phase-9]
date: 2026-05-23
---

# Phase 10 -- Rollout / Share Pipeline

> **Purpose**: 3-stage rollout pipeline: self-harness land -> public template baseline update -> managed fleet repository direct apply. For active managed repos, the central harness performs inspect -> patch -> verify -> report.

## 0.5 Design Goals (R9 anchor)

**3-axis contribution**:
- **Axis I (self-harness hardening)**: codify exit criteria and promote trigger for stage 1 (self-harness land + N-round stability verification)
- **Axis II (public template sync)**: stage 2 (template baseline update) -- sanitize + sync runbook + version bump procedure
- **Axis III (fleet central management)**: stage 3 (managed fleet direct apply) -- active managed repos are directly applied/verified/reported by the central harness. Greenfield new projects bootstrap from the stage 2 template.

**Inter-phase contract**:
- **Input** (consumes): phase-9 (fleet-harness-state.json + drift detection result) + phase-7 (family adoption decision + family_type)
- **Output** (provides): template repo PR + family share recommendation event -> phase-11 (innovation back-propagation trigger)

## 1. 3-Stage Pipeline Overview

```text
[Stage 1: Self-harness land + stability verification]
   | (exit: N-round stable + operator review)
[Stage 2: Template baseline update]
   | (exit: sanitize + verify + PR merged)
[Stage 3: Managed fleet direct apply]
   | (exit: inspect + patch + verify + report)
[fleet-harness-state.json update + phase-11 trigger]
```

Stages 1, 2, 3 are all part of the central harness operations pipeline. In stage 3, the central harness applies directly to active managed repos without waiting for family owner opt-in. Sealed/suspended/exception repos are separated into their own boundary.

## 2. Stage 1 -- Self-Harness Land + Stability Verification

### 2-1. Entry Conditions
- New phase / hook / skill / agent landed in self-harness (commit hash secured).
- `design` skill `design_goals` 5-field capture complete.
- Related test / regression added (where applicable).

### 2-2. Stability Verification (N rounds)
- Audit round 1+ (4-slice cold-context baseline).
- Operator review passed (Discord or explicit approval).
- Zero findings for the same artifact (or operator deferral explicit).
- **Minimum cadence**: 1 round (low risk) ~ 3 rounds (high risk / new phase).

### 2-3. Stage 1 Exit Criteria
| Item | Condition |
|---|---|
| commit hash | `git log --oneline -1 -- <path>` secured |
| design_goals capture | all 5 fields non-vacuous |
| audit round | >= 1 round, 0 findings |
| operator review | explicit approval |
| regression test (where applicable) | passing |

**If exit not met**: do not enter stage 2. Repeat defect fix rounds.

## 3. Stage 2 -- Template Baseline Update

### 3-1. Entry Conditions
Stage 1 exit 100% met.

### 3-2. Sanitize Procedure (mandatory)
Public template = sanitized template. Therefore:
- Korean -> English translation (user-facing strings).
- Family-specific expressions -> generalized ("your-harness" etc.).
- LICENSE preserved (do not modify).
- Private paths / secrets removed.

### 3-3. Sync Procedure
```bash
# 1. local harness -> template sync dry-run
python3 scripts/verify_codex_sync.py --diff

# 2. sanitize auto-apply
python3 scripts/sanitize_for_template.py   --input <your-harness-path>   --apply   --output-dir <template-repo-path>

# 3. version bump (semver)
# Update VERSION file in template repo: PATCH (drift fix) / MINOR (new phase) / MAJOR (breaking)

# 4. PR open
cd <template-repo-path>
git checkout -b <branch-name>
git commit -m "feat: <description>"
gh pr create --title "<title>" --body "..."

# 5. After merge, update template version in fleet-harness-state.json
```

### 3-4. Stage 2 Exit Criteria
| Item | Condition |
|---|---|
| sanitize verifier | exit 0 (0 private traces) |
| diff review | operator explicit approval |
| template PR | merged |
| version bump | tagged |
| `fleet-harness-state.json` | template version field updated |

## 4. Stage 3 -- Managed Fleet Direct Apply

### 4-1. Entry and Inspection
- Immediately after stage 2 merge, central harness confirms managed target repository list.
- Inspect current harness structure of each target repo.
- Confirm repository type, local/private agent topology, exception status.

### 4-2. Minimum Patch Plan
| Step | Action |
|---|---|
| inspect | Check current `.claude/`, `.ai-harness/`, docs/config, local agent/runtime surfaces |
| classify | Determine repository type + exception status |
| plan | Write minimum patch content per repository type |
| apply | Central harness directly applies patch |
| verify | Run per-repo verification commands |
| report | Record applied features, agent status, verification results, AI score report |

### 4-3. Apply Procedure
Apply new phase / hook / skill / agent from template or central source to target family repo.

1. Central harness writes minimum patch plan
2. Directly patch target repo
3. Per-repo verification
4. Update `fleet-harness-state.json` and per-repo report

### 4-4. Stage 3 Exit Criteria (per-family)
| Item | Condition |
|---|---|
| inspection snapshot | current harness structure recorded |
| minimum patch plan | minimum patch content per repository type recorded |
| family commit | change hash secured |
| verification | per-repo verification result recorded |
| central state cache | relevant family status in `fleet-harness-state.json` updated |
| report | report generated including applied features, agent status, AI score |

## 5. Greenfield Bootstrap Path (Stage 2 artifact)

New project bootstrap:

### 5-1. Procedure
```bash
# 1. Clone from template
git clone https://github.com/<org>/mir-yoke new-project
cd new-project

# 2. Family-specific initialization
python scripts/bootstrap.py   --family-name new-project   --family-type SE-product   --enabled-phases 0,1,2,3,4,5,6,7,8

# 3. CLAUDE.md / AGENTS.md auto-modified to match family name
# 4. config/repos/<new-project>.json created (family_type + adoption baseline)
# 5. Central harness registers new family row in fleet-harness-state.json

# 6. First commit + push
git remote set-url origin <new repo>
git commit -m "bootstrap: harness engineering from mir-yoke v<version>"
git push -u origin main
```

### 5-2. Bootstrap Verification
- New family passes phase-0 (Foundations) agreement procedure.
- Main-orchestrator can make the 5-element declaration.
- Pre-edit hook fire verified in practice (TDD ledger operational).
- New family row in central state cache shows phase-0~8 all `adopted` or `opt_in_pending`.

### 5-3. Default enabled_phases by family_type
| family_type | default enabled |
|---|---|
| SE-meta | 0,1,2,3,4,5,6,7,8,9,10,11 (all) |
| code_app | 0,1,2,3,4,5,6,7,8 |
| SE-product | 0,1,2,4,5,6,7,8 (3 partial, 9-11 catalog tracking only) |
| hybrid_pipeline | 0,1,2,3,5,7,8 (4 off, 6 partial) |
| content_app | 0,1,7,8 (minimum) |

See `applications/exceptions.md` section 3 matrix for the latest view.

## 6. Stage Transition Automation / Manual

| Transition | Automatic / Manual | Trigger |
|---|---|---|
| Stage 1 -> Stage 2 | Manual (operator review) | "Approve stage 2 entry" |
| Stage 2 -> Stage 3 | Automatic (after template merge) | `gh pr merged` event |
| Stage 3 inspect/apply | Automatic or operator-run | Managed rollout wave |
| Stage 3 -> catalog/report update | Automatic or operator-run | After verify completes |

## 7. Application Status

| Item | Status | Location |
|---|---|---|
| 3-stage pipeline doc | this phase | this file |
| sanitize verifier | landed | `scripts/verify_codex_sync.py` + `scripts/sanitize_for_template.py` |
| `sanitize_for_template.py` | landed | `scripts/sanitize_for_template.py` |
| `bootstrap.py` | partial | `scripts/bootstrap.py` (family-type default phases absent) |
| share dispatcher | landed | `tools/fleet_observe/share_dispatcher.py` |
| revert window automation | not yet implemented | manual cadence |

## 8. Exit Criterion

This phase is done when:
1. 3-stage doc published (this file).
2. Stage 2 sanitize + sync procedure executable (manual or scripted).
3. Greenfield bootstrap verified once (mock or real family).
4. At least 1 managed target repository verified with inspect -> patch -> verify -> report.
5. Operator review passed.

## 9. Next Step

[Phase 11 -- Back-Propagation](phase-11-back-propagation.md). Phase 10 (forward share) is self-harness -> fleet; Phase 11 (back-propagation) is family innovation -> self-harness -> other family share (reverse direction).

## 10. DispatchBrief Propagation Note

The `DispatchBrief + tiered gates` family should use a dedicated rollout playbook rather than free-form recommendation only.

Propagation rule:
- Public template baseline ships advisory defaults plus `tiny / normal / heavy` triage
- Maintainer workspaces may dogfood stronger strictness
- Family repositories are patched directly by the central harness according to repository type and current-state inspection
