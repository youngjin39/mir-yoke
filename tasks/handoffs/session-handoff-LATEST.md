# Session Handoff — Central Capability Supply Purpose Alignment

- Date: 2026-09-06.
- Status: canonical purpose and management alignment is verified and ready for parent-authorized
  delivery; the prior capability repair remains published and verified.
- Intent authority: `tasks/intent.json`; `tasks/plan.md` is the compact status projection.
- Overall design authority: parent Harness cursor `tasks/plan.md` run
  `harness-managed-central-provider-mandate-2026-09-06`. Yoke's current intent is recorded in
  `tasks/intent.json` with its prior cursor preserved in the archive.

## Current objective and decisions

- Make Yoke's primary purpose explicit as the Harness-managed central capability supply system for
  independently owned repositories. Harness owns management direction, reuse decisions,
  verification, and authorized delivery coordination; Yoke owns generic sources and versioned
  compatibility delivery; consumers retain goals, data, local policy, adapters, and execution.
- Keep `public_harness_template` as the distribution classification. Preserve the Starter, Project
  Agent Kit, optional CLI, and optional plugins without a forced channel, runtime, control-plane,
  universal-installer, or standing-consumer-authority claim.

The published capability-repair baseline, including provider/consumer separation, schema-3
catch-up, rollback, hook metadata, and package inventory evidence, remains recorded in
`tasks/change_log.md` and Git history.

## Verification

- The published capability repair previously passed clean-candidate readiness with 987 full tests;
  its evidence is `/tmp/mir-yoke-capability-release-readiness.log`.
- Canonical `AGENTS.md`/Codex derivatives and `config/adopter-payload.json` were regenerated.
  The current and legacy Yoke contract titles both remain adopter provider-identity markers.
  `uv run pytest -q tests/test_adopter_slim.py tests/test_template_asset_classification.py
  tests/test_public_template_identity.py tests/test_decision_authority.py
  tests/test_advanced_reference_templates.py tests/test_release_metadata.py
  tests/test_no_korean_in_user_facing.py` passed 52 tests. Codex parity, asset classification,
  Ruff, and diff checks passed. Log:
  `/tmp/mir-yoke-purpose-alignment-postdocs.log`.

## Resume and boundaries

This purpose-alignment change does not modify runtime code, consumer repositories, protected
memory, credentials, or external services.
Before a new session, compare current HEAD with `git ls-remote origin refs/heads/main` and inspect
the working tree. Parent retains commit and push authority; this handoff does not claim a new push.
Consumers retain their local policy and delivery authority; a modified hook requires its own
operator trust review.
