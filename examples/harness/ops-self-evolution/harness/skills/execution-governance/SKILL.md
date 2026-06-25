---
name: execution-governance
description: Enforce tier-based write gates, a 4-step promotion flow, a circuit breaker, and evidence-only completion during task execution. Use when a task touches files, when a change needs review/approval, when an action keeps failing, or before declaring work done.
---

# Execution Governance

Enforce tier-based write gates, 4-step promotion, a circuit breaker, and workflow gates during task execution.

Trigger: governance, tier, promotion, circuit breaker, blocked, pre-commit

## When activated

Read your repo's governance rules first (e.g. a `GOVERNANCE.md` you keep in your
repo), then apply the gates below. This skill is the generic pattern; your repo's
doc is the source of truth for which paths sit in which tier.

### Tier Check (before any file write)

Classify the write target into a tier and act accordingly:

- **Tier 0 (free)**: proceed.
- **Tier 1 (review)**: show a diff preview + state the reason before writing.
- **Tier 2 (promotion required)**: execute the 4-step promotion:
  1. PLAN — state reason + impact + rollback.
  2. APPLY — make the change.
  3. VERIFY — run your repo's lint/validation check (tests, linter, schema check).
  4. RECORD — write a promotion record (reason, diff summary, verification result)
     to wherever your repo keeps them.

### Circuit Breaker

If the same action fails **2 times in a row**:
1. STOP — do not retry blindly.
2. Analyze the root cause.
3. Change approach or escalate to the user.
4. Document the failure in your lessons/notes file if it is novel.

### Evidence-Only Completion

Never declare "done" without evidence:
- Command output showing success.
- File existence verified.
- Test passing.
- Diff reviewed.

Use your verification skill/gate for formal completion checks.

### Ambiguity Gate

If a request has zero specificity:
- Run a clarification/interview pass before any work.
- Clarify: what, why, where, constraints.

## Hard rules

- Never write outside the repo surfaces your governance doc marks as writable.
- Never skip the pre-commit / pre-write guard for the tier you are in.
- Never use auto-approve / "yolo" modes that bypass the gates.
- Archive before delete.
