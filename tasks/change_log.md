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
20. Historical pending item, closed 2026-09-24 by owner Tasks B and D below.
    Original record retained: one existing historical decision remains. Thirteen mirrored ADRs record
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
- Item 20 (historical; closed by owner Tasks B and D below): the sole historical successor-mapping decision remains in the prior twenty-item entry, item 20; retirement records are preserved and no successor is invented.
- Integrity: profile, receipts, capability lock and released plugin trees unchanged; adopter payload regenerated after tracked edits. No rebind or delivery required.
- No commits, pushes, tags, releases, consumer writes, secret access or direct database mutation.

## Owner Tasks B and D (2026-09-24)

Authority: owner Discord messages 1552352486801547415 (items 1–4) and
1552354384296411267 (lighter harness), relayed by Mir Harness. Scope: this repository
only; no delivery, re-attestation, secrets or direct memory writes.

### Superseded cursor (verbatim)

```markdown
# Plan

Owner-authorized maintenance re-verification, 2026-09-23–24, within this repository only.
`tasks/intent.json` remains the intent authority; the owner renewed the same scope.
Predecessor completion evidence: `tasks/change_log.md`, "Twenty-item repository maintenance re-verification".

- [x] Re-check twenty items, including output disclosure, guard errors, JSON types and hermetic tests.
- [x] Repair reproduced defects with failing regression tests, preserving released plugin bytes.
- [x] Run full tests, governance, temporary-root generation and payload/release evidence checks.
- [x] Record concise results, deferred work and owner decisions in the existing evidence log.

Verification and repairs are complete within scope. Full suite: 1300 passed; two unchanged
installation tests fail on PyPI DNS. Final record evidence: `tasks/change_log.md`,
"Owner-authorized maintenance continuation (2026-09-24)". No delivery or integrity rebind is pending.
```

### Historical profile enforcement region (verbatim)

Retired by the owner choice above. Safety behavior moves to the local guard; only
the redundant region and its code-path/dogfooding advisories are retired.

```bash
# --- Mir profile-driven enforcement (V2.2 — phase-2 scope + ADR-23 dogfooding exemption) ---
if [ "${MIR_FAMILY_CODE_PATHS_INITIALIZED:-no}" != "yes" ]; then
    MIR_FAMILY_SLUG="${MIR_FAMILY_SLUG:-your-harness}"
    MIR_FAMILY_CODE_PATHS=()
    _MIR_CODE_PATH_HELPER="$PROJECT_DIR/.claude/hooks/lib/code-path-config.py"
    if [ -f "$_MIR_CODE_PATH_HELPER" ]; then
        _mir_code_paths="$("$_MIR_PYTHON_LAUNCHER" "$_MIR_CODE_PATH_HELPER" \
                 --family "$MIR_FAMILY_SLUG" --check code-paths 2>/dev/null)" || {
            warn "code-path configuration inspection failed; using advisory defaults"
            _mir_code_paths=""
        }
        while IFS= read -r line; do
            [ -n "$line" ] && MIR_FAMILY_CODE_PATHS+=("$line")
        done <<< "$_mir_code_paths"
    fi
    [ "${#MIR_FAMILY_CODE_PATHS[@]}" -eq 0 ] && MIR_FAMILY_CODE_PATHS=( "tools/" "src/" )

    # ADR-23 dogfooding exempt check
    MIR_DOGFOODING_EXEMPT="no"
    if [ -f "$_MIR_CODE_PATH_HELPER" ]; then
        MIR_DOGFOODING_EXEMPT="$("$_MIR_PYTHON_LAUNCHER" "$_MIR_CODE_PATH_HELPER" \
                                --family "$MIR_FAMILY_SLUG" --check dogfooding-exempt 2>/dev/null)" || {
            warn "dogfooding advisory inspection failed; using advisory defaults"
            MIR_DOGFOODING_EXEMPT="no"
        }
    fi

    MIR_CODEX_DEFAULT_ENABLED="true"
    MIR_FAMILY_CODE_PATHS_INITIALIZED=yes
fi

_mir_path_matches_code_path() {
    "$_MIR_PYTHON_LAUNCHER" - "$1" "${MIR_FAMILY_CODE_PATHS[@]}" <<'PY'
import fnmatch
import os
import sys

path, *patterns = sys.argv[1:]
pwd = os.environ.get("PWD", "")
candidates = [path]
if pwd and path.startswith(pwd + "/"):
    candidates.append(path[len(pwd) + 1:])

def matches(candidate, pattern):
    if pattern.endswith("/"):
        return candidate.startswith(pattern) or ("/" + pattern) in ("/" + candidate + "/")
    return fnmatch.fnmatch(candidate, pattern.replace("**", "*"))

print("yes" if any(matches(candidate, pattern) for candidate in candidates for pattern in patterns) else "no")
PY
}

_mir_patch_path_safety_reason() {
    "$_MIR_PYTHON_LAUNCHER" - "$1" "$PROJECT_DIR" <<'PY'
import os
from pathlib import Path
import sys

raw_path, project_dir = sys.argv[1:]
root = Path(project_dir).resolve()
candidate = Path(os.path.expanduser(raw_path))
if not candidate.is_absolute():
    candidate = root / candidate
resolved = candidate.resolve(strict=False)
try:
    relative = resolved.relative_to(root).as_posix()
except ValueError:
    print("patch path outside project root")
    raise SystemExit(0)

parts = Path(relative).parts
if ".git" in parts:
    print("patch targets git internal state")
    raise SystemExit(0)

name = Path(relative).name
secret_names = {".env", "credentials", "id_rsa", "id_ed25519"}
if (
    name in secret_names
    or name.startswith(".env.")
    or name.startswith("credentials.")
    or name.endswith((".pem", ".key", ".p12"))
):
    print("patch targets a secret or credential file")
PY
}

_mir_tool_name="$TOOL_NAME"
if [ "$_mir_tool_name" = "Edit" ] || [ "$_mir_tool_name" = "Write" ]; then
    _mir_file_path="$FP"
    if [ -n "$_mir_file_path" ]; then
        _mir_file_safety_reason="$(_mir_patch_path_safety_reason "$_mir_file_path" 2>/dev/null)" || block "file path safety inspection failed"
        if [ -n "$_mir_file_safety_reason" ]; then
            echo "[PreToolUse BLOCK] $_mir_file_safety_reason: $_mir_file_path" >&2
            exit 2
        fi
        if [ "${#MIR_FAMILY_CODE_PATHS[@]}" -gt 0 ]; then
            _mir_match="$(_mir_path_matches_code_path "$_mir_file_path" 2>/dev/null)" || warn "code-path advisory inspection failed"
            if [ "$_mir_match" = "yes" ] && [ -z "${MIR_CODEX_SESSION_ID:-}" ] && [ "${MIR_CODEX_MAIN:-0}" != "1" ]; then
                echo "[mir ADVISORY] code-path edit on $_mir_file_path: consider the delegated lane when isolation, review independence, or parallelism justifies its cost; bounded direct-main edits are allowed." >&2
            fi
        fi
    fi
fi
if [ "$_mir_tool_name" = "apply_patch" ] || [ "$_mir_tool_name" = "ApplyPatch" ]; then
    _mir_patch="$(extract_json '.tool_input.command // .tool_input.input // .tool_input.patch // .tool_input.content | select(type == "string" and length > 0)')" || block "Malformed apply_patch payload"
    _mir_patch_paths="$(printf '%s\n' "$_mir_patch" | sed -nE \
        -e 's/^\*\*\* (Add|Update|Delete) File: (.*)$/\2/p' \
        -e 's/^\*\*\* Move to: (.*)$/\1/p')" || block "patch path extraction failed"
    while IFS= read -r _mir_patch_path; do
        [ -n "$_mir_patch_path" ] || continue
        _mir_patch_safety_reason="$(_mir_patch_path_safety_reason "$_mir_patch_path" 2>/dev/null)" || block "patch path safety inspection failed"
        if [ -n "$_mir_patch_safety_reason" ]; then
            echo "[PreToolUse BLOCK] $_mir_patch_safety_reason: $_mir_patch_path" >&2
            exit 2
        fi
        # ADR-87 follow-up: the safety reason above covers outside-root, git internals
        # and secret basenames, but not the deny-list. A patch could therefore add
        # secrets/prod.yaml, which protected-secrets-dir exists to stop.
        apply_deny_list "$_mir_patch_path" "path"
        _mir_match="$(_mir_path_matches_code_path "$_mir_patch_path" 2>/dev/null)" || warn "code-path advisory inspection failed"
        if [ "$_mir_match" = "yes" ] && [ -z "${MIR_CODEX_SESSION_ID:-}" ] && [ "${MIR_CODEX_MAIN:-0}" != "1" ]; then
            echo "[mir ADVISORY] code-path patch on $_mir_patch_path: consider the delegated lane when isolation, review independence, or parallelism justifies its cost; bounded direct-main edits are allowed." >&2
        fi
    done <<< "$_mir_patch_paths"
fi
# --- end Mir profile-driven enforcement (V2.2) ---

```

### Superseded index qualification (verbatim)

Mirrored summaries marked superseded say Mir Harness retired them but do not identify a
numbered successor. That missing mapping needs an owner decision before it can be asserted.

### B: behavior inventory and disposition

| Concern | Existing local behavior | Retired region contribution retained locally |
|---|---|---|
| Git internals | Raw `.git/config`, hooks, refs and objects check for file tools | Root-resolved `.git` at any path component for Edit/Write and patches |
| Secret basenames | Raw basename check for Edit/Write/NotebookEdit | Root-resolved basename checks for Edit/Write and patches, including symlink destinations |
| Outside root | Listed system prefixes block file tools | Every outside-root Edit/Write or patch target blocks; no outside-root advisory or exemption existed |
| Deny-list | File tools screen cwd-resolved relative paths | Patches keep their raw-path deny-list subject and rule reason; no pattern is removed |
| Protected paths | Secret/credential rules are literal and deny-list driven | No general profile protected-path loader existed in the region; no new profile policy is inferred |
| Memory/scratchpad | No dedicated exception | No exception existed; owner memory and scratchpad Write probes remain blocked |
| Parsing/errors | jq required; malformed JSON, missing paths, failed inspectors block | Non-string/empty patch and failed Add/Update/Delete/Move extraction or safety inspection still block |
| Redaction | Bash/validator contents omitted from block messages | Moved diagnostics use `block` with a fixed reason, never command or patch contents |

All file tools and both patch spellings now enter `screen_path_target`. The existing
root-based helper is retained within that local section to preserve its distinct
resolution semantics; NotebookEdit keeps its existing narrower checks. The removed
region never enforced family code-path ownership. Its initialization, matcher,
dogfooding probe and delegation advisory were advisory-only.

`rg` found no runtime readers of the removed initialized/code-path/dogfooding/default
variables outside the removed block. The remaining enabled-phases reader uses
`${MIR_FAMILY_SLUG:-your-harness}`, preserving the previous default without setup.
The standalone code-path helper and unrelated bluebrick/phase/contract advisories
remain unchanged. Removed unused tier declaration, preserved verbatim:

```bash
#   pre-tool-use/code-path-block  : tier=block  (your-harness BLOCK code path protection)
_MIR_HOOK_TIER_CODE_PATH="warn"
```

### D: authoritative successor resolution

Verified all 13 `superseded_by` fields in the Mir Harness archived copies named by
these records' `mirrors` fields. The complete mappings are now in
`docs/decisions/INDEX.md` and each corresponding ADR. Mir Harness ADR-06 explicitly
also names Mir Harness ADR-72 and Mir Harness ADR-73 in its supersession note;
Mir Harness ADR-23 points to Mir Harness ADR-41, whose archived field points to
Mir Harness ADR-76. No same-numbered Yoke decision is substituted.

The prior item 20 is closed under owner Discord 1552352486801547415 and
1552354384296411267 (2026-09-24), relayed by Mir Harness. Its original pending text
remains labeled historical. Tasks A/C were not assigned in this execution request.

### Verification evidence

- Before implementation, the updated retired-profile-advisory test and new compiler-marker
  regression both fail: 2 failed / 53 deselected. After implementation, hook and deny-list
  checks pass: 81 passed / 0 failed, including parser/extractor fail-closed and redaction cases.
- Bootstrap/decisions/governance/generation/classification/identity first run: 59 passed /
  1 failed. The failure is the stale adopter-payload digest after source edits;
  regenerate through `python -m tools.template_assets --write-adopter-payload` at closeout.
- Links, schemas and public surface/identity: 10 passed / 0 failed.
- Ruff, context paths (9 files / 69 references), repository agent management and Codex sync pass.
- Temporary-root Codex generation is byte-identical to every checked-in generated output;
  no extra Codex output exists and no `.codex` install or removal is needed.
- Real-repository probes before and after: 20/20 match the supplied baseline. Payloads only
  reach PreToolUse; no tested Bash command or file mutation executes. Probe-added invocation
  log suffixes are removed with prefix validation, preserving pre-existing log bytes.

| Case | Baseline | Before | After |
|---|---:|---:|---:|
| edit-src | 0 | 0 | 0 |
| write-readme | 0 | 0 | 0 |
| write-env | 2 | 2 | 2 |
| write-git | 2 | 2 | 2 |
| write-etc | 2 | 2 | 2 |
| write-outside | 2 | 2 | 2 |
| write-memory | 2 | 2 | 2 |
| write-scratch | 2 | 2 | 2 |
| write-secretsdir | 2 | 2 | 2 |
| nb-env | 2 | 2 | 2 |
| nb-src | 0 | 0 | 0 |
| patch-src | 0 | 0 | 0 |
| patch-env | 2 | 2 | 2 |
| patch-git | 2 | 2 | 2 |
| patch-outside | 2 | 2 | 2 |
| patch-secretsdir | 2 | 2 | 2 |
| bash-ls | 0 | 0 | 0 |
| bash-rmrf | 2 | 2 | 2 |
| bash-cat-env | 0 | 0 | 0 |
| malformed | 2 | 2 | 2 |

Bootstrap evidence changed: `.claude/hooks/pre-tool-use.sh`. Re-attestation belongs
to the Mir Harness orchestrator and was not performed. Profile, capability lock,
receipts, memory databases and released plugin bytes are unchanged. Owner B/D
implementation is complete; orchestrator clone remeasurement and re-attestation
remain external acceptance work. No commits, pushes, tags or consumer writes.

Final follow-up: after repository-owned payload regeneration, the same
bootstrap/decisions/governance/generation/classification/identity suite passes:
60 passed / 0 failed. Public sanitization passes; harness consistency reports
0 errors / 0 warnings. The payload changes only the 18 edited source-file hashes,
with identical file membership and classifications. Final record edits are followed
by regeneration and the focused payload/link/schema checks.


## Owner choice B orphan-helper follow-up (2026-09-24)

Authority: owner Discord 1552352486801547415 and 1552354384296411267, relayed
by Mir Harness. The follow-up section of `tasks/plan.md` is the active intent cursor.
Scope is this repository only. The prior B/D evidence above remains historical;
its statement that the standalone helper remains unchanged is superseded here.

### Changes and delivery

- Removed `.claude/hooks/lib/code-path-config.py`, the orphan reported by R8, and
  removed its construction from the retired-advisory test. Existing safety tests remain.
- Made the existing Codex generator tolerate an absent hook library and omit its
  mapping. Added a missing-source regression; the portable-copy test now supplies
  its own library fixture instead of depending on the retired production helper.
- Regenerated `.codex-sync/manifest.json` through the repository generator in a
  temporary output root. All other generated file bytes match the checked-in files.
- Regenerated `config/adopter-payload.json` through `tools.template_assets` against
  the candidate after applying generated removals. Both Claude and Codex helper
  entries are absent. No payload filtering or hand editing was used.
- Added an Unreleased entry in `CHANGELOG.md`, preserving the old introduction.
  Adopters no longer receive this helper or the profile enforcement block removed
  by owner choice B. Local safety guard behavior is unchanged.

Pending orchestrator application: delete `.codex/hooks/lib/code-path-config.py`
using the repository generator. The sandbox cannot modify `.codex/**`; its stale
copy remains in this working tree. Consequently the prepared payload describes
833 minus 1 = 832 candidate files, while the working tree still has 833 files.
This is a delivery dependency, not permission to suppress parity checks.

### Verification

- Before cleanup: existing `test_hook_file_reachability_real_repo_green` fails
  with the exact R8 orphan finding (1 failed).
- New missing-source generator regression before the fix: 1 failed, with
  `cp: .claude/hooks/lib: No such file or directory`. After the fix it passes.
- First focused run: 66 passed / 1 failed. The pre-existing portable-copy test
  assumed the retired production library existed; the independent fixture fixes
  that assumption without dropping its directory, symlink or digest assertions.
- Final hook, Codex generation, harness/governance, decisions, public surface,
  identity, links and schema tests: 153 passed / 0 failed.
- Candidate payload/classification/public tests: 10 passed / 0 failed. Candidate
  Codex sync passes. Working-tree Codex sync reports the expected portable-library
  drift until the orchestrator applies the generated deletion.
- The first candidate sync attempt could not download dependencies because PyPI
  DNS resolution failed. Retrying with the existing environment and UV_NO_SYNC=1
  passes; no dependency or environment policy was changed in the repository.
- Harness consistency: 0 errors / 0 warnings. Ruff, context paths (9 files /
  69 references), agent management, sanitization, links, schemas and diff checks pass.

### Task B probes versus the preserved baseline

These payloads are supplied only to PreToolUse; commands and edits are not executed.
The probe records stay in ignored runtime evidence. Nineteen direct probes match
the preserved baseline. The inline destructive-command probe was rejected by the
execution tool's own PreToolUse screening; an attempted temporary test-script patch
was also rejected as outside the project. Neither guard was bypassed. Existing
`test_should_redact_command_when_bash_guard_blocks` covers destructive command
blocking in the passing hook suite. That isolated test is not a twentieth direct probe.

| Case | BASELINE | Follow-up probe |
|---|---:|---:|
| edit-src | 0 | 0 |
| write-readme | 0 | 0 |
| write-env | 2 | 2 |
| write-git | 2 | 2 |
| write-etc | 2 | 2 |
| write-outside | 2 | 2 |
| write-memory | 2 | 2 |
| write-scratch | 2 | 2 |
| write-secretsdir | 2 | 2 |
| nb-env | 2 | 2 |
| nb-src | 0 | 0 |
| patch-src | 0 | 0 |
| patch-env | 2 | 2 |
| patch-git | 2 | 2 |
| patch-outside | 2 | 2 |
| patch-secretsdir | 2 | 2 |
| bash-ls | 0 | 0 |
| bash-cat-env | 0 | 0 |
| malformed | 2 | 2 |
| bash-rmrf | 2 | Not rerun directly; tool rejected the probe |

### Boundaries and remaining owner work

No declared bootstrap evidence changed in this follow-up (23 tracked evidence
files checked against starting hashes); no re-attestation is required by this pass.
The pre-existing `pre-tool-use.sh` edits and the orchestrator's SessionStart fix
remain intact. No memory commands, database edits, credential access, commits,
pushes, tags or consumer writes were performed. B's local helper cleanup is done;
D's earlier successor mapping remains closed. Owner A/C were not assigned here.
Only generated Codex deletion and the resulting parity/payload acceptance remain
with the orchestrator, in addition to any explicitly reported full-suite limits.

### Full-suite closeout

`UV_CACHE_DIR=/tmp/mir-yoke-followup-uv uv run pytest -q` completed with
1298 passed / 5 failed in 337.76 seconds:

- Two payload equality tests report the pending generated Codex removal; final
  payload regeneration and candidate checks below isolate the remaining mismatch
  to `.codex/hooks/lib/code-path-config.py`.
- `test_should_leave_minimal_starter_and_project_owned_changes_when_candidate_is_slimmed`
  cannot download PyYAML because files.pythonhosted.org DNS resolution fails.
- `test_should_run_copied_tool_when_repository_python_is_not_on_path` cannot fetch
  pydantic because pypi.org DNS resolution fails. No installation code was changed.
- `test_release_evidence_rejects_unobserved_git_configuration` reports a changed
  provider snapshot. Closeout documentation was edited while this full run was
  active, so the run was not frozen. With writes stopped, its exact rerun passes:
  1 passed / 0 failed in 5.60 seconds. No test or guard was changed for this failure.

The full suite is not claimed green. After final cursor/log writes, payload is
regenerated through the existing generator and its candidate/public checks are
rerun; the orchestrator must apply the Codex deletion and verify the working-tree
payload/parity checks. Network-enabled installation acceptance remains open.
Evidence logs are under `/tmp/mir-yoke-helper-followup/`: `generator-red.log`,
`focused.log`, `governance-tests.log`, `full.log`, `release-recheck.log`,
`payload-candidate-tests.log`, `sync-cwd.log`, `sync-candidate.log`, and `probes.json`.


## Codex/Claude hook parity (2026-09-24)

Authority: owner Discord 1552383320107515968, item 6, relayed by Mir Harness.
The active intent authority is `tasks/plan.md`; scope is this repository only.
Initial `git status --short` was empty.

### Preserved predecessor cursor (verbatim)

```markdown
# Plan

Owner Tasks B and D, 2026-09-24, in this repository only. Authority: owner Discord
1552352486801547415 and 1552354384296411267, relayed by Mir Harness; this cursor
records the current intent. Prior cursor and retired rules are preserved verbatim
in `tasks/change_log.md`, "Owner Tasks B and D (2026-09-24)".

- [x] B: inventory and consolidate the local path guard; preserve the 20-case baseline.
- [x] D: verify 13 archived Mir Harness successor mappings and close the pending item.
- [x] Verify fail-first regressions, hook/governance checks and generated parity.
- [x] Record evidence, generated installation differences and re-attestation needs.

Local implementation and verification are complete. Mir Harness owns clone
remeasurement and re-attestation of the changed PreToolUse bootstrap evidence.
No Codex generated-file installation is needed. Full evidence is in the log above.

## Owner choice B follow-up (2026-09-24)

This cursor records the owner-authorized cleanup of the orphan code-path helper.
The completed B/D work above remains historical evidence; the ready bootstrap
receipt and all declared bootstrap evidence must remain unchanged in this pass.

- [x] Reproduce R8, remove the unused helper and helper-only test fixture.
- [x] Regenerate payload and temporary Codex output; record pending installation.
- [x] Run full tests, public-surface and hook/governance checks, and baseline probes.
- [x] Record evidence and remaining external work in tasks/change_log.md.

Follow-up implementation and permitted verification are complete; full-suite status
is 1298 passed / 5 failed, with the snapshot failure passing its frozen rerun.
Two network failures and two payload checks remain limited. The orchestrator must
apply the generated deletion of `.codex/hooks/lib/code-path-config.py` and recheck
working-tree payload/parity. No bootstrap evidence changed in this follow-up.
See `tasks/change_log.md`, "Owner choice B orphan-helper follow-up (2026-09-24)".
```

### Policy finding and bounded decision

`git log -S 'remain Claude-only'` traced the generator exclusion to `d3693b8`
(2026-08-29). ADR-84 section 2.4 acknowledged Codex event support but deferred the
cross-runtime efficiency decision. No incompatible field or blocking requirement
was recorded. The current owner task resolves that deferral for this repository.
ADR-84 preserves the original ADR, registration and README wording as dated
superseded notes. The only new runtime registration is UserPromptSubmit; all
pre-existing Codex registrations compare equal. StopFailure stays Claude-only.

The hook is unchanged: at most six terms, one advisory hint, no retrieval execution,
network or memory write; parser/interpreter/tokenizer failures return zero.
Synthetic payload fields follow the official reference:
https://learn.chatgpt.com/docs/hooks#userpromptsubmit and #common-input-fields.

### SessionStart finding

The actual Claude command and generated Codex command produce identical stdout,
stderr and exit code zero with a synthetic startup payload. Both invoke the same
session-start script and upfront-context builder. They inject identity and safety
boundaries, not cursor or intent bodies; only an applicable intent-conflict advisory
is included. This preserves existing task-blind startup policy, so no parity fix
is needed. The compact-only resume registration is unchanged.

No native MEMORY.md for this repo was found at the repository root,
`.claude/MEMORY.md`, `.claude/memory/MEMORY.md`, or matching mir-yoke project-memory
paths under the standard Claude home and installed per-agent Claude homes. No
native index was available to compare/inject. This finding does not attest other
machines or operator-specific memory-directory overrides. No memory DB was accessed.

### Verification and fail-first evidence

- All 5 new generated-command regressions failed before the fix with
  KeyError: UserPromptSubmit. After the fix, the whole prompt-hook file passes
  9/9. New cases cover normal, short, slash-command, XML-like and invalid-type
  prompts, asserting exit zero and exact advisory/empty output.
- Focused hooks, startup and Starter/Kit checks: 81 passed / 0 failed.
- Candidate derivation, compact lifecycle, startup and Starter/Kit checks:
  40 passed / 0 failed. Initial candidate run: 39 passed / 1 failed because the
  disposable copy lacked Git metadata; initializing only that copy fixed it.
- Full documented `uv run pytest -q`: 1303 passed / 5 failed in 200.02 seconds,
  with source writes paused. Two payload equality failures were resolved by the
  existing payload generator, then 13/13 related checks passed. One hook equality
  failure awaits Codex installation. Two unchanged installation tests fail on DNS:
  greenfield-slim cannot download jsonschema from files.pythonhosted.org; copied
  CLI cannot fetch httpx from pypi.org. The full suite is not claimed green.
- Candidate payload/classification: 13 passed / 0 failed.
- Ruff, Bash syntax and diff whitespace checks pass. Context paths: 9 files /
  69 references pass.
- Documented Codex sync fails in cwd for exactly `.codex/README.md` and
  `.codex/hooks.json`; the same verifier passes with the generated candidate.

### Generated installation and boundaries

Temporary output: `/tmp/mir-yoke-hook-parity/generated/`, produced with
CODEX_DERIVATION_OUTPUT_ROOT by the repository generator. Install only
`.codex/hooks.json` and `.codex/README.md`, then rerun the existing
`uv run python tools/template_assets.py --write-adopter-payload` and
`uv run python scripts/verify_codex_sync.py`. The cwd payload manifest reflects
currently installed bytes and needs regeneration after Codex installation.
No other Codex/AGENTS/.agents or sync-manifest installation is required.
The payload generator also corrected a pre-existing stale hash for the unchanged
`.mir/repo-profile.toml`; the profile itself was not edited.

No declared bootstrap evidence changed: hook and repo-profile bytes are unchanged.
This checkout has neither a bootstrap adoption manifest nor a local bootstrap
receipt; the existing maintainer path is unchanged. No re-attestation, new guard,
removed-hook recreation, credential access, memory edits, commits or delivery
occurred. Starter, Project Agent Kit and the shared template renderer are unchanged.

Evidence: `/tmp/mir-yoke-hook-parity/` contains fail-first.log, focused.log,
full.log, candidate-tests.log, candidate-payload.log, session-start.json,
unchanged-boundaries.json, generated/ and candidate/. Synthetic invocation proves
payload compatibility, not live Codex dispatch/trust in a new session. Installation
and network-enabled acceptance remain external. A shell-based documentation append
was rejected by command screening; the explicit file patch succeeded without
changing any guard.


## Twenty-one-item maintenance skill implementation (2026-09-24)

Authority: owner Discord 1552387906927333458, relayed by Mir Harness.
The active design and scope authority is `tasks/plan.md`. ADR-80 binding is deferred.
The owner explicitly authorizes updating this plugin source, superseding the prior
maintenance task's released-plugin byte freeze for this implementation only.

### Implementation and verification

- Items 1-5 and 8-20 retain their original text. Item 6 adds documented database,
  memory and relation-graph repair and stable snapshots that include WAL state.
  Item 7 names Claude/Codex harness consistency. Item 21 covers both Main runtimes:
  root/nested instructions and design references, hook events/commands and documented
  runtime-only exemptions, SessionStart cursor/intent/native-memory index, skill and
  workflow loading, MCP bindings, current Codex hook trust, and observed evidence.
- Bounds prohibit new restrictions, owner-removed hook recreation and blocking
  previously allowed behavior. No runtime hook or safety guard was changed.
- Traced registration through `git log -S repo-maintenance` and e3cb1a8 (v0.10.6).
  Capability sources, agent-management catalog, verifier inventory, dual-runtime
  manifests and sixteen-skill package count already match; no registration edit needed.
  Current descriptions say twenty-one; historical v0.10.6 release text stays historical.
- Fail-first: 11 failed / 1 passed before the skill edit. Every new case failed:
  memory repair, harness bounds and eight parameterized Main-runtime probes, plus
  the updated item-count contract. The unchanged safety-bound contract passed.
- Full documented `uv run pytest`: 1315 passed / 3 failed in 206.87 seconds.
  The lock test fails because only mir-core differs from the unchanged capability
  lock; the other three plugin trees still match. ADR-80 binding is explicitly deferred.
  The greenfield-slim installation cannot download rpds-py from files.pythonhosted.org;
  the copied CLI installation cannot fetch httpx from pypi.org. Both report DNS errors.
  Full-suite acceptance remains blocked by binding and network-enabled installation.
- Final focused skill/package/common contracts: 33 passed / 0 failed after clarifying
  the WAL snapshot wording and fixing one Ruff line-length error in the test.
  Ruff, Codex sync, agent-management schema/catalog checks, context paths (9 files,
  69 references), and diff whitespace checks pass. No skill-size budget was found in
  repository checks; the skill is 63 lines / 6181 bytes (previously 52 / 4670), English only.
  CLAUDE.md stays 3448 bytes and AGENTS.md stays 3537 bytes, both byte-identical.
- Temporary generation produced no differing files: no .codex, AGENTS, .agents or
  sync-manifest installation is needed. The adopter payload is regenerated through
  `tools/template_assets.py --write-adopter-payload`; it is not a runtime lock rebind.
- Declared bootstrap evidence, profile, versions, locks and runtime hooks are unchanged.
  No re-attestation, credentials, protected memory writes, consumer edits or Git
  publication occurred. The worktree was clean before this task.
- Evidence lives at `/tmp/mir-yoke-maintenance-21/`: fail-first.log, focused.log,
  focused-final.log, full.log, generation.log, codex-sync.log and generated-diff.json.
  UV_CACHE_DIR points to its writable uv-cache subdirectory because the inherited cache
  was not writable. The documented intent launcher found no bootstrap receipt; the
  same intent_store.py document operation ran through uv without re-attestation.
- Statuses here concern implementing skill guidance, not certifying live CLI parity.
  Fresh-session hook trust and consumer installation are outside this source-only step.
  The prior generated checklist projection and handoff snapshot were not hand-edited.

### Superseded handoff (verbatim)

```text
# Session Handoff — Repository maintenance re-verification

Resume pointer: `tasks/plan.md` is the only cursor; `tasks/intent.json` records authority.
Evidence and preserved predecessor text: `tasks/change_log.md`, 2026-09-24.
Guards now reject checker errors, diagnostics omit command bodies, advisory hooks report failures,
and malformed external JSON completes with protocol errors instead of leaving pending calls.
Final full suite: 1300 passed; two unchanged installation tests failed on PyPI DNS.
Network access is needed for installation acceptance and current dependency intelligence.
No Codex installation/removal, receipt rebind, commit or delivery is pending.
The historical ADR mapping decision remains in the prior evidence entry, item 20.

<!-- mir:runtime-snapshot:begin -->
## Runtime Snapshot (Generated)

### Active Plan Items
- No open plan items.

### Working Tree
- Working tree dirty (18 paths; inspect git status --short).
<!-- mir:runtime-snapshot:end -->
```

### Superseded operations description (verbatim)

```text
Mir Yoke's portable set is intentionally limited to four plugins and sixteen skills. The optional
`mir-core:selective-relations` skill supports bounded retrieval through declared relationships. The
`design`, `governance`, `efficiency`, `bluebricks`, `testing`, `code-review`, and
`verify` skills already compose this upgrade workflow; an umbrella duplicate would add discovery
cost without a new capability. `mir-core:repo-maintenance` is the owner-defined twenty-item
periodic checklist; it sequences those skills for a maintenance pass and does not restate their procedures.
```

### Superseded input (verbatim)

#### tasks/plan.md

```
# Plan

Owner-authorized Codex/Claude hook parity, 2026-09-24, in this repository only.
Authority: owner Discord 1552383320107515968, item 6, relayed by Mir Harness.
This cursor is the active intent authority. Predecessor cursor is preserved verbatim
in `tasks/change_log.md`, "Codex/Claude hook parity (2026-09-24)".

- [x] Trace the Claude-only policy and verify synthetic Codex prompt compatibility.
- [x] Add only advisory parity through canonical sources; preserve superseded wording.
- [x] Compare SessionStart context and native memory index availability.
- [x] Prove regressions fail first; run documented verification and temp generation.
- [x] Record generated installation list, bootstrap evidence and residual risks.

No commits, delivery, memory writes, consumer-template changes, new restrictions,
or removed-hook recreation are authorized. Generated Codex output stays temporary.

Local source work and permitted verification are complete. Mir Harness must install
`.codex/hooks.json` and `.codex/README.md` from the temporary generator output, then
regenerate `config/adopter-payload.json` and rerun parity. Two installation tests
remain blocked by PyPI DNS. Full evidence is in the log entry named above.
No declared bootstrap evidence changed; no re-attestation was performed.
```

#### tasks/intent.json

```
{
  "goal": "Re-verify all twenty repo-maintenance checklist items against actual repository state and execution evidence, then minimally repair confirmed defects within this repository only.",
  "goal_type": "maintenance",
  "scope": "Owner-authorized maintenance on 2026-09-23. Preserve accepted decisions, user work, safety guards, released plugin and capability-lock bytes, generated-source boundaries and memory databases. No commits, delivery, dependency upgrades, credentials or consumer writes. Previous intent is preserved verbatim in tasks/change_log.md under Twenty-item repository maintenance re-verification.",
  "priority": "normal",
  "updated": "2026-09-23",
  "history": [
    {
      "goal": "Align Mir Yoke as the Harness-managed central capability supply system for independently owned repositories: make the primary purpose, management authority, supported adoption channels, consumer ownership boundaries, ADR precedence, maintainer Profile, operating documentation, contract tests, generated derivatives, and adopter payload consistent without changing interfaces, profile enums, runtime installations, consumer repositories, protected memory, credentials, or external services.",
      "updated": "2026-09-06",
      "status": "superseded"
    },
    {
      "goal": "Clean up Mir Yoke project documents under owner Discord message 1552197111624372339 (2026-09-23): align the current documentation entry points and decision index with the supported surfaces, keep one active plan, preserve historical text and existing work, and verify document references and tests without changing behavior or delivery state.",
      "updated": "2026-09-23",
      "status": "complete"
    },
    {
      "goal": "Re-verify and minimally fix all 15 owner fleet audit items in this repository only under the owner-authorized second pass of 2026-09-23. Preserve accepted decisions, safety gates, historical text and user work; validate actual commands and generated parity; report sandbox-only installation gaps without committing or delivering changes.",
      "updated": "2026-09-23",
      "status": "complete"
    }
  ]
}
```

#### plugins/mir-core/skills/repo-maintenance/SKILL.md

```
---
name: repo-maintenance
description: "Periodic maintenance checkup of an agent-operated repository across twenty fixed items: consistency, operating base, documents, archiving, context, memory, harness constraints, skills and agents, instruction docs, rules and lessons, architecture, delegation and routing, continuity, work-context retrieval, token efficiency, test health, code/security/dependencies, integrity evidence, runtime behavior, and open decisions.\n\nTrigger: repository maintenance, periodic check, repo checkup, fleet maintenance, clean up and improve the repository"
---

# Repository Maintenance

## Use When
- The owner asks for a full maintenance pass over one repository or every managed repository.
- A previous pass needs re-verification against actual files and command output.

## Bounds
- Read, review and status requests stay read-only. A fix request authorizes in-scope edits and relevant checks only.
- Commit, push, tag, release, protected paths, secrets and memory-store writes follow the repository's
  own authority rules. Use only documented commands for memory and generated files.
- Move stale or duplicate material verbatim to the repository's log or archive and leave a pointer.
  Never delete a rule, decision or lesson.
- Relaxing a constraint means removing duplication, dead checks or gates for removed features. It never weakens a safety guard.
- A change that contradicts an accepted decision record or recorded owner intent is listed for the owner, not applied.
- Use a concept (fleet registry, bootstrap receipt, memory store, provider lock) only when the repository declares it.

## Checklist
Apply each item proportionately. Mark it done, no change needed (with evidence), or skipped (with a reason).
1. Consistency: profile and declared paths and commands match reality; docs match code; references resolve; generator parity holds.
2. Operating base: scripts, configs and hooks for removed features; dead entries.
3. Documents: plans, checklists and decision records state current facts. History is not rewritten.
4. Archiving: stale explanations, detailed history and duplicates move to the log or archive.
5. Context: always-loaded files stay minimal and procedures load on demand. Keep a single active cursor.
6. Memory: memory-store integrity and size, stale or missing-source records, and relation-graph health, checked through the documented commands.
7. Harness: excessive, duplicated or dead constraints are relaxed; harness consistency is improved.
8. Skills and agents: unused or duplicate capabilities, stale model or tool references, broken frontmatter.
9. Instruction docs: CLAUDE.md and AGENTS.md stay within size limits and carry the same rules for both runtimes.
10. Rules and lessons: each rule has one home, and lessons live in the declared location.
11. Architecture: the overview matches the actual layout and lists no removed components.
12. Delegation: model routing, delegation lanes and sub-agent limits follow the governing policy.
13. Continuity: one cursor, one resume pointer, one status projection and one evidence log.
14. Work context: one retrieval smoke query returns relevant anchors when retrieval is supported.
15. Token efficiency: session-start and hook output size, always-loaded file sizes, oversized routine reads.
16. Test health: the whole suite runs by default, stays hermetic, is not flaky under load, and new regression tests fail without their fix.
17. Code, security, dependencies: real defects, secret exposure, vulnerable or outdated dependencies, licenses.
18. Integrity evidence: locks, ledgers, receipts, audit chains and profile baselines are rebound through their documented commands after edits. Never fabricate provenance.
19. Runtime behavior: hooks fire, plugins and skills load, tool servers connect, and CLI versions match. Static documentation is not proof.
20. Open decisions: every pending owner decision is listed once, with both sides and the item it blocks.

## Workflow
1. Record the request in the repository's active cursor, then read its contract and profile.
2. Start from a clean or snapshotted worktree so changes can be attributed.
3. Run the checklist. When available, use `mir-core:governance`, `mir-core:verify`, `mir-code:testing` and
   `mir-code:code-review` for item procedures. For many repositories, handle each one under its own contract.
4. Verify with the repository's documented tests and gates. Re-run them yourself before accepting delegated work.
5. Report per item, then list changed files, before/after instruction-doc sizes, checks with pass/fail counts,
   integrity evidence to rebind, owner decisions and residual risks.
```

## Executor common split successor (2026-10-01)

The user supplied a new executor-common specification and local-commit authority. The completed predecessor cursor is preserved below.

```markdown
# Plan

Owner-authorized twenty-one-item maintenance skill implementation, 2026-09-24.
Authority: owner Discord 1552387906927333458, relayed by Mir Harness; this repository only.
This cursor is the active intent authority. Predecessor cursor is preserved verbatim
in `tasks/change_log.md`, "Twenty-one-item maintenance skill implementation (2026-09-24)".

- [x] Trace v0.10.6 registration, current scope and owner intent; preserve prior text.
- [x] Prove missing repair, harness parity and Main-runtime probes with failing contracts.
- [x] Update the skill and current descriptions; preserve historical release facts.
- [x] Regenerate payload and temporary derivatives; run the full suite and documented checks.
- [x] Record counts, fail-first proof, installation needs and bootstrap boundaries.

Design: retain all twenty existing topics, strengthen items 6 and 7, and add item 21
with concrete instruction, event, startup, capability, MCP and trust probes tied to
runtime evidence. This edits guidance and its contracts, not runtime hooks. Existing
registration remains valid. Current docs state twenty-one; released history stays dated.

No commits, pushes, tags, stash/reset/checkout, release/version/lock binding, secrets,
memory writes, new restrictions or removed-hook recreation. Generated Codex output
stays temporary. Mir Harness owns subsequent installation, binding and release.

Implementation is complete. Full verification: 1315 passed / 3 failed (one expected
mir-core lock mismatch pending ADR-80 binding; two installation failures on PyPI DNS).
Final focused checks: 33 passed / 0 failed; Ruff and generated parity pass.
No generated Codex installation or bootstrap re-attestation is needed for this change.
Detailed evidence and preserved inputs are in the log entry linked above.
```

Executor common implementation evidence: 89 fail-first nodes, both full suites
1417 passed, both Ruff runs clean, Python 3.11.16 compiled 15 common files, Codex
parity passed. The common manifest is separate from adopter inventory; Yoke local
schema validation and verifier data remain excluded from common sync. Pilot syncs
were read-only and compared package/config/Git-index hashes before and after.

Local commit attempt was blocked: Git could not create `.git/index.lock` under the
session's read-only Git metadata boundary. No commits or remote delivery occurred.
The complete scoped change is retained in the working tree and a temporary patch.

## Archived cursor sections: executor common (moved 2026-10-02)

Moved verbatim from `tasks/plan.md` by the 2026-10-02 maintenance pass; the cursor keeps a pointer.
Resolution facts recorded after the move (from `git log`): the "Commit blocker" and the
unchecked commit item below were resolved by 79536b2; v3.4 (merge gate refuses declared
secrets, unused `state_callback` dropped) landed as 14209a2; Stop hook temp-file
randomisation as 443e293; Harness model-routing lock redeploys as 27ce08a and cf2aa6c.

```markdown
## Active task: executor common v3.3 (2026-10-01)

Authority: the current user request and supplied `spec-executor-v33.md`.
This cursor is the design authority for background failure exit codes and the
read-only route invariant after local hooks. Work only in mir-yoke; named
consumer files are read-only. Do not commit or push.

- [x] Port background regression tests and add route tests; observe failure first.
- [x] Record exit_code=1 and enforce read-only routes; observe focused passes.
- [x] Update the sync guide and regenerate common manifests and affected payload.
- [x] Run full pytest, Ruff, Python 3.11 compilation, self-target sync and parity.

Fail-first: `7 failed, 5 passed, 29 deselected in 0.20s`.
Same initial selection after implementation: `12 passed, 29 deselected in 0.16s`.
Expanded regression selection: `18 passed, 29 deselected in 0.24s`.
Affected files: `47 passed in 0.46s`.
Ruff (`tools tests`): `All checks passed!`. Python 3.11.16 compiled all 15
common manifest files. Self-target sync and Codex parity passed; manifest, sync
and adopter tests: `35 passed in 4.16s`.

First full run: `1 failed, 1597 passed in 210.13s (0:03:30)`.
The exact adopter-payload test failed because this cursor was updated during
that run, after payload generation. Regenerate the payload before rerunning;
keep hashed source documents unchanged while the suite executes.

Final full pytest: `1598 passed in 198.08s (0:03:18)`.
After regenerating the payload, exact inventory, adopter, sync and manifest checks
passed (`41 passed in 4.77s`). Final cursor updates are followed by payload
regeneration and the same generated-inventory checks. No commit, push or consumer
write occurred.

The predecessor records below preserve earlier implementation evidence.

## Active task: executor common v3.2 (2026-10-01)

Authority: the current user request and supplied `spec-executor-v32.md`.
This cursor owns the implementation plan: the invoking Git repository's optional
`authorize_target` guard and opt-in `verifier_env` isolation only.
Write only in mir-yoke; inspect Harness read-only. Do not commit or push.

- [x] Add guard tests, observe failure at ba298f0, implement and observe pass.
- [x] Add verifier isolation tests, observe failure, implement and observe pass.
- [x] Update sync guide and regenerate manifests (payload is affected).
- [x] Run full pytest, Ruff, Python 3.11 compilation and self-target sync checks.

Fail-first evidence (all new nodes also run against an exported ba298f0 package):
guard: `13 failed in 0.55s` -> `13 passed in 0.57s`;
verifier isolation: `5 failed in 1.04s` -> `5 passed in 1.02s`.
Guard coverage includes option registration, writer admission, root changes,
saved and legacy resume targets, and preserved local-option help.
Isolation covers per-verifier directories, explicit environment inputs and cleanup
on success, failure, timeout and process errors.

Final full pytest: `1580 passed in 210.20s (0:03:30)`.
Ruff (`tools tests`): `All checks passed!`. Python 3.11.16 compiled all 15
common manifest files. Self-target sync, Codex parity and 19 manifest/sync/adopter
checks passed. No repository commit, push or Harness write occurred.

The predecessor records below preserve earlier implementation evidence.

## Active task: executor common v3 (2026-10-01)

Authority: the current user request and supplied `spec-executor-v3.md`.
This cursor is the design authority for the six specified common execution changes.
Write only in mir-yoke; named consumers are read-only. No commit, push or tag.

- [x] Per item: add regression tests, observe fail, implement and observe pass.
- [x] Cover CLI routes, agent API, execution writer lease, strict item shape,
      provider hook and optional timeout bounds with compatible absent defaults.
- [x] Update sync guide and regenerate common manifests and affected payload.
- [x] Run full pytest, Ruff, Python 3.11 compilation and self-target drift check.

Evidence: `tasks/reports/executor-common-fail-first.md` owns per-item fail/pass
results. Final full pytest: `1546 passed in 205.29s (0:03:25)`; all 88 v3 tests
passed. Ruff, Python 3.11.16 common-file compilation, generated parity,
self-target sync and regenerated-payload checks passed. No commit, push, tag
or consumer write occurred.

The predecessor records below are preserved as historical evidence.

## Active task: executor common base v2 (2026-10-01)

Authority: the current user request and the supplied `spec-executor-v2.md`.
This cursor is the design authority for the v2 extension hooks and resume integrity.
Write only in mir-yoke; consumers remain read-only. Do not commit or push.

- [x] Add fail-first tests for lifecycle events, identity, rendered briefs, root selection and resume.
- [x] Implement optional hooks with compatible defaults and additive job options storage.
- [x] Document semantics and regenerate common manifests and affected adopter payload.
- [x] Run focused/full pytest, Ruff, Python 3.11 compilation, sync and parity checks.

Fail-first evidence: `test_hooks_v2.py` initially reported `13 failed in 0.39s`:
7 lifecycle nodes, 2 identity nodes, 2 rendered-brief nodes and 2 root-selection nodes.
Durable-review, started/running, effective-options and absent-render-hook regressions
each subsequently failed in a focused run before their respective fixes.
Resume tests first reported `4 failed in 0.11s`; after schema-only implementation,
`2 failed, 2 passed in 0.09s` independently proved lost options and digest acceptance.
The portable manifest test failed with common CLI drift before regeneration.

Final focused pass lines:
- Lifecycle: `9 passed, 8 deselected in 0.30s`.
- Identity: `2 passed, 15 deselected in 0.09s`.
- Rendered brief: `2 passed, 15 deselected in 0.09s`.
- Root selection: `2 passed, 15 deselected in 0.10s`.
- Resume and effective options: `6 passed, 16 deselected in 0.16s`.
- Common manifest and adopter classification: `7 passed in 0.32s`.
- All new v2 tests, including absent-hook compatibility: `22 passed in 0.68s`.

Final full pytest: `1452 passed in 190.83s (0:03:10)`.
Ruff (`tools tests`): `All checks passed!`. Python 3.11.16 compiled all 15
manifest common files. Self-target sync and Codex derivative parity passed.
`policy.py` has no diff and remains self-contained. `cli.py`: 960 lines;
`dispatch.py`: 1211 lines. No commit, push or consumer write occurred.
Fail-first and final suite logs are in `/tmp/mir-executor-v2-*.txt`; resume
fail-first output is explicitly labeled as a transcription of observed tool output.

The completed follow-up below is preserved as evidence, not active authority.

## Active follow-up: executor fixes (2026-10-01)

Authority: the current user request and the supplied `spec-executor-fix1.md`.
This cursor is the design authority for three bounded common-executor fixes.
The predecessor record below is retained as evidence; its commit permission does
not apply to this follow-up. Write only in mir-yoke; do not commit or push.

- [x] Fail first, fix and pass: blocked-dispatch hint uses the actual artifacts path.
- [x] Fail first, fix and pass: backend resolution accepts per-project objects and ignores malformed entries.
- [x] Fail first, fix and pass: fallback policies preserve routing and monitoring.
- [x] Regenerate manifests and adopter payload; run focused/full pytest, Ruff and Python 3.11 compilation.

Fail-first and immediate pass evidence (pytest selectors):
- `blocked_prints_retry_diagnostic`: `2 failed, 118 deselected in 0.35s` -> `2 passed, 118 deselected in 0.23s`.
- `should_return_backend_when_per_project`: `8 failed, 1 passed, 120 deselected in 0.30s` -> `9 passed, 120 deselected in 0.04s`.
- `should_return_routing_and_monitoring`: `3 failed, 33 deselected in 0.07s` -> `3 passed, 33 deselected in 0.03s`.

Focused executor/sync suite: `438 passed in 48.62s`. Ruff: `All checks passed!`.
Full suite: `1430 passed in 200.40s (0:03:20)`. Adopter payload tests: `6 passed`.
Python 3.11.16: all 15 manifest common files compiled. Codex derivatives match sources.
Use `UV_CACHE_DIR=/tmp/mir-yoke-uv-cache` because the default cache is outside writable roots.
All three fixes are complete. No commit, push or other-repository write occurred.

## Preserved predecessor

Executor common base, local split and explicit sync, 2026-10-01.
Authority: current user task and the full owner-approved executor-common specification.
This cursor owns the current intent; the completed predecessor is preserved in
`tasks/change_log.md`, "Executor common split successor (2026-10-01)".

Design authority: this cursor and the supplied spec. Keep common code byte-identical,
repository hooks/data local, and routing policy in existing deployed files.

- [x] Prove missing policy, dispatch, client, job, CLI and sync behavior with failing tests.
- [x] Implement common modules, optional local adapter and cycle-free CLI split.
- [x] Generate independent common manifests and document explicit sync/drift checks.
- [x] Run full pytest, Ruff, Python 3.11 compilation and Codex parity checks.
- [ ] Commit scoped files locally; both dry-run pilots and migration reports are complete.

Only mir-yoke writes and local commits are authorized. No push, tag, release,
capability-lock or plugin edits. Pilot repositories remain read-only. Leave
`tasks/handoffs/session-handoff-LATEST.md` unstaged and uncommitted.

Verification completed: 89 new test nodes have explicit fail-first and pass lines in
`tasks/reports/executor-common-fail-first.md`. Full `uv run pytest`: 1417 passed;
Python 3.11.16 full pytest: 1417 passed. Ruff (both environments), Python 3.11
compilation of 15 common files, Codex parity and manifest drift checks pass.
Both pilot dry-runs report eight changed, six added and two identical files.
Package/config/index hashes remain unchanged in both pilots. Migration details remain
in temporary pilot reports; no consumer file was written. Common source commits and
final pilot revision binding remain pending the Git write boundary below.

Final compatibility follow-up: both legacy executor paths now honor local child
environment filtering and extra keys. Two more nodes failed first and passed;
both final full suites passed all 1417 tests.

Commit blocker: `git add` returned Operation not permitted when creating
`.git/index.lock`. The session grants read-only Git metadata access. No staging,
commit, push, tag or release occurred. The implementation and all requested checks
are complete; source and consumer manifests retain the generated source placeholder
until a writable Git session can commit and bind the consumer manifest.
```

## Repository maintenance pass (2026-10-02)

Authority: the owner's 2026-10-02 maintenance instruction relayed by the Mir Harness
Control Plane (`mir-core:repo-maintenance`, 21 items, this repository only). Cursor:
`tasks/plan.md`. Starting worktree clean at `cf2aa6c`. Baseline: full pytest
`1604 passed in 463.76s`; Ruff `All checks passed!`; Codex parity OK.

Changes:
- Removed six never-called functions from `scripts/generate_codex_derivatives.sh`;
  regenerated output is byte-identical (parity OK, no generated file changed).
- Removed the wired `session-end.sh` from the hook manual-trigger allowlist in
  `config/harness-consistency.json`; regression test
  `test_manual_trigger_allowlist_lists_only_unwired_hooks` failed first on HEAD config.
- Upgraded anyio 4.13.0 -> 4.15.1 (GHSA-82r6-8w77-94w6, GHSA-5p39-cfhj-2xmp; pulls
  typing-extensions 4.16.0) in `uv.lock` and the exported CLI runtime constraints.
  pip-audit: 2 findings before, none after.
- Moved six completed executor-common cursor sections verbatim (above); refreshed the
  stale handoff and checklist (superseded text below); added ARCHITECTURE and
  Unreleased CHANGELOG entries for the executor common source and routing lock;
  corrected a stale session-start claim in `.ai-harness/failure-patterns.md`.

Verified without change: profile paths exist; context paths PASS (71 references);
harness consistency 0 findings; executor common manifest PASS (15 files); routing lock
`source_sha256` matches its Harness sources and agent model fields match the lock;
hook probes (fail-closed on malformed PreToolUse payloads, no Stop/StopFailure echo,
SessionStart identical for both runtimes); memory database integrity ok.

Owner decisions:
- `CLAUDE.md` ends with an empty `## Role policy (template summary)` heading whose
  generated block was removed in 3aab445; `.mir-preserve.toml` still preserves it.
  Keep it (preserve contract) or drop it from both files (35 bytes of always-loaded text).
- The opt-in `MIR_REVIEW_GATE` block in `.claude/hooks/mir-stop.sh` cannot succeed
  (unregistered change ID, `review` is not a lock category, placeholder family) and
  cites ADR files that do not exist here. Remove it or rewire it; blocks hook cleanup.
- `.mir/memory.db` is one migration behind (018); `mir migrate up` writes a protected store.
- Whether owner message identifiers in public tests and logs count as private identifiers.
- Two installation tests need PyPI and are unmarked; a network skip would hide failures.
- The 13 superseded ADRs without successor numbers remain open (prior item 20).

Mir Harness requests: guard non-object `agent_criteria` in common
`tools/mir_executor/dispatch.py` (AttributeError); qualify "ADR-88" as Mir Harness
ADR-88 in common `policy.py` comments; refresh `profile_base_commit` (`e3207d5`;
`mir context pull` reports `profile-freshness state=review_required`), which has no
documented rebind command. `.mir/capability-lock.json` (source d8a1516) needs no
rebind: all 17 pinned file digests match the working tree.

Resumed run (same day): the run above stopped before committing. Its edits were audited
against the files: the six removed shell functions had no callers; `session-end.sh` is
wired in `.claude/settings.json` and `.codex/hooks.json`; pip-audit on the HEAD
constraints reports PYSEC-2026-4024/4025 (aliases GHSA-5p39-cfhj-2xmp,
GHSA-82r6-8w77-94w6; fix 4.14.2) and nothing on the new lock export. Fail-first for
`test_manual_trigger_allowlist_lists_only_unwired_hooks` re-run: HEAD config
`1 failed`, fixed config `1 passed`. Memory database read through an immutable
snapshot (no WAL/SHM files present): `integrity_check` ok, `foreign_key_check` empty,
`mir migrate status` 017 of 018, `reconcile-missing --dry-run` would expire 0.
`mir memory doctor` reports `not_ready` only because this checkout has no active
`harness_a.toml` (profile `requires_memory_store = false`). Codex project trust is
`trusted` with 11 `trusted_hash` entries for the 11 hooks in `.codex/hooks.json`
(unchanged since 7b0c37f); the hash values were not recomputed.
Final gates: pytest `tools` 699 passed, `tests` 906 passed; Ruff `All checks passed!`;
Codex parity OK; context paths PASS (75 references); harness consistency 0 findings;
executor common manifest PASS; `uv lock --check` resolves. Committed locally only.

Superseded continuity text, verbatim:

```markdown
# Session Handoff — Twenty-one-item maintenance skill

Resume pointer: `tasks/plan.md` is the only cursor; `tasks/intent.json` records authority.
Evidence and preserved predecessor text: `tasks/change_log.md`,
"Twenty-one-item maintenance skill implementation (2026-09-24)".
Items 6 and 7 are strengthened; item 21 adds concrete parity probes for either Main CLI.
Full suite: 1315 passed / 3 failed. Final focused tests: 33 passed / 0 failed.
Mir Harness owns ADR-80 binding (mir-core currently differs from the unchanged lock).
Two installation checks also need working PyPI DNS. Ruff and generated parity pass.
No Codex installation, bootstrap evidence change or re-attestation is needed.
No new restriction, hook recreation, memory write, version bump or Git publication occurred.
The generated snapshot below belongs to the preceding hook run; inspect current Git status.

# Checklist

Status projection for `tasks/plan.md`: all twenty maintenance items were re-verified.
Guards, advisory failure handling, external JSON validation and startup-test timing were repaired.
Final full suite: 1300 passed, two unchanged installation tests failed on PyPI DNS.
Evidence and preserved predecessor text: `tasks/change_log.md`, 2026-09-24.
Generated parity passes; no Codex installation/removal or integrity rebind is pending.
The historical ADR mapping decision remains in the prior twenty-item evidence entry, item 20.
```

## Archived maintenance cursor (2026-10-02 executor follow-up)

# Plan

## Active task: repository maintenance pass (2026-10-02)

Authority: the owner's 2026-10-02 maintenance instruction, relayed by the
Mir Harness Control Plane: run `mir-core:repo-maintenance` (21 items) over this
repository, then improve it. This cursor is the intent and design authority.
mir-yoke only; local commits of own files only. No push, tag, release, consumer
write, secret access, `config/model-routing.lock.json` or synced
`tools/mir_executor` common edits (those go to NEEDS HARNESS).
Starting worktree: clean at `cf2aa6c`.

- [x] Baseline: full pytest, Ruff, Codex parity.
- [x] Audit 21 items; re-verify the 2026-09-23/24 fixes, the ADR-88 lock and executor v3.4.
- [x] Fix in-scope defects; each new regression test fails first, then passes.
- [x] Re-run documented gates; regenerate the adopter payload; commit own files locally.

Final gates (resumed run): `uv run pytest` over `tools` 699 passed and `tests` 906
passed (1605); Ruff, Codex parity, context paths, harness consistency and the
executor common manifest pass. No task item remains open.

Evidence, owner decisions and Mir Harness requests: `tasks/change_log.md`,
"Repository maintenance pass (2026-10-02)".

## Predecessor cursor sections

Executor common v3.3, v3.2, v3, base v2, the executor fixes follow-up and the
preserved executor-common predecessor (2026-10-01; its open commit item was resolved
by 79536b2) moved verbatim to `tasks/change_log.md`,
"Archived cursor sections: executor common (moved 2026-10-02)".

## Executor common v3.5 maintenance (2026-10-02)

Authority: the explicit owner follow-up relayed by Mir Harness; design and intent
authority: `tasks/plan.md`. Baseline: clean HEAD `279c90f`. The follow-up authorizes
common changes deferred by the preceding maintenance pass and a local commit.
No consumer writes, credentials, memory writes, capability lock edits or publication.

### Changes and fail-first evidence

1. Production `cleanup_worktree` already removes its tracked automatic temporary
   base. CLI-level tests used `_cleanup_repo_dispatch_worktrees`, which
   directly removed Git worktrees and bypassed that production cleanup. The test
   helper now reconstructs the dispatch metadata and calls `cleanup_worktree`.
   The isolated-TMPDIR regression counts `mir-wt-*` entries before/after and
   verifies the created base is inside that directory.
2. The resolver now rejects non-object `agent_criteria` and non-object selected
   agent entries with clear `ValueError` messages, matching the existing
   malformed-lock `policy` error wording. Missing criteria still default normally.
3. Only the host-mode test docstring changed in `test_policy.py`: the deployed
   repository lock wins; the host policy is a fallback when no lock is deployed.
4. Common `policy.py` comments/docstring now name Mir Harness ADR-88 explicitly.
   Documented the common increment as v3.5; manifest schema stays version 1.

Fail-first command (before the helper and production fixes):

```sh
uv run pytest -q -p no:cacheprovider tools/mir_executor/tests/test_dispatch.py -k 'temp_bases or agent_criteria_is_not'
```

Observed: **9 failed, 134 deselected in 0.61s** (pytest exit 1).
All nine new nodes were observed failing:
- `test_should_remove_temp_bases_when_cli_test_worktrees_are_cleaned`: one empty
  automatic temporary base remained after test cleanup.
- `test_should_raise_clear_error_when_agent_criteria_is_not_an_object`:
  `[None]`, `[criteria1]`, `[invalid]`, `[1]`, `[criteria4]`, `[criteria5]`,
  `[criteria6]`, `[criteria7]` each raised AttributeError instead of ValueError.
  Inputs were null/list/string/integer for the criteria map and for its selected entry.

The same command after the fix returned **9 passed, 134 deselected in 0.38s**.
No new test passed before its fix, and no collection failure is counted as evidence.

### Verification

- Full executor tests: `uv run pytest -q -p no:cacheprovider tools/mir_executor/tests`:
  **608 passed in 71.97s**. Fresh isolated TMPDIR had **0** `mir-wt-*` entries
  before and **0** afterward; **0** new entries.
- Ruff on all four touched Python files: all checks passed.
- Python 3.11.16 compilation: all **15** common-manifest Python files compiled.
- `python -m tools.executor_sync --generate`: regenerated both common manifests,
  retaining the literal `SOURCE_COMMIT` placeholder and schema version 1.
- `python -m tools.executor_sync --help`: exit 0.
- `python -m tools.executor_sync --check --target .`: Common manifest PASS.
- `uv run python scripts/verify_codex_sync.py`: derivatives match Claude sources.
- No modified path is pinned by `.mir/capability-lock.json`; no rebind is needed.
- Full repository suite: `uv run pytest -q -p no:cacheprovider`:
  **1614 passed in 315.35s (0:05:15)**, pytest exit 0.
- Continuity projections and the adopter payload are refreshed for this task.
  Final portable-manifest, sync-tool, template-classification and reference-payload
  checks returned **26 passed in 2.00s**. Payload hashes are regenerated after
  recording this result and checked for exact equality before local commit.

### Explicit consumer resync

From the tested, committed Mir Yoke checkout, for each owner-authorized target:

```sh
python -m tools.executor_sync --target /path/to/repo
python -m tools.executor_sync --target /path/to/repo --apply
python -m tools.executor_sync --check --target /path/to/repo
```

Sync copies common runtime files and the portable manifest test only. The
repository-owned `test_dispatch.py` cleanup fix and `test_policy.py` docstring
are not synced; target owners must adapt those local tests separately.
No consumer repository was inspected or changed during this task.

### Local commit blocked by filesystem permissions

After verification, an explicit `git add` of the fourteen task-owned files failed:
`Unable to create .git/index.lock: Operation not permitted`. The execution
environment exposes `.git` read-only and does not allow permission escalation.
No file was staged and no new commit was made; HEAD remains
`279c90f9fbd91aeab37ed19cfdf2d9a58f1dae6c`. The worktree contains the reviewed edits.
The owner already authorized the commit; a Git-writable session must finish it
before this checkout is used as a consumer sync source.

Prepared commit subject: `fix(executor): validate agent criteria and clean test worktree bases`.
Material boundary trailer: `Constraint: Mir Yoke only; no consumer writes or publication.`
Required final commit-message line:
`Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Executor common v3.5 extension: items 5-6 (2026-10-02)

Authority: the owner's additional instruction extends the same uncommitted
v3.5 maintenance task. `tasks/plan.md` remains the intent and design authority.
Items 1-4 and their fail-first evidence above remain part of this change.
No consumer writes or publication; no amendment occurred because the earlier
local staging attempt was denied and HEAD remains `279c90f`.

5. The client issues integer RPC request IDs. Responses with string IDs, including
   internal `turn:<threadId>` wait keys, are ignored. Integer IDs not present in
   the issued pending-request map are ignored before envelope validation. Thus an
   unknown response cannot resolve a turn or fail genuine requests.
6. JSON decoding RecursionError is recorded and ignored like invalid JSON.
   The stdout reader's finalization maps unexpected exceptions and EOF to
   CodexMcpProcessError, preserves explicit protocol errors, stops the server and
   signals all pending calls. It also drains requests registered during teardown.
   Normal process-exit diagnostics retain the exit code.

### Additional fail-first evidence

Tests use the real subprocess test server. No hard timeout is passed to the
reader-failure calls; each test bounds its own observation and closes the client
in finally, so red runs cannot hang the test suite.

Initial definitive red command:

```sh
uv run pytest -q -p no:cacheprovider tools/mir_executor/tests/test_codex_mcp_client.py -k 'internal_turn or invalid_input_or_dies'
```

Result before either implementation fix: **6 failed, 44 deselected, 2 warnings
in 8.65s** (exit 1).
- Item 5: `test_should_ignore_response_when_id_matches_only_an_internal_turn`
  failed for `[spoofed_turn]` (SPOOFED accepted), `[spoofed_scalar]`
  (AttributeError) and `[spoofed_error]` (unissued error rejected the genuine turn).
- Item 6: `test_should_release_no_timeout_call_when_reader_gets_invalid_input_or_dies`
  failed for `[deeply_nested]`, `[reader_exception]` and `[reader_eof]`:
  each left the no-timeout call pending. The nested line raised RecursionError in
  the reader; the test uses depth 10000 because depth 5000 parses on Python 3.12.

A further item-5 boundary case was added before its corresponding membership fix:

```sh
uv run pytest -q -p no:cacheprovider tools/mir_executor/tests/test_codex_mcp_client.py -k integer_id_was_never_sent
```

`test_should_ignore_response_when_integer_id_was_never_sent` failed with
CodexMcpProtocolError for an unknown integer response envelope:
**1 failed, 50 deselected in 0.36s** (exit 1).

Final additional regression selector:

```sh
uv run pytest -q -p no:cacheprovider tools/mir_executor/tests/test_codex_mcp_client.py -k 'internal_turn or invalid_input_or_dies or integer_id_was_never_sent'
```

Result: **7 passed, 44 deselected in 1.61s**.
Each of the seven additional new cases failed before its own fix.
An intermediate complete transport check returned **68 passed in 15.47s**;
final verification below includes the additional unknown-integer case.

Both common manifests are regenerated for the same v3.5 increment; the manifest
schema remains 1. The third changed common runtime module is
`codex_mcp_client.py`; repository-owned tests remain excluded from sync.
### Combined six-item verification

- Full repository command: `uv run pytest -q -p no:cacheprovider`:
  **1621 passed in 240.54s (0:04:00)**, exit 0.
- Full executor command: `uv run pytest -q -p no:cacheprovider tools/mir_executor/tests`:
  **615 passed in 72.35s (0:01:12)**. The isolated TMPDIR had 0 `mir-wt-*`
  entries before and 0 afterward; no new directory leaked.
- All sixteen new regression cases across items 1, 2, 5 and 6 failed before
  their own fixes and pass in the full suite. Items 3 and 4 only change wording;
  their existing tests and affected common-file checks pass.
- Ruff on all six touched Python files: all checks passed.
- Python 3.11 compilation: all 15 manifest Python files compiled.
- `python -m tools.executor_sync --help`: exit 0.
- Both regenerated common manifests pass self-target `executor_sync --check`.
- `scripts/verify_codex_sync.py`: derivatives match Claude sources.
- No modified path overlaps capability-lock pins; no rebind is needed.
- Added tracked text is English and contains no private paths, owner IDs or
  machine-specific identifiers. Consumers were not inspected or modified.

The common version remains v3.5 for all six items; manifest schema remains 1.
The explicit consumer resync commands above remain unchanged and require a
tested, committed source checkout. Local staging must be retried; no commit
exists yet because the earlier Git sandbox denied `.git/index.lock` creation.

Prepared final commit message:

```text
fix(executor): harden request correlation and dispatch cleanup

Reject malformed agent criteria and unissued response IDs. Ignore excessive
JSON nesting and fail pending calls on stdout-reader failure or EOF. Reuse
production cleanup in CLI tests and clarify Mir Harness policy precedence.

Constraint: Mir Yoke only; no consumer writes, push, tag or release.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

Final closure checks for the extension: portable manifest, executor sync,
classification and reference payload tests returned **26 passed in 1.44s**.
The final explicit staging attempt for all sixteen task-owned files again
returned exit 128: `Unable to create .git/index.lock: Operation not permitted`.
No new commit or amendment was possible. The local commit remains the only open
task; the prepared message above retains the required final Co-Authored-By line.
HEAD is still `279c90f9fbd91aeab37ed19cfdf2d9a58f1dae6c`. The final evidence
record is included in the regenerated adopter payload and its exact hashes are
checked after regeneration. Temporary task scratch is removed at closure.

## Executor common v3.6: redaction coverage (2026-10-02)

Authority: owner Discord 1555264868402335765 (fleet maintenance pass), relayed by the Mir
Harness Main. Reported by the quietleaf maintenance run and reproduced by the Main:
`redact_secret_like_content` left `"api_key": "value"`, `SECRET_KEY=value`,
`Authorization: Basic <credential>` and quoted values with spaces visible, and
`redact_structured_value` kept string values whose dict key names a secret.

- `tools/mir_executor/redaction.py`: the secret-name pattern accepts a `_KEY` suffix, an
  optional quote after the key, quoted values (replaced whole) and a `Basic` scheme; a dict
  string value under a secret-named key becomes `[REDACTED]`. Unquoted assignments keep the
  existing `key=[REDACTED]` form.
- `tools/mir_executor/tests/test_redaction.py`: 6 cases failed before the fix (4 shapes,
  quoted value with spaces, dict key); 5 cases passed before and after
  (`AWS_SECRET_ACCESS_KEY`, three plain mentions, the existing unquoted format).
- Manifests regenerated with `python -m tools.executor_sync --generate`.

## Archived cursor: before executor common v3.7 (2026-10-02)

# Plan

## Active task: fleet Codex transport wording (2026-10-02)

Authority: owner Discord 1555375556290154528, 2026-10-02. This cursor records
intent and is the design authority. Work only in mir-yoke; preserve history,
compatibility identifiers, generated sources and unrelated changes. No executor
common-code edits, protected-path writes, commits or pushes.

Design: classify the requested grep inventory; update live transport guidance;
add the exact supersession line only to current ADRs without an equivalent note.
Preserve the dependent inactive MCP example entry and report that limitation.

- [x] Inventory and minimally update eligible sources and ADR notes.
- [x] Refresh the repository-only adopter payload and check docs, links and parity.
- [x] Record class counts, changes, generators, checks and unresolved dependencies for reporting.

Inventory (original line numbers; matching rows, not individual occurrences):

- LIVE: zero requested-regex hits; supplemental `.mcp.json.example` guidance and
  split command/args identify one live configuration source.
- HISTORY (12): `CHANGELOG.md:187`; ADR-65:16; ADR-69:32; ADR-85:104;
  ADR-90:40; `tasks/change_log.md`:681,943,944,945,958,960;
  `tasks/tdd.json`:577. ADR-69 and ADR-85 already have equivalent amendments.
- IDENTIFIER (15): `config/adopter-payload.json`:4837,4927;
  `config/mir-executor-common.json`:8; ADR-90:38 (real `codex mcp list` client
  command); `tasks/change_log.md`:1038,1239,2571,2584,2600,2604,2610,2620;
  `tasks/tdd.json`:1395,1398,1403.

Evidence: 18 tests passed via `uv run pytest -q tests/test_link_integrity.py
 tests/test_decision_authority.py tests/test_template_asset_classification.py`;
`uv run python scripts/verify_codex_sync.py` passed. No tests assert the changed
transport wording, so the conditional full-suite gate does not apply.
Generator: `uv run python -m tools.template_assets --write-adopter-payload`.
Use the owner-provided external `UV_CACHE_DIR`; temporary verification files use
an external `TMPDIR` and are removed afterward. Host paths are normalized here;
the original cursor remains available at `7f7e677:tasks/plan.md`.
The generator also refreshes an already-stale routing-lock digest; it does not
modify the routing lock. The inactive example has dependants in README,
MIGRATION, capability configuration, asset inventory, operations and ADRs;
its removed server entry is retained under the owner's removal condition.

## Previous completed task

## Active task: executor common v3.5 maintenance (2026-10-02)

Authority: the explicit owner follow-up relayed by Mir Harness on 2026-10-02.
This cursor is the intent and design authority. The follow-up authorizes the
previously deferred common executor edits and one local commit in mir-yoke.
No consumer writes, push, tag, release, credentials or capability-pinned changes.
Starting worktree: clean at `279c90f`.

Design: reproduce the isolated-TMPDIR test leak and reuse production cleanup,
which already removes its temporary base. Reject non-object agent criteria with
the resolver's normal ValueError contract. Correct the requested policy docstring
and qualify common policy references as Mir Harness ADR-88. Version this bounded
common maintenance increment as v3.5 in the sync document and changelog; keep
manifest schema version 1.

Owner extension: include items 5 and 6 in this same v3.5 increment. Only response
IDs issued by this client may resolve requests; internal turn keys are not RPC
request IDs. Treat excessive JSON nesting like other malformed lines. Unexpected
stdout-reader failure or EOF must release pending calls, including calls without
a timeout, through the existing process-error contract.

- [x] Reproduce response-ID collisions, excessive JSON nesting and unexpected reader death.
- [x] Fix request correlation and reader failure handling; record fail-first evidence.
- [x] Regenerate manifests and rerun the full verification for items 1-6.

- [x] Add regression cases and record every case failing before its fix.
- [x] Repair cleanup and criteria validation; correct policy wording.
- [x] Generate manifests; verify full executor tests leave no new mir-wt directories.
- [x] Run full pytest, touched-file Ruff, Python 3.11 compilation, sync and Codex parity.
- [x] Record evidence and refresh continuity projections and payload.
- [x] Commit locally: the Codex sandbox could not create `.git/index.lock`; the Mir Harness Main re-ran the full suite and committed.

Evidence: `tasks/change_log.md`, "Executor common v3.5 maintenance (2026-10-02)".
Other open owner items in the preceding maintenance evidence remain unchanged.

Predecessor cursor: `tasks/change_log.md`,
"Archived maintenance cursor (2026-10-02 executor follow-up)".

## Executor common v3.7: symlink safety and backend precedence (2026-10-02)

Authority: current owner task; intent/design authority: `tasks/plan.md`.
Baseline: clean HEAD `7f7e677`, common v3.6. No commit, tag, push, release,
consumer write, secret access or generated `.codex/**` write is authorized.

- Private worktree writes now set O_NOFOLLOW before truncating/chmodding files.
- Artifact persistence opens `.mir-dispatch` with O_DIRECTORY/O_NOFOLLOW and
  opens each artifact relative to that directory descriptor with O_NOFOLLOW.
  Both file and directory symlinks fail closed; absent artifacts remain optional.
- Current CLI already gave agent-route backends precedence over policy force and
  default backends. Its remaining defect ignored conflicting explicit backend
  flags even in user_command_priority mode. Backend resolution now accepts the
  agent backend and preserves policy-permitted user_command precedence while
  agent backends win over forced, project and default policy choices.
- Documented the common increment as v3.7. Common manifests retain schema 1,
  the same 15 file entries and literal SOURCE_COMMIT placeholder. Routing lock
  bytes and format are unchanged.

Fail-first evidence is preserved in `tasks/reports/executor-common-fail-first.md`
under "Common v3.7". Worktree: 1 failed -> 1 passed. Artifacts: 12 failed ->
12 passed. CLI: 12 failed / 96 passed -> 108 passed. Focused four-file suite:
198 passed in 9.93s. One new test line exceeded Ruff's line limit and was wrapped;
repository-wide Ruff subsequently passed.

Generators: `uv run python -m tools.executor_sync --generate` (15 common files)
and `uv run python -m tools.template_assets --write-adopter-payload`.
Every uv command uses the owner-provided external UV_CACHE_DIR; scratch stays
under the owner-authorized external cache and is removed after checks.
Initial checks: common manifest PASS; Codex derivatives match Claude sources;
Python 3.11.16 compiled all 15 common files. Final suite evidence follows below.

### Final verification and remaining item

- `uv run pytest -q -p no:cacheprovider tools/mir_executor/tests`:
  **1 failed, 742 passed in 72.49s (0:01:12)**, exit 1.
- `uv run pytest -q -p no:cacheprovider`:
  **1 failed, 1748 passed in 232.84s (0:03:52)**, exit 1.
- Both final runs fail only
  `test_policy.py::test_adr88_this_repository_routes_from_its_deployed_lock`:
  `assert 'force_codex' == 'user_command_priority'`. The test hardcodes a mode
  inconsistent with the committed routing lock. The test, conftest, policy.py,
  local sub-agent policy and routing lock match HEAD byte-for-byte. Its isolated
  rerun also failed in 0.05s. This unrelated existing assertion is left unchanged.
- `uv run ruff check`: All checks passed!
- `uv run python scripts/verify_codex_sync.py`:
  OK: Codex derivatives match Claude sources.
- `uv run python -m tools.executor_sync --check --target .`:
  Common manifest: PASS. Manifest top-level keys, schema 1, SOURCE_COMMIT and
  all 15 file entries are unchanged; the two common manifests are identical.
- Python 3.11.16 compiled all 15 common files using an external pycache.
- Portable manifest, executor sync and payload checks: 19 passed in 1.76s.
  Public-surface and exact-payload checks after path normalization:
  9 passed in 0.42s. The initial whole-repository run had an additional public
  path failure caused by host paths copied from the prior cursor and new evidence;
  these paths were normalized and the final whole-repository run passes that check.

Changed paths: CHANGELOG.md; config/adopter-payload.json;
config/mir-executor-common.json; docs/operations/mir-executor-sync.md;
tasks/change_log.md; tasks/plan.md; tasks/reports/executor-common-fail-first.md;
tools/mir_executor/COMMON_MANIFEST.json; tools/mir_executor/cli.py;
tools/mir_executor/dispatch.py; tools/mir_executor/worktree.py;
tools/mir_executor/tests/test_cli_common.py;
tools/mir_executor/tests/test_dispatch_common.py;
tools/mir_executor/tests/test_v3_cli_routes.py;
tools/mir_executor/tests/test_worktree.py.

No requested production fix remains open. The stale repository-owned policy
assertion prevents a green full-suite gate; it is not distributed by executor sync.
No commit, tag, push, release, consumer change, protected-path change or generated
Codex installation occurred. Final evidence edits require the final adopter-payload
refresh and its exact-content check; temporary scratch is removed afterward.

## Archived cursor: before executor common v3.7 review corrections (2026-10-02)

# Plan

## Active task: executor common v3.7 (2026-10-02)

Authority: the current owner task; this cursor owns intent and design. Fix the
three reported executor common defects test-first within Mir Yoke only. Preserve
lock formats, protected paths and unrelated changes. No commits, tags, pushes,
releases, consumer writes, credentials or generated `.codex/**` writes.
Baseline: clean HEAD `7f7e677`; prior common base v3.6.

Design: refuse symlink destinations using O_NOFOLLOW in private worktree writes;
open artifact sources without following symlinks before copying. Current CLI
already lets agent-route backends win over policy defaults/force modes; reproduce
that behavior and fix the remaining explicit backend flag precedence only where
policy permits selection. Keep model/effort overrides and read-only constraints.
Version this common increment as v3.7 in the sync guide and CHANGELOG; retain
manifest schema 1 and routing lock bytes.

- [x] Add each regression and capture baseline failure/pass evidence before fixes.
- [x] Apply minimum fixes and rerun each regression.
- [x] Record version/changelog; regenerate common manifests and adopter payload.
- [x] Run executor suite, repository pytest/Ruff/parity, manifest check and Python 3.11 compilation.
- [x] Record changed paths, exact evidence and anything left.

The superseded cursor is preserved with host paths normalized in `tasks/change_log.md` under
"Archived cursor: before executor common v3.7 (2026-10-02)".
The original is available at `7f7e677:tasks/plan.md`.

Results: focused checks passed; executor suite 742 passed / 1 failed; repository
suite 1748 passed / 1 failed. Both failures are the same unchanged policy test:
it hardcodes user_command_priority while the committed lock declares force_codex.
Policy source, fixture, local policy and routing lock match HEAD byte-for-byte.
Ruff, Codex parity, common manifest and Python 3.11 compilation passed.
Final evidence: `tasks/change_log.md`, "Executor common v3.7", and
`tasks/reports/executor-common-fail-first.md`, "Common v3.7".
No commit, delivery or generated Codex write occurred. The unrelated stale policy
assertion remains open; no requested production defect remains.


## Executor common v3.7 owner review corrections (2026-10-02)

Authority: current owner follow-up; intent/design authority: `tasks/plan.md`.
This correction supersedes the earlier v3.7 decision that agent backends override
forced modes. `_resolve_dispatch_backend` again returns the forced backend
unconditionally for force_codex/force_claude. The new force_codex plus Claude
agent-route regression failed first with `assert 'claude' == 'codex'`,
`1 failed in 0.06s`, exit 1. Existing explicit user_command precedence and agent
precedence over project/default steps remain. The dispatch route matrix is
updated to expect the forced backend. The committed-lock policy test now reads
its expected mode from the lock; lock bytes and format remain unchanged.
The v3.7 CHANGELOG and sync guide explicitly document enforced forced modes.
Captured fail-first and final evidence belongs to
`tasks/reports/executor-common-fail-first.md`, "v3.7 owner review corrections".
Final follow-up outputs (all exit 0; external UV cache and scratch applied):

```text
uv run pytest -q -p no:cacheprovider tools/mir_executor/tests/test_cli_common.py tools/mir_executor/tests/test_v3_cli_routes.py tools/mir_executor/tests/test_policy.py
177 passed in 3.86s

uv run python -m tools.executor_sync --generate
Generated config/mir-executor-common.json: 15 files

uv run python -m tools.template_assets --write-adopter-payload
template asset classification: pass

uv run pytest -q -p no:cacheprovider
1750 passed in 248.36s (0:04:08)

uv run ruff check
All checks passed!

uv run python scripts/verify_codex_sync.py
OK: Codex derivatives match Claude sources

uv run python -m tools.executor_sync --check --target .
Common manifest: PASS
```

The fail-first regression is covered by the 177-test focused run and the full
1750-test run. Both required corrections are complete. This follow-up changed
CHANGELOG.md; config/adopter-payload.json; config/mir-executor-common.json;
docs/operations/mir-executor-sync.md; tasks/change_log.md; tasks/plan.md;
tasks/reports/executor-common-fail-first.md; tools/mir_executor/COMMON_MANIFEST.json;
tools/mir_executor/cli.py; tools/mir_executor/tests/test_cli_common.py;
tools/mir_executor/tests/test_policy.py; tools/mir_executor/tests/test_v3_cli_routes.py.
Earlier v3.7 symlink implementation/tests remain intact. No commit, tag, push or
consumer write occurred. The committed lock and generated `.codex/**` are
unchanged. Final evidence edits are followed by the same payload generator and
exact-payload/public-surface checks; task scratch is removed after those checks.
No requested item remains open.

Final record/payload checks: `9 passed in 0.41s` using
`uv run pytest -q -p no:cacheprovider tests/test_template_asset_classification.py
tests/test_public_template_surface.py`. Lock and all 15 generated `.codex/**`
files match the follow-up baseline SHA-256 values.


## Archived cursor: before executor common v3.8 (2026-10-02)

# Plan

## Active task: executor common v3.7 review corrections (2026-10-02)

Authority: the current owner follow-up; this cursor owns intent and design.
Preserve the existing uncommitted v3.7 work. The owner corrects the prior decision
that agent backends override forced modes: force_codex and force_claude must
return their forced backend unconditionally. Explicit user backend selection
still wins in the selected user_command step; agent routes otherwise beat
project/default steps. The committed routing lock decides the live-policy test.
Do not change the lock, consumers, protected paths or generated `.codex/**`.
No commit, tag or push is authorized. Use the owner-provided external UV cache.

- [x] Review existing diff, cursor and v3.7 evidence.
- [x] Add the force_codex/conflicting agent-route regression; capture its failure.
- [x] Restore forced backend resolution; update route matrix and lock-based assertion.
- [x] Correct v3.7 guide/changelog/evidence; run both requested generators.
- [x] Run full pytest (zero failures), Ruff, Codex parity and executor manifest check.
- [x] Record final outputs, changed paths and remaining work; remove scratch.

The prior cursor is preserved in `tasks/change_log.md` under
"Archived cursor: before executor common v3.7 review corrections (2026-10-02)".

Results: the force_codex/conflicting-agent regression failed first (`1 failed in
0.06s`); focused tests passed (`177 passed in 3.86s`). Full pytest passed:
`1750 passed in 248.36s (0:04:08)`, zero failures. Ruff, Codex parity and executor
manifest checks passed; both requested generators succeeded. Final evidence:
`tasks/reports/executor-common-fail-first.md`, "v3.7 owner review corrections",
and the matching entry in `tasks/change_log.md`. Final record edits were followed by the
same payload refresh and exact-content/public-surface checks: `9 passed in 0.41s`. No requested item
remains; no commit/tag/push, consumer write, lock edit or `.codex/**` write occurred.


## Executor common v3.8: forced-mode route model guard (2026-10-02)

Authority: owner Discord 1555426386900942934, 2026-10-02; intent and design
are recorded in the single `tasks/plan.md` cursor. Baseline: clean `f95dcd5`.
Agent-route model/effort now apply only when the explicit execution_backend
matches the resolved backend. Explicit CLI model/effort keep precedence.
Category/default routes declare no backend; resolve_category returns model/effort
only. Forced dispatch rejects recognized opposite-backend automatic models using
Claude aliases sonnet/opus/fable/haiku and claude-* versus Codex gpt-* before
creating a runner. Unknown model names remain usable; explicit user models bypass
the guard. No policy or lock changes are required.

Fail-first: the force_codex plus Claude/sonnet agent regression observed
`assert 'sonnet' == 'gpt-category'`, `1 failed in 0.07s`, exit 1 before the fix.
Focused policy/CLI/route tests: `211 passed in 4.00s`, exit 0.
Both generators passed: common manifest generated 15 files; adopter asset
classification passed. Required acceptance results (all exit 0):

```text
uv run pytest -q -p no:cacheprovider
1784 passed in 220.99s (0:03:40)

uv run ruff check
All checks passed!

uv run python scripts/verify_codex_sync.py
OK: Codex derivatives match Claude sources

uv run python -m tools.executor_sync --check --target .
Common manifest: PASS

python3.11 -m compileall -q tools/mir_executor
(no output; exit 0, external task bytecode cache)
```

The guide and CHANGELOG version the common base as v3.8; generated manifests keep
schema 1 and SOURCE_COMMIT. Full fail-first output, changed files and final outputs
are in `tasks/reports/executor-common-fail-first.md`, "Common v3.8". The previous
cursor is preserved above. No commit/tag/push, consumer write, lock edit or generated
`.codex/**` write occurred. Final record edits are followed by the payload generator
and exact-content/public-surface checks; task scratch is removed afterward.


Final record refresh: `uv run python -m tools.template_assets --write-adopter-payload`
passed; `uv run pytest -q -p no:cacheprovider tests/test_template_asset_classification.py
tests/test_public_template_surface.py` passed (`9 passed in 0.35s`, exit 0).
The closing cursor/log update repeats the same payload refresh and checks.
No requested implementation or acceptance item remains. Task scratch is removed
after the closing checks; no additional delivery or Git authority is exercised.
