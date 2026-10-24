---
name: verify
description: "Evidence-based completion verification, spec compliance and self-audit. Diff and PR review routes to code-review; architecture analysis routes to bluebricks.\n\nTrigger: verify, done check, proof, self-check, spec check, self-audit, spec audit\n\nAbsorbs: verification, verify-against-spec, self-audit, review-code"
---

# Verify

Routing precedence: diff and PR review → code-review; completion evidence and spec compliance → verify; architecture analysis → bluebricks.

## Use When
- Before claiming a task is complete.
- When checking that implementation matches spec or requirements.
- When running a self-audit against harness compliance baseline.
- When checking post-completion evidence; route diff and PR review to `mir-code:code-review`.

## Absorbed legacy skills
- verification — Evidence-gated completion. No unverified completion.
- verify-against-spec — Check design/requirements/purpose through multi-axis verification, optionally delegated when the host provides sub-agents.
- self-audit — Repository-contract self-check. Validates only the instructions, generated surfaces,
  structure, and evidence the current repository actually declares.
- review-code — Legacy alias: diff and PR review uses `mir-code:code-review`; completion evidence stays here.

## Evidence-claim discipline (central directive 2026-07-25)
- Completion is an evidence claim, not a confidence statement.
- A required check that cannot be evaluated — missing tool, unrunnable command, unreadable output — counts as a failure, not a pass.

## Workflow

When identity, relation or status meaning affects the task, apply `mir-core:ontology` using the project-owned mapping.
1. Convert the requested outcome into a checklist of observable claims (for a request over several targets or items, one claim per target × item), including explicit non-goals and protected boundaries.
2. Map each claim to the smallest check that can fail: focused test, static check, generated parity check, runtime probe, or direct artifact inspection.
   For a runnable service, CLI or UI, include one check beside the unit tests that runs it and observes a real response or effect when safe and permitted; otherwise label that claim unevaluated.
3. Run checks against the final worktree state and capture command, exit status, and relevant output. A missing tool or unreadable result is not a pass.
4. Inspect the diff for unintended scope, stale generated files, missing tests, secret exposure, and platform-specific assumptions.
5. Compare implementation to the governing requirement or spec and label each claim passed, failed, or unevaluated.
6. Report completion only when all required claims pass; otherwise report `N/M` with the open claims. Finish every claim an agent can finish; deliver owner-only decisions, each with a recommendation, after the rest. Report residual risk and unrun checks explicitly.

For consequential work with existing handoff/spec/plan documents, use the [optional fidelity audit](references/three-document-fidelity.md).

Inspired by fn-opt/dryforge at f5aa6d7.
