---
status: design-v1
date: 2026-05-22
scope: cross-family enforcement exception matrix — when a family is exempt from a harness enforcement rule
audience: your-harness control plane
---

# Exceptions — Cross-Family Enforcement Exception Matrix

> **Purpose**: Define when a family is exempt from a harness enforcement rule, how exceptions are applied, and how they are tracked and reverted.

## 1. Six Core Principles

1. **Exceptions are the minority case.** The enforcement matrix is the default. Exceptions require justification and tracking.
2. **Exceptions are family-specific.** An exception for one family does not generalize to others.
3. **Exceptions are time-bounded.** Every exception must have an expiry condition (not necessarily a date — can be a condition such as "until Flutter 4 migration complete").
4. **Exceptions are logged in fleet-harness-state.json.** The exception is not live until it is recorded in the catalog.
5. **User decision always overrides.** If the user explicitly grants or revokes an exception, that decision takes precedence over any automated compatibility matrix recommendation.
6. **Sealed families have pre-granted exceptions.** Sealed families are exempt from all enforcement rules until explicitly reactivated.

## 2. Strictness Matrix

The strictness matrix defines the default enforcement level per family type per phase:

| Phase | SE-meta | SE-product | code_app | hybrid_pipeline | template | notes |
|---|---|---|---|---|---|---|
| Phase 0 (Foundations) | enforced | enforced | enforced | enforced | enforced | |
| Phase 1 (Hooks) | enforced | enforced | enforced | enforced | enforced | |
| Phase 2 (Codex) | enforced | enforced | enforced | enforced | enforced | |
| Phase 3 (Design) | enforced | enforced | doc-strict | doc-strict | enforced | |
| Phase 4 (Execution) | enforced | enforced | doc-strict | doc-strict | enforced | |
| Phase 5 (Observability) | enforced | doc-strict | doc-strict | doc-strict | doc-strict | |
| Phase 6 (Observability Rollup) | enforced | doc-strict | warn | warn | doc-strict | |
| Phase 7 (Fleet Catalog) | enforced | warn | warn | warn | enforced | |
| Phase 8 (Adoption Matrix) | enforced | warn | warn | warn | enforced | |
| Phase 9 (Fleet Harness State) | enforced | warn | off | off | enforced | |
| Phase 10 (Rollout Pipeline) | enforced | off | off | off | enforced | |
| Phase 11 (Back-Propagation) | enforced | off | off | off | enforced | |
| Phase 12 (Template Lifecycle) | enforced | off | off | off | enforced | |
| Phase 13 (Applied-State Closure) | enforced | warn | off | off | enforced | |
| Phase 14 (Completion Consistency) | enforced | warn | off | off | enforced | |

**Levels**:
- `enforced`: Violation blocks or generates WARN/ERROR in verifier
- `doc-strict`: Violation generates advisory WARNING only; doc must exist but implementation is optional
- `warn`: Advisory note in fleet scan only; no verifier WARN
- `off`: Not applicable for this family type at this phase

## 3. Application Procedure

To apply an exception for a family:

```
Step 1: Identify the rule being excepted (phase + enforcement level)
Step 2: Document the justification (technical reason, not preference)
Step 3: Define the expiry condition (when does this exception stop applying?)
Step 4: Add opt-in field to family's config/repos/<slug>.json
Step 5: Update fleet-harness-state.json — add exception entry
Step 6: Verify with scripts/verify_repo_agent_management.py
```

## 4. Opt-In Field Schema

Add the following to the family's `config/repos/<slug>.json`:

```json
{
  "exceptions": [
    {
      "phase": "phase-N",
      "rule": "<specific rule ID or description>",
      "level_override": "doc-strict",
      "reason": "one-sentence technical justification",
      "expiry_condition": "until <condition>",
      "granted_at": "YYYY-MM-DD",
      "granted_by": "user | your-harness"
    }
  ]
}
```

The `granted_by` field distinguishes user-explicit exceptions from your-harness auto-grants (sealed family exemptions).

## 5. Revert Procedure

To revert an exception:

1. Remove or update the `exceptions[]` entry in `config/repos/<slug>.json`
2. Update `fleet-harness-state.json` — remove or mark exception as `reverted`
3. Run `scripts/verify_repo_agent_management.py` — confirm enforcement is restored
4. Record reason for revert in `tasks/plan.md`

## 6. Exemption List

### Pre-Granted Exemptions (Sealed Families)

Sealed families are exempt from all enforcement rules until explicitly reactivated:

- All sealed families in the fleet catalog

These exemptions are auto-granted at sealing time and do not require individual `config/repos/<slug>.json` entries.

### Known Active Exceptions

_No active exceptions beyond sealed family blanket exemptions as of this document's writing._

Exceptions will be recorded here as they are applied.

## 7. Conflict Resolution

When a proposed exception conflicts with an existing rule or another exception:

| Conflict Type | Resolution |
|---|---|
| Exception contradicts a Phase 0/1 rule | Escalate to user — foundation rules are not exception-eligible without explicit user override |
| Two exceptions for the same family contradict each other | Newer exception takes precedence; record supersession reason |
| Family type default says `off` but family needs partial enforcement | Add as opt-in exception with `level_override: warn` or `doc-strict`; do not escalate to `enforced` without user approval |

## 8. Cross-Pollination Safeguards

To prevent exceptions from spreading unintentionally:

1. **No exception inheritance**: If family A has an exception and family B is similar, family B does not inherit the exception automatically.
2. **Catalog-first**: An exception is not live until it appears in `fleet-harness-state.json`. A CLAUDE.md note alone is insufficient.
3. **Verifier-visible**: `scripts/verify_repo_agent_management.py` must be able to read and report all active exceptions.
4. **Review cadence**: Exception list reviewed during fleet scan waves. Expired exceptions are flagged for revert.

## 9. Reference

- `example-harness/README.md` — your-harness application of the exception matrix
- `fleet-catalog.md` — 3-axis fleet goals that exceptions must not undermine
- `family-type-adoption-runbooks.md` — per-family-type adoption procedures that reference exception handling

## 10. Exit Criterion

The exception matrix is operational when:

1. Strictness matrix defined and documented (§2 above)
2. Opt-in field schema is live in at least 1 family's config
3. At least 1 exception applied + verified through the 6-step procedure
4. `scripts/verify_repo_agent_management.py` can read and report active exceptions
