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
