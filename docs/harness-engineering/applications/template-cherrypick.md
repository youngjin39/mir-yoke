---
status: design-v1
date: 2026-05-23
scope: central template + partial cherry-pick model
audience: your-harness operators + external family operators
---

# Template Cherry-Pick — Central Template + Partial Selection Copy Model

> **Core**: your-harness = reference implementation for all phases. External families **partially copy** at the phase / skill / agent / hook granularity and apply to their repository's characteristics.

## 1. Definitions

The "harness engineering template" unit consists of 5 layers:

| Layer | Unit | Cherry-pick eligible |
|---|---|---|
| L1 | Phase (all phases) | Family selects via `enabled_phases` |
| L2 | Skill (skill catalog) | Per-family `add_skills` / `remove_skills` |
| L3 | Agent (agent catalog) | Per-family `add_specialists` / `remove_specialists` |
| L4 | Hook (hook library) | Per-family hook activation set |
| L5 | Config snippet (CLAUDE.md / AGENTS.md sections) | Partial inclusion via `@import` |

Families can freely select from all 5 layers.

## 2. Blueprint Integration

| Blueprint | Application to this document |
|---|---|
| [Phase 7 §8 Cross-pollination](../phase-7-fleet-expansion.md) | L2/L3 cross-pollination catalog |
| [Phase 7 §9 Public Template Sync](../phase-7-fleet-expansion.md) | template-harness public template |
| [Phase 3 §10 @import splitting](../phase-3-memory-context.md) | L5 config snippet partial inclusion |
| [`exceptions.md`](exceptions.md) §3 strictness matrix | L1 phase strictness defaults |
| ADR-13 harness-generator-bootstrap | bootstrap.py automates cherry-pick |

## 3. Central Template (your-harness reference impl)

your-harness maintains the **reference implementation for all items in all 5 layers**. Families select a subset and apply it.

### Reference Set your-harness Must Maintain

| Layer | your-harness reference location |
|---|---|
| L1 Phase | `docs/harness-engineering/phase-0`~`phase-N` (phase blueprints) + `applications/example-harness/phase-N-application.md` (application ledger) |
| L2 Skill | `~/.claude/skills/` (global) + `config/repo-agent-management.json` `core_skills` |
| L3 Agent | `.claude/agents/*.md` (15+) + `.codex/agents/*.toml` (mirror) + catalog's `external_agents` |
| L4 Hook | `.claude/hooks/*.sh` (your-harness body) + `scripts/lib/hooks/` (common library) |
| L5 Config | `CLAUDE.md` body + `AGENTS.md` + `@import` targets |

If your-harness cannot maintain the reference, cherry-pick itself becomes impossible → SE-meta self-stop violation.

## 4. Cherry-pick Mechanisms by Unit

### 4-1. L1 Phase cherry-pick

`enabled_phases` field in family JSON ([exceptions.md §5](exceptions.md)).

```yaml
# config/repos/example-infra.json (code_app example)
enabled_phases:
  - phase: 0
    strictness: doc-strict   # Phase 0 specific intensity (R4 terminology)
  - phase: 1
    strictness: enforced
  - phase: 2
    strictness: enforced     # code_app → exceptions.md §3 matrix default
  - phase: 4
    strictness: warn         # Light state machine adoption
  - phase: 7
    strictness: enforced
  # phases 3, 5, 6, 8 not selected (not applied)
```

**Valid strictness values** ([`exceptions.md`](exceptions.md) §3 basis): `doc-strict` (Phase 0 only) / `enforced` (Phase 1+) / `warn` / `off`. All `strict` written before R5 were cleaned up in R5-R1.

Unselected phases have hooks not applied. Selected phases have their strictness applied.

### 4-2. L2 Skill cherry-pick

`skill_overrides` field in family JSON (already landed in some families).

```yaml
# config/repos/example-content.json (hybrid_pipeline example)
skill_overrides:
  add:
    - research
    - publish
    - twitter-draft
    - knowledge-ingest
    - knowledge-lint
  remove:
    - tdd-strict
    - codex-execution-lane
```

`add` can only select from skills in the your-harness reference (rule at cherry-pick time). `remove` removes from family default.

### 4-2-bis. Family-Private Skill Registration Path (R10-T12 resolution)

R9 audit (Slice C BLOCKING #5 + Slice D Scenario 4) found a contradiction:
- Rule in §4-2 above: "add only from your-harness reference"
- Live precedent: example-personal added `think/graphify` (absent from your-harness reference) — example-video self-wrote `scene-render`

**Contradiction resolved (R10-T12)**: Separate the two paths.

| Path | Rule | Example |
|---|---|---|
| **cherry-pick (this §4-2)** | `add` only from your-harness reference skills | Family adds existing your-harness reference skill to their enabled set |
| **family-private creation** | Family writes new skill in their own repo | example-video's `scene-render` (new video pipeline skill) |

**Family-private creation procedure**:
1. Family self-writes `.claude/skills/<new-skill>/SKILL.md` (no your-harness approval required)
2. your-harness Role A detects via daily scan (`harness_drift.py` R11)
3. Registers in catalog `innovations[]` as `share_status: candidate`
4. Triage 4 decision ([phase-11 §3-1](../phase-11-back-propagation.md), [share-back-runbook §1](share-back-runbook.md)):
   - **absorb to your-harness**: Add to your-harness reference → other families can cherry-pick (enters "add" path in this §4-2)
   - **promote to template directly**: Add directly to template (skip your-harness absorption)
   - **share to fleet**: Share recommendation to compatible families (after user decision, then cherry-pick)
   - **archive**: Keep as family-private, not included in your-harness reference

→ The §4-2 rule "add only from your-harness reference" applies **at the cherry-pick time point after going through the 4 steps in §4-2-bis**. Family-private creation itself requires no your-harness approval (consistent with no-force principle).

### 4-3. L3 Agent cherry-pick

`add_specialists` field in family JSON (landed through Phase 4 hybrid_pipeline work).

```yaml
# config/repos/example-stock.json (hybrid_pipeline example)
add_specialists:
  - signal-analyst
  - portfolio-tracker
```

Specialists also selected from your-harness reference's agent catalog (cherry-pick time). New specialist family-private registration follows the same share-back path as §4-2-bis above (R10-T12 aligned). The "select from your-harness reference" in this §4-3 is the rule at cherry-pick time.

### 4-4. L4 Hook cherry-pick

`hooks_enabled` field in family JSON determines which hooks in `.claude/hooks/` are activated.

```yaml
# config/repos/example-notes.json (SE-product example)
hooks_enabled:
  - pre-tool-use
  - pre-commit-verification
  - tdd-guard       # SE-product TDD strictness = warn (exceptions.md §3)
  # session-start-validator not activated (5-element hook not applied)
```

Hooks not activated do not fire even if the file exists in `.claude/hooks/`.

### 4-5. L5 Config snippet cherry-pick

Family's CLAUDE.md partially includes sections from your-harness's CLAUDE.md via `@import`.

```markdown
# config/repos/example-service/.claude/CLAUDE.md example (possible after TC-5 work, not yet implemented)
@import shared/orchestration-presets.md
@import shared/hook-policy-boundary.md
# Family-specific sections written directly
## example-service-Specific Rules
- ...
```

`shared/` comes from your-harness reference sections (e.g., `docs/harness-engineering/shared/`).

**Current state (2026-05-23)**: `docs/harness-engineering/shared/` directory **does not exist**. Planned for creation in §9 TC-5 work.

**Alternative procedure until TC-5 lands (R6 explicit)**:

1. **Manual copy** — Manually copy sections from your-harness CLAUDE.md to family CLAUDE.md. `# BORROWED-FROM: your-harness@<sha> CLAUDE.md#<section>` comment required.
2. **One-way reference link** — Link to absolute path in family CLAUDE.md `ref: <your-harness-path>/CLAUDE.md §Orchestration Presets` (only when family can access your-harness body).
3. **Summary citation** — Summarize only the key decisions from your-harness section in 5-10 lines in family CLAUDE.md. Family manually syncs with user confirm when your-harness body changes.

When TC-5 is created, (1) → replaced with `@import shared/<file>.md` automatic mechanism. Until then, use one of the 3 alternatives above.

### 4-5-1. Effective Phase per Family Type (R8 supplement — Slice D WARN resolution)

When cherry-picking, the effective phases differ by family_type. For personal SE-product families, registering phase 1/2/4/5 in enabled_phases is meaningless (exceptions.md §3 personal SE-product column = off).

| family_type | Effective phases (meaningful to register in enabled_phases) | Ineffective phases (advisory only when registered) |
|---|---|---|
| SE-meta (your-harness, template-harness, claude-starter) | 0 through all | (none) |
| code_app (example-infra, example-service) | 0 through all | (none) |
| SE-product (example-notes, example-game, example-app, example-brand) | 0, 1, 2, 3, 6, 7, 8 enforced | Phase 4/5 = warn |
| hybrid_pipeline (example-content, example-story, example-video, example-stock) | 0, 3, 6, 7, 8 enforced | Phase 1/2 (code path) = warn, Phase 4/5 = warn |
| SE-product personal (example-learning, example-personal) | 0, 3, 6, 7, 8 only | Phase 1/2/4/5 = off (advisory only when registered) |

If a family operator registers an off phase in enabled_phases ignoring this table, fleet_observe advisory generates a false signal from an intensity-0 hook. ADR-21 schema validation logs advisory when this table is violated.

## 5. Cherry-pick Decision Procedure

6-step cherry-pick decision per family.

| Step | Work |
|---|---|
| CP-1 | Confirm family type ([exceptions.md §4](exceptions.md) classify) |
| CP-2 | Look up type-specific default strictness in [exceptions.md §3](exceptions.md) matrix |
| CP-3 | Identify items to override from default (reflecting family characteristics) |
| CP-4 | 5-layer cherry-pick decision — phase / skill / agent / hook / config units |
| CP-5 | Specify `enabled_phases` + `skill_overrides` + `add_specialists` + `hooks_enabled` in family JSON |
| CP-6 | cherry-pick consistency advisory via `scripts/verify_repo_agent_management.py` |

## 6. Sync Policy — Family Propagation on your-harness Changes

How families keep up when your-harness reference changes.

### Automatic Propagation (mandatory — opt-in exceptions)
- L4 Hook security fixes (deny-list new patterns, vulnerability fixes) → **forced sync** for all families (security priority, exception to opt-in default in [`exceptions.md`](exceptions.md) §2 principle 2)
- SE-meta self-stop violation detected → immediate notification to family

**Forced sync execution mechanism**:
- Trigger: security patch commit to your-harness body's `.ai-harness/deny-list.yaml` or `.claude/hooks/*.sh`
- Executor: `scripts/sync_security_patch.py` (TC-4 work output, scripted — R29-T05 land)
- Scope: includes families without `enabled_phases`. Security patches are opt-in exempt
- User notification: `forced_sync` event in per-family advisory_log + Discord push notification
- Revert procedure: security patches do not apply the §6 1-week revert window (revert requires ADR authorship)

### Opt-in Propagation (advisory)
- New phase added to L1 Phase → family decides whether to add to `enabled_phases`
- New skill in L2 Skill → family decides whether to add to `skill_overrides.add`
- New specialist in L3 Agent → same

### Frozen (no propagation)
- Family-specific sections of L5 Config → family's own decision
- Family-only overrides in L2 Skill → family's own decision

## 7. Cherry-pick Conflict Resolution

Example: family adds L2 skill A while removing L3 agent B that skill A depends on.

### Consistency Verification (automated)
- Confirm new skill's required agent is activated for the family
- Confirm new hook's required script exists for the family
- `scripts/verify_repo_agent_management.py` detects dangling references

### Defaults on Conflict
- Skill's required agent absent → skill auto-disabled + advisory
- Hook's required script absent → hook auto-disabled + advisory
- Phase dependency of `enabled_phases` phase not selected → dependency phase also auto-enabled + user confirm

## 8. Public Template Sync

`template-harness` (public template) is a **sanitized version** of your-harness reference.

- Korean → English
- Family-specific examples → generalized expressions
- Private family names / details → redacted
- Sanitization required (`scripts/verify_codex_sync.py`)

External users cherry-picking from `template-harness` use the same §4 mechanism. They see the sanitized mirror, not the your-harness reference itself.

## 9. your-harness Application Priority

| Step | Work | Dependencies | Estimate |
|---|---|---|---|
| TC-1 | Family JSON schema extension — add `enabled_phases` / `hooks_enabled` fields | Phase 7 step 7-5 | 2h |
| TC-2 | Cherry-pick auto-estimation logic in bootstrap.py | TC-1 | 4h |
| TC-3 | Cherry-pick consistency verification in `scripts/verify_repo_agent_management.py` | TC-1 | 3h |
| TC-4 | Sync policy auto-propagation — L4 hook security fix fan-out to all families | TC-1 | 3h | scripted (R29-T05 land) |
| TC-5 | Create `docs/harness-engineering/shared/` directory — L5 config snippet catalog | – | 2h |
| TC-6 | Advisory auto-fire to families when your-harness reference changes | TC-1, TC-3 | 3h |

New work in this §9: 17h. Depends on Phase 7.

## 10. External Modification Allowed — Bidirectional (R6 explicit)

Separating the two meanings of the user-stated "external modification allowed":

### 10-1. Family self-modification rights (forward — your-harness → family)
- After new family onboarding, family operators have rights to **self-modify hooks / skills / agents in their own repo**
- Even after registering `enabled_phases`, families can freely edit `add_specialists` / `skill_overrides` / `hooks_enabled` in family JSON
- 1-week revert window ([`exceptions.md`](exceptions.md) §6) — immediately removable with one word from user after application
- Exception: security patches (§6 automatic propagation) — strict sync

### 10-2. your-harness reverse-pollination (backward — family → your-harness)
- When a family's code/skill/agent is more refined than your-harness reference — absorb family assets as your-harness reference
- Explicit user approval required + dep-auditor subagent verification
- Example: hybrid_pipeline director specialization (Phase 4 work, 2026-05-22) — specialists from example-video / example-stock / example-content absorbed into your-harness external agents catalog
- After absorption, other families can cherry-pick — cross-pollination activated

### 10-3. Additional Exemptions
- When a family uses their own template framework → your-harness cherry-pick not applied. But `external_template: true` field must be specified to protect SE-meta self-stop.
- Exempt families are not exempted from security patch automatic propagation (§6).

## 11. SE-meta Self-Stop

This document is directly related to the self-stop condition.

> If your-harness reference breaks, cherry-pick itself becomes impossible → all families halt.

Automatic verification:
- Check that your-harness reference (§3 table above) is complete on every commit
- Verify your-harness hooks work as intended on your-harness itself using false-negative-tester ([Phase 8 §8](../phase-8-garbage-collection.md))

## 12. Change History

- 2026-05-23: Initial draft. 5-layer cherry-pick + 6-step decision procedure + sync policy + consistency verification.
- 2026-05-23 R1 (after codex-final-reviewer verification and reinforcement): §6 forced sync execution mechanism specifics (trigger / executor / scope / revert exemption). §4-5 `shared/` directory current absence explicitly stated. opt-in exception registered in exceptions.md §2 principle 2.
