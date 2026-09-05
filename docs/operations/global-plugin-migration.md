---
title: Global Plugin Migration for Existing Repositories
keywords: [plugin, capability, migration, collision, rollback]
created: 2026-08-07
---

# Global Plugin Migration for Existing Repositories

Use this runbook before the first Mir global-plugin activation on a user account that already has
repositories with `.claude/skills` or `.agents/skills`. It implements ADR-75. It never authorizes a
cross-repository write, deletion, commit, or push.

The published packages group common work by role (`mir-core`, `mir-code`, and `mir-content`). Do not
copy their common skill bodies back into repositories. ADR-90's `mir-lifecycle-hooks` is the fourth
current package and contains only one acknowledged, read-only `SessionStart` reminder plus its
supporting skill. Repository-coupled hooks remain local. The current MCP inventory is empty, so
there is no `mir-mcp` package to install.

This runbook describes the primary macOS host flow. Linux and WSL are separate compatibility lanes
with separate user homes and receipts. Native Windows must not execute these commands as a claimed
ready-state installation; use `docs/operations/windows-wsl-reference-adaptation.md` so the target's
AI agent can select and adapt the required structure without changing the macOS provider.

## 1. Establish the host inventory

Start from an operator-owned registry of repositories that may be opened by the same Claude or
Codex user. For every root, run the Yoke CLI environment's read-only check:

```bash
uv run --project /absolute/path/to/mir-yoke mir capability status \
  --project-root /absolute/repository --json
```

This command may inspect a global-only repository that has no Yoke configuration, capability lock,
or copied provider files. It reports host provider health separately from consumer enrollment, which
is `not-enrolled` until the repository owner explicitly applies local integration. Read-only status
does not calculate a project-tree change diff; its `change_evidence` records that this observation is
not applicable to a read-only operation. An explicitly supplied malformed `--config` still fails
closed. A consumer's own `mir` command need not expose the Yoke capability subcommand.

Record all paths in `collisions`. Also record whether `.claude/skills` or `.agents/skills` has
uncommitted changes. Do not activate a provider until every active root has been inspected. A
repository that is absent from the inventory is an unresolved host risk.

The collision check is intentionally slug-based. Do not automate a content comparison and infer
that a matching directory is safe to delete.

## 2. Resolve each collision locally

Choose exactly one disposition in the affected repository:

| Disposition | Use when | Required local outcome |
| --- | --- | --- |
| `adopt_global` | The raw skill is common capability that the pinned plugin should own. | Preserve a recoverable baseline, remove both runtime mirrors through the repository's canonical generation path, mark legacy registry entries `external`/`external` or remove them when runtime discovery is authoritative, and prove no stale references remain. |
| `rename_local` | The raw skill contains repository-specific behavior that must remain. | Rename it to a repository-unique slug, update instructions/agents/generators, regenerate mirrors, and run the repository's smallest skill checks. |
| `local_authority_exception` | The repository is the authoritative source or cannot yet be reconciled safely. | Keep the provider disabled for the host. Record the blocker; do not claim the repository or host ready. |

Perform this work through each repository's own agent and authority contract. Re-run `status` until
`collisions` is empty for every root and all selected skill surfaces are clean.

Do not restore `.claude/skills/<slug>` or `.agents/skills/<slug>` merely because a legacy registry
verifier still expects a local path. Update the repository's canonical agent-management registry
so plugin-supplied skills use `status: external` and `source_path: external`, or remove those rows
when the registry schema treats runtime discovery as authoritative. Regenerate derivatives and run
the repository-local verifier, such as `uv run python scripts/verify_repo_agent_management.py`,
before claiming the migration complete.

## 3. Activate one pinned provider

Select one clean canary repository whose profile represents the intended plugin pack:

```bash
uv run mir capability check --project-root /absolute/canary --json
uv run mir capability sync --project-root /absolute/canary --apply --json
```

`check` is remote but read-only. `sync --apply` pins the exact Git commit, materializes one provider
under `MIR_CAPABILITY_HOME`, registers the canary, and installs the selected plugins through the
supported host CLIs at user scope. Consumer repositories must contain no project- or local-scope
`mir-yoke` plugin registration and no `enabledPlugins` or `extraKnownMarketplaces` override for
these packages. Remove such legacy entries only after confirming the user-scope provider is active;
otherwise a project entry can override central activation. Schema-4 sync also copies the selected
Claude agent and command sources into the canary, records their digests, and regenerates Codex
agents. A differing project-owned file
blocks overwrite; Codex command intent comes from the mapped plugin skill rather than a copied
command file. Codex installation evidence is valid only when the `mir-yoke` marketplace and
enabled plugin entries persist in `CODEX_HOME/config.toml` and the installed cache trees match the
lock. The marketplace source tree alone is not installation evidence. Stop if a runtime listed in
`policy.activation_required_runtimes` cannot provide installation evidence. The current policy
requires both Claude and Codex.

Explicit `--capability-home` and `MIR_CAPABILITY_HOME` remain authoritative. If neither is present
in a bridge session with a temporary `HOME`, the manager may recover the external provider only
from a local `mir-yoke` Codex marketplace whose source and active receipt agree on the configured
Git source and materialized root. Persist the storage environment on hosts without that receipt.

## 4. Restart and prove activation

Start new Claude and Codex sessions. Review the hook trust prompt, inspect each runtime-provided
catalog rather than the provider files, and attest every selected namespaced skill. Repeat
`--observed-skill` for each name actually present,
for example:

```bash
uv run mir capability attest --project-root /absolute/canary \
  --runtime codex-cli-desktop \
  --observed-skill mir-core:design --observed-skill mir-core:spec-architect \
  --observed-hook mir-lifecycle-hooks:SessionStart \
  --apply --json
```

Claude operators run the same command from a restarted Claude session with
`--runtime claude-code`; both receipts are required under the current policy. Each command
requires its current runtime to export the session ID and has no operator-supplied session-ID
override. Skills and hooks are operator observations: do not derive them from files or from
`plugin list`. Record `mir-lifecycle-hooks:SessionStart` only after the current hook definition was
reviewed, trusted, and its fixed continuity output was observed in that restarted runtime. Install
and enable state alone cannot satisfy this gate.

After the required Codex attestation succeeds, run:

```bash
uv run mir capability finalize --project-root /absolute/canary \
  --apply --after-restart --json
uv run mir capability status --project-root /absolute/canary --json
```

Ready means every runtime named by `policy.activation_required_runtimes` exposes exactly one
enabled plugin per selected name, Claude reports that copy at `scope: user`, every required installed
tree matches the lock digest, the required runtime has complete skill and hook discovery receipts,
and the canary has no standalone collisions.
Register each additional clean repository with `sync --apply`; the one-version consumer registry
refuses a divergent digest.

## 5. Optional user-level agents and commands

When the operator wants the reviewed common agents available from every working directory without
editing consumer repositories, use the separate user-runtime installer. Supply both runtime homes
explicitly because bridge sessions may not share one `HOME`:

```bash
python3 scripts/install_user_runtime_agents.py \
  --claude-home /absolute/claude-config-root \
  --codex-home /absolute/codex-home
```

Review the dry-run JSON, then repeat with `--apply`. The installer copies only the union of tracked
Profile selections, refuses symlinked paths and unmanaged divergence, removes only unchanged files
that its prior receipt still owns, and records source and target SHA-256 values. Claude receives
agents and commands; Codex receives generated agents and uses the installed plugin skills for
command intent. Yoke-only allowlist entries stay local, and project-local files take precedence.
The capability source records those repository-only agents under `agents.provider_local`, so a
provider update preserves them without adding them to the user-runtime union.

## 6. Rollback

If runtime proof fails, keep the project receipt incomplete. Disable or uninstall the Mir plugins
with the same host runtime managers that installed them, and verify they no longer appear enabled.
Only then restore an archived raw skill copy if needed. Never leave a provider and a same-name raw
skill active together. Preserve `.mir/capability-lock.json`, the provider receipts, and command
output as diagnostic evidence until the failure is understood.
