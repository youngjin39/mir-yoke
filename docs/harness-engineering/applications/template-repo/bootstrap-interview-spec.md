---
status: design-v1
date: 2026-05-23
scope: bootstrap.py CLI interview expansion (R11 code spec)
audience: R11 developer + your-harness-as-agent (Role A automation stage)
priority: R10-T07 newly established (resolves R9 Slice C BLOCKING #2)
---

# Bootstrap Interview Spec (R10 design → R11 code)

> **Purpose**: bootstrap.py CLI spec for interactively collecting **purpose / character / custom skill needs / phase opt-outs** of the family identity during greenfield family bootstrap. R10 design, R11 code land.

## 0.5 Design Goals (R10 anchor)

**3-axis contribution**:
- **Axis I (your-harness strengthening)**: your-harness-as-agent (Role A) schemas new family identity from day-0
- **Axis II (Public template sync)**: template's `bootstrap.py` provides fleet-wide consistent interview procedure
- **Axis III (Fleet central management + back-propagation)**: catalog's new family row enables share-back compatibility assessment with purpose+character

**Inter-phase contract**:
- **Input** (consumed): user explicit answers (interactive prompt OR CLI args)
- **Output** (produced): `config/repos/<name>.json` (your-harness side) + family repo `.claude/family-config.json` + catalog new row → daily scan entry

## 1. Current bootstrap Limitations (R10 baseline)

`tools/profile_compiler/bootstrap.py` (your-harness) currently collects only 6 fields:
- `family_slug`
- `display_name`
- `family_path`
- `archetype`
- `management_mode`
- `rollout_class`

R9 audit (Slice C Q2) defects:
- "what this repo does (purpose)" not asked → recipe-app and example-game share the same default
- "what traits (character)" not asked → only family_type classification = 5 bucket / fleet families
- "custom skill needed?" not asked → manual post-bootstrap addition required
- "which phases to opt-out?" not asked → only family_type defaults applied

## 2. R11 New Interview Items (3 categories)

### Category A — Identity (R11 mandatory)
| Field | type | example prompt | validation |
|---|---|---|---|
| `family_slug` | string (kebab) | "Family slug? (e.g., recipe-tracker)" | `^[a-z0-9][a-z0-9-]*[a-z0-9]$` |
| `display_name` | string | "Display name?" | non-empty |
| `family_path` | string (abs path) | "Family repo absolute path?" | dir exists |
| `family_type` | enum | "Family type? [SE-meta/code_app/SE-product/hybrid_pipeline/template]" | enum match |
| `purpose` | string (max 200) | "One-line mission/purpose?" | non-empty, ≤200 chars |
| `character` | string[] (controlled vocab) | "Distinguishing traits? (comma-separated, see schema enum)" | enum match |

### Category B — Customization (R11 optional, default available)
| Field | type | prompt | default |
|---|---|---|---|
| `enabled_phases` | int[] | "Enabled phases? (default: per family_type phase-10 §5-3)" | per family_type default |
| `custom_skills` | string[] | "Custom skills to author? (comma-separated)" | empty |
| `hooks_enabled` | object | "Hook overrides? (default: all enabled)" | all-enabled |
| `sealed` | bool | "Sealed (block external push)?" | `false` |

### Category C — Operational (R11 optional)
| Field | type | prompt | default |
|---|---|---|---|
| `archetype` | enum | "Archetype? [code_app/hybrid_pipeline/content_workspace/...]" | derived from family_type |
| `management_mode` | enum | "Management mode? [standard/bounded/minimal]" | `standard` |
| `rollout_class` | enum | "Rollout class? [immediate_migrate/observe_first/supersede]" | `observe_first` |
| `external_path` | string | "External git path (if different from family_path)?" | == family_path |

## 3. CLI Modes

**R10-R1 path decision**: this spec is an R11 extension to the existing `tools/profile_compiler/bootstrap.py` (R8 land). Do NOT create a new `scripts/bootstrap.py` — add interview + purpose/character options to the existing module.

### 3-1. Interactive mode (default)
```bash
python -m tools.profile_compiler.bootstrap --interactive
# Sequential prompts for Category A, then B, then C
```

### 3-2. Args mode (CI / scripted)
```bash
python -m tools.profile_compiler.bootstrap \
  --family-slug recipe-tracker \
  --display-name "Recipe Tracker" \
  --family-path /Users/.../recipe-tracker \
  --family-type SE-product \
  --purpose "recipe database + meal plan tracker" \
  --character desktop-app,personal-data,offline-first \
  --enabled-phases 0,1,2,3,4,5,7,8 \
  --custom-skills recipe-management
```

### 3-3. Manifest mode (R11+)
```bash
python -m tools.profile_compiler.bootstrap --manifest family-recipe-tracker.yaml
```

## 4. Manifest YAML format (R11)
```yaml
# family-recipe-tracker.yaml
family_slug: recipe-tracker
display_name: Recipe Tracker
family_path: /Users/.../recipe-tracker
family_type: SE-product
purpose: recipe database + meal plan tracker
character:
  - desktop-app
  - personal-data
  - offline-first
enabled_phases: [0, 1, 2, 3, 4, 5, 7, 8]
custom_skills: [recipe-management]
hooks_enabled:
  pre-commit-verification.sh: enabled
sealed: false
archetype: code_app
management_mode: standard
rollout_class: observe_first
```

## 5. Output Artifacts

bootstrap.py generates the following outputs:

### 5-1. `config/repos/<slug>.json` (your-harness side)
Commit all input values in `family-config.schema.json`-compliant format.

### 5-2. Family repo `.claude/family-config.json` (R11 new)
Commit the same information to the family side (cross-reference + self-recovery when your-harness is unavailable).

### 5-3. `config/fleet-harness-state.json` new row append
Add new family row to catalog + all phases default to `opt_in_pending`.

### 5-4. Family repo profile and startup source
Auto-replace template generic expressions in `.mir/repo-profile.toml` and `CLAUDE.md`, then
regenerate `AGENTS.md` and other Codex derivatives.

### 5-5. Discord notification
your-harness Role A sends new family registration notification (for user + self).

## 6. Validation

### 6-1. Schema validation
All inputs must conform to `repo-agent-management.schema.json` + `family-config.schema.json`.

### 6-2. Cross-field validation
- If `enabled_phases` includes `enforced` strictness → `self_stop_acknowledged: true` required + prompted
- If `sealed: true` → `sealed_policy.reason` required prompt
- If both `purpose` and `character` empty → warning (avoid 3.4 family/bucket classification issues)

### 6-3. Verifier pass required
`python scripts/verify_repo_agent_management.py` auto-runs immediately after bootstrap → exit 0 required.

### 6-4. Runtime role contract pass required
- Bootstrap output must preserve Claude/Codex Main parity in `CLAUDE.md` and generated `AGENTS.md`.
- Bootstrap output profile baseline must specify `main_agent_contract = "shared_parity"` and `delegated_execution_contract = "subagents_codex_first"`.
- Before public-template promotion, verify role contract with `python scripts/verify_template_applied_state.py` or equivalent verifier.

## 7. R10 / R11 Separation

| Area | R10 (this doc) | R11 (code land) |
|---|---|---|
| Interview item spec (Category A/B/C) | ✅ | bootstrap.py interactive prompt + args parsing |
| Manifest YAML format | ✅ | `--manifest` flag handling |
| Output 5 artifact spec | ✅ | actual file generation code |
| Validation 3 layers | ✅ | schema + cross-field + verifier chain |
| Family repo `.claude/family-config.json` new file | ✅ doc | actual file write + sync |

## 8. your-harness Application Status (2026-05-23)

| Item | Status |
|---|---|
| This spec doc | **this R10-T07 land** |
| bootstrap.py interview expansion | **not yet** (R11) |
| Manifest mode | **not yet** (R11) |
| Family repo .claude/family-config.json | **not yet** (R11) |

## 9. Exit Criterion

1. Category A/B/C items + validation specified ✓
2. CLI 3 modes (interactive / args / manifest) ✓
3. Output 5 artifacts specified ✓
4. R10/R11 separation ✓
5. User review passed

R9 Slice C BLOCKING #2 (bootstrap interview absent) resolved — design complete. Code R11.

## 10. Next Steps

R11 code — bootstrap.py expansion + `.claude/family-config.json` self-recovery format + Discord notification integration.
