---
phase: 11
title: Back-Propagation
status: consolidated-v1
depends_on: [phase-9, phase-10]
---

# Phase 11 — Back-Propagation (Innovation Share-Back)

> **Purpose**: When a fleet family independently improves its harness, detect that innovation and propagate it back to your-harness and/or the public template. Reverse flow: family → your-harness / template.

## 0.5 Design Goals (R9 anchor)

> This phase's connection to the [3-axis fleet goals](applications/fleet-catalog.md). When adding a new phase or cherry-picking for a family, the `design` skill (R9-T11) requires `design_goals` as a mandatory input.

**3-axis contribution**:
- **Axis I (your-harness hardening)**: absorb innovations from fleet families into your-harness (your-harness learns from fleet)
- **Axis II (public template sync)**: promote innovations worthy of generalization directly to template baseline
- **Axis III (fleet central governance / back-propagation)**: detect + triage + route innovations from all fleet families → your-harness catalog + share decisions

**Inter-phase contract**:
- **Input** (consumes): phase-9 (fleet-harness-state.json family-ahead drift entries) + phase-6 (7-axis observability rollup per family)
- **Output** (provides): `innovations[]` entries in fleet-harness-state.json + triage decisions + your-harness absorb commits + template promotion PRs

## 1. 3-Way Share-Back Flow

```text
family-A  ←────────────────────────────────── your-harness ──────────────────────────────────→  family-B
    │       Forward-1 (your-harness → family)                Forward-2 (your-harness → family)      │
    │                                                                                                │
    └──── Backward-1 (family-A → your-harness) ────→ your-harness ←──── Backward-2 (family-B → your-harness)
                                                          │
                                               Lateral (your-harness mediates
                                               family-A innovation → family-B)
```

**5 Sync Directions**:
1. **Forward-1**: your-harness → specific family (Phase 10 Stage 3)
2. **Forward-2**: your-harness → all families (fleet rollout)
3. **Backward-1**: family-A → your-harness (this phase, direct absorb)
4. **Backward-2**: family-B → your-harness (this phase, via catalog)
5. **Lateral**: family-A innovation → your-harness mediates → family-B (your-harness decides routing)

## 2. Innovation Detection

`harness_drift.py` detects family-ahead drift and registers it as an innovation candidate. (Code not yet landed as of this document's writing — spec below.)

### Innovation Data Model

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class Innovation:
    id: str                   # unique identifier
    kind: str                 # "skill" | "hook" | "agent" | "config" | "doc"
    source: str               # source family name
    detected_at: str          # ISO 8601 timestamp
    share_status: str         # "candidate" | "recommended" | "promoted" | "absorbed" | "archived" | "declined"
    phase: str                # related phase (e.g., "phase-5")
    path: str                 # file path relative to family root
    diff_summary: str         # brief description of what changed
    user_decision_at: Optional[str]  # ISO 8601 timestamp, None if not yet decided
```

### Detection Algorithm (pseudocode)

```python
def detect_innovations(family_path, template_baseline_path):
    candidates = []

    # Location 1: .claude/skills — new or modified skill definitions
    for skill_file in family_path / ".claude/skills":
        if not exists_in_template(skill_file, template_baseline_path):
            if not in_skip_list(skill_file):
                candidates.append(Innovation(kind="skill", path=skill_file, ...))

    # Location 2: .claude/hooks — new hook implementations
    for hook_file in family_path / ".claude/hooks":
        if is_novel_hook_pattern(hook_file, template_baseline_path):
            if not in_skip_list(hook_file):
                candidates.append(Innovation(kind="hook", path=hook_file, ...))

    # Location 3: .claude/agents — new agent definitions
    for agent_file in family_path / ".claude/agents":
        if not exists_in_template(agent_file, template_baseline_path):
            if not in_skip_list(agent_file):
                candidates.append(Innovation(kind="agent", path=agent_file, ...))

    return candidates
```

### False-Positive Suppression

Controlled vocabulary for items to skip:

```python
FAMILY_SPECIFIC_SKIP_GLOBS = [
    "*.local.*",          # family-local configs
    "*-private.*",        # explicitly private files
    "*secrets*",          # credential files
]

SKIP_FILES = [
    "CLAUDE.md",          # family-specific instruction files
    "AGENTS.md",
    ".mcp.json",
]

SKIP_DIRS = [
    ".git",
    "__pycache__",
    "node_modules",
    ".env",
]
```

## 3. Triage — 4 Decisions

When an innovation candidate is detected, your-harness (or the user) makes one of 4 triage decisions:

### 3-1. Triage Decision Table

| Decision | Meaning | Action |
|---|---|---|
| **share to fleet** | Innovation is generalizable — recommend to all fleet families | Add to `recommendations_received` for all compatible families via compatibility matrix |
| **absorb to your-harness** | Innovation improves your-harness directly | Open absorb task; apply to your-harness via Phase 10 Stage 1 flow |
| **promote to template** | Innovation is generic enough for the public template baseline | Open template PR; apply sanitization; promote via Phase 10 Stage 2 |
| **archive** | Innovation is family-specific and not generalizable | Mark `share_status: archived` in fleet-harness-state.json; no further action |

**Manual override**: User can explicitly state any triage decision regardless of the compatibility matrix. User decision always takes precedence. Example: even if the compatibility matrix marks a hybrid_pipeline → SE-meta share as ✗ (incompatible for auto-recommend), a user explicit "absorb to your-harness" overrides this.

## 4. Share Lifecycle

```text
candidate → (triage) → recommended | promoted | absorbed | archived
                              │
                    recommended → (family accepts/declines)
                              → accepted → applied → verified
                              → declined → archived (reason recorded)
                    promoted → template PR → merged → template-baseline updated
                    absorbed → your-harness task → land → Phase 10 Stage 1 flow
```

**Pending expiry**: If a family leaves an innovation recommendation `pending` for 30 days with no response, automatically transitions to `declined`. your-harness records reason and does not repeat the same recommendation.

## 5. Template Sync Runbook (§8a)

Three perspectives for template sync operations.

### Perspective 1: Template User (New Project)
1. Clone template-harness repository
2. Run `bootstrap.py` with your project configuration
3. Apply Phase 0 baseline
4. Customize family-specific sections
5. Register in your-harness fleet catalog (optional but recommended)

### Perspective 2: Existing Family (Receiving Update)
1. your-harness notifies via Discord (share recommendation)
2. Review proposed patch (minimum patch plan)
3. Accept → your-harness applies via Stage 3; Decline → record reason
4. Verify post-apply (family's own test suite)
5. Report result to your-harness (fleet-harness-state.json updated)

### Perspective 3: Sync-Back (Contributing Innovation)
1. family-ahead drift detected by `harness_drift.py`
2. your-harness catalogs as innovation candidate
3. User triage decision (share/absorb/promote/archive)
4. If promote: your-harness opens template PR with sanitization applied
5. Template PR merged → all families can receive via Forward-2

## 6. Conflict Resolution

Three types of conflicts when an innovation from a family conflicts with existing your-harness / template patterns:

| Conflict Type | Detection | Resolution |
|---|---|---|
| **Incompatible** | Innovation uses a pattern that directly contradicts an existing rule | User decision required; escalate as ADR candidate if architectural |
| **Abstractable** | Innovation and existing pattern serve the same purpose with different implementations | Abstract the shared interface; keep family-specific variants as overrides |
| **Individual specialization** | Innovation is valid within its family_type but not generalizable | Triage as "archive"; record in family's local notes; do not promote |

## 7. Application State

| Item | Status | Location |
|---|---|---|
| harness_drift.py | **landed** (551 LOC) | `tools/fleet_observe/harness_drift.py` |
| Innovation data model | **landed** | fleet-harness-state.json `innovations[]` field |
| 5 sync directions | **landed** (conceptual SoT) | This document |
| Triage 4 decisions | **partial land** | Manual triage via Discord notification; automated routing is follow-up |
| Template sync runbook | **landed** | This §5 + Phase 10 Stage 2 |
| Conflict resolution | **landed** (policy) | This §6 |
| False-positive suppression | **landed** | `harness_drift.py` FAMILY_SPECIFIC_SKIP_GLOBS |
| Pending expiry (30-day auto-decline) | **not implemented** | Cadence automation follow-up |

**Gap**: Automated triage routing, 30-day pending expiry enforcement, lateral sync (family-A → family-B mediation) formalization.

## 8. ADR Candidates

ADR-27 — Back-Propagation and Innovation Share-Back Policy.

## 9. Prohibitions

- Pushing innovations to families without triage decision
- Skipping sanitization when promoting to template
- Allowing same innovation to be recommended repeatedly after `declined`
- Lateral sync without your-harness as mediator (direct family-to-family prohibited)
- Absorbing family-specific private patterns into your-harness or template without generalization

## 10. Exit Criterion

1. At least 1 complete back-propagation cycle: family-ahead drift detected → triage decision made → action taken (absorb OR promote OR archive)
2. fleet-harness-state.json `innovations[]` field populated for at least 1 family
3. Template sync runbook validated against at least 1 real sync operation
4. ADR-27 published

## 11. Next Steps

Proceed to [Phase 12 — Template Lifecycle](phase-12-template-lifecycle.md). Phase 11 handles the detection and routing of innovations. Phase 12 handles the lifecycle of the template repository itself — versioning, deprecation, and upgrade paths.
