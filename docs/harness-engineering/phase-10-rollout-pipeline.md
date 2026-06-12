---
phase: 10
title: Rollout Pipeline
status: consolidated-v1
depends_on: [phase-7, phase-9]
---

# Phase 10 — Rollout / Share Pipeline

> **Purpose**: Define a 3-stage pipeline — your-harness land + stability verification → template baseline update → managed fleet direct apply — so that improvements to your-harness are consistently shared to the public template and all fleet families.

## 0.5 Design Goals (R9 anchor)

> This phase's connection to the [3-axis fleet goals](applications/fleet-catalog.md). When adding a new phase or cherry-picking for a family, the `design` skill (R9-T11) requires `design_goals` as a mandatory input.

**3-axis contribution**:
- **Axis I (your-harness hardening)**: N-round stability verification standard before your-harness land → template promotion decision
- **Axis II (public template sync)**: sanitize procedure mandatory in Stage 2 + template baseline diff review
- **Axis III (fleet central governance / back-propagation)**: Stage 3 managed fleet direct apply — Minimum Patch Plan → per-family apply → verify → report loop

**Inter-phase contract**:
- **Input** (consumes): phase-9 (fleet-harness-state.json current state + drift log) + phase-7 (family_type + rollout_class)
- **Output** (provides): template baseline update commit + per-family patch result + `fleet-harness-state.json` status update → phase-11 back-propagation trigger

## 1. 3-Stage Pipeline Overview

```text
Stage 1 (your-harness)
  land → N-round stability verification → Stage 2 entry

Stage 2 (Template Baseline)
  sanitize → template sync → exit criteria → Stage 3 entry (automatic)

Stage 3 (Managed Fleet)
  inspect → classify → minimum patch plan → apply → verify → report
```

Stage transitions:
- Stage 1 → Stage 2: **manual** (user decision)
- Stage 2 → Stage 3: **automatic** (exit criteria satisfied)

## 2. Stage 1 — your-harness Land + Stability Verification

### Entry Conditions
- Implementation complete (code + TDD + review passed)
- Merged to main branch
- fleet-harness-state.json updated (Phase 9)

### N-Round Stability Verification

| Round | Check | Pass Criterion |
|---|---|---|
| R1 | `uv run pytest` full suite | 0 failures |
| R2 | `scripts/verify_repo_agent_management.py` | 0 WARN/ERROR |
| R3 | `fleet_observe scan` | no new WARN |
| R4 | Manual smoke test (1 representative task) | expected behavior confirmed |
| R(N) | Repeat R1–R4 for N consecutive sessions | All rounds pass |

**N selection**: Minimum N=2 for routine changes. N=3 or more recommended for changes affecting hooks, enforcement, or fleet-wide policy.

### Exit Criteria (Stage 1 → 2)

| Criterion | Status |
|---|---|
| All N rounds pass | required |
| No regressions in fleet-harness-state.json | required |
| User explicitly approves Stage 2 entry | required |

## 3. Stage 2 — Template Baseline Update

### Sanitize Procedure (mandatory)

Before writing to the template repository, apply ALL of the following sanitization rules:

1. **Path replacement**: `<your-harness-path>/` → `<your-harness-path>/` (use generic placeholder)
2. **Family name replacement**: use generic names (example-harness, example-app, etc.) for all private family names
3. **Korean text**: translate all Korean text to English
4. **Private references**: remove or genericize all organization-specific names, URLs, and identifiers

Sanitization verification:
```bash
# Run after copy — confirm zero private strings remain
grep -r "your-private-org" <template-harness-path>/docs/harness-engineering/
grep -r "private-family-name" <template-harness-path>/docs/harness-engineering/
```

### Sync Procedure

```bash
# Example sync — adjust paths for your environment
SOURCE="<your-harness-path>/docs/harness-engineering/"
TARGET="<template-harness-path>/docs/harness-engineering/"

# Copy sanitized files (sanitize first, then cp)
cp "$SOURCE/phase-N-sanitized.md" "$TARGET/phase-N-baseline.md"

# Verify sanitization gate
scripts/verify_codex_sync.py --check-sanitize "$TARGET"
```

### Exit Criteria (Stage 2 → 3)

| Criterion | Status |
|---|---|
| All sanitization checks pass (0 private strings) | required |
| Template baseline diff reviewed by user | required |
| `scripts/verify_codex_sync.py` passes | required |
| Stage 3 auto-triggered | automatic on above pass |

## 4. Stage 3 — Managed Fleet Direct Apply

### Entry Conditions
- Stage 2 exit criteria all satisfied
- Target family's `fleet-harness-state.json` entry confirms `patch_planned` or `in_review` status

### Inspection Phase

Before applying any patch, run inspection:
```bash
# Survey target family current state
tools/fleet_observe/mir_manage.py --check-family <family-name>
```

Review output for:
- Current phase adoption status
- Existing customizations that must be preserved
- Conflicts with the incoming patch

### Minimum Patch Plan Table

| Step | Action | Owner | Verification |
|---|---|---|---|
| inspect | Survey family current state | your-harness | fleet_observe report |
| classify | Determine applicable phases + exceptions | your-harness | family_type matrix |
| plan | Write minimum patch plan (touched files + expected diffs) | your-harness | user review |
| apply | Apply patch to target family | your-harness (Bash channel) | git diff check |
| verify | Run family verification suite | your-harness | pytest / verifier pass |
| report | Update fleet-harness-state.json + per-family report | your-harness | state entry updated |

### Apply Procedure

Cross-repo writes use the Bash channel (ADR-52):
```bash
# Example: apply patch to a managed family
cd /tmp && git --git-dir=<family-repo>/.git --work-tree=<family-repo> \
  apply <patch-file>

# Verify after apply
cd <family-repo> && uv run pytest
```

Record every cross-repo fleet apply in `tasks/plan.md` or active handoff note with:
- target_repos
- surfaces modified
- reason
- verification result

### Exit Criteria (per-family)

| Criterion | Status |
|---|---|
| Patch applied cleanly (no conflicts) | required |
| Family verification suite passes | required |
| fleet-harness-state.json entry updated to `verified` | required |
| Per-family report written | required |

## 5. Greenfield Bootstrap Path

For new families with no prior harness adoption, use the bootstrap procedure instead of Stage 3 direct apply:

```python
# bootstrap.py — registry_entry auto-estimate example
# Replace 'example-brand' with the actual family name

from bootstrap import registry_entry

entry = registry_entry(
    family_name="example-brand",
    family_type="code_app",
    rollout_class="bootstrap_only"
)
print(entry)
```

Bootstrap procedure:
1. `bootstrap.py registry_entry` — auto-estimate config
2. User confirmation of estimated values
3. `scripts/verify_repo_agent_management.py` dry-run advisory pass
4. Apply Phase 0 baseline (hooks + CLAUDE.md + basic catalog)
5. fleet-harness-state.json entry created with `patch_applied` status

## 6. Stage Transition Table

| Transition | Trigger | Condition |
|---|---|---|
| Stage 1 → Stage 2 | Manual (user decision) | N-round stability verification complete + user approval |
| Stage 2 → Stage 3 | Automatic | All Stage 2 exit criteria satisfied |
| Stage 3 repeat | Per-family loop | Repeat for each family in batch |
| Rollback | Manual | Any stage: revert to prior baseline on failure |

## 7. Application State

| Item | Status | Location |
|---|---|---|
| Stage 1 N-round stability verification | partial land | pytest + verifier in use; N-round formal cadence is follow-up |
| Stage 2 sanitize procedure | land | `scripts/verify_codex_sync.py` + template-sync-validator |
| Stage 3 direct apply | land | Bash channel ADR-52 + fleet-admin elevation records |
| Minimum patch plan | land | per-family plan + report pattern established |
| Greenfield bootstrap | land | `bootstrap.py` + registry_entry |
| Rollback procedure | partial land | git revert available; automated rollback trigger is follow-up |

**Gap**: Formal N-round cadence documentation + automated Stage 2→3 trigger + rollback automation.

## 8. ADR Candidates

ADR-26 — Rollout Pipeline formalization. ADR-48 — Central Fleet Management and Direct Apply Policy (shared with Phase 9).

## 9. Exit Criterion

At least 1 complete 3-stage cycle executed:
1. your-harness land verified (Stage 1 N≥2 rounds pass)
2. Template baseline updated with sanitization gate passing (Stage 2)
3. At least 1 managed family patched + verified + state updated (Stage 3)

## 10. DispatchBrief Propagation Note

When Stage 3 applies patches via delegated execution lane, pass a DispatchBrief containing:
- `target_family`: family name
- `patch_files`: list of files to modify
- `verification_commands`: commands to run post-apply
- `rollback_ref`: git ref to revert to on failure
- `report_target`: location for fleet-harness-state.json update

## 11. Next Steps

Proceed to [Phase 11 — Back-Propagation](phase-11-back-propagation.md). Phase 10 pushes changes downstream (your-harness → fleet). Phase 11 handles the reverse flow (family innovations → your-harness / template).
