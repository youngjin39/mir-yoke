# Change log

One bullet per non-trivial change. Newest at the top.

- 2026-09-06: aligned Yoke's current purpose as the Harness-managed central capability supply
  system for independently owned repositories. Mir Harness manages direction, reuse decisions,
  verification, and authorized delivery coordination; Yoke supplies versioned generic capabilities;
  consumers retain their goals, data, local policy, adapters, and execution. The public-template
  classification and Starter, Project Agent Kit, optional CLI, and plugin channels remain intact.
  ADR-86 now takes precedence over older template-only role wording. The adopter boundary detects
  both the new and legacy Yoke contract titles. Regenerated derivatives and payload passed 52
  focused tests plus Codex parity, asset, Ruff, and diff checks; log:
  `/tmp/mir-yoke-purpose-alignment-postdocs.log`.

- 2026-09-06: published central operations implementation `0d5501fb765e7a829d3aec7ff64fa591f226f0d9` to main and verified origin parity. Compact current trackers supersede the mixed historical completion lists retained at that commit; the final implementation baseline is 987 full tests, not the earlier 974-test audit.

- 2026-09-06: separated central provider health from consumer enrollment and local integration,
  made read-only status bounded and snapshot-free, and added schema-3 provider advancement with
  receipt-bound pending-consumer catch-up and candidate-config rollback. Clean-candidate readiness
  passed every gate with 987 full tests.
- 2026-09-05: published the verified implementation as
  `dcff8d155ecb996b2a0dc014a293775fd05f5f06` on local `main` and `origin/main`.
- 2026-09-05: made the user-runtime installer reject lexical and physical runtime-home overlap,
  including case-insensitive macOS aliases and physical ancestors, before it writes a receipt or
  payload. Its transaction now rolls back on process interrupts before reraising the original
  `KeyboardInterrupt` or `SystemExit`. Final verification passed 974 tests, and clean-candidate
  release readiness passed every gate.
- 2026-09-05: repaired the maintainer and Project Agent Kit `PreCompact` hooks so the generated
  handoff snapshot keeps ordered Markdown tasks and formal incomplete `Step N:` cursors. The shared
  single-pass matcher accepts `in progress`, `in_progress`, `pending`, `blocked`, `active`,
  `running`, and `todo`, while excluding completed steps.
- 2026-09-05: recorded the current Yoke maintenance audit in the canonical intent cursor, archived
  superseded cursor history, and regenerated the adopter payload so its asset hashes remain exact.
  The first full run exposed the expected stale-payload detection after that cursor write
  (`test_should_remove_reference_snapshot_when_adopter_payload_is_built` and
  `test_should_match_exact_adopter_payload_when_release_inventory_is_generated`); regeneration
  restored the derived-state contract.
- 2026-08-30: accepted ADR-86, assigned Mir Harness as repository-maintenance manager, tracked the
  portable maintainer Profile without capability-lock protection, preserved adopter lock protection,
  regenerated derivatives and payload, and passed all 803 tests.
- 2026-08-30: replaced the remaining host-specific Codex reviewer contracts, made generated
  read-only sandbox classification require exact `Write` and `Edit` tool tokens, rejected invalid
  patterned frontmatter before agent output, refreshed the adopter payload and derivatives, and
  bound the protected capability lock to implementation commit `3018f5c`, and passed all 803 tests.
- 2026-08-30: made generated Codex configuration inherit operator-owned approval and native-agent
  routing policy, modernized host-neutral agent contracts, derived the fleet documentation
  advisor's read-only sandbox from frontmatter, preserved Claude model fields while keeping Codex
  agents unpinned, and documented external skill registry migration; implementation commit
  `90bb4f6` is lock-bound and all repository checks pass.
- 2026-08-29: migrated generated Codex permission ownership to operator-selected profiles, rejected
  legacy/profile mixing, bound vector writes to a persisted encoder fingerprint, preserved fact
  subject/provenance, quarantined credential-shaped facts, and passed clean-candidate readiness
  with 797 tests; published the implementation to `origin/main` at `d3693b8`.
- 2026-08-28: added ADR-84 and the current harness engineering upgrade guide without expanding the
  Starter, Project Agent Kit, optional CLI, plugin, or consumer-authority boundaries.
- 2026-08-28: corrected current-only fact/document retrieval, semantic history classification,
  explicit resumable missing-vector backfill, and the public 1024-dimension vector contract.
- 2026-08-28: fixed current Codex patch hook input, secret-value redaction, instruction-like memory
  quarantine, least-privilege generated Codex defaults, bounded SessionEnd parity, and hook-trust
  guidance; clean-candidate readiness passed with 793 tests.
- 2026-08-28: published the portable compact lifecycle and Project Agent Kit common-harness parity
  on `main`; owner-run Claude/Codex example repositories remain optional post-release acceptance.
- 2026-08-28: refreshed the protected capability lock against implementation commit `a0768ce` and
  reconciled the canonical intent, plan, checklist, TDD evidence, profile, and handoff.
- 2026-08-11: closed the active repository plan, reconciled canonical state, and removed merged
  local and remote agent branches so `main` is the only branch.
- 2026-08-11: clarified the canonical Project Agent Kit prompt in `409d09e`; concrete project
  purpose and goals are required before repository writes.
- 2026-08-11: published the restored harness engineering surface as GitHub Release `v0.9.0`; the
  immutable tag points to release commit `1d17358`.


## Archived trackers replaced by the 2026-09-06 closeout

These are historical snapshots from `0d5501fb765e7a829d3aec7ff64fa591f226f0d9`; current status belongs only to the active intent, plan and canonical handoff.

<details>
<summary>Historical tasks/plan.md</summary>

# Plan

## Current status — central capability operations repair complete (2026-09-06)

- [x] Separate host provider health from optional consumer enrollment and local integration status.
- [x] Make status read-only without project-tree hashing, while reporting bounded common-skill
  collisions and explicit `change_evidence` non-measurement.
- [x] Preserve current legacy active-provider compatibility and fail closed on a missing, tampered,
  or symlinked receipt-bound active configuration.
- [x] Migrate a fully verified legacy consumer set to schema 3, advance one host provider version
  without peer writes, and let pending peers catch up from the receipt-bound active configuration.
- [x] Prove candidate-config rollback restores the prior provider, registry, requester, and peer
  state; run focused capability and adopter checks before the final repository suite.
- [x] Regenerate the adopter payload and pass clean-candidate release readiness, including 987 full
  repository tests and the configured contract, CLI, asset, derivative, sanitization, link, schema,
  and lint gates.

- [x] Record the current audit in `tasks/intent.json`, archive superseded cursor history, and keep
  the active cursor as the authority for this review.
- [x] Confirm the four role-plugin manifests, inventories, shared lifecycle contract, capability
  source, managed lock, Claude/Codex generated parity, platform-lane documentation, and exhaustive
  asset classification remain aligned.
- [x] Inspect plugin and user-runtime installation boundaries for symlinks, collisions, divergence,
  home replacement, and rollback. Repair lexical and physical runtime-home overlap rejection and
  make process interrupts run transactional rollback before propagating the original interrupt.
- [x] Repair the maintainer and Project Agent Kit `PreCompact` hooks so one ordered matcher retains
  incomplete Markdown and formal `Step N:` plan cursors while excluding complete steps.
- [x] Regenerate `config/adopter-payload.json` after cursor and evidence-log changes, then rerun
  static gates, focused contract tests, and the full suite (974 passed); clean-candidate release
  readiness passed every gate.

The audit repaired the user-runtime installer and shared continuation snapshot. It found no remaining
plugin, platform, lock, Profile, or generated-parity defect. ADR-79 remains unchanged: macOS is the
primary operational and release-evidence lane; Linux and WSL are separate compatibility lanes;
native Windows is reference adaptation only.

Implementation commit `dcff8d155ecb996b2a0dc014a293775fd05f5f06` is verified at both local
`main` and `origin/main`. This closeout records the observed implementation delivery. Before further Yoke work, compare
`git rev-parse HEAD` with `git ls-remote origin refs/heads/main` to verify the latest local and
remote revisions.

## Completed prerequisite — role-plugin and common-hook delivery (2026-09-04)

- [x] Record the operator's packaging rule: common workflows formerly copied into repositories are
  grouped into Yoke-owned, role-oriented plugins and selected by repository Profile.
- [x] Accept ADR-90, which reserves a separately named `mir-lifecycle-hooks` package while keeping
  target-specific policy, protected paths, and writes repository-owned.
- [x] Publish `mir-lifecycle-hooks` with one shared, read-only `SessionStart` handler and supporting
  skill; admit only its exact schema-4 shape and acknowledged digest.
- [x] Add a separate dry-run-first installer for Yoke-authored Claude/Codex agents and Claude
  commands, with explicit homes, divergence protection, and file-digest receipts.
- [x] Audit MCP runtime and repository state: neither Claude nor Codex has a registered server, and
  Yoke implements no MCP server; `.mcp.json.example` is inactive consumer guidance only.
- [x] Record the future `mir-mcp` admission boundary without publishing an empty or misleading MCP
  plugin.
- [x] Prepare the Codex feature-request comment for the existing agent-plugin issue and a separate
  command-alias issue without duplicating upstream issue `#18308`.
- [x] Submit the Yoke use case to the open plugin-agent request `#18308`. Do not open the command
  alias issue because three prior requests were closed as intentionally replaced by skills.
- [x] Regenerate declared asset projections; run focused, full, derivative, lint, asset, and
  isolated real-CLI verification gates. The user-runtime installer has 14 passing safety tests.
- [x] Commit and push Yoke `main`, then activate and verify the published surfaces in the current
  Claude and Codex user homes without changing consumer repositories.

The four plugins are enabled in both runtimes and visible from all 14 registered repository roots.
The separate installer projects 11 agents into both runtimes and six commands into Claude; Codex
resolves those command intents through the corresponding plugin skills. Fresh Claude and Codex
sessions observed the exact 14-skill catalog and the trusted common `SessionStart` hook, so the
capability state is active and READY. The final closeout commit and remote-parity check are part of
this same completed delivery record.

Consumer repository mutation remains prohibited. The current operator instruction authorizes Yoke
commit/push and user-level activation; it does not authorize a PR, workflow, tag, or release.

## Completed prerequisite — ADR-89

- [x] Preserve and re-verify the completed ADR-88 supply-chain hardening.
- [x] Confirm isolated Claude and Codex installations expose the same three Yoke plugin trees from
  a working directory outside the provider checkout.
- [x] Record one explicit five-surface management contract for agents, skills, hooks, MCP servers,
  and commands without treating every surface as a plugin component.
- [x] Extend the commit-pinned capability sync so selected Claude commands are copied and locked
  like agents while Codex resolves the same workflow intent through the mapped plugin skill.
- [x] Strengthen the real-CLI probe to prove host-level recognition from two independent consumer
  working directories and verify installed skill inventories.
- [x] Update ADRs and current documentation, regenerate declared derivatives, and run focused and
  full verification plus independent review.

ADR-88 remains binding: the three role plugins stay skills-only, the exact `skills-hooks` package is
admitted under ADR-90, and MCP remains rejected. Central management means one Yoke-owned contract
with runtime-native delivery, not one undifferentiated plugin format. Status output distinguishes
the global plugin hook from repository-coupled generated hooks.

ADR-89 is now accepted and implemented. The schema-4 contract exposes all five surfaces, command
sync is digest-bound, host activation preserves the union of registered consumers, and rollback,
interruption, symlink, schema-downgrade, and concurrent-apply regressions are covered. The current
operator instruction authorizes commit, publication, and user-level host activation; only
consumer-repository mutation remains outside this delivery scope.

## Completed prerequisite — ADR-88

- [x] Classify the interrupted three-path worktree state and preserve valid generated output.
- [x] Remove host-specific tracked plugin activation from the public maintainer checkout.
- [x] Add an accepted decision for passive versus active plugin components and runtime boundaries.
- [x] Make capability-source declarations and validation fail closed for undeclared hooks or MCP.
- [x] Add focused regressions, regenerate declared projections, and run the affected/full gates.
- [x] Record verified completion without committing, pushing, tagging, releasing, reinstalling host
  plugins, or modifying a consumer repository.
- [x] Close final-review gaps for manifest permissions, schema-1 revalidation, and marketplace
  inventory/digest provenance; rerun all gates and obtain a clean independent verdict.
- [x] Close version-validation, receipt-downgrade, and rollback activation-scope findings; rerun
  all gates and obtain a clean independent verdict.

Independent final and CWE reviews returned PASS after the last rollback schema cross-check.

The current user instruction authorizes direct Mir Yoke edits, commit and push to `main`, and
user-level plugin/agent/command activation. It does not authorize a PR, workflow, tag, release, or
consumer-repository changes.

The three role plugins remain skills-only. ADR-90 admits only the separately named, exact read-only
hook package; no MCP behavior is invented without a concrete server requirement.

## Deferred owner work

When the owner supplies a target, run the published prompt once with Claude and once with Codex in
separate empty repositories. This is post-release acceptance, not an open repository task or a
`v0.9.0` claim.

</details>

<details>
<summary>Historical tasks/handoffs/session-handoff-LATEST.md</summary>

# Session Handoff — Yoke Central Capability Operations Repair

- Date: 2026-09-06
- Status: central capability status and multi-consumer update repair is implemented and awaiting
  final repository verification and authorized delivery.
- Authority: `tasks/intent.json` is the active audit cursor. The operator authorized this Yoke
  review and direct main delivery. Do not mutate user runtimes, consumer repositories, protected
  memory, credentials, external accounts, releases, or tags.

## Current Decision

Host provider health is separate from consumer-local enrollment and integration. Read-only status
uses bounded provider receipt, marketplace, package-tree, runtime activation, and collision evidence
without hashing the inspected repository tree. A global-only root reports `not-enrolled`; an enrolled
root can remain `pending-local-update` after a host provider advance.

Schema-3 registry state keeps one active provider commit and preserves peer local files and locks.
The first schema migration validates every legacy peer before activation. A pending peer later uses
the active receipt-bound configuration and commit rather than its stale local configuration or a
newer remote revision. The active configuration is digest-bound and rejects missing or symlinked
paths. Rollback restores the prior bound configuration before restoring host runtime registration.

Provider status proves installed package activation and cache evidence for the required hosts. It
does not substitute for a fresh repository-specific hook execution or trust attestation.

The supported capability contract remains healthy. The four optional role plugins have one shared
skill provider each, and `mir-lifecycle-hooks` alone supplies the exact, read-only shared
`SessionStart` handler. Project hooks and MCP configuration remain target-local. The user-runtime
installer and capability manager reject symlinked or replaced homes and paths, unmanaged collisions,
diverged managed files, unsafe caches, and incomplete rollback states. The installer now rejects
lexical and physical Claude/Codex home overlap, including a case-insensitive macOS alias or a
physical ancestor. It rolls back on a process interrupt before reraising that original interrupt.

ADR-79 remains binding: macOS is the primary provider and release-evidence lane; Linux and WSL are
separate compatibility lanes; native Windows is a target-owned reference-adaptation lane. No
platform-runtime, plugin, lock, Profile, or generated-parity defect remained after review. The
audit repaired one continuation defect: `PreCompact` had recognized only unchecked Markdown items,
so it could falsely report no active work for formal `Step N:` cursors. Both shipped hook copies now
use one ordered matcher for unchecked Markdown plus incomplete `in progress`, `in_progress`,
`pending`, `blocked`, `active`, `running`, and `todo` step states; completed steps are excluded.

## Evidence and next step

- `uv run python scripts/verify_release_readiness.py` passed every clean-candidate gate with exit
  code 0 after 987 full tests in 161.72 seconds. Its log is
  `/tmp/mir-yoke-capability-release-readiness.log`.

- Implementation commit `dcff8d155ecb996b2a0dc014a293775fd05f5f06` was verified at both local
  `main` and `origin/main` after publication.
- The final full suite passed 974 tests in 162.78 seconds with exit code 0. Its authoritative log is
  `/tmp/mir-yoke-final-pytest.log`.
- Focused plugin, capability, installer, derivative, asset, decision, and classification checks
  passed. The installer-specific suite has 19 passing tests, including physical macOS alias and
  process-interrupt rollback coverage. `uv run python scripts/verify_codex_sync.py`,
  `uv run python -m tools.template_assets --json`, and `uv run ruff check` also passed.
- `uv run python scripts/verify_release_readiness.py` passed every clean-candidate gate with exit
  code 0; its authoritative log is `/tmp/mir-yoke-final-release-readiness.log`.
- The first full run correctly failed two stale `config/adopter-payload.json` hash tests after the
  audit cursor changed. Regenerating the payload fixed the derived-state drift; the final full run
  passed.
- Changed files are the installer and its regression, two shipped pre-compact hooks and regression,
  cursor/history, plan, checklist, handoff, change log, and generated adopter payload. No
  user-runtime installation or consumer write occurred.

No further repository repair is pending. Before the next session begins new work, compare
`git rev-parse HEAD` with `git ls-remote origin refs/heads/main` to verify the latest local and
remote revisions. The generated snapshot below records the checkpoint before closeout delivery.

<!-- mir:runtime-snapshot:begin -->
## Runtime Snapshot (Generated)

### Active Plan Items
- No open plan items.

### Working Tree
- Working tree dirty (inspect git status --short).
<!-- mir:runtime-snapshot:end -->

</details>

Final independent parent acceptance (2026-09-06): 52 tests passed in 4.07s across `test_adopter_slim`, `test_public_template_identity`, `test_decision_authority`, `test_template_asset_classification`, `test_advanced_reference_templates`, `test_release_metadata`, and `test_no_korean_in_user_facing`. Current and legacy provider contract titles are both detected even when CLAUDE.md is the only copied provider surface. An intermediate exact-payload failure during documentation changes was resolved by final payload regeneration. Ruff passed; the independent final policy/docs review has no remaining blocker.

## 2026-09-06: Central capability supply mandate delivered

Implementation `f6d3f9a4949cfe19785d37ab952bf8f699d51802` was committed and pushed to `origin/main`; the parent observed matching local HEAD and remote refs/heads/main after the push. Final independent review has no remaining blocker. This documentation closeout records that observed delivery; its own revision can be checked through Git. No consumer commit/push or runtime installation was performed.
