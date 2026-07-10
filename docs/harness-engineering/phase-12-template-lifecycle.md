---
phase: 12
title: Template Lifecycle
status: design-v1
depends_on: [mir-roles, phase-9, phase-10]
date: 2026-05-23
---

# Phase 12 -- Template Lifecycle (Template Sunset + Upgrade Migration)

> **Purpose**: Lifecycle management for the public template repo (`mir-yoke`) -- version-lag detection, upgrade migration runbook, sunset / hand-off / fork. The lifecycle lane for Role B (Template Maintainer).

## 0.5 Design Goals (R10 anchor)

**3-axis contribution**:
- **Axis I (self-harness hardening)**: automating template lifecycle operations for the central harness as agent (Role B)
- **Axis II (public template sync)**: explicit fleet migration procedure when the template version changes
- **Axis III (fleet central management)**: track `adopted_version` for N families + version-lag detection + upgrade orchestration

**Inter-phase contract**:
- **Input** (consumes): [phase-9](phase-9-fleet-catalog.md) (catalog per-family `adopted_version`) + [phase-10](phase-10-rollout-pipeline.md) (3-stage promote) + [roles doc §3 Role B](mir-roles.md)
- **Output** (provides): template version bump decision + upgrade migration runbook + sunset/hand-off procedure -> [phase-11](phase-11-back-propagation.md) (drift detector 6th kind `version_lag`) + Discord notification

## 1. Template 4 Lifecycle Stages

```text
[CREATE] -> [MAINTAIN] -> [DEPRECATE] -> [SUNSET]
              | (version bumps)
              [LIVE w/ versions v1.0 -> v1.1 -> v2.0 -> ...]
```

Owner of each stage = central harness as agent (Role B). Stages requiring operator review are explicitly noted.

### 1-1. CREATE
- Initial template repository creation.
- Initial baseline = self-harness state at adoption point (sanitized).
- When bootstrapping: create `VERSION` file + first tag before landing new phases.

### 1-2. MAINTAIN -- Normal version bump
- PATCH (`vN.M.X+1`): drift fix, doc typo, broken link, dependency security patch
- MINOR (`vN.M+1.0`): new phase / hook / skill, backwards-compatible extension
- Detailed procedure: [`applications/template-repo/versioning.md`](applications/template-repo/versioning.md)

### 1-3. DEPRECATE -- phase / hook / skill sunset
- Central harness as agent (Role B) decides deprecation of a phase / hook / skill
- Triggers:
  - New phase N+1 supersedes phase N (e.g., schema change when existing code lands)
  - Usage 0 (phase-8 GC result)
  - Security incident (security / data corruption)
- Procedure:
  1. Add deprecation notice to template `CHANGELOG.md` + planned sunset date (90 days out)
  2. Discord notification -- alert affected families
  3. 90-day grace period -- operator migration window
  4. Sunset date arrives -> MAJOR version bump + item removed
- Operator review required (no forced sunset)

### 1-4. SUNSET -- template repo itself changes

| Sunset Type | Description | Procedure |
|---|---|---|
| **Archive** | Freeze template repo as read-only | (a) archive notice in `CHANGELOG.md` (b) fleet 90-day notification (c) catalog `family_type: archived_template` label (d) freeze `adopted_version` for all families at last active version |
| **Replace** | Migrate to new template repo (`mir-yoke-v2`) | (a) bootstrap new repo (b) 6-month dual-live (c) family migration cadence (d) archive old repo |
| **Rename** | Same owner, URL change only | (a) verify old URL -> new URL redirect (b) update `template_repo_url` in fleet config (c) 7-day grace |
| **Fork** | External owner forks for independence | (a) fork gets `family_type=template` separate catalog entry (b) cross-pollination decision between two templates (not maintained by central harness) |

For each sunset type: mandatory impact assessment for all managed families + explicit migration path.

## 2. Version-Lag Detection (6th kind in phase-11 §2)

### 2-1. Detection Targets
| Kind (phase-11 §2-1) | What is Detected |
|---|---|
| 1 new skill | New SKILL.md in family `.claude/skills/` |
| 2 new hook | New hook file in family `.claude/hooks/` |
| 3 new agent | New agent frontmatter in family `.claude/agents/` |
| 4 new phase pattern | New section in family `docs/harness-engineering/` |
| 5 config evolution | New field in family `config/repos/<self>.json` |
| **6 version_lag (new)** | **family `adopted_version` < template `current_version`** |

### 2-2. version_lag detector algorithm (pseudocode)
```python
def detect_version_lag(family_state: FamilyState, template_version: str) -> Optional[VersionLag]:
    adopted = family_state.get("template_version") or family_state.get("adopted_version")
    if adopted is None:
        return VersionLag(severity="unknown", reason="adopted_version not set")

    current = parse_semver(template_version)
    behind = parse_semver(adopted)

    diff = current - behind
    if diff.major > 0:
        return VersionLag(severity="major", behind_by=diff, requires_user_review=True)
    elif diff.minor > 0:
        return VersionLag(severity="minor", behind_by=diff, requires_user_review=False)
    elif diff.patch > 0:
        return VersionLag(severity="patch", behind_by=diff, auto_eligible=True)
    return None
```

### 2-3. Reporting
- After daily scan, append version_lag entry to `config/fleet-drift-log/<family>-<ts>.json` when applicable.
- Weekly Discord digest: "N families behind by >= 1 MINOR" summary.
- Monthly: "Recommend family X upgrade to vN+1" operator recommendation.

## 3. Upgrade Migration Runbook (Per Bump Type)

### 3-1. PATCH bump (auto-eligible)
template `v1.2.3` -> `v1.2.4`
- Changes: drift fix / doc / broken link / dep security
- Impact: 0 (backwards compatible guaranteed)
- Procedure:
  1. Scan detects `version_lag.severity=patch`
  2. Discord notification (advisory only)
  3. Family owner chooses (option a) auto upgrade -- central harness updates family `adopted_version` + Discord notify, (option b) skip -- family declines
  4. 30-day timeout -> auto upgrade

### 3-2. MINOR bump (opt-in advisory)
template `v1.2.3` -> `v1.3.0`
- Changes: new phase / hook / skill / backwards-compatible extension
- Impact: family stays compatible even without adopting
- Procedure:
  1. Scan detects `version_lag.severity=minor`
  2. New capability summary in weekly Discord digest
  3. Family owner decides in `recommendations_received` (adopted / declined / pending 30d)
  4. On adoption: follow family cherry-pick procedure (template-cherrypick.md §6 6-step)
  5. After decision: central harness updates family `adopted_version`

### 3-3. MAJOR bump (guided migration)
template `v1.x.y` -> `v2.0.0`
- Changes: breaking -- phase rename / schema field removal / hook signature change / family_type change
- Impact: families not adopting may have future hooks/scripts stop working
- Procedure:
  1. Central harness requests operator review 90 days before MAJOR bump decision (CHANGELOG breaking change pre-notice)
  2. At MAJOR bump, detect -> `version_lag.severity=major` + `requires_user_review=true`
  3. Impact assessment:
     - Which families are affected by breaking changes (per-family override analysis)
     - Per-family migration procedure (template `MIGRATION.md` vN->vN+1 section)
  4. Discord priority alert -- individual notification to each family owner
  5. 6-month grace period -- family chooses vN or vN+1
  6. After grace: central harness stops tracking vN (catalog family row `adopted_version` stale label)

### 3-4. Conflict Resolution
When a family has customizations that differ from the template baseline:
- PATCH conflict: skip (family customization wins)
- MINOR conflict: family review required (3-way merge: template baseline / family override / operator decision)
- MAJOR conflict: explicit operator review

## 4. Hand-off Protocol

When the central harness as agent can no longer perform Role B (e.g., operator changes, fork, self-archive).

### 4-1. Hand-off Types
| Type | Description |
|---|---|
| Sub-agent hand-off | Central harness delegates Role B to another agent |
| User-self hand-off | Operator maintains template repo directly (central harness keeps Role A only) |
| Successor hand-off | New generation agent takes over |
| Fork hand-off | External owner forks template -> Role B separates |

### 4-2. Hand-off Procedure
1. Hand-off decision (explicit operator instruction)
2. Record current state:
   - Self-health snapshot
   - All in-progress innovation triage decisions
   - Last template promote + version
   - Incomplete maintenance tasks (e.g., pending CVE patch)
3. Transfer to new agent / owner:
   - Read access to `fleet-harness-state.json`
   - Write access to template repo (Role B authority)
   - Dependency: ADR-40 charter agreement
4. Verification:
   - New agent performs first daily scan live
   - New agent runs `sanitize_for_template.py` dry-run in sandbox
   - Discord notification

### 4-3. Format Stability
For the successor agent to maintain catalog compatibility:
- `fleet_harness_state.schema.json` = stable interface
- `family_type` enum (6-Type: SE-meta / code_app / SE-product / hybrid_pipeline / template / [optional reserved]) = stable
- `adoption.status` enum = stable
- Adding new enum value = MINOR (compatible), removing enum value = MAJOR

## 5. Template Repo CI / Pre-commit (Under Role B)

### 5-1. Template Repo `.github/workflows/`
- `validate.yml`: on every PR -- schema validation + link check + sanitize verify + role-policy parity verify
- `release.yml`: on every version tag -- auto-update CHANGELOG + Discord notify
- `daily_health.yml`: daily cron run of `template_health.py`

### 5-2. Template Repo `.claude/hooks/`
- `pre-commit-verification.sh`: lint + schema validation
- `tdd-guard.sh`: enforced when adding tests to the template itself

### 5-3. Template Repo `tests/`
- `test_schema_validity.py`: self-validation for all schemas
- `test_hook_executability.py`: hook file syntax + permission
- `test_link_integrity.py`: markdown link resolution
- `test_phase_doc_completeness.py`: verify §0.5 + Exit Criterion + Application Status table exist

## 6. ADR Candidates

- ADR-42 -- Template Lifecycle (sunset + upgrade migration + hand-off)
- ADR-43 -- Template CI / pre-commit charter

## 7. Application Status

| Item | Status | Location |
|---|---|---|
| version_lag detector | landed | `harness_drift.py` `detect_version_lag()` + `_parse_semver()` + kind enum + `tests/test_version_lag.py` |
| Upgrade migration runbook (PATCH/MINOR/MAJOR) | this phase | this §3 |
| Sunset procedure (archive/replace/rename/fork) | this phase | this §1-4 |
| Hand-off protocol | this phase | this §4 |
| Template CI / pre-commit | partial | template repo CI running -- minimum gate includes schema/link/sanitize + role-policy parity verifier |
| Template tests | partial | template repo `tests/` running |
| MIGRATION.md (template repo) | partial | template repo `MIGRATION.md` running |

## 8. Exit Criterion

This phase is done when:
1. 4 lifecycle stages (CREATE/MAINTAIN/DEPRECATE/SUNSET) documented + each stage owner = central harness as agent Role B.
2. version-lag detector spec (§2) + harness_drift.py 6th kind consistent.
3. Upgrade migration runbook (PATCH/MINOR/MAJOR) §3 documented.
4. Hand-off protocol §4 documented.
5. Template CI / tests spec §5 documented.
6. Applied-state verifier passes with main-agent parity + delegated Codex-first contract included.
7. Operator review passed.

## 9. Next Step

The next task after this phase is physical closeout rather than entering a new round. `template_health.py`, `harness_drift.py` version_lag kind, template repo CI/tests, and `MIGRATION.md` are already in landed category. Remaining work is reducing template repo applied-state backlog and continuing to reconcile phase-12/13 docs. No new phase created.
