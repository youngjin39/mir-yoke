# Session Handoff — Yoke Role Plugins and Global Runtime Delivery

- Date: 2026-09-04
- Status: repository implementation and verification are complete; commit, push, and user-runtime
  activation are the remaining delivery steps.
- Branch: `main`; two earlier local commits preceded this work.
- Authority: the operator authorized direct Yoke edits, user-level activation, commit, and push to
  `main`. Consumer-repository mutation, PRs, workflows, tags, and releases remain excluded.

## Current Decision

Yoke is the sole authoring source for common role workflows. `mir-core`, `mir-code`, and
`mir-content` remain skills-only plugins. `mir-lifecycle-hooks` is a separately named
`skills-hooks` plugin containing the shared read-only `SessionStart` handler and its
`runtime-continuity` skill. Agents and Claude commands are not plugin components: a separate
digest-bound installer projects the Profile-selected agent union into both user runtimes and
projects Claude commands into Claude only. Codex resolves the same command intent through plugin
skills.

Repository-coupled hooks remain generated from each repository's own Profile and adapter. The
common plugin hook never reads repository files, environment values, credentials, or runtime input;
it performs no writes or subprocess/network work and emits one fixed 94-byte line. Status output
separates this global plugin hook from repository-coupled generated hooks.

No MCP plugin exists. Both runtime MCP registries were empty when audited and Yoke implements no
server. MCP stays reserved until a concrete server and the ADR-88 admission, digest, rollback, and
real-client gates exist.

## Implemented Surfaces

- Both marketplaces publish four Profile-selectable packages from the same Yoke tree.
- Capability-source schema 4 admits exactly `skills` and the acknowledged
  `mir-lifecycle-hooks` `skills-hooks` shape. It rejects MCP and all undeclared active content.
- Active-package validation pins exact manifests, file inventories, handler bytes, permissions,
  non-symlink roots, credential-pattern exclusions, and the reviewed package digest.
- Capability sync/update preserves registered consumer unions, supports compatible schema-1 and
  schema-2 migration, rejects partial or invented legacy state, and requires `update --apply` when
  an older lock lacks a newly selected package.
- READY requires a new session for every required runtime, exact skill-catalog attestation, and a
  fresh observation of `mir-lifecycle-hooks:SessionStart` after hook-digest trust review.
- `scripts/install_user_runtime_agents.py` is dry-run-first, accepts explicit absolute Claude and
  Codex homes, installs only the Profile-selected union, preserves unknown files, rejects managed
  divergence and unsafe roots, and rolls both homes and receipts back transactionally.
- The Codex plugin-agent feature request was added to the existing upstream issue:
  `https://github.com/openai/codex/issues/18308#issuecomment-5527444139`. No duplicate command issue
  was opened because Codex intentionally maps reusable command intent to skills.

## Verification

- Full suite: `uv run pytest -q` passes 961 tests in 168.52 seconds.
- Focused capability, supply-chain, installer, architecture, and asset suite: 178 tests pass.
- Ruff, Codex derivative verification, and the 805-file template-asset classification pass.
- Claude validates both `plugins/mir-lifecycle-hooks` and the Yoke marketplace.
- The isolated real-CLI verifier installs all four packages into fresh Claude and Codex homes,
  removes provider availability, and confirms identical plugin digests from two independent
  consumer directories.
- Codex reports stable `hooks` and `plugins`; the removed `plugin_hooks` feature flag is not the
  current stable hook capability.

## Remaining Delivery Sequence

1. Commit and push the verified provider implementation to `origin/main`.
2. Reconcile the existing schema-1 global provider state against its pinned legacy source, then
   run schema-4 `capability update --apply` from the published commit.
3. Run the separate agent/command installer for the actual Claude user root and the bridge Claude
   root against the shared Codex home; verify receipts and that Yoke-only agents are excluded.
4. Review and trust the exact installed Codex hook digest interactively, start fresh runtime
   sessions, attest the skill catalogs and observed hook, and finalize activation.
5. Record the activation evidence and resulting lock commit, then commit and push that closeout.

Consumer repositories must remain untouched throughout this sequence.

<!-- mir:runtime-snapshot:begin -->
## Runtime Snapshot (Generated)

### Active Plan Items
- Publish and activate the verified role-plugin and user-runtime surfaces.

### Working Tree
- Working tree contains the verified ADR-88 through ADR-90 implementation pending publication.
<!-- mir:runtime-snapshot:end -->
