# Session Handoff — Yoke Role Plugins and Global Runtime Delivery

- Date: 2026-09-04
- Status: complete. Provider publication, global installation, runtime trust, attestation, and
  direct delivery to `origin/main` are complete.
- Branch: `main`.
- Authority: the operator authorized direct Yoke edits, user-level activation, commit, and push to
  `main`. Consumer-repository mutation, PRs, workflows, tags, and releases remained excluded.

## Current Decision

Yoke is the sole authoring source for common role workflows. `mir-core`, `mir-code`, and
`mir-content` are skills-only plugins. `mir-lifecycle-hooks` is the separately named
`skills-hooks` plugin containing the shared read-only `SessionStart` handler and its
`runtime-continuity` skill. Agents and Claude commands are separate from plugins: the digest-bound
installer projects the Profile-selected agent union into both user runtimes and projects Claude
commands into Claude only. Codex resolves the same command intent through plugin skills.

Repository-coupled hooks remain generated from each repository's Profile and adapter. The common
plugin hook never reads repository files, environment values, credentials, or runtime input; it
performs no writes, subprocesses, or network access and emits one fixed 94-byte line. Status output
separates this global hook from repository-coupled generated hooks.

No MCP plugin exists. Both runtime MCP registries were empty when audited and Yoke implements no
server. MCP remains reserved until a concrete server and the ADR-88 admission, digest, rollback,
and real-client gates exist.

## Delivered Surfaces

- Both marketplaces publish the same four Profile-selectable packages from the Yoke tree.
- Capability-source schema 4 admits only the exact `skills` and acknowledged `skills-hooks`
  shapes; MCP and undeclared active content fail closed.
- The global provider migrated from its valid legacy state and now reports `active`, exact provider
  integrity, verified discovery for both required runtimes, and `ready: true`.
- Claude and Codex each expose the exact 14 namespaced Yoke skills. Both executed the trusted
  `mir-lifecycle-hooks:SessionStart` handler in fresh runtime sessions.
- The four plugins are enabled and visible from all 14 registered repository roots without any
  consumer-repository edits.
- The separate installer placed 11 Profile-selected agents in the actual and bridge Claude homes
  and in the shared Codex home. It placed six commands in each Claude home; Codex intentionally
  has no copied command files and uses the mapped skills instead.
- Provider-local `template-sync-validator` remains in Yoke and is intentionally excluded from all
  global runtime homes.
- The Codex plugin-agent use case is recorded at
  `https://github.com/openai/codex/issues/18308#issuecomment-5527444139`. No duplicate command issue
  was opened because Codex maps reusable command intent to skills.

## Runtime Evidence

- Codex session `01a06838-1d44-7f50-b0bc-53c4ad08f525` displayed all 14 skills, showed the
  lifecycle hook as trusted, and received its exact fixed SessionStart output.
- Claude session `A3F9F6E8-1462-4448-A3B2-6B9AA8949B73` loaded all four plugins and logged the
  exact successful SessionStart output before the subsequent model request encountered a revoked
  OAuth token. The authentication failure does not invalidate plugin discovery or hook execution;
  renewing the user's Claude credential is an external account action.
- Finalization accepted both independent new-session attestations and changed the registration
  state from `restart-required` to `active`.

## Verification

- Focused capability, supply-chain, installer, architecture, compatibility, and transaction tests
  pass, including the 14 user-runtime installer safety tests.
- Ruff, Codex derivative verification, plugin validation, template-asset classification, and the
  isolated real-CLI activation probe pass.
- The full suite passes 966 tests in 178.68 seconds. Independent final re-review returned READY
  with no actionable findings.
- The protected memory database, secrets, and consumer repositories were not modified.

## Remaining Operator Boundary

Claude's model API currently returns an OAuth revocation error. Reauthentication is the only
remaining external account action; Yoke's Claude plugin and hook loading were already proven before
that request failed, so it is not an open repository delivery item.

<!-- mir:runtime-snapshot:begin -->
## Runtime Snapshot (Generated)

### Active Plan Items
- No open plan items.

### Working Tree
- Working tree dirty (inspect git status --short).
<!-- mir:runtime-snapshot:end -->
