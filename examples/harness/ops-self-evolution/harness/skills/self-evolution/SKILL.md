---
name: self-evolution
description: Self-improvement judgment and execution for an agent harness — scan for upgrades, reflect on long-term memory, classify change candidates by risk, and gate technical claims through a 3-tier validation. Use when asked to self-improve, research tooling upgrades, reflect on memory, or review a proposed change to the harness itself.
---

# Self-Evolution

Self-improvement judgment + execution skill for the harness.

Trigger: self-improve, research, reflect, self-review, evolution, upgrade check

## When activated

1. Read your repo's self-evolution rules first (e.g. a `SELF-EVOLUTION.md` you keep
   in your repo) — that doc is the source of truth; this skill is the generic flow.
2. Determine which sub-function applies:
   - **research**: AI/tooling research scan.
   - **reflect**: long-term memory deep reflect.
   - **review**: version delta + change-type classification.
   - **validate**: research validation gate.
   - **snapshot**: docs diff.

## Sub-functions

### research
1. Scan sources (your tooling's release notes, AI news, skill registries).
2. For each finding, run the validation gate below (T1 source -> T2 reproduce -> T3 value).
3. Ingest validated findings into your long-term memory store + report to the user.

### reflect
1. Run your memory store's maintenance report to surface stale / duplicate / conflicting entries.
2. Stage short summaries (keep the working set small, ~2-5k tokens).
3. Judge each: keep / merge / archive / delete.
4. Apply to your memory store + log the decision.

### review
1. Classify the change candidate as Type A/B/C/D:
2. Type A (trivial/safe) -> fix immediately, report after.
3. Type B (user-visible) -> propose to the user, apply on approval.
4. Type C (behavioral) -> stage + apply a cooling-period delta gate.
5. Type D (structural) -> design doc -> user review -> 4-step promotion.

### validate
Apply a 3-tier gate to any technical claim:
- **T1: Source** — does it exist? (official docs, GitHub, release notes)
- **T2: Reproducible** — can you install/run it locally?
- **T3: Valuable** — does it benefit your harness + memory setup?

## Hard rules

- Never apply Type C/D changes without user approval.
- Never trust AI-generated function names / APIs without T1 verification.
- Keep a cooling period before landing Type C changes.
- All structural changes (Type D) require a promotion record.
