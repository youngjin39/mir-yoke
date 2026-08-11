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
- self-audit — Repository-contract self-check. Validates only the instructions, generated surfaces,
  structure, and evidence the current repository actually declares.
- review-code — Review written code via independent sub-agents (multi-layer, bias-free).

## Evidence-claim discipline (central directive 2026-07-25)
- Completion is an evidence claim, not a confidence statement.
- A required check that cannot be evaluated — missing tool, unrunnable command, unreadable output — counts as a failure, not a pass.

## Workflow
1. Convert the requested outcome into a checklist of observable claims, including explicit non-goals and protected boundaries.
2. Map each claim to the smallest check that can fail: focused test, static check, generated parity check, runtime probe, or direct artifact inspection.
3. Run checks against the final worktree state and capture command, exit status, and relevant output. A missing tool or unreadable result is not a pass.
4. Inspect the diff for unintended scope, stale generated files, missing tests, secret exposure, and platform-specific assumptions.
5. Compare implementation to the governing requirement or spec and label each claim passed, failed, or unevaluated.
6. Report completion only when all required claims pass. Report residual risk and unrun checks explicitly.
