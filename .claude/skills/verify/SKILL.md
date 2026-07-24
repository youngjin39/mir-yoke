---
name: verify
description: "Evidence-based verification (verification gate, spec compliance, self-audit, post-review code review).\n\nTrigger: verify, done check, proof, self-check, spec check, audit, review code\n\nAbsorbs: verification, verify-against-spec, self-audit, review-code"
---

# Verify

## Use When
- Before claiming a task is complete.
- When checking that implementation matches spec or requirements.
- When running a self-audit against harness compliance baseline.
- When reviewing written code for quality and correctness post-completion.

## Absorbed legacy skills
- verification — Evidence-based verification + 7-stage gate. No unverified completion.
- verify-against-spec — Verify implementation against design/requirements/purpose via multi-axis sub-agents.
- self-audit — Starter compliance self-check. Validates CLAUDE.md sections, .claude/ components, docs/ structure, and tasks/ files against the 21-element baseline.
- review-code — Review written code via independent sub-agents (multi-layer, bias-free).

## Evidence-claim discipline (central directive 2026-07-25)
- Completion is an evidence claim, not a confidence statement.
- A required check that cannot be evaluated — missing tool, unrunnable command, unreadable output — counts as a failure, not a pass.

## Workflow
1. Identify which absorbed legacy intent applies (design vs. plan vs. interview etc.).
2. Refer to the archived legacy SKILL.md under `archive/skills/<legacy>/` for original workflow.
3. Output per absorbed legacy's protocol.

## Status
This skill is the canonical entry point. Legacy slugs remain dispatchable until P15-I archive completes.
