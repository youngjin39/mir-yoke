---
adr: 88
title: "Active plugin component admission"
type: template-adr
created: 2026-09-03
status: accepted
amends: [adr-74, adr-75, adr-76, adr-83, adr-85]
amended_by: [adr-89, adr-90]
template_scope: mir-yoke
schema: docs/templates/_schema/adr.schema.json
---

# ADR-88 — Active Plugin Component Admission

## 1. Context

Mir Yoke publishes three dual-runtime plugins. Their common skill trees are passive instruction
content, while plugin hooks can execute commands and MCP servers can start processes or reach
network services. Treating those component classes as interchangeable would let an ordinary skill
update silently enlarge runtime authority.

The repository fleet also has project hooks with different protected paths, code paths, and family
identities. Those files are generated from each target's tracked configuration. Publishing one of
those complete hook sets as a common plugin would erase the target-specific enforcement boundary.
Claude Code and Codex support overlapping plugin component types, but their manifests and runtime
activation evidence are not byte-identical contracts.

An interrupted maintainer change attempted to enable the Yoke marketplace from this public checkout
by writing an absolute host path into generated `.claude/settings.json`. That path bypassed the
receipt-managed capability provider, was not portable, and mixed repository integration with host
installation.

## 2. Decision

### 2.1 Separate package classes

`mir-core`, `mir-code`, and `mir-content` remain skills-only packages. Their roots may contain only
the two runtime manifests and `skills/`. `config/capability-sources.json` schema 4 declares every
package's `package_kind` and admits `skills` plus the exact `skills-hooks` shape introduced by
ADR-90; the validator dispatches by that declared kind and has no generic active-component path.
Each skills-only runtime manifest is also constrained by
an explicit key allowlist, so permissions, runtime policy, and unknown future keys cannot enter by
omission from a deny-list. The shared manifest version must also match the safe version grammar
before any runtime installation command is issued.

`mir-lifecycle-hooks` is the only admitted active package. It uses the `skills-hooks` kind and may
contain only its two manifests, `skills/`, and the exact reviewed `hooks/` inventory. It is selected
by every default Profile because its sole `SessionStart` handler is target-independent and
read-only. MCP remains reserved. Agents, commands, apps, arbitrary scripts, permissions, runtime
policy, generic `hooks`, `mcp`, mixed, missing, and unknown kinds remain forbidden.

Both marketplace indexes must list exactly the configured plugin inventory and point to the
canonical in-provider local paths; the Claude index version must match the package manifest. The
manager allows only the reviewed runtime-specific marketplace fields, requires the canonical Codex
installation/authentication policy, validates those indexes before any runtime registration, and
binds both file digests into new project locks and active-provider receipts. New receipts also bind
all materialized plugin digests, including packages outside one consumer's selected profile. As
amended by ADR-89, the receipt keeps that complete inventory separate from the host-active union of
registered consumer selections used for rollback. Registry state records that active union and each
consumer's selected set independently; status and rollback require the schema-2 receipt and registry
to agree and require every active digest to match the validated materialized inventory. Before any
rollback registration command, the restored provider's complete
plugin inventory and marketplace paths, semantics, and receipt digests are revalidated. Recovery
therefore cannot expand host activation to an unselected package or register a restored marketplace
that normal status would reject. If either the restored lock or registry is schema 2, rollback also
requires a schema-2 receipt; changing only the receipt marker cannot enter the legacy path.

### 2.2 Preconditions and the first admitted active package

Admitting either reserved kind requires a later accepted decision and all of the following in the
same verified change:

1. A kind-specific validator checks canonical in-package paths and JSON structure, rejects
   symlinks, submodules, executable file modes, undeclared files, credential-bearing values, and
   target-relative writes.
2. Claude and Codex manifests expose the same normalized component identifiers and semantics.
   Runtime-native wire formats may differ, so parity is semantic rather than byte-identical.
3. The consumer's tracked capability source explicitly selects the separately named package and
   records the supported runtimes and expected component inventory.
4. Materialization remains commit-pinned and content-addressed. Registration requires a local,
   human-reviewed acknowledgement of the exact package digest. Any digest change invalidates the
   acknowledgement and fails closed until it is renewed. A generic `sync --apply` or marketplace
   enable action is not sufficient acknowledgement for active content.
5. Rollback restores the preceding provider, lock, registry, and runtime registration state. A new
   Claude/Codex session proves the installed digest and normalized component inventory.

ADR-90 satisfies these conditions only for the exact `skills-hooks` schema and the acknowledged
`mir-lifecycle-hooks` digest. The capability manager still rejects every other active shape.

### 2.3 Provider supply versus project integration

Plugin manifests are the runtime-native declaration sources. The tracked capability source is the
selection, package-class, and admission-policy source. Target-local `config/project-hooks.json` and
`.mcp.json` remain the project integration sources; their existing generator owns
`.claude/settings.json`, `.codex/hooks.json`, and `.codex/config.toml`.

A remote plugin never writes or merges those target files. Repository-specific blocking policy
stays local. Common, target-independent mechanics may later move into a dedicated hook package, but
the target's thin adapter must still supply and enforce its own Profile, protected paths, code
paths, and family identity. MCP is an optional interface boundary, not a replacement for plugin
provenance or project policy.

### 2.4 Host installation boundary

The public source checkout does not configure itself as a host marketplace. The capability manager
materializes a receipt-bound provider copy and runtime installation remains an explicit host
operation. Repository generation must not embed an absolute maintainer path or treat a dirty source
checkout as an installed provider.

Existing schema-1 locks remain readable, but status, attestation, and finalization revalidate their
active trees and marketplace semantics with the current kind-specific validators. The next explicit
sync writes schema-2 locks and receipts with required package kinds, marketplace digests, and the
all-materialized inventory. A schema-2 state missing any required binding fails closed; it cannot
be mistaken for a legacy record merely because fields were removed. A legacy digest therefore
cannot preserve a component that the current policy rejects.

## 3. Consequences

- Skill updates cannot silently acquire command execution or network-bearing components.
- Claude and Codex share one admitted skill inventory while preserving their native manifest forms.
- Project hooks keep target-specific policy and may call shared logic only after that logic has an
  independently reviewed active supply path.
- Adding or changing a hook or MCP package requires deliberate schema, validation,
  acknowledgement, rollback, and dual-runtime evidence work. This cost is intentional because
  those packages carry more authority than skills.
- The three role packages keep their existing behavior; every default Profile additionally selects
  the read-only lifecycle package.

## 4. Rejected Alternatives

- **Add `hooks/` or `.mcp.json` to the generic plugin root allowlist.** Rejected because content
  presence would become authority without a kind-specific review boundary.
- **Put common hooks or MCP in each existing skill package.** Rejected because a skill-only update
  could activate commands or network access.
- **Use one fleet hook configuration as the plugin source.** Rejected because fleet copies contain
  target-specific enforcement and have materially different content.
- **Use a local MCP server as the universal package manager.** Rejected because transport does not
  provide immutable package provenance, runtime-native discovery, or target policy ownership.
- **Track a maintainer checkout path in generated runtime settings.** Rejected because it is
  machine-specific and bypasses the receipt-managed provider.

## 5. Verification

- Configuration tests reject missing, reserved, mixed, and unknown package kinds and any local
  relaxation of the canonical component policy.
- Package tests prove the three role plugins are isolated skills-only trees and the fourth package
  has the exact dual-runtime hook schema, allowlisted manifest keys, and reviewed handler bytes.
- Marketplace tests reject remote redirects, duplicate or incomplete inventory, and version drift;
  sync binds the accepted marketplace files into both lock and active receipt.
- Receipt downgrade and rollback tests keep the all-materialized digest binding mandatory for new
  locks, bind the host-active union to schema-2 registry state, and restore only that validated
  union. A tampered restored marketplace prevents every rollback registration command.
- A four-state compatibility matrix keeps schema-1 lock/schema-1 receipt and schema-1 lock/schema-2
  receipt readable, accepts schema-2/schema-2 only with complete bindings, and rejects stripped or
  mixed-down schema-2 state.
- A schema-1 lock test proves a safe legacy tree remains readable while a matching legacy digest
  cannot admit content that the current validator rejects.
- Capability sync tests prove newly written locks record `package_kind: skills` without changing
  selected plugin or skill inventories. Existing commit-pinned schema-1 locks remain readable until
  an explicit schema-4 `update --apply` rewrites them from the newer capability source.
- Generated parity restores `.claude/settings.json` and `.codex/hooks.json` from tracked project
  sources, with no host-specific marketplace path.
