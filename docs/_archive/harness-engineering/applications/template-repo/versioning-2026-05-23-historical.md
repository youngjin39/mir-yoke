---
status: design-v1
date: 2026-05-23
scope: template repo (template-harness) versioning policy
audience: your-harness Role B (Template Maintainer) + fleet owners (receiving side)
priority: R10-T02 newly established (ADR-40 §Versioning Policy operational guide)
---

# Template Versioning Runbook

> **Purpose**: Version decision, bump, tag, CHANGELOG, and MIGRATION procedures for the `template-harness` template repo. Operational guide for the versioning policy defined in ADR-40 (Role B charter).

## 0.5 Design Goals (R10 anchor)

**3-axis contribution**:
- **Axis I (your-harness strengthening)**: your-harness-as-agent (Role B) maintains single source of truth for template version
- **Axis II (Public template sync)**: Standard artifact specification for VERSION + CHANGELOG + MIGRATION → external fleet adopters can determine their adoption base
- **Axis III (Fleet central management + back-propagation)**: per-family `adopted_version` field maps 1:1 against this doc's semver → version-lag detection (phase-12 §2) enabled

**Inter-phase contract**:
- **Input** (consumed): [phase-10 stage 2 promote](../../phase-10-rollout-pipeline.md) (your-harness land + sanitize result)
- **Output** (produced): template VERSION + CHANGELOG entry + (when applicable) MIGRATION section → [phase-12 §3 upgrade migration](../../phase-12-template-lifecycle.md) + fleet notification

## 1. 3 Artifacts (within template repo)

| File | Location | Format | Update trigger |
|---|---|---|---|
| `VERSION` | template repo root | single line semver (e.g., `1.2.3`) | every version bump |
| `CHANGELOG.md` | template repo root | [KeepAChangelog](https://keepachangelog.com/) format | every version bump |
| `MIGRATION.md` | template repo root | per-MAJOR vN → vN+1 section | MAJOR bump only |

All 3 artifacts updated together with git commit + tag.

## 2. Semver Decision Rules

| Bump type | Condition | Example |
|---|---|---|
| **PATCH** (`vN.M.X+1`) | drift fix / doc typo / broken link / dependency security patch / 0 user-facing changes | `1.2.3` → `1.2.4` |
| **MINOR** (`vN.M+1.0`) | new phase / hook / skill / agent added (backwards compatible) / new schema field (optional) | `1.2.4` → `1.3.0` |
| **MAJOR** (`vN+1.0.0`) | breaking change: phase rename / phase removal / schema field removal / hook signature change / family_type enum change | `1.3.0` → `2.0.0` |

### 2-1. Edge Cases
- New phase addition is default MINOR. But if a new phase changes the meaning of an existing phase, it is MAJOR.
- Optional schema field addition = MINOR. Required field addition = MAJOR (breaks existing instances).
- enum value addition = MINOR (compatible). enum value removal = MAJOR.
- hook file addition = MINOR. Existing hook signature change = MAJOR.

### 2-2. Pre-release
- `vN.M.X-rc.1`: release candidate (user review stage)
- `vN.M.X-beta.1`: experimental (explicit user opt-in required)
- All pre-releases before official release are registered in fleet `recommendations_received` but default to `pending`

## 3. Bump Procedure (manual today, R11 automation)

### Step 1 — Change Analysis
```bash
cd <your-harness-path>/git_public/template-harness
git log --oneline $(cat VERSION)..HEAD
```

Review the commit list above → decide PATCH/MINOR/MAJOR (§2 rules above).

### Step 2 — Update VERSION file
```bash
echo "1.3.0" > VERSION
```

### Step 3 — Add CHANGELOG entry
```markdown
## [1.3.0] - 2026-05-24

### Added
- Phase 12 Template Lifecycle (R10 land)
- your-harness dual-role doc

### Changed
- Phase 11 §4 heading: "3 types" → "5 types"

### Deprecated
- (none)

### Removed
- (none)

### Fixed
- ADR-25 status drift (pending → accepted)
- 9-state → 13-state SM bulk replace

### Security
- (none)
```

### Step 4 — (MAJOR only) Add MIGRATION section
```markdown
## v2.0.0 ← v1.x.y

### Breaking changes
- phase-7 §3 6-Type classification: `SE-meta` renamed to `SE-foundation`

### Migration steps (per family)
1. Update `family_type: "SE-meta"` to `"SE-foundation"` in `config/repos/<family>.json`
2. Update all schema enums (`grep -rn '"SE-meta"' docs/templates/_schema/`)
3. Apply cherry-pick — no backwards compat fallback

### Rollback
- Freeze family `adopted_version` at v1.x.y → catalog tracking ends when 6-month grace expires
```

### Step 5 — Commit + Tag + Push
```bash
git add VERSION CHANGELOG.md MIGRATION.md
git commit -m "release: v1.3.0 — R10 fleet catalog + template lifecycle"
git tag -a v1.3.0 -m "v1.3.0"
git push origin main --tags
```

### Step 6 — Update your-harness state cache
```bash
# (manual today; R11 automation)
# Update template_version field in config/fleet-harness-state.json
python3 -c "
import json
state = json.load(open('config/fleet-harness-state.json'))
state['template_version'] = '1.3.0'
state['last_updated'] = '2026-05-24T03:00:00Z'
json.dump(state, open('config/fleet-harness-state.json', 'w'), indent=2, ensure_ascii=False)
"
```

### Step 7 — Fleet notification
- (MINOR) Include new capability summary in Discord weekly digest (wait until next cron)
- (MAJOR) Discord priority alert — immediate notification to each family owner + migration procedure link

## 4. CHANGELOG Entry Writing Guide

### Required sections
- `### Added`: new phase / hook / skill / agent / schema field
- `### Changed`: meaning change to existing item (backwards compatible)
- `### Deprecated`: items scheduled for sunset (to be removed in next MAJOR)
- `### Removed`: deleted items (MAJOR only)
- `### Fixed`: bug fix / drift fix
- `### Security`: CVE patch / security hardening

### Writing principles
- All entries based on user-facing changes (internal refactors omitted or kept brief)
- Specify impacted family_types (e.g., "[SE-product, hybrid_pipeline only]")
- ADR / phase doc cross-reference (e.g., "see phase-12 §3")
- Breaking items prefixed with `**BREAKING:**`

## 5. Cross-Reference

- ADR-40 (Maintainer Charter — versioning policy SoT)
- ADR-39 (Applied-State Charter — defines version baseline)
- phase-12-template-lifecycle.md §2 (version-lag detector spec — consumer of version)
- phase-10 §3-3 (your-harness → template promote — version bump trigger)
- [`ci.md`](ci.md) (template CI auto-validates version bumps)
- [`upgrade-runbook.md`](upgrade-runbook.md) (family-side version upgrade procedure)

## 6. R10 / R11 Separation

| Area | R10 (this doc) | R11 (code land) |
|---|---|---|
| VERSION file spec | ✅ | initial VERSION file creation + first tag `v0.1.0` (R10-R1 confirmed) |
| CHANGELOG format | ✅ | auto generator (`scripts/generate_changelog.py`) |
| MIGRATION format | ✅ | first MIGRATION section in template repo |
| Bump procedure (manual) | ✅ | `scripts/release_template.py` automates steps 2–6 |
| Fleet notification | ✅ doc | `scripts/notify_template_release.py` |
| Pre-release procedure | ✅ doc | (R11+) |

## 7. your-harness Application Status (2026-05-23)

| Item | Status |
|---|---|
| VERSION file | **absent** in template repo (measured 2026-05-23). R10-R4 hand-promote must create initial `0.1.0` |
| CHANGELOG.md | **present** in template repo BUT format violation — last entry `## 2026.05.2` (date-format, not KeepAChangelog standard). R10-R4 must rewrite as v0.1.0 entry + migrate to KeepAChangelog format |
| MIGRATION.md | **absent** (measured 2026-05-23). R10-R4 must create initial empty file (empty section maintained until first MAJOR) |
| Bump procedure doc | **this R10-T02 land** |
| Automation script | **not yet** (R11) |

**R10-R3-T07 correction (2026-05-23)**: prior row "CHANGELOG.md absent (R11)" claim was false — template has an actual CHANGELOG.md (`<your-harness-path>/git_public/template-harness/CHANGELOG.md`). However the format violates KeepAChangelog standard (date-format `## 2026.05.2`), so R10-R4 hand-promote must rewrite to KeepAChangelog format. This correction resolves R10-R2 audit Slice B BLOCKING #7 (doc author never grep'd template repo). Details: [`current-state.md §2 Versioning Artifacts`](current-state.md).

## 8. Exit Criterion

This doc is done when:
1. 3 artifact formats (VERSION / CHANGELOG / MIGRATION) specified ✓
2. Semver decision rules (PATCH/MINOR/MAJOR + edge cases) specified ✓
3. 7-step bump procedure (manual today) specified ✓
4. CHANGELOG entry guide ✓
5. R10/R11 separation specified ✓
6. User review passed

## 9. Next Steps

[`ci.md`](ci.md) — template repo CI auto-validates version bumps (PR-stage validate).
