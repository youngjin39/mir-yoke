---
status: active
date: 2026-05-28
scope: DispatchBrief rollout playbook — sibling repository deployment
audience: your-harness control plane
---

# DispatchBrief Rollout Playbook (2026-05-28)

> **Purpose**: Step-by-step playbook for rolling out the DispatchBrief default triage contract to all managed family repositories.

## 1. Rollout Package Contents

The rollout package for DispatchBrief consists of:

| File | Target Location | Description |
|---|---|---|
| `dispatchbrief-defaults-2026-05-28.md` | `docs/harness-engineering/applications/` | Default triage contract (already in template) |
| `dispatchbrief-rollout-playbook-2026-05-28.md` | `docs/harness-engineering/applications/` | This file |
| CLAUDE.md DispatchBrief section | Root `CLAUDE.md` | Inline reference to contract defaults |
| AGENTS.md DispatchBrief section | Root `AGENTS.md` | Codex-side reference |

The defaults document is the authoritative source of truth. CLAUDE.md and AGENTS.md contain inline summaries that must stay in sync with it.

## 2. Default Triage Contract

The DispatchBrief triage contract classifies tasks into three sizes:

| Size | Definition | Default Execution |
|---|---|---|
| `tiny` | Single file, bounded scope, no design pass required | Direct execution — no DispatchBrief required |
| `normal` | Multi-file, requires design pass, one execution lane | DispatchBrief to one execution lane |
| `heavy` | Multi-step, multiple execution lanes, or cross-repo | DispatchBrief to orchestrator + sub-lanes |

**Classification rule**: When in doubt, classify up. A misclassified `normal` task treated as `tiny` risks scope creep without a design pass.

## 3. Repository-Type Defaults

Default DispatchBrief behavior by repository type:

| Repository Type | Default Brief | Notes |
|---|---|---|
| SE-meta (your-harness) | Full DispatchBrief for `normal`+ | Hook enforcement changes always require full brief regardless of size |
| SE-product | Full brief for `normal`+ | |
| code_app | Full brief for `heavy`; lightweight for `normal` | |
| hybrid_pipeline | Full brief for `normal`+ | Pipeline runtime changes require full brief |
| template | Full brief always | Template changes propagate fleet-wide |

## 4. Sibling Repository Mapping

Wave-by-wave rollout schedule:

### Wave 1 — your-harness (self-verification)

- `your-harness` (`<your-harness-path>/`)
- Verify: DispatchBrief contract referenced in CLAUDE.md + AGENTS.md

### Wave 2 — Template Baseline

- `template-harness` (`<template-harness-path>/`)
- Sanitization required before write
- Verify: `template-sync-validator` passes + no private strings

### Wave 3 — Active application families

Families ordered by blast-radius (lowest first):

- `example-notes` (`<family-repo-path>/`)
- `example-app` (`<family-repo-path>/`)
- `example-brand` (`<family-repo-path>/`)
- `example-game` (`<family-repo-path>/`)
- `example-personal` (`<family-repo-path>/`)
- `example-video` (`<family-repo-path>/`)
- `example-content` (`<family-repo-path>/`)
- `example-story` (`<family-repo-path>/`)

### Wave 4 — Infrastructure and runtime families

- `example-infra` (`<family-repo-path>/`)
- `example-service` (infra-adjacent, apply with extra care)

**Sealed families**: Apply only when explicitly reactivated by user instruction.

## 5. Adoption Checklist

For each family in the rollout wave:

```
[ ] 1. Read current CLAUDE.md — confirm no conflicting DispatchBrief reference exists
[ ] 2. Read current AGENTS.md — confirm no conflicting reference exists
[ ] 3. Add DispatchBrief section to CLAUDE.md (inline summary referencing defaults doc)
[ ] 4. Add DispatchBrief section to AGENTS.md (Codex-side summary)
[ ] 5. Verify family-specific size classification aligns with repository type defaults
[ ] 6. Run verify_codex_sync.py — confirm CLAUDE.md + AGENTS.md are in sync
[ ] 7. Update fleet-harness-state.json entry: dispatchbrief_adopted: true
[ ] 8. Record in tasks/plan.md or active handoff note
```

## 6. Rollout Sequence

```text
1. your-harness self-verify (Wave 1)
   └── confirm contract is live + referenced
2. Template baseline update (Wave 2)
   └── sanitize + write + template-sync-validator pass
3. Application families (Wave 3, ordered by blast-radius)
   └── per-family adoption checklist
4. Infrastructure families (Wave 4)
   └── extra review for runtime-adjacent changes
5. Post-rollout audit (all waves complete)
   └── agent-recognition audit (see §7)
```

Cross-repo writes use the Bash channel (ADR-52). Record every write in tasks/plan.md with:
- target repos
- surfaces modified
- reason
- verification result

## 7. Post-Rollout Agent-Recognition Audit

After rollout is complete, verify that every family's agent can recognize the DispatchBrief contract:

```bash
# Check that DispatchBrief section is present in each family's CLAUDE.md
grep -l "DispatchBrief" <family-repo-path>/CLAUDE.md

# Check that AGENTS.md is in sync with CLAUDE.md
scripts/verify_codex_sync.py --family <family-name>
```

**Agent recognition requirement**: A harness deployment is not complete until the agent can recognize it. Existence in a file is necessary but not sufficient — the agent must be able to act on the contract in a live session.

## 8. Rollback Procedure

If a family's adoption causes issues:

1. Revert CLAUDE.md and AGENTS.md to their pre-rollout state (git revert)
2. Set `dispatchbrief_adopted: false` in fleet-harness-state.json
3. Record rollback reason in tasks/plan.md
4. Do not re-attempt rollout without diagnosing root cause
