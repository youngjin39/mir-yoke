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
supporting skill. Repository-coupled hooks remain local. ADR-91 adds the separate, opt-in
`mir-mcp` stdio package. Marketplace availability does not select it; none of the default
Profiles includes it. Its owner acknowledgement and live B4 evidence remain separate gates.

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

### Optional MCP admission and receipts

Only `mir-mcp` at `plugins/mir-mcp` is admitted as `mcp-stdio`. Generic `mcp` stays reserved.
Before selecting it, the owner must review its computed tree SHA256 and record that exact value
in the consumer's own `<consumer-root>/config/capability-sources.json`, at
`active_package_digest_acknowledgements["mir-mcp"]`. When using `--config`, edit that explicit
consumer-owned configuration instead. The provider's configuration cannot renew this approval.
This source change supplies no acknowledgement.
Any changed byte invalidates an existing acknowledgement. Status reports local drift; it does
not claim that a previously running process has stopped.

To renew approval, first review the exact candidate checkout and compute its package digest
from a Yoke CLI environment:

```sh
uv run --no-sync python -c 'from pathlib import Path; from mir.core.capabilities.manager import _tree_digest; print(_tree_digest(Path("/absolute/reviewed-yoke/plugins/mir-mcp")))'
```

Manually set the consumer-local JSON entry above to that full 64-character digest, then run
`mir capability update --mcp --apply --project-root /absolute/consumer-root` (include
`--config /absolute/consumer-owned-config.json` when applicable). For first selection, use
`mir capability sync --mcp --apply` from the consumer root. Approval must precede the update;
a provider update that changes both bytes and its own approval fails until this local edit.
The active receipt's `mcp_digest_acknowledgements` preserves the prior state's approval for
rollback. Rollback checks it against the restored inventory and bytes before re-registration;
it does not renew approval for a different digest. Hook update behavior is unchanged.

Use `sync --mcp --apply` to select it explicitly and `sync --no-mcp --apply` to remove that
consumer's selection. Omitting either option retains its lock selection. A peer consumer's
selection keeps the host registration active. Selection is host-wide at user scope, so sessions
in other repositories can see these tools. No consumer runtime settings or policy are merged.
Native Windows activation is refused; macOS, Linux and WSL require independent runtime evidence.

From each fresh runtime session outside the provider checkout, pass `attest --mcp-evidence
/absolute/receipt.json` alongside the observed skills/hooks. The JSON object must be keyed by
`mir-mcp`; each observation has these fields:

| Field | Required observation |
| --- | --- |
| `installed_sha256`, `server` | Exact installed tree digest and `mir-mcp`. |
| `client`, `client_version`, `session_id`, `session_cwd` | Runtime key, observed version, current exported session ID, absolute session working directory outside the provider. |
| `platform`, `interpreter` | `macos`, `linux` or `wsl`; `{executable,version}` for an absolute Python path and Python 3.9+. |
| `launcher` | `{command:"python3",args:["-I","-B","-u","<installed-root>/mir_mcp.py"],env:{}}`. |
| `protocol_version` | Observed `2026-07-28` or `2025-11-25`. |
| `tools` | Ordered `{name,raw_name}` entries for `ontology_validate`, `ontology_lookup`, `ontology_impact`, `handoff_pins`, `relations_query`; preserve raw host-prefixed names. |
| `safe_calls` | Exactly those five names, each with `{arguments,result_sha256,is_error:false,ok:true}` from a bounded successful call. Copy `ok` from the structured result; an MCP `isError` response is not successful. Arguments must satisfy that tool's closed input schema, including required fields, types and bounds, and the absolute `target_root`. |
| `tools_list` | `{sha256,bytes,tokens,tokenizer,initial_tokens,after_call_tokens,deferred_loading}` for the complete deterministically serialized tool-list result. Bytes must be at most 16384 and tokens at most 6000; record the accounting method and both measured loads. |

`deferred_loading` is `observed` or `eager`; recording eager loading does not claim deferred
loading or savings. Missing counters cannot pass B4 evidence. Both runtime receipts must agree
on the serialized tool-list SHA256 and byte count. These are operator observations, not values
inferred from manifests or skill discovery. Finalization revalidates installed bytes, the complete
materialized inventory, acknowledgement, both receipts and schema parity. Source tests alone
do not establish B4 or runtime readiness.

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
