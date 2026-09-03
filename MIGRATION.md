# Migration Guide

## Unreleased capability-source schema 4

The tracked `config/capability-sources.json` now uses `schema_version: 4`, retaining the explicit
`package_kind: skills` for the three role plugins and admitting the exact `skills-hooks` shape for
`mir-lifecycle-hooks`. The canonical `plugin_component_policy` and exact active-package digest
acknowledgement prevent other executable shapes from entering through the new kind.
It adds a command allowlist that maps each Claude command source to the existing Codex plugin skill
that absorbs the same workflow, plus explicit target-local hook and MCP integration records.
Schema-1 and schema-2 capability sources remain readable and select no managed commands or active
hook package. Copy the schema-4 fields from the current template before expecting command or hook
delivery from a newer capability manager.
The existing plugin and skill inventories do not change.
Schema-1 locks remain readable, but their active provider is revalidated under the current
skills-only manifest and marketplace rules. After adopting the schema-4 source, explicit
`update --apply` adds package kinds and
marketplace digests to a schema-2 lock and receipt. Schema-2 records require those bindings and the
receipt's complete materialized-plugin inventory. Schema-2 provider registry state separately binds
the selected installed set used for rollback.

Do not translate a local enforcement hook or MCP configuration into a plugin entry.
`mir-lifecycle-hooks` contains only the admitted target-independent `SessionStart` reminder. Keep
repository-coupled registrations local unless a later decision introduces and verifies an adapter.
No MCP server is registered or implemented, so do not publish an empty MCP plugin from the inert
`.mcp.json.example`.

The first explicit schema-4 `update --apply` copies and digest-locks selected
`.claude/commands/*.md` alongside
selected agent sources. A project-owned command that differs from its prior lock or the exact
incoming source is not overwritten. Codex receives no generated command file; it uses the mapped
namespaced plugin skill.

Agents and Claude commands can alternatively be installed outside every repository:

```bash
python3 scripts/install_user_runtime_agents.py \
  --claude-home /absolute/claude-config-root \
  --codex-home /absolute/codex-home
```

The first run is a dry run. Add `--apply` only after reviewing the planned paths. The installer
refuses symlinked homes and unmanaged divergence and writes a SHA-256 receipt. Project-local agent
and command files continue to take precedence.

Schema-4 readiness requires current schema-2 state evidence. `sync` remains pinned to the existing
lock and reports that an update is required when that old commit lacks a newly selected package.
If multiple repositories register the
same provider commit, the host-active plugin set is their union; each project lock remains its own
subset. A failed apply restores that prior union and removes candidate-only plugins.

## 0.9.0 from 0.8.x

### Product boundary

- `starter/` remains the only fixed consumer payload and the four-file compatibility layer.
- New empty repositories use the standard `recipes/project-agent-kit/` guidance flow, which now
  requires a bounded project-owned common harness and SQLite+FTS5 memory baseline.
- Common plugins remain optional host capabilities and are portable outside the Mir Yoke checkout.
- The 0.9 package restores the public v0.8 `mir` command surface as an optional installed operator
  tool. It is not copied into Project Agent Kit targets and grants no authority until explicitly
  invoked for the user's named scope.
- ADR-82 product-plane and `yoke` composition sources remain superseded. Preserved files live only
  under `reference-templates/advanced-composition/`; no `yoke` console entrypoint is active.

### Existing 0.8 adopters

Existing users may install v0.9 to retain the public v0.8 `mir` command contract. Mir Yoke performs
no automatic migration, state deletion, repository rewrite, target update, or implicit command.
Adopt the Project Agent Kit or a changed local contract only through an owner-reviewed repository
change.

### New projects

Open one empty target and use the short prompt from `README.md`. The agent creates and verifies a
project-owned common harness and memory foundation, one initial commit, and then stops before
development planning. Do not vendor the Mir CLI source into the target.

### Rollback

Discard an uncommitted Project Agent Kit adaptation in the target or restore the target's own prior
commit. For an explicitly invoked CLI transaction, use that command's recorded rollback/recovery
contract. Installing the CLI does not itself mutate a target.

Current version: `0.9.0`. See `CHANGELOG.md` for release details.
