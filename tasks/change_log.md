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

## 2026-09-23: Fleet consolidation — preserved inputs

Owner authority: Discord message 1552179237325377586, relayed by Mir Harness.
This maintenance continues ADR-86 without replacing its accepted purpose or consumer boundary.
Prior active documents below are preserved verbatim; current work lives in `tasks/plan.md`.

<details>
<summary>Pre-consolidation CLAUDE.md</summary>

```text
# Mir Yoke — Harness-Managed Central Capability Supply Contract

Mir Yoke is the Harness-managed central capability supply system for independently owned repositories. It distributes versioned generic capability sources as a public agent-guided template,
not an agent runtime and not a universal installer, and has no standing authority over consumers.
`starter/` is the four-file payload; the Project Agent Kit is the greenfield recipe; installed `mir`
acts only on an explicit target and operation.

## Outcome and completion

- Mir Harness owns Yoke management direction, reuse decisions, verification, and authorized
  delivery coordination. Yoke owns the generic shared sources, plugins, separately delivered common
  agents and commands, versioned delivery, and compatibility evidence.
- Consumers own their goals, data, local policy, adapters, and execution. Maintain the four-file
  Starter, Project Agent Kit with harness and required memory, optional public `mir` CLI,
  namespaced plugins, and retrievable reference corpus without requiring any channel.
- Finish when the affected supported-surface contracts, generated parity, and smallest relevant
  checks pass.

## Sources

- `starter/HARNESS.md`, `recipes/project-agent-kit/`, and `src/mir/cli/` own the minimum consumer contract, empty-target recipe, and optional installed CLI; the Kit never copies CLI code.
- `plugins/` owns common skills and the exact read-only global hook; `config/capability-sources.json` owns commit-pinned runtime selection.
- ADR-86, including its 2026-09-06 amendment, owns current purpose and management; ADR-79 controls platform lanes, and ADRs 81, 83-86, and 88-90 control adoption and capability boundaries.
- `config/template-assets.json` classifies the checkout; `.mir/repo-profile.toml` owns local boundaries.

- Yoke-only read-only SRR uses `"<user-bin>/mir"` with `--root "<yoke-checkout>"`; consumers use `MIR_SRR_PROVIDER` and `MIR_SRR_ROOT` with their own memory path.

## Authority and safety

- Mir Harness may manage Yoke directly within current user authority; `.mir/capability-lock.json` is
  managed, not protected. That responsibility does not give Yoke authority to manage consumers.
- Get explicit direction before destructive actions, credentials, consumer writes, commits, pushes,
  tags, releases, or material scope expansion.
- Preserve unrelated local changes and keep public material generic, English, and sanitized.
- Consumers own every result. Mir Yoke never discovers them, grants standing write authority, or
  provides an active `yoke` composer; installing `mir` does not expand authority.
- The Project Agent Kit recipe may describe target-local Git initialization and one commit only when
  the user's target prompt explicitly grants that authority.
- The Kit creates bounded project-owned files and SQLite+FTS5 memory. Its thin `scripts/mir.sh`
  executes the exact provider revision with runtime state below ignored `.mir/`, without vendoring
  the package or requiring a host-global installation.
- Plugins are optional; local skills must not shadow them, and ADR-82 stays inert. Agents and Claude
  commands use project sync or the user-runtime installer; Codex uses generated agents and mapped
  skills. ADR-90 admits only the global continuity hook; coupled hooks and MCP stay target-local.
- Edit canonical sources first and regenerate `AGENTS.md`, nested `AGENTS.md`, and `.codex/`.

## Execution and evidence

- Use direct work for bounded changes; scale design, delegation, and review with uncertainty.
- Run the smallest check that can fail for changed behavior.
- For Starter or recipe changes, run
  `uv run pytest -q tests/test_project_agent_kit.py tests/test_minimal_starter.py`.
- For CLI changes, include `tests/test_installed_cli.py` and the affected command regression.
- For plugin changes, run isolated package and common-contract tests.
- Use broader tests only when affected maintainer code or release coupling requires them.

Commands: `uv run pytest`, `uv run ruff check`, `uv run python scripts/verify_codex_sync.py`. Artifacts are English; user-facing language follows the user.

## Role policy (template summary)
```

</details>

<details>
<summary>Pre-consolidation AGENTS.md</summary>

```text
<!-- GENERATED FILE: edit CLAUDE.md and rerun scripts/generate_codex_derivatives.sh -->

# Mir Yoke — Harness-Managed Central Capability Supply Contract

Mir Yoke is the Harness-managed central capability supply system for independently owned repositories. It distributes versioned generic capability sources as a public agent-guided template,
not an agent runtime and not a universal installer, and has no standing authority over consumers.
`starter/` is the four-file payload; the Project Agent Kit is the greenfield recipe; installed `mir`
acts only on an explicit target and operation.

## Outcome and completion

- Mir Harness owns Yoke management direction, reuse decisions, verification, and authorized
  delivery coordination. Yoke owns the generic shared sources, plugins, separately delivered common
  agents and commands, versioned delivery, and compatibility evidence.
- Consumers own their goals, data, local policy, adapters, and execution. Maintain the four-file
  Starter, Project Agent Kit with harness and required memory, optional public `mir` CLI,
  namespaced plugins, and retrievable reference corpus without requiring any channel.
- Finish when the affected supported-surface contracts, generated parity, and smallest relevant
  checks pass.

## Sources

- `starter/HARNESS.md`, `recipes/project-agent-kit/`, and `src/mir/cli/` own the minimum consumer contract, empty-target recipe, and optional installed CLI; the Kit never copies CLI code.
- `plugins/` owns common skills and the exact read-only global hook; `config/capability-sources.json` owns commit-pinned runtime selection.
- ADR-86, including its 2026-09-06 amendment, owns current purpose and management; ADR-79 controls platform lanes, and ADRs 81, 83-86, and 88-90 control adoption and capability boundaries.
- `config/template-assets.json` classifies the checkout; `.mir/repo-profile.toml` owns local boundaries.

- Yoke-only read-only SRR uses `"<user-bin>/mir"` with `--root "<yoke-checkout>"`; consumers use `MIR_SRR_PROVIDER` and `MIR_SRR_ROOT` with their own memory path.

## Authority and safety

- Mir Harness may manage Yoke directly within current user authority; `.mir/capability-lock.json` is
  managed, not protected. That responsibility does not give Yoke authority to manage consumers.
- Get explicit direction before destructive actions, credentials, consumer writes, commits, pushes,
  tags, releases, or material scope expansion.
- Preserve unrelated local changes and keep public material generic, English, and sanitized.
- Consumers own every result. Mir Yoke never discovers them, grants standing write authority, or
  provides an active `yoke` composer; installing `mir` does not expand authority.
- The Project Agent Kit recipe may describe target-local Git initialization and one commit only when
  the user's target prompt explicitly grants that authority.
- The Kit creates bounded project-owned files and SQLite+FTS5 memory. Its thin `scripts/mir.sh`
  executes the exact provider revision with runtime state below ignored `.mir/`, without vendoring
  the package or requiring a host-global installation.
- Plugins are optional; local skills must not shadow them, and ADR-82 stays inert. Agents and Claude
  commands use project sync or the user-runtime installer; Codex uses generated agents and mapped
  skills. ADR-90 admits only the global continuity hook; coupled hooks and MCP stay target-local.
- Edit canonical sources first and regenerate `AGENTS.md`, nested `AGENTS.md`, and `.codex/`.

## Execution and evidence

- Use direct work for bounded changes; scale design, delegation, and review with uncertainty.
- Run the smallest check that can fail for changed behavior.
- For Starter or recipe changes, run
  `uv run pytest -q tests/test_project_agent_kit.py tests/test_minimal_starter.py`.
- For CLI changes, include `tests/test_installed_cli.py` and the affected command regression.
- For plugin changes, run isolated package and common-contract tests.
- Use broader tests only when affected maintainer code or release coupling requires them.

Commands: `uv run pytest`, `uv run ruff check`, `uv run python scripts/verify_codex_sync.py`. Artifacts are English; user-facing language follows the user.

## Role policy (template summary)
```

</details>

<details>
<summary>Pre-consolidation tasks/plan.md</summary>

```text
# Plan

## Current status — completed and published (2026-09-06)

- Authority: `tasks/intent.json` records the current Yoke purpose and management alignment. Parent
  Harness cursor `tasks/plan.md` run `harness-managed-central-provider-mandate-2026-09-06` is the
  overall design authority.
- [x] Preserve the published central capability implementation and its 987-test clean-candidate
  evidence at `0d5501fb765e7a829d3aec7ff64fa591f226f0d9`.
- [x] Record the superseding Yoke intent and preserve the previous cursor in the evidence archive.
- [x] Amend the current purpose/authority sources and maintain public-template distribution,
  supported-channel, and consumer-ownership boundaries.
- [x] Regenerate canonical derivatives and adopter payload after documentation stabilizes, then pass
  focused purpose, authority, adopter-boundary, asset, and parity verification: 52 tests passed;
  Codex derivative, asset classification, Ruff, and diff checks passed. The current and legacy
  Yoke contract titles both remain provider-identity markers. Log:
  `/tmp/mir-yoke-purpose-alignment-postdocs.log`.

Published implementation `f6d3f9a4949cfe19785d37ab952bf8f699d51802` has verified local/origin main parity.

## Current boundaries

- Retain the three role packages and one exact lifecycle package (14 skills total). Agents/commands remain separately delivered, and project policy/hooks/MCP remain target-owned.
- Source/config/path/digest/runtime checks remain fail-closed. Removed peer-required plugin names are a compatibility rejection, not an automatic migration.
- No live provider update/install, user trust change, capability-driven peer write, PR, workflow, tag or release was part of this repository repair.
- macOS remains the executed lane. WSL/native Windows and live model/hook execution are not claimed by these tests.

Before new work, compare `git rev-parse HEAD` with `git ls-remote origin refs/heads/main` and inspect the working tree.
```

</details>

<details>
<summary>Pre-consolidation tasks/checklist.md</summary>

```text
# Checklist

Historical evidence remains in `tasks/change_log.md`, `tasks/tdd.json` and Git history.

## Current purpose alignment

- [x] Record the Yoke purpose/management alignment in the active cursor and preserve the prior
  cursor in the evidence archive.
- [x] Align canonical purpose, authority, Profile, current ADR precedence, and supported-channel
  documentation without changing consumer interfaces or classification enums.
- [x] Regenerate derivatives and adopter payload after the final canonical wording, then pass
  focused purpose, authority, adopter-boundary, asset, and parity checks (52 focused tests;
  derivative, asset, Ruff, and diff checks passed;
  `/tmp/mir-yoke-purpose-alignment-postdocs.log`).

Prior capability implementation and publication evidence remains in `tasks/change_log.md` and Git
history. Recheck current local/remote revisions and dirty state before new work.
```

</details>

<details>
<summary>Pre-consolidation tasks/handoffs/session-handoff-LATEST.md</summary>

```text
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

<!-- mir:runtime-snapshot:begin -->
## Runtime Snapshot (Generated)

### Active Plan Items
- No open plan items.

### Working Tree
- Working tree dirty (11 paths; inspect git status --short).
<!-- mir:runtime-snapshot:end -->
```

</details>

<details>
<summary>Pre-consolidation tasks/intent.json</summary>

```text
{
  "goal": "Align Mir Yoke as the Harness-managed central capability supply system for independently owned repositories: make the primary purpose, management authority, supported adoption channels, consumer ownership boundaries, ADR precedence, maintainer Profile, operating documentation, contract tests, generated derivatives, and adopter payload consistent without changing interfaces, profile enums, runtime installations, consumer repositories, protected memory, credentials, or external services.",
  "goal_type": "maintenance",
  "scope": "Align only Yoke-owned purpose, management, supported-surface, and consumer-ownership documentation and metadata. Preserve the accepted capability repair, current source/digest/runtime boundaries, supported Starter/Project Agent Kit/optional CLI interfaces, and public_harness_template classification. Do not mutate live user runtimes, consumer repositories, protected memory, credentials, external services, code, schemas, or delivery state. Update canonical derivatives, task evidence, focused contract tests, and the generated adopter payload; prepare the bounded Yoke result for authorized delivery after verification.",
  "priority": "normal",
  "updated": "2026-09-06",
  "history": [
    {
      "goal": "Complete and deploy Yoke-owned role plugins so Claude and Codex load the same common skills and read-only lifecycle hook globally, while agents and commands use a separate digest-bound user-runtime distribution path and repository-local definitions retain precedence.",
      "updated": "2026-09-04",
      "status": "superseded"
    },
    {
      "goal": "Audit and minimally repair Mir Yoke supported surfaces: plugin configuration and contract alignment, Claude/Codex generated parity, platform continuity documentation, installer and lock references, asset classification, current Profile and documentation consistency, and concrete runtime defects. Preserve the ADR-79 macOS-primary and Linux/WSL-compatible posture, with native Windows as a reference-adaptation lane; do not install into user runtimes or consumer repositories. Record evidence, run focused and full verification, and prepare the maintainer-owned result for direct main commit and push.",
      "updated": "2026-09-05",
      "status": "superseded"
    },
    {
      "goal": "Repair Mir Yoke central capability status and multi-consumer update architecture: make global provider health readable without a consumer-local configuration or enrollment, separate consumer-local integration state, and permit atomic provider version migration across registered consumers while preserving non-requesting consumer files and locks as pending local integration. Preserve capability trust, digest, identity, secret, path, runtime, and activation checks; update ADR-89, current documentation, tests, and generated adopter payload without user-runtime or consumer writes.",
      "updated": "2026-09-06",
      "status": "superseded"
    }
  ]
}
```

</details>

<details>
<summary>Pre-consolidation config/doc-size-guard.json</summary>

```text
[
  {"path": "CLAUDE.md", "max_lines": 65, "max_bytes": 4304, "label": "CLAUDE.md (startup invariants only; keep procedures on demand)"},
  {"path": "AGENTS.md", "max_lines": 67, "max_bytes": 4393, "label": "AGENTS.md (generated shared startup contract)"},
  {"path": "tasks/plan.md", "max_lines": 800, "label": "tasks/plan.md"},
  {"path": "tasks/tdd.json", "max_lines": 20000, "label": "tasks/tdd.json (TDD ledger — run archiver when exceeded)"},
  {"path": "tasks/lessons.md", "max_lines": 600, "label": "tasks/lessons.md (generated projection)"}
]
```

</details>

### Architecture wording clarified

The Git authority condition already required by the canonical contract now appears in the supported flow. Previous wording:

4. It initializes Git locally only after verification, installs the tracked pre-commit hook, and
   creates one verified initial commit.

### Profile purpose contract repair

The pre-existing shortened purpose failed `test_public_template_identity.py:52`. Preserve it verbatim below; the active Profile retains its meaning and restores the tested ADR-86 identity phrase. No bootstrap receipt exists in this provider checkout; the existing template-maintainer bootstrap exemption applies. No receipt or runtime was changed.

```toml
purpose = "Harness-managed central capability supply for independent repositories: Starter, Project Agent Kit recipe, optional CLI, plugins, and versioned Claude/Codex delivery evidence."
```

### Memory projection before regeneration

The previous generated block is preserved below; the current projection is generated by `mir memory render`.

```text

## Keyword → File Index (DB projection)

| Keyword | File | Title |
|---|---|---|
| (no ingested documents) | — | — |
```

## 2026-09-23: Fleet consolidation audit evidence

Authority: owner Discord message 1552179237325377586 relayed by Mir Harness; repository-only.
The design authority is the current `tasks/plan.md` cursor backed by `tasks/intent.json`.
ADR-86 purpose and consumer boundaries remain accepted. No commit, push, tag, stash, reset,
checkout, release, consumer write, secret access or direct database edit was performed.

### Owner items

1. Consistency: Profile paths all exist. Restored the tested purpose phrase, checked references,
   regenerated derivatives in a temporary root and refreshed the exact adopter payload.
2. Operating base: inspected hook registration and maintainer scripts. No justified dead safety
   gate removal was found; the missing receipt limits the target launcher in this provider checkout.
3. Current facts: updated cursor, status, resume pointer, purpose wording and the memory projection;
   historical publication claims remain in their original wording in the log.
4. Archival: previous instructions, intent, cursor, checklist and handoff are preserved verbatim
   above with pointers in their current surfaces. No rule, decision or lesson was deleted.
5. Context: root instructions now contain startup invariants and short verification commands;
   the repository-only SRR invocation is on demand in the preserved input. One active cursor remains.
6. Memory: `.mir/memory.db` is 348160 bytes. Immutable read-only SQLite `pragma quick_check`
   returned `ok`. Ordinary `sqlite3 -readonly` could not open it; no unsupported cause is asserted.
   `mir memory doctor --project-root . --json` returned `not_ready` because `harness_a.toml` is
   absent. This pre-existing provider configuration was not replaced with a new consumer runtime.
   Documented `memory query` returned the SRR title; `memory render` refreshed the projection.
7. Constraints: raw-exec and secret-path hook regressions passed. Bootstrap and receipt guards,
   protected paths, preservation rules and destructive-action boundaries remain unchanged.
8. Skills/agents: isolated plugin/common-contract checks and agent registry checks passed.
   No repository Codex model pins exist. No plugin skill behavior or central capability changed.
9. Instructions: CLAUDE.md 59 lines / 4219 bytes -> 41 / 3448; AGENTS.md 61 / 4308 -> 43 / 3537.
   The generated body matches the canonical source; enforced budgets are now 55/3600 and 60/3800.
10. Rules/lessons: rules stay canonical in CLAUDE.md and generated into AGENTS.md; the existing
    lesson projection remains the lesson location. No populated duplicate lesson store was found.
11. Architecture: supported modules match the checkout; the Kit Git step now repeats its existing
    explicit-authority condition so the flow cannot imply unconditional commit permission.
12. Routing: the pre-existing executor uses app-server; its code and tests remain untouched.
    The central policy overlay resolves unit work to gpt-6-luna/high. Local route fields are null,
    so they introduce no competing pins. Accepted transport wording remains an owner decision below.
13. Continuity: one cursor (`tasks/plan.md`), resume pointer (`tasks/handoffs/session-handoff-LATEST.md`),
    status projection (`tasks/checklist.md`) and evidence log (this file).
14. Retrieval: the file-anchor implementation query had no edges. The declared requirement anchor
    `SRR-MEMORY-RELATIONS` returned four implementation edges, including the CLI and memory-reader
    files. `context pull "central capability supply"` returned architecture references but no
    facts/chunks and reported no configured archives; task retrieval is only partially populated.
15. Efficiency: observed repository SessionStart output was 946 bytes (existing 10240-byte cap);
    the shared continuity hook prints 94 bytes. Combined root instructions fell by 1542 bytes.
    Large historical and spec-reference documents remain on demand, not startup input.

### Observed verification

- Focused instruction, identity, authority, decision, adopter, classification, hook, continuity,
  intent, link, schema and sanitization suite: 95 passed in 16.03s.
- Isolated plugins, common skill contracts, routing policy and the pre-existing app-server/client,
  dispatch and shim regressions: 214 passed in 35.80s. No live model was invoked.
- Codex derivative verification passed; temporary generation differs in no `.codex/` file.
- Context paths: 9 files and 60 references passed. Agent management checks passed.
- Harness consistency passed with zero errors and zero warnings after documented projection render.
- Ruff and `git diff --check` passed. DB quick_check passed. Memory doctor remains not ready as above.
- Initial generator/hook failures came from an inaccessible inherited uv cache. They disappeared
  with a task-local `UV_CACHE_DIR`. The remaining pre-existing Profile phrase failure was repaired
  while preserving its prior added line verbatim above. No introduced failure remains in these runs.
- The original dirty implementation, capability lock and untracked evaluation artifact were not
  edited. Original changed instruction/Profile lines remain in the current diff or verbatim archive.

### Owner decisions needed

ADR-69 currently requires Claude-to-Codex MCP delegation and an MCP-backed executor. ADR-85 also
names the supported MCP/native lane. The current owner direction requires the user-scope
`codex:codex-rescue` / `/codex:rescue` plugin with model/effort, and `codex app-server` for
`tools/mir_executor`; the existing dirty implementation already uses app-server. Under the owner's
explicit conflict rule, no accepted ADR or agent routing wording was overwritten. Authorize a
transport amendment before changing ADR-69/85 and the four affected maintainer agents
(main-orchestrator, executor-agent, codex-final-reviewer and pipeline-validator). The raw-exec ban
must remain intact. No delegated model run was attempted through the stale lane.

### Remaining limits and delivery

- `scripts/mir.sh` reports a missing bootstrap receipt. The provider's existing bootstrap gate
  recognizes its template-maintainer identity without a receipt; none was created or re-attested.
  The only Profile edit restores identity wording. No profile edit is awaiting orchestrator install.
- Memory doctor cannot prove a configured archive baseline; context facts/chunks were empty.
  SQLite vector support is absent and queries report FTS5-only mode. No configuration or DB schema
  mutation was attempted to disguise these limits.
- No `.codex/` installation is pending, and no plugin behavior was changed. Shared/runtime delivery,
  native Windows execution, live model execution and a full release gate were outside this audit.
- Prior local diffs and generator output are retained in
  a local temporary directory together with the consolidation test logs (paths redacted for the public surface).

## 2026-09-23: Project-document cleanup preserved inputs

### Pre-cleanup tasks/plan.md

```text
# Plan

## Fleet consolidation — bounded work complete (2026-09-23)

Authority: `tasks/intent.json`; owner Discord message 1552179237325377586 relayed by Mir Harness.
This is repository-only maintenance under ADR-86; its accepted purpose and consumer boundaries remain binding.
The completed prior cursor is preserved verbatim in `tasks/change_log.md` under the 2026-09-23 preserved inputs.

- [x] Capture initial dirty state and preserve prior instructions, intent and continuity records.
- [x] Audit the 15 owner items against actual paths, documented commands and accepted decisions.
- [x] Minimize startup instructions without losing rules; regenerate into a temporary output root.
- [x] Run focused governance, documentation, safety, memory and relation checks; classify failures.
- [x] Record final evidence, remaining owner decisions and generated files for orchestrator installation.

No commit, push, tag, stash, reset, checkout, credential access, consumer write, release or direct DB edit.
Keep one cursor here, one resume pointer in `tasks/handoffs/session-handoff-LATEST.md`, one status
projection in `tasks/checklist.md`, and one evidence log in `tasks/change_log.md`.

Accepted transport decisions still need owner adjudication; see the 2026-09-23 audit evidence in
`tasks/change_log.md`. Memory readiness is reported, not claimed. No publication is authorized.
```

### Pre-cleanup tasks/checklist.md

```text
# Checklist

Status projection for `tasks/plan.md`; it is the only active cursor.

- [x] Complete the repository-only 15-item consolidation audit and bounded repairs.
- [x] Preserve prior edits and moved text; verify instruction budgets and generated parity.
- [x] Record passing checks, memory limitations and the unresolved transport decision in `tasks/change_log.md`.

Previous checklist: `tasks/change_log.md`, 2026-09-23 preserved inputs.
No release or consumer deployment was performed. Resume through `tasks/handoffs/session-handoff-LATEST.md`.
```

## 2026-09-23: Project-document cleanup evidence

Authority: owner Discord message 1552197111624372339 relayed by Mir Harness; `tasks/intent.json` is the cursor authority. The completed fleet consolidation pass above was not repeated.

### Preserved predecessor records

Pre-cleanup `tasks/intent.json` scope (verbatim):

```text
Repository-only governance and continuity maintenance. Preserve all pre-existing edits and accepted decisions; archive moved text verbatim. No commits, pushes, tags, stash, reset, checkout, secrets, direct database edits, live runtime installs or consumer writes. Generate derivatives in a temporary root; leave .codex installation to the orchestrator.
```

Pre-closeout `tasks/plan.md` (verbatim):

```text
# Plan

## Project-document cleanup (2026-09-23)

Authority: `tasks/intent.json`; owner Discord message 1552197111624372339 relayed by Mir Harness.
The completed fleet consolidation cursor is preserved verbatim in `tasks/change_log.md` under
"Project-document cleanup preserved inputs". ADR-86 and the owner decisions in that log still govern.

- [x] Audit the current spec snapshot and document entry points against the supported surfaces.
- [x] Index every ADR with its recorded status and successor where one is known.
- [x] Align the architecture and README navigation without changing product behavior.
- [ ] Run document/reference/size/spec checks, document-pinning tests and the full suite if reasonable.
- [ ] Record evidence, remaining owner decisions and generated-file installation needs in the log.

No commit, push, tag, stash, reset, checkout, credential access, consumer write, release or direct DB edit.
Keep one cursor here, one resume pointer in `tasks/handoffs/session-handoff-LATEST.md`, one status
projection in `tasks/checklist.md`, and one evidence log in `tasks/change_log.md`.
```

Pre-closeout `tasks/checklist.md` (verbatim):

```text
# Checklist

Status projection for `tasks/plan.md`; it is the only active cursor.

- [x] Audit current spec and supported document entry points.
- [x] Complete the decision-record index and document navigation.
- [ ] Verify references, sizes, spec, relevant tests and the full suite.
- [ ] Record owner decisions and residual risks in `tasks/change_log.md`.

Previous checklist: `tasks/change_log.md`, 2026-09-23 project-document cleanup preserved inputs.
No release or consumer deployment is authorized. Resume through `tasks/handoffs/session-handoff-LATEST.md`.
```

Pre-closeout `tasks/handoffs/session-handoff-LATEST.md` (verbatim):

```text
# Session Handoff — Fleet Consolidation

Resume pointer: `tasks/plan.md` is the only active cursor; `tasks/intent.json` records owner authority.
Status is projected in `tasks/checklist.md`; detailed evidence and verbatim prior records live in
`tasks/change_log.md` under 2026-09-23. The bounded consolidation is complete.

Before follow-up, inspect current dirty state and the remaining owner transport decision in that
log. Preserve the pre-existing app-server implementation and recovery stash. Do not infer delivery,
runtime installation, consumer-write or memory-reconfiguration authority from this handoff.
There are no differing `.codex/` files to install. The provider has no bootstrap receipt to re-attest.

Prior resume text is preserved verbatim in the 2026-09-23 evidence log.

<!-- mir:runtime-snapshot:begin -->
## Runtime Snapshot (Generated)

### Active Plan Items
- No open plan items.

### Working Tree
- Working tree dirty (22 paths; inspect git status --short).
<!-- mir:runtime-snapshot:end -->
```

### Result

- `spec/STATE.md` and `spec/index.yaml` already identify the complete v0.8 automation tree as a superseded reference. No active PRD exists; ADR-83 remains the current support contract. No spec shard or accepted ADR body was rewritten.
- `docs/decisions/INDEX.md` now links all 71 local ADRs and mirrors their frontmatter statuses: 49 accepted, 14 superseded, 5 archived, 2 deferred, 1 rejected. ADR-82 points to ADR-83. The 13 superseded Mir Harness mirror summaries say they were retired but provide no numbered successor; the register records that uncertainty without inventing one.
- `README.md` and `ARCHITECTURE.md` now point to current architecture, decision, historical spec, active cursor and evidence log. The pre-existing architecture Git-authority clarification remains intact. The completed consolidation plan and checklist were moved verbatim into this log.
- No `.codex/` file differs or needs installation. The orchestrator-owned `config/adopter-payload.json` was not edited. Its generated inventory now differs only for seven edited document paths: `ARCHITECTURE.md`, `README.md`, `docs/decisions/INDEX.md`, `tasks/change_log.md`, `tasks/checklist.md`, `tasks/intent.json`, and `tasks/plan.md`. The orchestrator must regenerate it after this documentation pass.

### Checks and failure classification

- Document-focused pytest: 38 passed. `scripts/verify_context_paths.py` checked 8 files and 108 path references. `scripts/verify_codex_sync.py`, Ruff, document-size budgets and `git diff --check` passed.
- Full pytest: 1224 passed, 5 failed in 224.65 seconds. Two exact-adopter-payload tests fail because the seven document hashes changed and the owner-reserved generated inventory cannot be refreshed here; this is pending orchestrator installation.
- Two isolated install/greenfield tests fail while fetching PyPI packages because the current sandbox has no DNS/network access. The unchanged setup-wrapper test `test_receipt_cli_is_not_reused_after_locked_source_changes` fails because its fake `uv` marker is absent; it exercises `setup.sh` and temporary fixtures, none of the edited documents. Its exact upstream cause remains unevaluated.

### Owner decisions needed and risks

- The pre-existing ADR-69/ADR-85 transport conflict remains as recorded in the fleet consolidation evidence above. No accepted decision body or orchestrator-owned path was changed.
- The retired Mir Harness mirror ADRs do not identify numbered successors. Confirm the upstream mappings if those records must name successors; the current index explicitly marks them unrecorded.
- The document inventory needs an orchestrator-owned regeneration before the two payload equality tests can pass. Network-dependent tests need a network-capable environment, and the setup-wrapper failure needs separate diagnosis if it persists there.


## 2026-09-23 — Second-pass fleet re-verification

Owner-authorized repository-only second pass, relayed by the control plane. This extends the completed cleanup and preserves ADR-86 purpose; it grants no delivery or consumer authority. The single cursor is `tasks/plan.md`.

### Preserved predecessor continuity records

#### tasks/plan.md

````text
# Plan

No active repository document cleanup remains. The completed 2026-09-23 plan and verification
record are preserved verbatim in `tasks/change_log.md` under "Project-document cleanup evidence".
`tasks/intent.json` records the owner instruction. The orchestrator-owned adopter payload refresh
and unresolved owner decisions are listed once in that log.
````

#### tasks/checklist.md

````text
# Checklist

Status projection for the single `tasks/plan.md` cursor: document cleanup is complete.
The check results, pending orchestrator payload refresh and owner decisions are recorded in
`tasks/change_log.md` under "Project-document cleanup evidence".

Previous checklist text is preserved verbatim in that log. No release or consumer deployment was performed.
````

#### tasks/handoffs/session-handoff-LATEST.md

````text
# Session Handoff — Project-document cleanup

Resume pointer: `tasks/plan.md` is the only cursor; `tasks/intent.json` records owner authority.
The cleanup and verification evidence, preserved predecessor records, pending adopter payload refresh,
and unresolved owner decisions live in `tasks/change_log.md` under 2026-09-23.

The orchestrator owns `config/adopter-payload.json` and must refresh the seven changed document
hashes before its exact-inventory tests can pass. No `.codex/` file differs. Preserve the pre-existing
dirty implementation, protected files, recovery stash and worktrees. Do not infer release, consumer
write, runtime installation or memory-reconfiguration authority from this handoff.

Prior resume text is preserved verbatim in the evidence log.

<!-- mir:runtime-snapshot:begin -->
## Runtime Snapshot (Generated)

### Active Plan Items
- No open plan items.

### Working Tree
- Working tree dirty (26 paths; inspect git status --short).
<!-- mir:runtime-snapshot:end -->
````

#### tasks/intent.json

````text
{
  "goal": "Clean up Mir Yoke project documents under owner Discord message 1552197111624372339 (2026-09-23): align the current documentation entry points and decision index with the supported surfaces, keep one active plan, preserve historical text and existing work, and verify document references and tests without changing behavior or delivery state.",
  "goal_type": "maintenance",
  "scope": "Repository-only PRD/spec, architecture/decision-index, plan/checklist, README and document-index cleanup. Preserve all pre-existing edits and accepted decision bodies; archive moved text verbatim. Do not edit orchestrator-owned paths, behavior, configuration values, generated projections, secrets, memory databases, recovery stash or worktrees. No commits, pushes, tags, stash, reset, checkout, releases, runtime installs or consumer writes.",
  "priority": "normal",
  "updated": "2026-09-23",
  "history": [
    {
      "goal": "Consolidate this Mir Yoke checkout under owner Discord message 1552179237325377586 (2026-09-23): audit the 15 fleet items, preserve ADR-86 purpose and all safety boundaries, minimize startup context, verify generated parity and read-only memory/relation health, and report remaining owner decisions without delivery or consumer writes.",
      "updated": "2026-09-23",
      "status": "complete"
    },
    {
      "goal": "Audit and minimally repair Mir Yoke supported surfaces: plugin configuration and contract alignment, Claude/Codex generated parity, platform continuity documentation, installer and lock references, asset classification, current Profile and documentation consistency, and concrete runtime defects. Preserve the ADR-79 macOS-primary and Linux/WSL-compatible posture, with native Windows as a reference-adaptation lane; do not install into user runtimes or consumer repositories. Record evidence, run focused and full verification, and prepare the maintainer-owned result for direct main commit and push.",
      "updated": "2026-09-05",
      "status": "superseded"
    },
    {
      "goal": "Repair Mir Yoke central capability status and multi-consumer update architecture: make global provider health readable without a consumer-local configuration or enrollment, separate consumer-local integration state, and permit atomic provider version migration across registered consumers while preserving non-requesting consumer files and locks as pending local integration. Preserve capability trust, digest, identity, secret, path, runtime, and activation checks; update ADR-89, current documentation, tests, and generated adopter payload without user-runtime or consumer writes.",
      "updated": "2026-09-06",
      "status": "superseded"
    },
    {
      "goal": "Align Mir Yoke as the Harness-managed central capability supply system for independently owned repositories: make the primary purpose, management authority, supported adoption channels, consumer ownership boundaries, ADR precedence, maintainer Profile, operating documentation, contract tests, generated derivatives, and adopter payload consistent without changing interfaces, profile enums, runtime installations, consumer repositories, protected memory, credentials, or external services.",
      "updated": "2026-09-06",
      "status": "superseded"
    }
  ]
}
````

### Preserved superseded runtime guidance

The ADR-69/85 transport amendment already authorizes the plugin/app-server route. These replacements update operational guidance without changing accepted decisions or safety guards. Compatibility class and function names remain unchanged.

#### .claude/agents/main-orchestrator.md

````text
- Match trigger table (CLAUDE.md) → Read matching skills (max 3) → one-line report.
See CLAUDE.md "Orchestration Presets" table (single source of truth).
2. If `execution_backend: codex`, use the supported MCP/native lane when that agent is selected. Raw `codex exec` is banned. A missing preferred lane blocks only work that truly requires that protected or isolated route; safe bounded direct work may continue.
See CLAUDE.md "Role Policy (Template Profile)" and AGENTS.md `template:profile:role-policy` block for the binding policy contract. This section covers the per-agent declarative surface introduced by ADR-09.
- A missing preferred MCP lane is a lane limitation, not a task blocker when a safe direct, native, or manual path remains. Never use raw `codex exec` fallback.
- **Supported Codex MCP lane**:
  - When the current host exposes a Codex MCP lane, keep read-only investigation or review bounded
    and request its read-only sandbox mode.
    explicit routing fields when the active policy requires them. Repository custom-agent settings
    still take precedence when the runtime defines that behavior.
- User correction feedback → record pattern in tasks/lessons.md.
- New project knowledge → save to docs/{category}/ + update memory-map.md.
````

#### .claude/agents/executor-agent.md

````text
> **Codex Backend Dispatch Rule (ADR-18 §S2, amended by ADR-69/73)**: When this delegated agent is selected, use the MCP/native Codex lane and never raw `codex exec`. Delegation itself is proportional; bounded main work may stay direct.
Routing SoT: ADR-69 amends ADR-65. Raw `codex exec` is banned. When delegation is selected, use `mir_executor --dispatch`, MCP, or native read-only breadth according to the task. A missing preferred lane is not a task blocker when a safe bounded direct path remains.
`--codex-args` is a legacy option name; in `--dispatch` mode its positional prompt is sent to the MCP Codex backend, not to raw `codex exec`.
### Read-only / non-mutating work → MCP/native routing (nothing to merge)
Claude-main investigation/review uses the supported Codex MCP lane. Codex-main breadth uses only
MCP/native routes. If the selected lane is unavailable, report the lane limitation so the parent
  positional prompt and sends it to the MCP backend.
- **Verify Codex actually ran** by checking the JobRegistry status/result plus MCP dispatch artifacts.
  `${CODEX_HOME:-$HOME/.codex}`). If `codex --version` works in the shell, auth is set.
````

#### .claude/agents/codex-final-reviewer.md

````text
> **Codex Backend Dispatch Rule (ADR-85)**: This agent declares `execution_backend: codex`. When delegation is selected, use the supported MCP or native Codex collaboration operation exposed by the current host. Never invoke raw `codex exec`.
````

#### .claude/agents/pipeline-validator.md

````text
> **Codex Backend Dispatch Rule (ADR-85)**: This agent declares `execution_backend: codex`. When delegation is selected, use the supported MCP or native Codex collaboration operation exposed by the current host. Never invoke raw `codex exec`.
````

#### scripts/codex-shim.sh

````text
# MCP-backed clients honor CODEX_BIN when a shimmed Codex binary is required.
    _POLICY_MESSAGE="[codex-shim] raw 'codex exec' and 'codex e' are prohibited; use MCP-backed dispatch."
````

#### tools/mir_executor/tests/test_codex_shim.py

````text
        'use MCP-backed dispatch.\n'
````

#### tools/mir_executor/executor.py

````text
        """Run Codex through the MCP backend (blocking).

        Maps the MCP response into the existing SubprocessResult contract.
````

#### Additional stale invocation text

The design skill absorbs deep-interview. The raw-exec guard keeps the same condition and exit status; only its route hint changes. Prior lines:

````text
**0 signals** → load deep-interview skill → ambiguity gating.
    block "raw codex exec/e is banned — route through MCP/mir_executor"
````

### Second-pass item results

1. Consistency: Profile-declared paths exist; current references and root rule parity pass.
   Codex candidate parity passes, with four sandbox-blocked agent derivatives awaiting installation.
2. Operating base: registered hook targets exist. Retained optional/reference hooks do not grant
   activation authority; no justified safety-gate removal was found. Stale transport hints were fixed.
3. Current facts: corrected agent invocation, missing section references, binary/auth distinction,
   generated-memory write guidance and obsolete continuity claims. Accepted ADR bodies stay unchanged.
4. Archival: all four predecessor continuity records and 24 replaced agent guidance lines were
   checked verbatim against HEAD in this log; current documents retain archive pointers.
5. Context: root instructions already meet budget. The single cursor remains tasks/plan.md;
   detailed evidence stays here on demand. No additional status or handoff document was created.
6. Memory: the 348160-byte database passes immutable read-only quick_check; 21 facts exist.
   Ordinary sqlite3 -readonly reports unable to open database (cause not established).
   Memory doctor fails with missing harness_a.toml. The Profile does not require the memory baseline;
   no consumer configuration was introduced. Documented dry-run renders match both existing projections.
7. Constraints: secret/protected-path, destructive-action, raw-exec, bootstrap and receipt tests
   remain intact. A pre-existing setup test tried the real host data directory before its fake uv;
   XDG_DATA_HOME now points to its temporary fixture. The same assertions pass without guard changes.
8. Skills/agents: isolated plugin/common-contract checks, registry checks and strict parsing of
   all four changed agents pass. No local duplicate skills or Codex model pins were introduced.
9. Instructions: unchanged CLAUDE.md = 41 lines / 3448 bytes; AGENTS.md = 43 / 3537.
   Both before and after satisfy 55/3600 and 60/3800; generated root body equals the source.
10. Rules/lessons: corrected the orchestrator to use documented memory commands and render lessons
    and memory-map projections. No lesson, safety rule or accepted decision was deleted.
11. Architecture: supported Starter, recipe, CLI, plugin, agent/command and reference boundaries
    match the checkout. No architecture rewrite was needed.
12. Routing: applied the already accepted ADR-69/85 amendment to the four operational agent
    contracts and route hints. The central policy overlay resolves unit work to gpt-6-luna/high;
    local null routing fields inherit policy. Compatibility CodexMcp* API names remain unchanged.
13. Continuity: one cursor, one resume pointer, one status projection and one evidence log remain.
    The canonical pre-compact generator refreshes the handoff's managed runtime snapshot.
14. Retrieval: memory-backed SRR-MEMORY-RELATIONS returns four implementation edges, including
    src/mir/core/memory_relations.py and src/mir/cli/relations.py. Context pull returns relevant
    architecture/verification anchors but no facts or chunks because no archives are configured.
    The historical spec graph does not contain that SRR anchor; no graph was synthesized.
15. Efficiency: current repository SessionStart emits 551 bytes; the shared continuity hook emits
    94 bytes. Large evidence, TDD and historical documents remain on demand. Root sizes are unchanged.

### Second-pass verification and failure classification

- Full final suite: 1226 passed, 3 failed in 203.46 seconds.
- Focused generator, isolated plugin/common-contract, public-surface/sanitization, links, payload,
  release-evidence, release metadata, startup, safety guards and shim suite: 166 passed.
- Setup isolation regression: observed failure with a host-directory permission error, then 1 passed
  after the fixture-only change. The full final suite also passes that test.
- The first full run overlapped the diagnostic-text edit after pytest had imported its old expectation,
  producing 8 transient shim mismatches; the final full run passes all 8. They are not pre-existing defects.
- Two final failures are pre-existing environment limitations: test_greenfield_slim_integration and
  test_installed_cli cannot download required PyPI packages because DNS/network access is unavailable.
  Their test files and production paths were not changed; the same failures appeared in the initial run.
- One final failure is caused by these authorized agent-source edits: the capability-lock test requires
  both committed-source hashes and working-source hashes to match. All existing committed-source hashes
  still verify, but the four edited agents differ. ADR-85 requires committed-source binding, while this
  turn forbids commits. The lock and its test were not weakened or given fabricated provenance.
- Worktree verify_codex_sync reports exactly the four pending agent derivatives below. A temporary
  tracked-source copy with generated output installed passes the same verifier. Non-Codex generator
  outputs are byte-identical; nothing needed copying back. Root and nested generated files are intact.
- Ruff, context paths (9 files / 69 references), document-size budgets, agent registry, strict agent
  frontmatter and harness consistency (0 errors / 0 warnings) pass. git diff --check passes.
- The adopter payload is regenerated after tracked documentation changes. Final closing checks
  are run again after recording this evidence and generating the handoff snapshot.

### Second-pass delivery and owner boundaries

Pending generated installation (re-run scripts/generate_codex_derivatives.sh in an authorized environment):

- .codex/agents/codex-final-reviewer.toml
- .codex/agents/executor-agent.toml
- .codex/agents/main-orchestrator.toml
- .codex/agents/pipeline-validator.toml

The temporary generated output and command logs are retained outside the checkout for the orchestrator;
no host-specific absolute path is added to public files. After installing derivatives, regenerate the
adopter payload. Capability-lock binding requires a separately authorized commit containing the source
changes, followed by the repository's normal committed-source binding process and lock verification.

No Profile edit or bootstrap re-attestation is pending. No new ADR policy decision is needed for the
transport corrections: amendment A1 already settled it. The prior uncertainty about unnumbered
successors for 13 retired mirror ADRs remains historical and was not resolved by guessing.
The remaining owner boundary is the no-commit instruction versus committed-source lock binding;
this pass preserves both and leaves that delivery action to the orchestrator. Live model execution,
runtime installation, network-dependent acceptance, commits, tags and releases were not performed.

Orchestrator acceptance (2026-09-23): the four `.claude/agents/*.md` wording edits and their
`.codex/agents/*.toml` derivatives were withheld from the local commit because the capability lock
binds agent bytes to a published source commit, which requires release authority. The replaced lines
listed above remain the current agent text until that release. The adopter payload was regenerated
and the full suite passed (1,229).


## Twenty-item repository maintenance re-verification (2026-09-23)

Owner-authorized repository-only re-verification and minimal improvements. The active intent authority is `tasks/intent.json`; the sole cursor is `tasks/plan.md`. No delivery or runtime authority is added.

### Preserved predecessor continuity records

#### tasks/plan.md

````text
# Plan

Owner-authorized second-pass audit, 2026-09-23. `tasks/intent.json` is the intent authority.

- [x] Re-check the 15 items against actual files, commands and read-only health evidence.
- [x] Repair stale runtime guidance and the setup test isolation defect; preserve prior wording.
- [x] Generate Codex output in a temporary root and verify the generated candidate.
- [x] Run the full suite and affected checks; classify residual failures.

Repository work is complete. The orchestrator committed the verified changes locally (no push, tag or
release). The four agent-source wording edits were withheld: the capability lock binds agent bytes to
a published commit, so they ship with the next authorized release together with the lock binding.
Two network-dependent tests still need a network-capable environment.
Evidence, predecessor records and exact delivery paths: `tasks/change_log.md`,
"Second-pass fleet re-verification".

````

#### tasks/intent.json

````text
{
  "goal": "Re-verify and minimally fix all 15 owner fleet audit items in this repository only under the owner-authorized second pass of 2026-09-23. Preserve accepted decisions, safety gates, historical text and user work; validate actual commands and generated parity; report sandbox-only installation gaps without committing or delivering changes.",
  "goal_type": "maintenance",
  "scope": "Repository-only second-pass audit and minimal fixes. No commits, pushes, tags, stash, reset, checkout, user-work deletion, credentials, consumer writes, runtime installation or direct database mutation. Generated files change only through repository generators; sandbox-blocked Codex derivatives are staged outside the checkout for the orchestrator.",
  "priority": "normal",
  "updated": "2026-09-23",
  "history": [
    {
      "goal": "Repair Mir Yoke central capability status and multi-consumer update architecture: make global provider health readable without a consumer-local configuration or enrollment, separate consumer-local integration state, and permit atomic provider version migration across registered consumers while preserving non-requesting consumer files and locks as pending local integration. Preserve capability trust, digest, identity, secret, path, runtime, and activation checks; update ADR-89, current documentation, tests, and generated adopter payload without user-runtime or consumer writes.",
      "updated": "2026-09-06",
      "status": "superseded"
    },
    {
      "goal": "Align Mir Yoke as the Harness-managed central capability supply system for independently owned repositories: make the primary purpose, management authority, supported adoption channels, consumer ownership boundaries, ADR precedence, maintainer Profile, operating documentation, contract tests, generated derivatives, and adopter payload consistent without changing interfaces, profile enums, runtime installations, consumer repositories, protected memory, credentials, or external services.",
      "updated": "2026-09-06",
      "status": "superseded"
    },
    {
      "goal": "Clean up Mir Yoke project documents under owner Discord message 1552197111624372339 (2026-09-23): align the current documentation entry points and decision index with the supported surfaces, keep one active plan, preserve historical text and existing work, and verify document references and tests without changing behavior or delivery state.",
      "updated": "2026-09-23",
      "status": "complete"
    }
  ]
}

````

#### tasks/handoffs/session-handoff-LATEST.md

````text
# Session Handoff — Second-pass re-verification

Resume pointer: `tasks/plan.md` is the only cursor; `tasks/intent.json` records authority.
Evidence and predecessor records: `tasks/change_log.md`, "Second-pass fleet re-verification".
Verified changes are committed locally; the four agent-source wording edits were withheld until the
next authorized release can bind them in the capability lock. No push, tag, release or consumer write.

<!-- mir:runtime-snapshot:begin -->
## Runtime Snapshot (Generated)

### Active Plan Items
- No open plan items.

### Working Tree
- Working tree clean.
<!-- mir:runtime-snapshot:end -->

````

#### tasks/checklist.md

````text
# Checklist

Status projection for the single `tasks/plan.md` cursor: all 15 audit items were checked.
Local fixes and verification are complete and committed; the withheld agent-source edits (next
authorized release, with lock binding) and two network-dependent tests remain open.
Details and preserved predecessor text: `tasks/change_log.md`, "Second-pass fleet re-verification".

````

### Preserved stale closeout guidance

The generated Claude and Codex registrations both include SessionEnd;
`tests/test_compact_lifecycle_hooks.py` asserts the respective 60s and 3s timeouts.
Prior `.ai-harness/session-closeout.md` text:

````text
Claude wires `.claude/hooks/session-end.sh` to `SessionEnd`. This template's Codex hook surface does
not have that event, so run the same script manually only when a Codex closeout is explicitly
requested.
````

### Bounded maintenance design

Authority: `tasks/intent.json`. Correct only the on-demand closeout document to match
the existing canonical hook configuration and executed lifecycle tests. Preserve its
old text above; change no event, timeout, guard, profile, released package or lock.
The predecessor audit is marked complete in intent history because its cursor and
orchestrator acceptance already record completion; this new request extends it to
the twenty-item checklist. No unresolved owner conflict is suppressed.

The earlier handoff claimed four agent-source corrections were still withheld.
Current HEAD already contains those corrections after the intervening 0.10.5 release;
the generated mirror and committed capability-lock tests are rechecked below.
The superseded handoff is retained above, not rewritten as historical fact.

### Twenty-item results and evidence

1. Consistency: done. Profile paths exist; context verifier checks 9 files / 69 references;
   source/derivative parity, registry and harness consistency pass. Context freshness still
   correctly identifies the historical Profile baseline as review_required; this audit does not
   invent a replacement attestation.
2. Operating base: no change needed. Registered hook targets exist. Retained optional hooks and
   inert reference surfaces do not imply activation; no justified safety-check removal was found.
3. Documents: done. Corrected the on-demand SessionEnd statement against canonical configuration
   and existing lifecycle tests; current continuity no longer repeats the pre-0.10.5 release hold.
4. Archiving: done. Four predecessor continuity files and replaced closeout guidance are preserved
   verbatim above, with live pointers. No rule, decision or lesson was deleted.
5. Context: no change needed. One plan cursor; large logs and historical specifications remain
   on demand. Root instruction documents remain within their stricter budgets.
6. Memory: partial. Immutable read-only quick_check returns ok; database 348160 bytes / 21 facts;
   no foreign-key errors or expired facts. Documented reconcile-missing --dry-run returns 0;
   both render projections match. Doctor reports missing harness_a.toml, as before; the provider
   Profile requires no memory baseline. No memory reconfiguration or direct mutation was performed.
7. Harness: done. Both runtimes register SessionEnd. Actual PreToolUse permits a safe read and
   rejects raw Codex exec and secret-path edits. Bootstrap/receipt and protected-path guards remain.
8. Skills and agents: no change needed. Plugin/common-contract tests pass; no local skills shadow
   plugins. All 12 generated agent TOMLs parse with no model pins. Current agent transport wording
   already uses the Codex plugin/native lane; compatibility CodexMcp API names are not MCP dispatch.
9. Instructions: unchanged before/after: CLAUDE.md 41 lines / 3448 bytes; AGENTS.md 43 / 3537.
   Generated root body equals the source; limits 55/3600 and 60/3800 pass.
10. Rules and lessons: no change needed. Existing canonical rule ownership is retained; lessons and
    memory-map match documented dry-run rendering. No competing policy or lesson store was added.
11. Architecture: no change needed. Starter, Kit recipe, optional CLI, plugins, separate agent and
    command delivery, and inert references match actual paths and public-surface contract tests.
12. Delegation: no change needed. Central overlay resolves Astra > Sol > Luna, unit=Luna/high,
    default=Sol/medium; no model pin or extra delegation layer was introduced. App-server protocol
    tests execute locally; no authenticated live model run is claimed.
13. Continuity: done. One cursor, resume pointer, status projection and evidence log are retained;
    the repository PreCompact generator refreshes the handoff runtime snapshot.
14. Work context: done. Context pull returns relevant architecture anchors; archives are unconfigured,
    so facts/chunks are empty. Immutable SRR query returns four current implementation edges.
15. Token efficiency: no change needed. Actual SessionStart emits 551 bytes; shared continuity
    emits 94 bytes. Completed predecessor intent is marked complete using its recorded acceptance,
    preventing a false unfinished-intent advisory. No startup context expansion was added.
16. Test health: done with environment limits. All tracked tests lie under default tests/tools
    testpaths. A teardown regression had an unrelated 1-second process-start deadline: the full
    suite observed an initialize timeout, and an injected 1.2-second startup reproduced it before
    the fix. The same probe passes after restoring the normal client startup budget; all teardown
    assertions and kill timeout remain unchanged. Transport tests: 27 passed. Two new ancestor-path cases fail before the scan fix and pass after it; all 52 rule tests pass.
    Two installation tests still require PyPI access and therefore are not hermetic offline.
17. Code/security/dependencies: done with skipped online checks. The isolated full run exposed two scans that skipped all code when an ancestor directory
    was named tests. Both now apply the existing exclusion to repository-relative paths.
    Bounded transport and final-diff review found no further confirmed production defect. Public sanitization passes; no private
    absolute paths were found. The only credential-pattern hit is a synthetic security fixture in
    tests/test_capability_security.py. Direct runtime/dev dependency metadata uses MIT, BSD-3-Clause
    or Apache-2.0. Latest-version lookup fails with PyPI DNS errors; current vulnerability and
    transitive-license verification are not claimed. No dependency upgrade was made.
18. Integrity: done. Adopter payload is regenerated after tracked edits. Provider lock, Profile,
    plugin trees and receipts stay unchanged; only two maintainer scan conditions change. No integrity evidence needs rebind.
19. Runtime: done with live-runtime exclusions. All 17 shell hook entrypoints were invoked in an
    isolated fixture: 16 exit 0, PreToolUse rejects its missing bootstrap evidence as designed;
    missing-TDD warnings are advisory. Real-repository safe/blocked probes pass. The shared hook
    exits 0. Installed package and all plugins are 0.10.6; Codex CLI reports 0.156.0. Credential-backed
    live execution and runtime installation are outside this pass; no activation claim is made.
20. Open decisions: one existing historical decision remains. Thirteen mirrored ADRs record
    retirement, but no numbered successor is recorded. Keep their retirement notes unless the
    owner supplies authoritative successor mappings; only a definitive historical mapping is
    blocked. No implementation change in this pass conflicts with an accepted ADR.

### Verification and failure classification

- First full run: 1227 passed / 4 failed. Two payload mismatches were caused by this pass's
  concurrent documentation updates; generation and frozen-state reruns resolve them. Two failures
  were PyPI DNS/network limitations in unchanged installation tests.
- Second frozen-state run: 1228 passed / 3 failed. The same two network failures plus an existing
  teardown test's initialize timeout. Its exact scheduling cause is unknown; the bounded slow-start
  reproduction establishes the unrelated startup-budget sensitivity. The test-only fix restores
  the existing 10-second initialization default; no production timeout or guard changes.
- An additional full rerun lost its shared pytest scratch directory mid-run: 378 passed,
  1 failed, 852 setup errors. FileNotFoundError identifies the missing directory; the removal
  cause is unknown and disk space was available. No code fix was inferred from that event.
  The final run uses a new dedicated --basetemp outside the shared pytest scratch tree.
- First isolated full run: 1227 passed / 4 failed: the two network failures plus two confirmed
  ancestor-path scan defects. Added two regression cases: 2 fail and 2 existing cases pass before
  the fix; all 52 rule tests pass after the two-line fix. Existing repository-local test exclusions
  remain intact; parent directory names no longer suppress production scanning.
- Final implementation-state full run: 2 failed, 1231 passed in 200.74s (0:03:20).
  Both remaining failures are PyPI DNS/network errors in test_greenfield_slim_integration.py and
  test_installed_cli.py. Their files and production paths are unchanged.
- Focused lifecycle/plugin/common/release-evidence checks: 83 passed. Document/payload/generator,
  schemas, links, sanitization and decision checks: 72 passed. Transport tests after the fix:
  27 passed; injected slow-start probe fails before and passes after.
- Ruff, context paths, agent registry, harness consistency (0 errors / 0 warnings), generated
  parity and git diff --check pass. Existing tests cover the documentation contract; two new scan regression cases fail
  without the fix and pass with it. Closing record edits are followed by payload regeneration and
  relevant payload/release-evidence checks.
- Temporary-root generator initially failed on the inaccessible default uv cache; retry with
  UV_CACHE_DIR in a writable temporary directory succeeds. Generated outputs are byte-identical:
  no non-Codex copy-back, Codex installation or Codex removal is required.

### Delivery boundary

No commits, pushes, tags, releases, dependency upgrades, consumer writes, runtime installation,
secret access or direct database writes. No pending Codex derivative installation/removal or
integrity rebind. The remaining operational limitations are offline installation acceptance and
online dependency intelligence; optional provider memory doctor remains not_ready as documented.
Only the historical ADR mapping decision in item 20 remains; the prior agent release hold is closed.

## Preserved predecessor continuity text (2026-09-24)

### tasks/plan.md

```markdown
# Plan

Twenty-item repository maintenance, 2026-09-23. `tasks/intent.json` is the intent authority.
Predecessor records and evidence: `tasks/change_log.md`, "Twenty-item repository maintenance re-verification".

- [x] Re-check all twenty items against files, runtime probes and read-only memory evidence.
- [x] Correct closeout guidance, teardown startup budget and repository-relative scan exclusions.
- [x] Verify full tests, governance, generator parity and adopter payload/release evidence.
- [x] Record results, environment limits and the existing historical owner decision.

Repository maintenance is complete within the authorized boundary. Two installation checks remain
limited by unavailable PyPI access. No delivery, Codex installation or integrity rebind is pending.
```

### tasks/checklist.md

```markdown
# Checklist

Status projection for the single `tasks/plan.md` cursor: all twenty maintenance items were checked.
Closeout guidance, teardown-test startup sensitivity and ancestor-sensitive scans are repaired. Two installation tests are
network-limited; online dependency checks are unavailable. Generated derivatives match.
Evidence, preserved predecessor text and the single historical owner decision are in
`tasks/change_log.md`, "Twenty-item repository maintenance re-verification".
```

### tasks/handoffs/session-handoff-LATEST.md

```markdown
# Session Handoff — Twenty-item repository maintenance

Resume pointer: `tasks/plan.md` is the only cursor; `tasks/intent.json` records authority.
Evidence and predecessor records: `tasks/change_log.md`, "Twenty-item repository maintenance re-verification".

Corrected SessionEnd guidance, a teardown test's startup deadline, and repository-relative scan exclusions.
Final full suite: 1231 passed, two PyPI DNS/network failures; the slow-start reproduction and
27 transport tests pass. No Codex installation/removal or integrity rebind is pending.
Next verification requires network access for the two installation tests and dependency intelligence.
The existing historical ADR-mapping decision is recorded once in the evidence log.
No commit, push, tag, release, runtime installation or consumer write was performed.

<!-- mir:runtime-snapshot:begin -->
## Runtime Snapshot (Generated)

### Active Plan Items
- No open plan items.

### Working Tree
- Working tree dirty (11 paths; inspect git status --short).
<!-- mir:runtime-snapshot:end -->
```

## Owner-authorized maintenance continuation (2026-09-24)

- Authority: renewed owner maintenance scope; `tasks/intent.json` and `tasks/plan.md`; initial tree clean at 9b1fde0.
- Items 1–5: profile/layout/contracts checked; predecessor cursor, projection and handoff preserved verbatim above; one current cursor remains.
- Items 6, 14: immutable quick_check ok, 348160 bytes, 21 facts, no FK errors, expired facts or missing sources; both memory projections match.
- Memory relation retrieval returned four implementation edges without notices; context pull returned architecture anchors. Optional doctor remains not_ready because harness_a.toml is absent.
- Item 7: fail closed on bootstrap, parser, path, required-validator and safety-regex errors; diagnostics omit command and validator bodies.
- Items 8–12: registry, instruction parity, canonical rules, architecture and central routing checked; no local shared-skill shadow or model pin introduced.
- Item 9 before/after: CLAUDE.md 41 lines / 3448 bytes; AGENTS.md 43 / 3537; unchanged and within limits.
- Items 13, 15: one cursor/resume/projection/log retained; SessionStart emits 550 bytes and the shared continuity hook 94 bytes.
- Item 16: all tests remain under default tests/tools collection; unrelated one-second startup limits removed after a 1.2-second delayed-handshake reproduction failed before and passed after.
- Item 17: Codex completion params/items and external capability-status JSON now validate types; malformed replies reject pending calls. No dependency upgrades.
- Items 18–19: temporary-root generation is byte-identical; no Codex install/removal. All 17 shell hooks exit 0 on isolated representative inputs; shared hook exits 0.
- Guard regressions: 38 new cases fail without their respective fixes; guard/deny suite 81 passed. Client regressions: 17 fail against preceding/original code; client suite 44 passed.
- Slim JSON regression: 5 failed before, 22 passed after. Advisory regressions: 6 failed before fixes; related suite 43 passed; template parity suite 6 passed.
- Independent review reproduced patch-extraction and Python-fallback defects; both repaired. Final safety-regex review accepted; no unresolved introduced defect reported.
- Frozen full run: 1300 passed / 2 failed in 365.99s. Both failures are unchanged test_greenfield_slim_integration.py and test_installed_cli.py PyPI DNS failures.
- Earlier runs: 1231/4 and 1284/4 pass/fail; concurrent edits caused payload/clean-room mismatches, and the compact template parity regression was repaired. Final frozen run clears these.
- Earlier focused run: 177 passed / 1 existing initialize-timeout failure; the test-only startup fix above resolves the reproduced sensitivity.
- Ruff, context references (9 files / 69 refs), agent registry, harness consistency (0 errors / 0 warnings), generator parity and diff checks pass.
- Dependency latest-version lookup failed on DNS; online vulnerability and transitive-license checks skipped. Direct installed package metadata reviewed; no private absolute-path matches found.
- Credential-pattern locations only (not proof of real credentials): docs/_archive/harness-engineering/applications/example-harness/phase-1-application-2026-06-13-historical.md; tests/test_adr53_phase3b_context_cli.py; tests/test_capability_security.py; tests/test_hook_executability.py.
- Runtime limits: general Bash writes do not expose edit paths to the post-edit scan; intended context output sites remain pre-compact.sh, compact-resume.sh and user-prompt-submit.sh. No credential-backed runtime activation exercised.
- Item 20: the sole historical successor-mapping decision remains in the prior twenty-item entry, item 20; retirement records are preserved and no successor is invented.
- Integrity: profile, receipts, capability lock and released plugin trees unchanged; adopter payload regenerated after tracked edits. No rebind or delivery required.
- No commits, pushes, tags, releases, consumer writes, secret access or direct database mutation.
