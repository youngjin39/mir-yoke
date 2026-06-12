---
phase: 11
title: Back-Propagation (Innovation Share-Back)
status: design-v1
depends_on: [phase-9, phase-10]
date: 2026-05-23
---

# Phase 11 -- Back-Propagation (Innovation Share-Back)

> **Purpose**: When a family produces an innovation, the central harness detects it, catalogs it, and converts it into a directly applicable patch for managed families. Maintain 5-direction flow of the **3-node sync hub** (family-A <-> central harness <-> family-B), and for active managed repos, go beyond recommendation to direct apply.

## 0.5 Design Goals (R9 anchor)

> This phase connects to the [3-axis fleet goals](applications/fleet-catalog.md). When adding a new phase or cherry-picking from a family, the `design` skill (R9-T11) requires the `design_goals` field as mandatory input.

**3-axis contribution**:
- **Axis I (self-harness hardening)**: family innovation absorbed into self-harness becomes input for self-harness strengthening
- **Axis II (public template sync)**: generalizable patterns from family innovations are promoted to the template baseline (via self-harness absorption then phase-10 stage 2)
- **Axis III (fleet central management)**: **core of this phase**. 3-way share-back catalog + drift detector across family <-> central harness <-> other family

**Inter-phase contract**:
- **Input** (consumes): phase-9 (fleet-harness-state.json + drift_log family-ahead drift) + phase-6 (per-family observability rollup) + phase-7 (per-family adoption history)
- **Output** (provides): innovation share/apply event -> phase-10 stage 3 (managed fleet direct apply) trigger + phase-9 catalog update

## 1. 3-Way Share-Back Flow

```text
[family-A]                                    [family-B]
     | (innovation emerges)                        ^ (direct apply / exception review)
     |                                             |
     +-> [central harness drift_detector]          |
              |                                    |
              +- catalog registration              |
              +- compatibility check (family_type) |
              +- self-harness absorption eval      |
              +- template promote eval             |
              |                                    |
              +-> [central harness share_dispatcher] ------+
                       |
                       +- Discord notification (operator review)
                       +- recommendations_received array updated
```

**Key principles**:
- Innovations from family-A are not automatically absorbed by the central harness (operator review required).
- For active managed repos, the central harness applies directly after inspection.
- Absorption stages (self-harness / template promote / family share) are each independent decisions.

## 2. Innovation Detection -- `harness_drift.py`

[`tools/fleet_observe/harness_drift.py`](../../tools/fleet_observe/harness_drift.py). This section is the spec; code is a separate round.

### 2-1. Detection Targets
| Kind | Detection Method | Example |
|---|---|---|
| **new skill** | Compare family `.claude/skills/` SKILL.md vs template | example-pipeline `scene-render` skill |
| **new hook** | Compare family `.claude/hooks/` hook files vs template | example-notes `note-conflict-resolver.sh` |
| **new agent** | Family `.claude/agents/` agent frontmatter | example-infra `signal-analyst` agent |
| **new phase pattern** | New section in family `docs/harness-engineering/` phase-N-application | (operator review required) |
| **config evolution** | New field usage in family `config/repos/<self>.json` | `local_phase_override` field |

### 2-2. Innovation dataclass

`fleet_harness_state.schema.json` innovation schema 1:1 mapping. Python type signature:

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional

@dataclass(frozen=True)
class Innovation:
    """Runtime representation of a family-ahead innovation. Matches fleet_harness_state.schema.json $defs/innovation."""
    id: str                                          # kebab-slug, e.g. "scene-render-pipeline-2026-05-20"
    kind: Literal["skill", "hook", "agent", "phase_pattern", "config_field"]
    source: str                                      # family slug (catalog families.<key>)
    detected_at: datetime                            # ISO-8601 UTC
    share_status: Literal[
        "candidate", "recommended", "absorbed_to_self",
        "promoted_to_template", "archived", "rejected"
    ]
    phase: Optional[str] = None                      # "phase-N" or design-process etc.
    path: Optional[str] = None                       # relative path in family repo
    diff_summary: Optional[str] = None
    user_decision_at: Optional[datetime] = None

    @classmethod
    def make_id(cls, kind: str, source: str, slug: str, date: datetime) -> str:
        """ID generation rule: <slug>-<YYYY-MM-DD>. Example: scene-render-pipeline-2026-05-20."""
        return f"{slug}-{date.strftime('%Y-%m-%d')}"
```

**Field naming**: both schema and code use `source` (family slug).

### 2-3. Detection Algorithm (pseudocode)
```python
def detect_family_innovations(family_path: Path, template_path: Path) -> list[Innovation]:
    innovations = []
    today = datetime.now(UTC)

    # 1. file existence diff (3 locations)
    for loc in [".claude/skills", ".claude/hooks", ".claude/agents"]:
        family_files = set((family_path / loc).glob("*/SKILL.md" if "skills" in loc else "*"))
        template_files = set((template_path / loc).glob("*/SKILL.md" if "skills" in loc else "*"))
        new_files = family_files - template_files
        for f in new_files:
            kind = {"skills": "skill", "hooks": "hook", "agents": "agent"}[loc.split("/")[-1]]
            slug = f.parent.name if "skills" in loc else f.stem
            innovations.append(Innovation(
                id=Innovation.make_id(kind, family_path.name, slug, today),
                kind=kind,
                source=family_path.name,
                path=str(f.relative_to(family_path)),
                detected_at=today,
                share_status="candidate",
            ))

    # 2. content drift (meaningful diff in existing files)
    # algorithm: line-count diff > 30% OR header structure diff
    # implementation deferred -- false-positive concern, manual review queue only

    # 3. config evolution (new key in config/repos/<self>.json)
    # algorithm: schema diff vs family_config.schema.json -- new top-level key
    # implementation deferred

    return innovations
```

### 2-4. False-Positive Suppression Controlled Vocab
```python
FAMILY_SPECIFIC_SKIP_GLOBS = [
    "**/family_local_*.sh",
    "**/private/*",
    "**/_test_fixtures/*",
    "**/*-experimental.md",
    "**/SCRATCH.md",
    "**/.local-config.json",
]

SKIP_FILES = {"LICENSE", "README.md", "AGENTS.md", "CLAUDE.md"}
SKIP_DIRS = {"archive", ".git", "node_modules", "venv", "__pycache__"}
```

Updates to this vocab require a patch to this doc (PR + operator review).

**False positive suppression rules**:
- Skip clearly family-specific files (e.g., `family_local_hook.sh`)
- Skip LICENSE / README / user-facing string changes
- Family-private notes (e.g., local README) are not share candidates

## 3. Innovation Triage (Operator Review)

### 3-1. 4 Triage Decisions
| Decision | Action |
|---|---|
| **share to fleet** | Register in compatible family rollout/apply queue (enter Stage 3 direct apply) |
| **absorb to self-harness** | Integrate into central harness (code commit + this phase docs updated). Then template promote via phase-10 stage 2 |
| **promote to template directly** | Add directly to template (skip self-harness absorption -- for small fixes) |
| **archive (no share)** | Record in catalog only, no share (when family-specific) |

### 3-2. Triage UI / Procedure
- Discord weekly digest: list of new innovations (central harness fetches).
- Operator selects decision 1-4 for each innovation.
- After decision, auto-dispatch:
  - share to fleet -> phase-10 stage 3 trigger
  - absorb to self-harness -> TODO created (operator runs as separate round)
  - promote to template directly -> phase-10 stage 2 PR draft
  - archive -> catalog updated only

### 3-3. Triage SLA
- New innovation detected -> operator notified (weekly digest).
- Operator review is for confirming triage criteria; it does not block direct apply for active managed repos. Only sealed/suspended/exception repos get separate hold.

## 4. 5 Sync Directions

| Direction | Source | Destination | Trigger |
|---|---|---|---|
| **Forward 1: self-harness -> template** | self-harness land | template baseline update | phase-10 stage 2 |
| **Forward 2: template -> fleet** | template baseline | managed family apply | phase-10 stage 3 (direct apply) |
| **Backward 1: family -> self-harness** | family innovation | self-harness catalog | this phase §2 detector + §3 triage |
| **Backward 2: family -> template** | family innovation | template (via self-harness) | this phase §3 decision -> phase-10 stage 2 |
| **Lateral: family -> family** | family-A | family-B | self-harness catalog + direct apply queue |

All 5 directions hub through the central harness. For active managed repos, the central harness has direct apply authority.

## 5. Template Sync Runbook §8a (R9 Hardened)

This section supplements phase-10 §3-3 sync procedure. Perspective of an external user (new family owner who cloned the template).

### 5-1. Template User Perspective (greenfield owner)
```bash
# 1. clone
git clone https://github.com/<org>/claude-codex-harness new-family

# 2. family initialization (see phase-10 section 5-1)
python scripts/bootstrap.py --family-name new-family --family-type SE-product

# 3. After first cycle, optional: set up communication with central harness
# Add central harness hub endpoint to .claude/settings.json (optional)
# Family can operate standalone without communication, but repos in a managed workspace become direct-apply targets.
```

### 5-2. Existing Family Perspective (receiving template updates)
```bash
# 1. Receive new template version notification from central harness or Discord
# 2. Review template changes
git -C /path/to/claude-codex-harness log v1.0.0..v1.1.0

# 3. Decide on cherry-pick for your family
# - adopt: apply changes to family .claude/
# - decline: notify central harness of declined status (CLI or manual)
```

### 5-3. Share-Back Perspective (family -> central harness)
```bash
# 1. Family produces innovation
# 2. Central harness detects via daily scan (auto) OR
#    family owner manually notifies
python -m tools.fleet_observe.harness_drift --notify <innovation_id>

# 3. Added to central harness triage queue -> operator review -> section 3 decision
```

## 6. Conflict Resolution

When an innovation conflicts with existing template patterns.

### 6-1. Conflict Types
| Type | Example | Decision Procedure |
|---|---|---|
| **Incompatible** | family-A hook occupies same trigger as family-B hook | Operator review -- pick one or merge |
| **Abstractable** | Similar patterns in both family-A and family-B -> abstract and promote to template | Absorb to self-harness then template promote |
| **Individual specialization** | Only applicable to specific family | Archive (no share) |

### 6-2. Decision Owner
- Code conflicts (hook trigger overlap etc.) -> explicit operator review.
- Semantic conflicts (e.g., design philosophy differences between SE-product and SE-meta) -> automatic compatibility check via family_type matrix (phase-9 §5-2).

## 7. Application Status

| Item | Status | Location |
|---|---|---|
| `harness_drift.py` | landed | `tools/fleet_observe/harness_drift.py` |
| Triage UI (Discord digest) | partial (manual Discord notification) | Discord notification (auto cron not running) |
| `share_dispatcher` | landed | `tools/fleet_observe/share_dispatcher.py` |
| This phase doc | this round | this file |
| Sync runbook 3 perspectives | this section | (operator-reviewable and expandable) |

## 8. ADR Candidate

ADR-27 -- Back-Propagation Pipeline (3-way share-back, conflict resolution).

## 9. Exit Criterion

This phase is done when:
1. `harness_drift.py` spec (this §2) published -- code land in a later round.
2. 4 triage decisions (this §3-1) documented in operator-reviewable form.
3. All 5 sync directions (this §4) have explicit triggers.
4. Operator review passed.

## 10. Next Step

Next round -- implement phase-9/10/11 doc code (drift detector + share dispatcher + sanitize_for_template). No new phase needed -- this is a separate implementation round.
