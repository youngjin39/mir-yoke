---
adr: 89
title: "Dual-runtime capability management"
type: template-adr
created: 2026-09-03
status: accepted
amends: [adr-74, adr-75, adr-85, adr-88]
amended_by: [adr-90]
template_scope: mir-yoke
schema: docs/templates/_schema/adr.schema.json
---

# ADR-89 — Dual-Runtime Capability Management

## 1. Context

Mir Yoke must provide common capabilities to Claude Code and Codex in repositories other than the
provider checkout. The managed surface includes agents, skills, hooks, MCP servers, and commands,
but those runtimes do not expose one identical plugin schema. Treating every surface as a generic
plugin component would either invent unsupported Codex commands and agents or erase a target's
protected paths, code paths, family identity, and trust decisions.

ADR-88 already separates passive skill packages from active hook and MCP packages. This decision
retains that security boundary and defines how Yoke centrally manages all five surface classes
without claiming that they share one wire format.

## 2. Decision

### 2.1 One management contract, runtime-native delivery

`config/capability-sources.json` schema 3 is the tracked capability selection and delivery contract.
It keeps plugin, profile, and agent inventories and adds the managed command map plus explicit
project-integration records for hooks and MCP servers.

| Surface | Yoke source | Claude delivery | Codex delivery |
|---|---|---|---|
| Skills | `plugins/*/skills/*` | namespaced plugin skill | the same namespaced plugin skill |
| Agents | `.claude/agents/*.md` | commit-pinned project file | generated `.codex/agents/*.toml` |
| Commands | `.claude/commands/*.md` | commit-pinned project command | mapped, already-absorbing plugin skill |
| Hooks | `config/project-hooks.json` plus project hook code | generated `.claude/settings.json` | generated `.codex/hooks.json` |
| MCP servers | target-owned `.mcp.json`; `.mcp.json.example` is inert guidance | opt-in native configuration | generated `.codex/config.toml` entry |

The capability manager copies and locks only the selected agent and command sources. It refuses to
overwrite a file that differs from its prior lock or from the exact incoming source on first sync.
Every command entry names the existing Codex plugin skill that absorbs the same workflow intent.
Yoke does not create duplicate Codex command wrappers or raw local skill copies.

The separate `scripts/install_user_runtime_agents.py` path is available when an operator wants the
reviewed common agents and Claude commands in every working directory without consumer writes. It
requires explicit Claude and Codex homes, defaults to dry-run, copies only the union selected by
configured Profiles, refuses unmanaged divergence, and records exact file digests. Unselected
Yoke-only allowlist entries are not installed. Codex receives generated agents and
continues to use plugin skills for command intent. Project-local files retain precedence.

### 2.2 Cross-repository plugin discovery

Skill plugins remain host-installed, namespaced, and independent of a consumer working directory.
Activation is exclusively user-scoped: consumer repositories carry neither Claude project/local
plugin records nor `enabledPlugins`/`extraKnownMarketplaces` overrides for Mir Yoke. Runtime
evidence must reject a Claude package reported at any scope other than `user`; multiple matching
records already fail the exact-one check. Codex uses its host configuration because it has no
repository-scoped plugin installation mode.
The real-CLI verifier installs the configured Yoke marketplace into isolated Claude and Codex homes,
removes access to the provider checkout, and checks two distinct consumer working directories. Each
runtime must report one enabled installed copy of every configured plugin, the installed tree digest
must match the provider digest, and the installed skill inventory must match the capability source.

This is host discovery evidence, not target authority. A new runtime session is still required when
the runtime's plugin loader only refreshes its catalog at session start.

### 2.3 Active-component boundary is kind-specific

ADR-90 admits the separately named `mir-lifecycle-hooks` package under schema 4. Its exact,
read-only `SessionStart` component is global and selected by every Profile. Commands remain
forbidden in all plugins, and the three role skill packages remain skills-only.

Project-local hook records still own repository-coupled enforcement, generation, and state. A
future hook with target access or any MCP server must satisfy a new ADR-88 admission review. A
remote package must not write or merge target configuration. A target adapter continues to own
repository identity, protected paths, code paths, endpoints, credentials, trust, and family policy.

### 2.4 Compatibility

> **2026-09-06 amendment:** Section 2.5 supersedes the universal same-commit and peer-lock status
> rules below for schema-3 registry state. The retained schema-1/2 wording describes the legacy
> migration proof that must succeed before a registry can enter schema 3.

Capability-source schemas 1 and 2 remain readable and yield no managed commands or active hook
package. The first explicit `update --apply` against schema 4 writes command digests, Codex skill
mappings, and the selected hook package into the existing schema-2 project lock format. A pinned
`sync` reports that an update is required when its old commit lacks a newly selected package.
Schema-4 status requires schema-2 lock, receipt, and registry evidence, so changing all three state
markers to legacy schema 1 cannot bypass current digest bindings. Genuine schema-1 and schema-2
capability sources retain their skills-only compatibility paths.

For legacy schema-1/2 registry state, the host-global active plugin set is the union of every
registered consumer's selected set at the same commit. Each project lock retains only that project's
subset. Apply removes configured plugins
outside the union; rollback restores the prior union and removes candidate-only plugins. Local file
and runtime state is also restored for catchable process interruptions before the interruption is
re-raised.

Legacy status recomputes that union from every validated registry consumer and requires exact agreement
between the registry, active receipt, materialized plugin digests, and the current consumer lock.
Codex persistence verification also compares the complete enabled `mir-yoke` configuration set,
not only plugins reported by the CLI. Project lock reads and writes reject a symlinked or non-
directory `.mir` boundary. Apply, attestation writes, and activation finalization share one guard;
each operation reads and revalidates state only after acquiring it.

Legacy rollback uses the same complete consumer-union validation before issuing any restoration command;
an unverifiable prior receipt produces an explicitly incomplete rollback instead of expanding host
activation. Required project integrations and generated output roots reject symlinked ancestors
immediately before derivative generation, and Codex cache evidence rejects a symlinked component or
resolved path outside the configured Codex home.

Schema-2 union membership is not self-asserted by the registry. Every non-pending consumer key must
resolve to the same canonical, existing, symlink-free project path and its regular local capability
lock must match the registered commit and exact plugin digests. Apply may substitute only its own
pending entry before the new lock is published. Generated and cleanup paths are checked at their
actual nested locations, and Codex home containment is compared with the fixed canonical path
captured during manager initialization so a later ancestor replacement cannot redefine the root.

For a schema-3 or schema-4 source, guarded enrollment adds a random 256-bit consumer binding to the project
lock, registry entry, and a mode-0600 capability-home ledger. Consumer union validation requires all
three copies plus the exact manager-written source and plugin metadata. Project and Codex home roots
also retain their initial device and inode identities. A replaced project root cannot receive
managed writes, deletion, generator execution, or lock rollback, and a replaced Codex home cannot
provide installation or cache evidence. These checks detect stale or independently forged state;
they do not claim resistance to a same-user attacker who can rewrite every control-plane file.

A new binding is issued only for a new consumer or a verified schema-1 consumer whose real local
lock exactly matches its registry entry. Multi-consumer schema-1 registries migrate one consumer at
a time: unbound peers remain valid only while their canonical legacy locks continue to match.
Partial, invented, or mismatched state fails before runtime commands; a missing ledger cannot
silently re-enroll a current-schema consumer. Every ledger read requires a regular non-symlink file
with exact mode 0600. Because this is a dual-runtime contract, both `claude-code` and
`codex-cli-desktop` are required for installation evidence, discovery attestation, finalization, and
READY.

Schema-3 and schema-4 configuration accepts exactly those two required runtimes in canonical order; a local
policy edit cannot reduce the gate to one CLI. The capability-home root is also anchored by canonical
path plus device and inode when created or adopted. Guard creation, provider state reads and writes,
runtime commands, and rollback all revalidate that identity so replacing the state root cannot
redirect global control files.

### 2.5 Provider health and pending local integration

The host provider has one active commit and digest union. Consumer-local agent, command, lock, and
integration state is separate. A global-only `status` uses the Yoke CLI's receipt-bound active
provider configuration when present, or its shipped compatibility configuration for an older active
provider. It validates the active receipt source, materialized root, marketplaces, and package trees
without traversing or hashing the whole inspected repository. Only bounded skill roots are inspected
for naming collisions. Provider health can therefore be healthy while that repository reports
`not-enrolled`.

Schema-3 registry state permits a provider update to activate a candidate after validating the
registered selection union and current runtime registration. It writes only the requesting
consumer's local files and lock. Other registered consumers retain their files and old local lock
commit as `pending-local-update`; their later explicit update uses the active receipt-bound
candidate commit, not a newer remote revision. A legacy registry moves to schema 3 only after every
legacy peer has passed its existing lock and binding validation. Missing or renamed peer-selected
plugin names remain a visible fail-closed incompatibility.

## 3. Consequences

- Yoke is the central source for the five managed surface classes without becoming a universal
  runtime or gaining standing authority over consumers.
- Claude commands can be updated through the same explicit, commit-pinned sync and divergence guard
  used by agent sources; Codex reaches the equivalent intent through the installed common skill.
- Agents and Claude commands can also be installed at user scope without modifying consumer
  repositories; their receipt remains separate from plugin activation.
- Plugin skills are proven usable outside the provider checkout for both CLIs.
- Claude activation evidence proves the single matching package is user-scoped, so a legacy
  project/local record cannot satisfy readiness.
- Hook and MCP ownership is visible. The exact read-only hook package is admitted; every other
  executable or network-bearing plugin shape remains fail-closed until separately designed and
  acknowledged.

## 4. Rejected Alternatives

- **One plugin containing agents, skills, commands, hooks, and MCP.** Rejected because runtime
  component support differs and target policy would be hidden inside a global package.
- **Duplicate each Claude command as a Codex wrapper skill.** Rejected because the existing design
  and verify skills already absorb those workflows; duplicates increase discovery and context cost.
- **Use a local MCP server as the package manager.** Rejected because transport does not replace
  commit provenance, content digests, runtime-native registration, or target policy ownership.
- **Copy target hook configurations from Yoke during capability sync.** Rejected because repository
  enforcement and trust are target-owned and cannot be inferred from a profile name.

## 5. Verification

- Configuration tests validate schema-3 command paths, skill mappings, profile selection, target-
  local integration constants, and schema-2 compatibility.
- Capability tests prove commands are reported, copied, digest-locked, status-checked, rollback-
  restored, and protected from divergent or symlinked overwrite.
- Multi-consumer tests prove host activation is the union of registered selections, profile rollback
  removes candidate-only plugins, required hook projections cannot be omitted, and schema markers
  cannot be downgraded together under a schema-3 source.
- State-integrity tests prove registry/receipt union inflation, hidden Codex configuration,
  symlinked `.mir` lock redirection, and stale attestation or finalization writes fail closed.
- Rollback and path-boundary tests prove an inflated prior union cannot reach restoration commands,
  derivative roots cannot be redirected during apply, and Codex cache evidence stays inside a
  symlink-free runtime home path.
- Consumer-authenticity and time-of-check tests prove invented consumer paths cannot enlarge apply,
  status, or rollback state; nested cleanup parents cannot redirect deletion; and a later Codex-home
  ancestor swap cannot move the verification boundary.
- Binding and root-identity tests prove a structurally complete invented lock without an enrolled
  ledger value is rejected and rename-and-recreate replacement roots receive no managed mutation.
- Enrollment-state tests prove missing, mismatched, symlinked, or over-permissive ledgers cannot be
  repaired implicitly, and dual-runtime tests prove neither CLI can reach READY alone.
- Policy and provider-root tests prove a singleton or reordered runtime gate is invalid and a
  replaced capability home cannot receive a guard, state mutation, rollback, or runtime command.
- The Codex derivative verifier checks all five managed surfaces, exact command inventory and skill
  absorption, agent projections, hook targets, and the inactive MCP reference path.
- The real-CLI probe checks configured plugin and skill inventories from two consumer directories in
  isolated Claude and Codex homes after the provider checkout becomes unavailable.

ADR-90 records the operator's role-plugin rule, admits the bounded global continuity hook package,
and preserves the target-adapter boundary for repository-coupled hooks. It also records that no MCP
server is registered or implemented by Yoke.
