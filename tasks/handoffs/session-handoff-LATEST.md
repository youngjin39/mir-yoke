# Session Handoff — Central Capability Supply Purpose Alignment

- Date: 2026-09-06.
- Status: completed and published.
- Intent authority: `tasks/intent.json`; `tasks/plan.md` is the current cursor. The Harness cursor run `harness-managed-central-provider-mandate-2026-09-06` owns the overall design.

## Decisions

Mir Yoke is the Harness-managed central capability supply system for independently owned repositories. Harness owns management direction, reuse decisions, verification and authorized delivery coordination. Yoke owns generic shared sources, plugins, separate common agents/commands, versioned delivery and compatibility evidence. Consumers retain goals, data, local policy, adapters and execution.

ADR-86's 2026-09-06 amendment controls this primary purpose and management split. Starter, Project Agent Kit, optional CLI and plugins remain supported; `public_harness_template` remains the distribution classification. New and legacy provider contract titles are recognized by adopter boundary checks.

## Verified Delivery

Implementation `f6d3f9a4949cfe19785d37ab952bf8f699d51802` was committed and pushed to origin/main with matching local/remote revisions. The parent observed 52 passing focused tests, exact payload parity, complete classification of 806 assets, generated Codex parity, Ruff and diff checks. Final policy/docs review has no blocker. For future delivery-record edits, regenerate the payload and verify its exact hashes before committing.

Detailed evidence and the prior capability/runtime proof remain in `tasks/change_log.md` and Git history. No live provider installation/update, consumer deployment, trust/credential/protected-memory change, PR or workflow was performed.

## Resume

No work remains for this mandate. Compare current local/remote main revisions and inspect the working tree before new work. Consumer ownership and explicit delivery authority remain intact.
