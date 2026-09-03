---
adr: 90
title: "Role plugins and common hook architecture"
type: template-adr
created: 2026-09-03
status: accepted
amends: [adr-88, adr-89]
template_scope: mir-yoke
schema: docs/templates/_schema/adr.schema.json
---

# ADR-90 — Role Plugins and Common Hook Architecture

## 1. Context

The operator's current intent is authoritative for this work:

> Common working methods that were previously copied into each repository are grouped into
> role-oriented plugins.

Yoke already publishes the `mir-core`, `mir-code`, and `mir-content` role packages and proves that
Claude Code and Codex discover their namespaced skills outside the provider checkout. Agents,
commands, hooks, and MCP configuration still use runtime-native projections because the two hosts
do not expose the same plugin component surface.

The desired next step is one common hook implementation for every repository rather than a fleet
of diverging generated hook bodies. That objective cannot erase repository-owned Profile data,
protected paths, code paths, family identity, trust decisions, or writes to session state.

The installed Codex CLI is `0.152.1`. Its ordinary project hooks are stable and current official
OpenAI plugin documentation includes lifecycle hooks. `codex features list` reports the former
`plugin_hooks` feature flag as removed while the general `hooks` and `plugins` features are stable.
An isolated real-CLI probe successfully installed and enabled a plugin whose manifest declares
`hooks`. The removed flag therefore does not mean that plugin hooks were removed; the capability
has moved out of that former experimental flag. A bundled local `plugin-creator` validator that
rejects the field is stale relative to both the current documentation and runtime.

Neither host currently has an MCP server registered: `codex mcp list --json` returns an empty array
and `claude mcp list` reports no configured servers. Yoke implements no MCP server. Its
`.mcp.json.example` is only inactive guidance for opting into the external `codex mcp-server`
stdio endpoint.

## 2. Decision

### 2.1 Role-oriented plugins are the common-workflow source

Yoke packages reusable workflow guidance by role and concern. A repository Profile selects a
combination of the core, code, and content packages instead of receiving copied common skill
directories. The package namespace is part of the public contract. Repository-unique instructions,
agents, policy data, and generated runtime projections remain owned by that repository.

Adding another workflow does not justify a new package by itself. It belongs in the smallest
existing role package whose scope and trigger contract fully contain it. A separately named package
is required when the component changes runtime authority, as hooks and MCP servers do.

### 2.2 One global, read-only lifecycle hook package

`mir-lifecycle-hooks` is a separately named fourth package and is selected by every Yoke Profile.
It contains one shared `SessionStart` hook and the supporting `runtime-continuity` skill. The same
Both hosts auto-discover the standard `hooks/hooks.json`, so neither manifest repeats that path.
The non-executable Python handler emits
one fixed, bounded continuity reminder and performs no file, environment, network, subprocess, or
repository access.

This first common hook deliberately has no target adapter because it performs no target operation.
Repository adapters remain required for any future hook that reads or writes project state. Such an
adapter continues to own the Profile, protected and code paths, deny rules, family identity,
session paths, and trust state. Existing project hooks remain independent and may run alongside the
global reminder because their semantics do not overlap. The plugin never writes or merges
`.claude/settings.json`, `.codex/hooks.json`, or target policy files.

### 2.3 Schema-4 active-package admission

Capability-source schema 4 admits exactly `skills` and the reviewed `skills-hooks` package kind.
The latter is not a generic executable-content escape hatch. Its validator requires the exact root,
manifest keys, shared hook file, `SessionStart` event, command, timeout, handler bytes, file modes,
and `hooks/` inventory. It rejects symlinks, executable modes, undeclared hook files, semantic
drift, and any handler other than the reviewed read-only implementation.

The tracked `active_package_digest_acknowledgements` map must cover every active hook package and
match its exact computed tree digest before any runtime registration command runs. A changed byte
therefore requires a new reviewed acknowledgement. Marketplace indexes, project locks, active
receipts, rollback, and dual-runtime activation evidence retain ADR-88 and ADR-89's existing digest
and state-integrity controls. Installation and enablement do not prove hook trust or execution:
finalization requires a fresh-session operator observation of
`mir-lifecycle-hooks:SessionStart` from both runtimes. MCP remains reserved and rejected.

### 2.4 No empty MCP plugin

Yoke will not publish `mir-mcp` until a concrete Yoke-owned MCP server or an explicit external
server dependency and use case exists. A future package is opt-in and non-default. It requires a
dedicated MCP validator, exact endpoint/tool inventory, credential-free manifests, semantic
dual-runtime registration, digest acknowledgement, rollback, and real client evidence.

The current `.mcp.json.example` remains reference-only. The existence and successful handshake of
the Codex executable's `mcp-server` subcommand does not mean that Yoke owns, registers, or runs an
MCP server.

### 2.5 Upstream Codex requests

Codex custom agents remain project `.codex/agents/*.toml` resources and cannot be contributed by a
plugin. Yoke therefore manages agents separately as generated project files or explicitly installed
user-level files. The existing upstream request is `openai/codex#18308`, “Add Agents to Plugins
System.” Yoke
will add its concrete multi-repository use case there instead of creating a duplicate issue when a
GitHub-authenticated route is available.

Plugin command aliases remain a separate request because a command name, discoverability contract,
and explicit invocation UX are not the same thing as an implicitly selected skill. The exact
comment and issue drafts live in
`docs/operations/codex-plugin-agents-commands-feature-request.md`.

## 3. Consequences

- Common skills and the target-independent continuity reminder travel as four global role packages
  and no longer need repository copies.
- The admitted hook package has no repository authority. Project-coupled enforcement and state
  changes remain local and require a thin target adapter.
- Every active-package byte change invalidates the tracked acknowledgement and blocks registration.
- No MCP package implies no MCP server. Status and documentation must continue to say zero until a
  real server is selected, implemented, registered, and verified.
- Agents and command sources continue through ADR-89's generated project projections while the
  upstream feature gaps remain open.

## 4. Rejected Alternatives

- **Allow arbitrary hook packages.** Rejected because runtime parsing support does not replace a
  closed component schema, digest acknowledgement, rollback, or dual-runtime evidence.
- **Put target hook scripts in one global package unchanged.** Rejected because those scripts embed
  target paths, policy, and writes that differ by repository.
- **Register both local and plugin hooks during migration.** Rejected because duplicate lifecycle
  execution can write the same state twice and produce inconsistent enforcement.
- **Publish an MCP manifest around `.mcp.json.example`.** Rejected because the example describes an
  external optional endpoint and is not a Yoke MCP server implementation.
- **Open a second agent-plugin issue.** Rejected because the upstream request already exists and a
  concrete interoperability comment adds more signal than a duplicate.

## 5. Verification

- Runtime inventory records Codex `0.152.1` with stable hooks and plugins. Isolated Claude and Codex
  installations accept and enable the same four-package marketplace, including the hook package;
  the old feature flag alone is not used as a capability verdict.
- Package tests pin the exact hook schema and handler, reject undeclared hook files, and prove the
  handler emits only the fixed 94-byte stdout line, including its trailing newline.
- Capability tests require the exact acknowledged digest before runtime registration and preserve
  rollback and dual-runtime state evidence. Skill-only discovery cannot finalize an active hook
  package; both runtime receipts must include the observed hook identifier from a fresh session.
- Host MCP inventory is empty for both CLIs and the repository contains no active `.mcp.json` or
  Yoke MCP server entry point.
- Existing role-plugin real-CLI evidence proves the three skill packages install from one Yoke
  marketplace and are discovered from two independent consumer directories.
- Decision and documentation tests pin this ADR as the current authority and prevent a hook or MCP
  package from being claimed before its runtime and admission gates exist.
