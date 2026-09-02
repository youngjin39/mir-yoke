---
status: design-v1
date: 2026-05-23
scope: template vN → vN+1 family upgrade runbook
audience: fleet family owner (receiving side) + your-harness Role B (notification sender)
priority: R10-T02 newly established (phase-12 §3 operational guide)
---

# Template Upgrade Runbook

> **Purpose**: Upgrade procedure for fleet families (receiving side) to follow when the template repo bumps its version. Separated by PATCH / MINOR / MAJOR. Operational guide for family-side work from phase-12 §3.

## 0.5 Design Goals (R10 anchor)

**3-axis contribution**:
- **Axis I (your-harness strengthening)**: your-harness-as-agent (Role B) automates fleet notification + version-lag detection
- **Axis II (Public template sync)**: template version bump → explicit adoption procedure for families
- **Axis III (Fleet central management + back-propagation)**: family `adopted_version` update flow → consistent catalog maintenance

**Inter-phase contract**:
- **Input** (consumed): new template version (CHANGELOG entry + MIGRATION section if MAJOR)
- **Output** (produced): family commit + `recommendations_received.decision` → `fleet-harness-state.json` updated

## 1. Family Owner Upgrade Decision Flow

```text
[Receive your-harness notification]
    ↓
[Review CHANGELOG entry]
    ↓
[Impact assessment — conflict with family customizations?]
    ↓
[Decision]
  ├─ Adopted → cherry-pick + commit + notify your-harness
  ├─ Declined → notify your-harness with reason (recorded in catalog)
  ├─ Pending → 30-day timeout (auto-declined)
  └─ Superseded → new pattern is more appropriate (recorded in catalog)
```

## 2. PATCH Upgrade (Auto-Eligible)

### 2-1. Notification format (Discord)
```
[template PATCH] v1.2.4 (drift fix)
- Fixed: ADR-25 status drift
- Fixed: 9-state → 13-state SM bulk replace
Auto-eligible for fleet (no breaking change).
Reply `decline` within 30 days to opt out.
```

### 2-2. Family Action
- **Default (no action)**: Auto-upgrade after 30 days — your-harness updates catalog `adopted_version`
- **Decline (manual)**: Reply to your-harness (Discord or CLI)
  ```bash
  # After R11 land
  python tools/fleet_observe/family_decision.py --family <name> --version 1.2.4 --decision declined --reason "..."
  ```

### 2-3. Conflict handling
PATCH is backwards compatible — no conflict with family customizations. If a conflict is discovered, the PATCH was misclassified (user alert).

## 3. MINOR Upgrade (Opt-in Advisory)

### 3-1. Notification format
```
[template MINOR] v1.3.0 (new capability)
### Added
- Phase 12 Template Lifecycle (R10 land)
- your-harness Roles dual-role doc

Review in 30 days. Default = pending (no auto-upgrade).
- adopt: `python tools/family_decision.py --version 1.3.0 --decision adopted`
- decline: ... --decision declined --reason "..."
```

### 3-2. Family Action
1. Review CHANGELOG entry → evaluate whether new capability is valuable to the family
2. (Adopt decision)
   - Apply template-cherrypick.md §6 6-step (CP-1~CP-6)
   - Update family `enabled_phases` / `hooks_enabled` / `skill_overrides`
   - Commit to family repo
   - Notify your-harness → `adopted_version` updated
3. (Decline decision)
   - State reason (recorded in your-harness catalog)
   - your-harness will not repeat recommendation for the same version
4. (After 30-day pending)
   - Auto-declined + advisory log

### 3-3. Conflict handling
Family customization conflicts with new capability:
- New hook occupies family's existing hook trigger → family decides (a) choose one or (b) merge
- New schema field (optional) conflicts in meaning with family override → field use is optional
- New phase conflicts with family's sealed policy → sealed family skips by default

## 4. MAJOR Upgrade (Guided Migration)

### 4-1. Pre-Notification (90 days before)
```
[template MAJOR preview] v2.0.0 in 90 days
**BREAKING:**
- phase-7 `SE-meta` → `SE-foundation` rename
- task_state.schema.json `risk_level` enum change

Migration window: 6 months from v2.0.0 release.
See MIGRATION.md vN → vN+1 section.
```

### 4-2. Release Notification
```
[template MAJOR] v2.0.0 RELEASED
**BREAKING CHANGES** — review MIGRATION.md
Family migration deadline: 2026-11-23 (6 month grace).
After deadline, vN tracking dropped.
```

### 4-3. Family Action (per family, individual)
1. **Impact assessment** — review breaking items in `MIGRATION.md vN → vN+1` section
2. **Per-breaking decision**:
   - All families: apply schema rename (e.g., `SE-meta` → `SE-foundation`)
   - Analyze impact on family customizations
3. **Migration commit** (family repo)
   ```bash
   # Example migration procedure
   sed -i 's/"SE-meta"/"SE-foundation"/g' .claude/config.json
   git add . && git commit -m "migrate: template v1 → v2"
   ```
4. **Verification** — confirm family hooks + tests work correctly
5. **Notify your-harness** → `adopted_version` updated + migration complete status
6. **Rollback option** — can revert to vN within 6-month grace period (but no new PATCH/MINOR for vN)

### 4-4. Grace Period End
- At 6-month end: catalog row `adopted_version` for vN families gets stale label
- your-harness will not recommend additional PATCH/MINOR
- At 6 months + 30 days: family row archived in catalog (user-explicit active → archived transition)

## 5. Conflict Resolution Matrix

| Conflict type | PATCH | MINOR | MAJOR |
|---|---|---|---|
| Family hook trigger occupied | skip (family wins) | family review required | user-explicit review |
| Family schema override | n/a (PATCH does not change schema) | family review (compat OK?) | migration required |
| Family sealed policy | sealed = decline default | sealed = decline default | sealed = impact assessment + user review |
| Family customization violation | n/a | family review | migration required |

## 6. Sealed Family Special Handling

Per the sealed family policy (ADR-22):

- PATCH: upgrade only with user-explicit approval (default = decline)
- MINOR: default = decline, user-explicit opt-in required
- MAJOR: user-explicit review + migration decision. External git push block for sealed families applies.

This sealed policy aligns with [ADR-22](../../../decisions/adr-22-sealed-family-policy-2026-05-23.md).

## 7. SE-meta Self-Stop Application

Aligned with [mir-roles.md §6 SoT reconciliation](../../mir-roles.md) + [ADR-41 verify_self_stop hook](../../../decisions/adr-41-verify-self-stop-hook-2026-05-23.md).

- your-harness-as-agent (Role B) fires `verify_self_stop.py` before recommending template's new capability to a family
- If your-harness's own `phase adoption.status != adopted` for that phase, recommendation is BLOCKED
- User-explicit override available (your-harness partial land state can still promote template-only as reference)

## 8. R10 / R11 Separation

| Area | R10 (this doc) | R11 (code land) |
|---|---|---|
| family decision CLI spec | ✅ doc | `tools/fleet_observe/family_decision.py` |
| Migration notification format | ✅ doc | Discord template renderer |
| Pre-notification (90-day) | ✅ doc | cron + scheduler |
| Auto-upgrade (PATCH default) | ✅ doc | catalog update job |
| Grace period end automation | ✅ doc | cron + alert |

## 9. your-harness Application Status (2026-05-23)

| Item | Status |
|---|---|
| Upgrade runbook (per bump type) | **this R10-T02 land** |
| family_decision.py | **not yet** (R11) |
| Discord notification template | **not yet** (R11) |
| Cron scheduler | **not yet** (R11) |
| SE-meta self-stop hook | **spec only** (R10 ADR-33 + R11 code) |

## 10. Exit Criterion

1. Family action procedure for PATCH / MINOR / MAJOR ✓
2. Pre-notification + release notification format ✓
3. Conflict resolution matrix ✓
4. Sealed family special handling ✓
5. SE-meta self-stop alignment ✓
6. R10/R11 separation ✓

## 11. Next Steps

[`bootstrap-day-0.md`](bootstrap-day-0.md) — greenfield family first 24-hour / 7-day operational guide.
