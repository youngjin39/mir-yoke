---
phase: 12
title: Template Lifecycle
status: design-v1
depends_on: [mir-roles, phase-9, phase-10]
date: 2026-05-23
---

# Phase 12 — Template Lifecycle (Template Sunset + Upgrade Migration)

> **Purpose**: Manage the lifecycle of the public template repo (`template-harness`) — version-lag detection, upgrade migration runbook, sunset / hand-off / fork. The lifecycle lane for Role B (Template Maintainer).

## 0.5 Design Goals (R10 anchor)

> This phase's connection to the [3-axis fleet goals](applications/fleet-catalog.md). When adding a new phase or cherry-picking for a family, the `design` skill's `design_goals` 5-field enforcement applies.

**3-axis contribution**:
- **Axis I (your-harness hardening)**: Automate template lifecycle operations for your-harness-as-agent (Role B)
- **Axis II (public template sync)**: Explicitly define fleet migration procedure when template version changes
- **Axis III (fleet central governance / back-propagation)**: Track `adopted_version` for all fleet families + version-lag detection + upgrade orchestration

**Inter-phase contract**:
- **Input** (consumes): [phase-9](phase-9-fleet-catalog.md) (per-family `adopted_version` in catalog) + [phase-10](phase-10-rollout-pipeline.md) (3-stage promote) + [mir-roles §3 Role B](mir-roles.md)
- **Output** (provides): template version bump decisions + upgrade migration runbook + sunset/hand-off procedures → [phase-11](phase-11-back-propagation.md) (drift detector's 6th kind `version_lag`) + Discord notification

## 1. Template 4 Lifecycle Stages

```text
[CREATE] → [MAINTAIN] → [DEPRECATE] → [SUNSET]
            ↓ (version bumps)
            [LIVE w/ versions v1.0 → v1.1 → v2.0 → ...]
```

Owner of each stage = your-harness-as-agent (Role B). Stages requiring mandatory user review are identified.

### 1-1. CREATE
- Initial template repository creation — `github.com/<your-org>/claude-codex-harness` already exists (prior to R7).
- This R10 doc is retroactive — creating the `VERSION` file + first tag in the template repo is the first step for R11 land.
- Initial baseline = your-harness R8 state (sanitized).

### 1-2. MAINTAIN — Normal Version Bump
- PATCH (`vN.M.X+1`): drift fix, doc typo, broken link, dependency security patch
- MINOR (`vN.M+1.0`): new phase / hook / skill added, backwards-compatible extension
- Detailed procedure: [`applications/template-repo/versioning.md`](applications/template-repo/versioning.md)

### 1-3. DEPRECATE — phase / hook / skill sunset
- your-harness-as-agent (Role B) makes the deprecation decision for a phase / hook / skill
- Triggers:
  - New phase N+1 replaces phase N (e.g., schema change when phase-4 13-state SM code lands)
  - Usage is 0 (phase-8 GC result)
  - Safety incident (security / data corruption)
- Procedure:
  1. Add deprecation notice to template `CHANGELOG.md` + planned sunset date (90 days later)
  2. Discord notification — notify affected families
  3. 90-day grace period — user migration window
  4. When sunset date arrives → MAJOR version bump + item removed
- Mandatory user review (forced sunset is not done)

### 1-4. SUNSET — Template Repo Structural Change
The most extreme case of "the agent managing the template repository."

| Sunset Type | Description | Procedure |
|---|---|---|
| **Archive** | Template repo frozen to read-only | (a) Archive notice in `CHANGELOG.md` (b) Fleet 90-day notification (c) Catalog `family_type: archived_template` label (d) Freeze all fleet families' `adopted_version` (last active version) |
| **Replace** | Migrate to new template repo (`claude-codex-harness-v2`) | (a) Bootstrap new repo (b) 6-month dual-live (c) Family migration cadence (d) Archive old repo |
| **Rename** | Same owner changes URL only | (a) Verify old URL → new URL redirect (b) Update `template_repo_url` in fleet config (c) 7-day grace |
| **Fork** | External owner forks for independence | (a) Catalog fork with separate `family_type=template` (b) Cross-pollination decision between two templates (your-harness-as-agent does not maintain fork) |

Each sunset requires: fleet family impact assessment + migration path must be explicitly defined.

## 2. Version-Lag Detection (6th kind in phase-11 §2)

R9 audit (Slice A Q3 + Slice C BLOCKING) identified absence of version drift detection. This §2 is the detector extension spec for phase-11.

### 2-1. Detection Targets
| Kind (phase-11 §2-1) | What it detects |
|---|---|
| 1 new skill | New SKILL.md in family `.claude/skills/` |
| 2 new hook | New hook file in family `.claude/hooks/` |
| 3 new agent | New agent frontmatter in family `.claude/agents/` |
| 4 new phase pattern | New section in family `docs/harness-engineering/` |
| 5 config evolution | New field in family `config/repos/<self>.json` |
| **6 version_lag (R10 new)** | **family `adopted_version` < template `current_version`** |

### 2-2. version_lag Detector Algorithm (pseudocode)
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
- After daily scan, append `version_lag` entry to `config/fleet-drift-log/<family>-<ts>.json` (when applicable).
- Weekly Discord digest: "N families behind by ≥1 MINOR" summary.
- Monthly: "Family X recommended to upgrade to vN+1" user recommendation.

## 3. Upgrade Migration Runbook (Per Bump Type)

Core omission from R9 audit (Slice A BLOCKING #8). This §3 explicitly defines the upgrade procedure for fleet families.

### 3-1. PATCH Bump (auto-eligible)
template `v1.2.3` → `v1.2.4`
- Changes: drift fix / doc / broken link / dep security
- Impact: 0 (backwards compatible guaranteed)
- Procedure:
  1. your-harness scan detects `version_lag.severity=patch`
  2. Discord notification (advisory only)
  3. Family owner chooses: (option a) auto upgrade — your-harness updates family `adopted_version` + Discord notify, (option b) skip — family declines
  4. 30-day timeout → automatic upgrade

### 3-2. MINOR Bump (opt-in advisory)
template `v1.2.3` → `v1.3.0`
- Changes: new phase / hook / skill / backwards-compatible extension
- Impact: families that do not adopt remain compatible
- Procedure:
  1. your-harness scan detects `version_lag.severity=minor`
  2. New capability summary in Discord weekly digest
  3. Family owner makes `recommendations_received` decision (adopted / declined / pending 30d)
  4. When adopted: family's cherry-pick procedure ([`applications/template-cherrypick.md`](applications/template-cherrypick.md) §6 6-step)
  5. After decision, your-harness updates family `adopted_version`

### 3-3. MAJOR Bump (guided migration)
template `v1.x.y` → `v2.0.0`
- Changes: breaking — phase rename / schema field removed / hook signature changed / family_type changed
- Impact: families that do not adopt may have future hooks/scripts stop working
- Procedure:
  1. your-harness issues user review 90 days before MAJOR bump decision (CHANGELOG breaking change pre-notice)
  2. At MAJOR bump time: your-harness detects → `version_lag.severity=major` + `requires_user_review=true`
  3. Impact assessment:
     - Which families are affected by the breaking change (per-family override analysis)
     - Per-family migration procedure (template `MIGRATION.md` vN→vN+1 section)
  4. Discord priority alert — individual notification to each family owner
  5. 6-month grace period — family chooses vN or vN+1
  6. After grace ends: your-harness stops tracking vN (catalog family row gets `adopted_version` stale label)

### 3-4. Conflict Resolution
When a family has customizations that differ from the template baseline:
- PATCH conflict: skip (family customization wins)
- MINOR conflict: mandatory family review (3-way merge: template baseline / family override / user decision)
- MAJOR conflict: mandatory explicit user review

## 4. Hand-off Protocol

When your-harness-as-agent can no longer perform Role B (e.g., user changes, fork, your-harness itself archived).

### 4-1. Hand-off Types
| Type | Description |
|---|---|
| Sub-agent hand-off | your-harness-as-agent delegates Role B to another agent (e.g., codex-template-maintainer) |
| User-self hand-off | User maintains template repo directly (your-harness retains Role A only) |
| Successor hand-off | New agent (your-harness-v2) succeeds your-harness-as-agent |
| Fork hand-off | External owner forks template → Role B splits |

### 4-2. Hand-off Procedure
1. Hand-off decision (explicit by user)
2. Record current state:
   - `config/mir-agent-self-health.json` snapshot
   - All in-progress innovation triage decisions
   - Last template promote + version
   - Incomplete maintenance tasks (e.g., pending CVE patch)
3. Transfer to new agent / owner:
   - Read access to `fleet-harness-state.json`
   - Write access to template repo (your-harness Role B permissions)
   - Dependency: ADR-40 charter agreement
4. Verification:
   - New agent runs first daily scan measured
   - New agent runs `sanitize_for_template.py` dry-run in sandbox
   - Discord notification

### 4-3. Format Stability
In a multi-agent environment, your-harness may be superseded. Successor agents must be compatible with the catalog format.
- `fleet_harness_state.schema.json` = stable interface (R10 explicit)
- `family_type` enum (6-Type: SE-meta / code_app / SE-product / hybrid_pipeline / template / [optional reserved]) = stable
- `adoption.status` enum = stable
- Adding new enum value = MINOR (compatible), removing enum value = MAJOR

## 5. Template Repo CI / Pre-commit (Under Role B)

R9 audit (Slice A Q2) BLOCKING — template's own CI was not defined. This §5 is the spec.

### 5-1. Template Repo `.github/workflows/` (R11 land)
- `validate.yml`: schema validation + link check + sanitize verify + role-policy parity verify on every PR
- `release.yml`: automatic CHANGELOG update + Discord notify on every version tag
- `daily_health.yml`: daily cron `template_health.py` execution

### 5-2. Template Repo `.claude/hooks/` (R11)
- `pre-commit-verification.sh`: lint + schema validation
- `tdd-guard.sh`: enforced when adding tests to the template itself

### 5-3. Template Repo `tests/`
- `test_schema_validity.py`: self-validate all schemas
- `test_hook_executability.py`: hook file syntax + permissions
- `test_link_integrity.py`: markdown link resolve
- `test_phase_doc_completeness.py`: verify §0.5 + Exit Criterion + Application State table exist

## 6. ADR Candidates

- ADR-42 (R10 new candidate) — Template Lifecycle (sunset + upgrade migration + hand-off)
- ADR-43 (R10 new candidate) — Template CI / pre-commit charter

## 7. Application State

| Item | Status | Location |
|---|---|---|
| version_lag detector | **landed** (R29-T03 scripted `detect_version_lag()` 2026-05-24) | `harness_drift.py` `detect_version_lag()` + `_parse_semver()` + kind enum + `tests/test_version_lag.py` (6 pass) |
| Upgrade migration runbook (PATCH/MINOR/MAJOR) | **landed in this R10-T05** | This §3 |
| Sunset procedure (archive/replace/rename/fork) | **landed in this R10-T05** | This §1-4 |
| Hand-off protocol | **landed in this R10-T05** | This §4 |
| Template CI / pre-commit | **partially landed** (external to your-harness) | Template repo (`template-harness`) CI in operation — cannot be stored inside your-harness. Minimum gate must include not just schema/link/sanitize but also role-policy parity verifier. |
| Template tests | **partially landed** (external to your-harness) | Template repo `tests/` in operation — cannot be stored inside your-harness |
| MIGRATION.md (template repo) | **partially landed** (external to your-harness) | Template repo `MIGRATION.md` in operation — cannot be stored inside your-harness |

## 8. Exit Criterion

Phase done conditions:
1. 4 lifecycle stages (CREATE/MAINTAIN/DEPRECATE/SUNSET) defined + each stage owner = your-harness-as-agent Role B.
2. version-lag detector spec (§2) + `harness_drift.py` 6th kind are consistent.
3. Upgrade migration runbook (PATCH/MINOR/MAJOR) defined in §3.
4. Hand-off protocol defined in §4.
5. Template CI / tests spec defined in §5.
6. Applied-state verifier must return `pass` including main-agent parity + delegated Codex-first contract.
7. User review passed.

When R11 code lands, all procedures in this doc become automatable and verifiable.

## 9. Next Steps

The follow-up work is physical closeout rather than entering R11. `template_health.py`, `harness_drift.py` version_lag kind, template repo CI/tests, and `MIGRATION.md` are already in the landed category. The remaining work is reducing the template repo's actual applied-state backlog and continuous reconciliation of phase-12/13 documents. No new phases.
