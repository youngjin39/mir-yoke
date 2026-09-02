---
status: design-v1
date: 2026-05-23
scope: end-to-end family → your-harness → family share-back runbook
audience: your-harness Role A/B + family owners
priority: R10-T11 new (resolves Slice D Scenario 4 BLOCKING)
---

# Share-Back Runbook — end-to-end family → your-harness → family

> **Purpose**: End-to-end procedure for detecting a family-originated innovation → cataloging → sharing to other families. **Each step has a "manual today / scripted R11" column** — users can operate manually until R11 code lands. Operating guide for phase-11.

## 0.5 Design Goals (R10 anchor)

**3-axis contribution**:
- **Axis I (your-harness strengthening)**: Formalize your-harness Role A's share-back operating procedure in an observable form
- **Axis II (public template sync)**: Specify template promote path for family innovations (forward 2 directions)
- **Axis III (fleet central management / back-propagation)**: Observable operating guide for 5 sync directions (phase-11 §4) — not enforced, opt-in

**Inter-phase contract**:
- **Input** (consumed): [phase-11 §1 3-node hub diagram](../phase-11-back-propagation.md) + [phase-11 §2 detector spec](../phase-11-back-propagation.md) + [phase-11 §3 Triage 4](../phase-11-back-propagation.md)
- **Output** (provided): family-by-family share decision history + your-harness Role B's template promote queue → [phase-10 stage 3](../phase-10-rollout-pipeline.md) trigger

## 1. End-to-End Flow (6 steps)

```text
[Step 1: Family innovation occurs]
   ↓ (manual today: family owner notifies; scripted R11: harness_drift.py daily scan)
[Step 2: your-harness detects + registers in catalog]
   ↓ (manual today: user manually edits JSON; scripted R11: harness_drift writes to JSON)
[Step 3: Triage 4 decision (user review)]
   ↓ (manual today: Discord chat; scripted R11: Discord weekly digest + decision UI)
[Step 4: Dispatch (action by decision)]
   ↓ (manual today: user + your-harness collaboration; scripted R11: share_dispatcher.py automated)
[Step 5: Other family adoption decision]
   ↓ (manual today: family owner Discord reply; scripted R11: family_decision.py CLI)
[Step 6: Final catalog update + Discord log]
   ↓ (manual today: user JSON edit; scripted R11: automated)
```

## 2. Per-Step Manual / Scripted Procedures

### Step 1 — Family innovation occurs

**Manual today**:
- Family owner writes new skill / hook / agent / phase pattern in their repo
- Notifies your-harness via Discord or explicit user message:
  ```
  [innovation notify] example-video
  - kind: skill
  - path: .claude/skills/scene-render/SKILL.md
  - reason: scene render automation for video production pipeline
  ```

**Scripted R11** (manual `--notify` scripted R29-T02 2026-05-24):
- `tools/fleet_observe/harness_drift.py` daily 04:30 cron automatically scans `.claude/{skills,hooks,agents}/` file diffs for all fleet families
- `--notify` flag allows family owner to register immediately (landed R29-T02):
  ```bash
  python tools/fleet_observe/harness_drift.py --notify scene-render-pipeline-2026-05-20 \
    --family example-video --kind skill --path .claude/skills/scene-render/SKILL.md
  ```

### Step 2 — your-harness detects + registers in catalog

**Manual today**:
- User or your-harness-as-agent directly edits `config/fleet-harness-state.json`:
  ```python
  # CLI snippet (R10 manual)
  python3 << 'EOF'
  import json
  state = json.load(open("config/fleet-harness-state.json"))
  innovations = state["families"]["example-video"]["innovations"]
  innovations.append({
    "id": "scene-render-pipeline-2026-05-20",
    "kind": "skill",
    "phase": "phase-5",
    "path": ".claude/skills/scene-render/SKILL.md",
    "detected_at": "2026-05-20T00:00:00Z",
    "share_status": "candidate",
    "source": "example-video",
    "diff_summary": "scene render automation pipeline"
  })
  json.dump(state, open("config/fleet-harness-state.json", "w"), indent=2, ensure_ascii=False)
  EOF
  ```

**Scripted R11**:
- `harness_drift.py` appends detection results to `fleet-harness-state.json.families.<source>.innovations[]`
- Simultaneously records detection event in `config/fleet-drift-log/<family>-<ts>.json` (for audit)

### Step 3 — Triage 4 decision (user review)

**Manual today**:
- User reviews `candidate` items in catalog's `innovations[]`
- Declares one of 4 decisions in Discord:
  ```
  innovation scene-render-pipeline-2026-05-20:
  decision: share to fleet (hybrid_pipeline families only — character compatibility: media-pipeline)
  ```
- your-harness-as-agent updates `share_status` to reflect decision (manual JSON edit)

**Scripted R11**:
- Weekly Discord digest (Sun 12:00) automatically sends pending candidates:
  ```
  [weekly share digest 2026-06-01]
  New candidates (3):
  1. scene-render-pipeline-2026-05-20 (example-video) — hybrid_pipeline/media-pipeline
     Reply: `triage scene-render-pipeline-2026-05-20 share|absorb|promote|archive`
  ...
  ```
- User reply → `share_dispatcher.py` automatically dispatches

Worked example (2026-05-28):
- `terse-output-policy-2026-05-28` (source=`your-harness`, phase=`phase-10`) was triaged as `share_to_fleet`
- pre-dispatch self-stop returned `WARN` (`design-level only`), not `BLOCK`
- `share_dispatcher.py` appended `recommendations_received[]` to 13 target families
- this created catalog evidence for recommendation readiness without claiming target-family adoption

### Step 4 — Dispatch (action by decision)

| Decision | Manual today | Scripted R11 |
|---|---|---|
| **share to fleet** | User manually adds entry for compatible families in `recommendations_received[]` | `share_dispatcher.py` automatically adds based on compatibility matrix (phase-9 §5-2) |
| **absorb to your-harness** | User creates your-harness TODO (`tasks/plan.md` entry) + runs separate round | `share_dispatcher.py` automatically creates your-harness TODO queue (e.g., `tasks/absorb_queue.json`) |
| **promote to template directly** | User manually runs phase-10 stage 2 (sanitize + sync + version bump) | `share_dispatcher.py` creates PR draft + waits for Role B review |
| **archive (no share)** | User updates `share_status: archived` + records reason | Automated update |

### Step 5 — Other family adoption decision

**Manual today**:
- Other family owner reviews `recommendations_received[]` in catalog (reading JSON directly or via Discord digest)
- Declares decision in Discord reply:
  ```
  family example-content: adopt scene-render-pipeline-2026-05-20 (yes)
  ```
- User or your-harness-as-agent updates JSON:
  ```python
  rec = state["families"]["example-content"]["recommendations_received"][0]
  rec["decision"] = "adopted"
  rec["decided_at"] = "2026-06-05T...Z"
  ```

**Scripted (R29-T01 — `tools/fleet_observe/family_decision.py`)**:
- `python -m tools.fleet_observe.family_decision --family example-content --id scene-render-pipeline-2026-05-20 --decision adopted`
- 30 day timeout → automatic `declined`

### Step 6 — Final catalog update + Discord log

**Manual today**:
- User reviews and determines `share_status` final state
- Writes Discord audit log manually

**Scripted R11**:
- Automatic daily / weekly aggregation report:
  ```
  [share-back week 2026-06-01]
  Innovation scene-render-pipeline-2026-05-20:
  - share to fleet: 2 adopted (example-content, example-personal), 1 declined (example-notes)
  - 2 pending (example-brand, example-app)
  ```

## 3. SE-meta Self-Stop Verification (ADR-41 alignment)

At the point of sharing a `source=your-harness` innovation:
1. `scripts/verify_self_stop.py` (R11) fires just before Step 4 dispatch
2. Verifies the relevant phase status in the your-harness ledger
3. status != adopted → BLOCK (user override possible)

This hook prevents your-harness Role A from over-rating risk.

## 4. Family-Private Skill Registration Procedure (R10-T12 alignment)

When a family creates a new skill of their own (not in your-harness reference):
1. Family commits to their repo freely
2. your-harness Role A detects in Step 2 scan
3. Registers in catalog as `kind: skill, share_status: candidate, source: <family>`
4. Triage decision — **absorb to your-harness or promote to template** is the explicit path from family-private to fleet-wide
5. archive decision → keeps as family-private (not included in your-harness reference)

**Contradiction resolved**: The rule in `template-cherrypick.md:96` "add only from your-harness reference" applies at the **cherry-pick time point** (family adding a your-harness reference skill to their enabled skill set). Family-private skill creation is separate — it can only enter your-harness reference through the share-back path in this §4.

→ `template-cherrypick.md` body updated ([R10-T12 — template-cherrypick.md §4-2-bis](template-cherrypick.md)): "add only from your-harness reference / new family-private skills can be added only after being registered in your-harness reference through share-back".

## 5. hybrid_pipeline → SE-meta Compatibility Matrix vs Triage "absorb to your-harness" Contradiction Resolution

R9 audit (Slice D Scenario 4 finding #3) contradiction:
- `phase-9 §5-2` compatibility matrix: hybrid_pipeline → SE-meta = ✗ (auto skip)
- `phase-11 §3-1` Triage: "absorb to your-harness" is a valid decision

**Resolution** ([R10-T13 — phase-9 §5-2 footnote](../phase-9-fleet-catalog.md)):
- Compatibility matrix ✗ = **only blocks auto recommendation** (Step 4 dispatch auto skip)
- **User explicit override** can fire "absorb to your-harness" — Step 3 Triage user decision takes precedence over compatibility matrix
- That is:
  - Auto share to fleet (Step 4 automated): hybrid_pipeline → SE-meta = ✗
  - Manual absorb to your-harness (Step 4 user decision): hybrid_pipeline → SE-meta = possible (after user explicit review)

`phase-9 §5-2` compatibility matrix footnote added (R10-T13): "This matrix is the compatibility determination for auto recommendations. Manual override via Triage decision (Step 3) is not subject to this."

## 6. R10 / R11 Separation

| Area | R10 (this doc + template-cherrypick §4-2-bis + phase-9 §5-2 footnote) | R11 (code land) |
|---|---|---|
| End-to-end 6-step procedure | ✅ | `share_dispatcher.py` + `family_decision.py` automation |
| Manual fallback per step | ✅ | (user uses R10 manual when needed) |
| SE-meta self-stop integration | ✅ ADR-41 | `verify_self_stop.py` actual code |
| Family-private skill path | ✅ template-cherrypick updated | `harness_drift.py` family-private detection |
| Compatibility matrix vs Triage contradiction resolved | ✅ phase-9 §5-2 footnote | `share_dispatcher.py` manual override flag |
| Discord weekly digest | ✅ format spec | actual cron + Discord API integration |

## 7. your-harness Application Status (2026-05-23)

| Item | Status |
|---|---|
| This runbook | **R10-T11 landed** |
| harness_drift.py | **landed** (R24-T05 correction 2026-05-24) — `tools/fleet_observe/harness_drift.py` (551 LOC) |
| share_dispatcher.py | **landed** (R24-T05 correction 2026-05-24) — `tools/fleet_observe/share_dispatcher.py` (858 LOC) |
| family_decision.py | **landed** (R29-T01 scripted 2026-05-24) — `tools/fleet_observe/family_decision.py` (119 LOC) |
| verify_self_stop.py | **landed** (R24-T05 correction 2026-05-24) — `scripts/verify_self_stop.py` (ADR-41 spec) |
| Discord weekly digest cron | **not yet** (R27 scope, manual notification in operation) |

## 8. Exit Criterion

1. End-to-end 6-step flow ✓
2. Manual / scripted procedure per step ✓
3. SE-meta self-stop integration ✓
4. Family-private skill registration path contradiction resolved ✓
5. Compatibility matrix vs Triage contradiction resolved ✓
6. R10 / R11 separation ✓
7. User review passed

R9 Slice D Scenario 4 (family share-back) walkability PARTIAL → YES (manual today, R11 fully YES).

## 9. Next Steps

R11 code land — `harness_drift.py` + `share_dispatcher.py` + `family_decision.py` + Discord integration. Also R10-T12/T13 body edits to phase-9/template-cherrypick (to land next).
