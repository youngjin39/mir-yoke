---
status: design-v1
date: 2026-05-23
scope: greenfield family Day-0 / Day-1 / Day-7 operational checklist
audience: greenfield repo owner (e.g., example-brand pattern) + your-harness Role A (catalog registration)
priority: R10-T02 newly established (resolves R9 Slice D Scenario 1 BLOCKING)
---

# Bootstrap Day-0 / Day-1 / Day-7 Checklist

> **Purpose**: Explicit procedure for new families (greenfield) during the first 24 hours and first week after template clone. Resolves R9 audit (Slice D Scenario 1) "no Day-0 checklist" BLOCKING.

## 0.5 Design Goals (R10 anchor)

**3-axis contribution**:
- **Axis I (your-harness strengthening)**: your-harness-as-agent (Role A) automates catalog registration procedure for new families
- **Axis II (Public template sync)**: proves template is the verifiable starting point for new projects with measurable procedures
- **Axis III (Fleet central management + back-propagation)**: catalog tracking + share recommendation reception enabled from day-0 of new family

**Inter-phase contract**:
- **Input** (consumed): latest release of `template-harness` + user intent (what this repo will do)
- **Output** (produced): family repo `.claude/` bootstrap + `config/repos/<name>.json` creation + catalog row registration → daily scan entry

## 1. Day-0 (First 24 Hours)

### Step 1 — Clone template
```bash
git clone https://github.com/<your-org>/mir-yoke <new-family-name>
cd <new-family-name>
```

### Step 2 — Determine family identity (interview)
**Required decisions** (aligned with R10-T07 bootstrap interview spec):

| Item | Meaning | Example |
|---|---|---|
| `family_name` | repo slug (kebab-case) | `recipe-tracker` |
| `family_type` | 6-Type classification | `SE-product` |
| `purpose` | one-line mission (R10 new schema field) | "recipe database + meal plan tracker" |
| `character` | distinguishing traits (controlled vocab list) | `["desktop-app", "personal-data", "offline-first"]` |
| `enabled_phases` | phases the family will adopt | `[0,1,2,3,4,5,7,8]` (phase-6 opt-out, phase-9~11 catalog only) |
| `custom_skills` | family-private new skill candidates | `["recipe-management"]` |
| `sealed` | whether external git push is prohibited | `false` |
| `external_path` | actual git working path of the family | `/Users/.../recipe-tracker` |

### Step 3 — Run bootstrap.py
```bash
# At R10 stage: tools/profile_compiler/bootstrap.py handles family_type defaults only (R11 adds new interview)
# R10 manual fallback:
python tools/profile_compiler/bootstrap.py \
  --family-slug recipe-tracker \
  --display-name "Recipe Tracker" \
  --family-path /Users/.../recipe-tracker \
  --archetype code_app \
  --management-mode standard \
  --rollout-class immediate_migrate
```

At R10 stage — then manually edit `config/repos/recipe-tracker.json` to add `family_type`, `purpose`, `character`, `enabled_phases`, `custom_skills` fields.

### Step 4 — Verify family identity
```bash
python scripts/verify_repo_agent_management.py
# Expected: exit 0, no errors
```

### Step 5 — Update Family CLAUDE.md / AGENTS.md
Replace generic template expressions with family-specific values:
```bash
# Replace family name + purpose (not Korean → English translation)
sed -i "s/your-harness/recipe-tracker/g" CLAUDE.md
sed -i "s/your-harness/recipe-tracker/g" AGENTS.md
```

After bootstrap, verify role contract:
- Confirm `Main agent parity:` is preserved in `CLAUDE.md` and `AGENTS.md`
- Confirm `Delegated sub-agents are the default execution plane` is preserved
- Confirm `Codex-first backend default:` is preserved

### Step 6 — Register in your-harness catalog
```bash
# R10 manual fallback:
# Manually add new family row to config/fleet-harness-state.json
python3 -c "
import json
state = json.load(open('config/fleet-harness-state.json'))
state['families']['recipe-tracker'] = {
    'family_type': 'SE-product',
    'repo_path': '/Users/.../recipe-tracker',
    'purpose': 'recipe database + meal plan tracker',
    'character': ['desktop-app', 'personal-data', 'offline-first'],
    'adoption': {
        'phase-0': {'status': 'opt_in_pending'},
    },
    'innovations': [],
    'recommendations_received': []
}
json.dump(state, open('config/fleet-harness-state.json', 'w'), indent=2, ensure_ascii=False)
"
```

R11 automation: `python tools/fleet_observe/register_family.py --slug recipe-tracker --config config/repos/recipe-tracker.json`

### Step 7 — First commit
```bash
git remote set-url origin <new-repo-url>
git add .
git commit -m "bootstrap: harness engineering from template-harness v$(cat VERSION 2>/dev/null || echo '0.1.0')"
git push -u origin main
```

### Step 8 — Day-0 verification
- ✅ `git log` shows 1 bootstrap commit
- ✅ `config/repos/<name>.json` (your-harness side) exists + verifier exit 0
- ✅ New family row exists in `config/fleet-harness-state.json`
- ✅ Family repo `.claude/` structure intact (hooks + skills + agents present)
- ✅ At least 1 task (`hello world` or README update) runnable

## 2. Day-1 (Next 24 Hours)

### Step 1 — First real task
- Execute 1 actual work item for this family (e.g., first recipe schema definition for recipe-tracker)
- Enter main-orchestrator → confirm 5-element declaration → confirm hook fires correctly

### Step 2 — Phase-by-phase application check
- Verify each phase in enabled_phases is actually running:
  - phase-0: terminology / principle agreement complete (Exit Criterion §11)
  - phase-1: routing working correctly
  - phase-2: hook fires (pre-edit, post-edit, deny-list)
  - phase-3: memory injection working
  - phase-4: state machine (after R11 code land)
  - phase-5: subagent dispatch possible
  - phase-7: family_type-specific strictness applied
  - phase-8: GC cadence (monthly) registered

### Step 3 — Register customizations
- Start writing family-private skill for `custom_skills` (e.g., `recipe-management/SKILL.md`)
- Writing is autonomous to the family; your-harness detects and registers to catalog (phase-11 §2 detector R11)

### Step 4 — First communication with your-harness
- (optional) Discord channel integration — `mcp__plugin_discord_discord__reply` etc. available
- (optional) your-harness confirms new family state on first daily scan

### Step 5 — Day-1 verification
- ✅ 1 first real task complete (PASS or user review)
- ✅ All hooks in enabled_phases fired at least once (check advisory log)
- ✅ 1 custom_skill file created
- ✅ `last_sync` timestamp updated for family after your-harness first daily scan

## 3. Day-7 (First Week)

### Step 1 — Self-evaluation
- Compare with phase application ledger in `applications/example-harness/`
- Identify partial / pending items in this family's phase application

### Step 2 — First innovation OR adoption
- (innovation case) family generates new pattern → your-harness detects (manual today: `harness_drift --notify <id>`)
- (adoption case) your-harness recommends new template capability → family decides cherry-pick

### Step 3 — Fleet observability
- Check first week results for this family on phase-6 7-axis measurement
- Record first baseline for the actionable subset among 12 metrics (cost / latency / tool_use)

### Step 4 — Day-7 verification
- ✅ 1 first share recommendation processed (adopted / declined / pending)
- ✅ phase-6 7-axis week-1 report output
- ✅ `adoption[phase-N].drift` updated for this family in fleet-harness-state.json (vs template baseline)
- ✅ First entry for this family registered in your-harness weekly digest (Sun 12:00)

## 4. Required User Decision Points

User explicit decision is required at the following points in this runbook (your-harness does NOT proceed automatically):

| Point | Decision item |
|---|---|
| Day-0 Step 2 | family_type / purpose / character / enabled_phases (interview) |
| Day-0 Step 6 | your-harness catalog registration (for family types requiring explicit user add) |
| Day-1 Step 3 | whether to write custom skill |
| Day-7 Step 2 | first share recommendation decision |

## 5. Failure Modes (Day-0/1/7)

| Failure | Cause | Resolution |
|---|---|---|
| bootstrap.py error | archetype mismatch / family_path permission | manual fallback (Step 3 R10 stage) |
| verify_repo_agent_management.py fail | missing family_type / sealed_policy | direct edit config/repos/<name>.json |
| your-harness catalog registration failure | fleet-harness-state.json permission / schema violation | R11 register_family.py or manual JSON edit |
| Day-1 hook not firing | enabled_phases missing a phase | update enabled_phases + re-register hook |
| Day-7 first share decline-only | family isolation intent | review sealed=true label + explicit user decision |

## 6. R10 / R11 Separation

| Area | R10 (this doc) | R11 (code land) |
|---|---|---|
| Day-0 7-step procedure (manual) | ✅ | bootstrap.py interview automation |
| Day-1 phase verification | ✅ doc | automated verifier script |
| Day-7 first share handling | ✅ doc | share_dispatcher automation |
| your-harness catalog registration (manual) | ✅ | `register_family.py` automation |
| Failure mode manual | ✅ doc | automated diagnosis script |

## 7. your-harness Application Status (2026-05-23)

| Item | Status |
|---|---|
| Day-0/1/7 checklist | **this R10-T02 land** |
| bootstrap.py interview | **partially landed** (archetype only — `purpose` / `character` R11) |
| register_family.py | **not yet** (R11) |
| Day-1 verifier | **not yet** (R11) |
| Failure mode auto-diagnosis | **not yet** (R11) |

## 8. Exit Criterion

1. Day-0 8-step procedure ✓
2. Day-1 5-step procedure ✓
3. Day-7 4-step procedure ✓
4. Required user decision points specified ✓
5. Failure modes table ✓
6. R10/R11 separation ✓
7. User review passed

R9 Slice D Scenario 1 (greenfield bootstrap) walkability: PARTIAL → YES (manual today, fully YES after R11 automation land).

## 9. Next Steps

R11 code land — bootstrap.py interview expansion, register_family.py, Day-1 verifier, share_dispatcher automation.
