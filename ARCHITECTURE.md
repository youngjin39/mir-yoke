# Mir Yoke Product Plane Architecture

## Product boundary

Mir Yoke is a public, template-backed, agent-guided local project-harness platform and reference
implementation, not a universal installer. It has no provider runtime and no standing authority over consumer
repositories. `starter/` is the only required and default consumer payload. Capability packs are
explicit opt-ins with independent support levels.

The required payload is four Markdown files. It starts no agent, service, hook, target scan,
scheduler, or background process and does not require a CLI, plugin, memory database, spec system,
sub-agent, receipt, or platform-specific runtime.

## Product planes

```text
Source Plane -> Distribution Plane -> explicit plan -> Project Plane
                                             \-> Local Plane receipts and provider pins
```

- **Source Plane** contains maintainer source, the preserved platform, tests, schemas, packs,
  profiles, release tooling, and decisions.
- **Distribution Plane** contains ignored deterministic core and pack archives plus checksums,
  manifest, and provenance.
- **Project Plane** contains consumer-owned contracts, optional tracked policy, and selected pack
  payloads.
- **Local Plane** contains ignored receipts, caches, memory databases, and content-addressed
  provider installations.

`config/product-planes.json` is the machine-readable boundary. Asset classification, support level,
and execution state are separate axes: a retained maintainer hook can be active in this checkout
without being part of the default consumer payload.

## Supported flow

1. The active AI agent inspects the target repository and existing instructions without mutation.
2. It identifies local purpose, paths, authority, safety boundaries, and verification commands.
3. It adapts, merges, renames, or skips each starter file without overwriting repository-owned work.
4. It runs the target repository's own smallest relevant checks and reviews the final diff.

Manual adoption remains contextual composition. Automated composition uses an explicit read-only
plan followed by a separate transactional apply. Both paths preserve target ownership.

## Modules

- **Starter contract** — `starter/HARNESS.md` contains the generic operating contract.
- **Runtime bridges** — `starter/CLAUDE.md` and generated `starter/AGENTS.md` route two common agent
  clients to that one contract.
- **Adoption guide** — `starter/README.md` and `BOOTSTRAP.md` explain preservation-first adaptation.
- **Pack catalog** — `packs/*/pack.json` declares source, adoption assets, compatibility, state, and
  pack-scoped verification.
- **Profiles** — `profiles/*.toml` provides non-mandatory composition defaults and recommendations.
- **Distribution** — `src/mir/core/distribution/` builds artifacts, installs immutable providers,
  and implements plan/apply without overwrites.
- **Preserved platform** — existing source, tools, plugins, hooks, specs, and tests remain the source
  and regression evidence for optional packs.

Dependencies point from pack manifests to preserved sources and from profiles to packs. Optional
machinery cannot become a starter prerequisite without a new explicit support-boundary decision.

## Data and deployment

The core stores no runtime data and has no deployment topology. Distribution artifacts are
deterministic archives identified by SHA-256. A provider installation lives at
`providers/<content-digest>`; there is no host-global active alias. Project policy is tracked only
when selected, while `.mir/local-state.json`, `.mir/yoke-receipts/`, and databases remain local.

## Verification

`tests/test_minimal_starter.py` pins the four-file boundary. Product-plane, distribution, composer,
safety, classification, semantic adapter, and release-readiness tests cover optional behavior.
Existing platform regression checks remain available and are not replaced by the core gate.
