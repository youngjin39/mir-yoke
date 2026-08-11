---
title: Product Planes, Capability Packs, and Preservation-First Composition
type: template-adr
created: 2026-08-10
status: superseded
amends: [adr-81]
superseded_by: [adr-83]
schema: docs/templates/_schema/adr.schema.json
---

# ADR-82 — Product Planes, Capability Packs, and Preservation-First Composition

> Superseded by ADR-83. Removed paths named below remain available in Git history and are not part
> of the active supported surface.

## 1. Context

ADR-81 made the four-file Markdown starter the narrowest useful consumer contract. The repository
also retains a substantial bootstrap, memory, capability, hook, executor, agent, specification, and
release implementation. Treating all of that code as an undifferentiated unsupported remainder
made the public identity inaccurate, while making it all mandatory would recreate the excessive
greenfield entry cost that ADR-81 corrected.

The product needs a small stable default, explicit support boundaries for advanced features, a
distribution format that does not inherit provider Git history, and an adoption path that never
overwrites repository-owned work. Existing implementation and adopter workflows must remain
available; this decision classifies and composes them rather than deleting them.

## 2. Decision Drivers

- Keep the minimum consumer contract documentation-only and runtime-independent.
- Preserve the complete implemented platform and its regression evidence.
- Make optional capability cost, support level, runtime compatibility, and execution state explicit.
- Separate maintainer source, release artifacts, repository-owned policy, and machine-local state.
- Produce deterministic, digest-verifiable release assets from a clean candidate.
- Inspect before mutation and reject conflicts instead of silently merging or overwriting.
- Allow different projects on one host to pin different immutable provider versions.

## 3. Considered Alternatives — HARD

1. Keep ADR-81 literally unchanged and publish only the four files.
2. Return to full-provider clone, mandatory bootstrap, mandatory memory/spec initialization, and
   post-bootstrap slim.
3. Split every advanced implementation into separate repositories immediately.
4. Keep one source repository but introduce product planes, capability packs, advisory profiles,
   deterministic release assets, and an explicit plan/apply composer.

## 4. Decision

Mir Yoke is a public local project-harness platform and reference implementation. It is not a
hosted agent runtime, universal installer, service, fleet controller, or authority over adopters.
ADR-81's `starter/` remains the only required and default consumer payload. Optional features are
supported only through a declared pack manifest and never become readiness prerequisites merely
because their source exists.

The repository defines four physical planes in `config/product-planes.json`:

- **Source Plane** — maintainer-owned source, tests, schemas, decisions, profiles, packs, and the
  retained platform implementation.
- **Distribution Plane** — ignored deterministic archives plus manifest, checksums, and provenance.
- **Project Plane** — consumer-owned `HARNESS.md`, runtime entrypoints, optional tracked policy, and
  explicitly selected pack payloads.
- **Local Plane** — ignored receipts, provider references, caches, databases, and host state under
  `.mir/` or the configured provider home.

Capability packs are schema-validated and declare source paths, adoption assets, dependencies,
support level, compatibility, verification, local state, and an opt-in execution state. `safety`
is stable. `memory`, `collaboration`, and `assurance` are preview. Existing platform files remain in
place and are named as the source of those packs. Runtime-neutral payloads replace historical
family or fleet assumptions on new adoption paths without modifying the retained implementation.

Profiles (`minimal`, `code`, `content`, `collaboration`, and `assured`) are advisory composition
presets. They may select stable defaults and recommend additional packs, but their policy is never
mandatory. The `yoke` CLI provides these bounded operations:

1. `build` creates deterministic core and pack archives and digest sidecars;
2. `provider install` installs an immutable provider under `providers/<content-digest>` without a
   host-global active-version alias;
3. `plan` inspects one explicit target and records create, identical, and conflict actions without
   writing to that target; and
4. `apply` accepts only an unchanged provider and unchanged plan, refuses every conflict, writes
   only planned new files, records local receipts, and rolls back its own creations on failure.

The release workflow builds the Distribution Plane and requests GitHub artifact attestation. The
lightweight core contract is the normal pull-request gate. The complete pre-0.9 platform regression
remains available as an explicitly triggered job; it is preserved rather than removed.

## 5. Rejected Alternatives — HARD

Alternative 1 leaves valuable implemented capability without a public support or compatibility
model. Alternative 2 makes the highest-assurance workflow the entry fee for every repository and
continues provider-history inheritance. Alternative 3 creates immediate repository, release, and
migration fragmentation without first proving stable module boundaries. Alternative 4 is selected
because it changes the default and distribution boundary while preserving the implementation.

## 6. Positive Consequences

- Small projects keep a four-file, zero-runtime starting point.
- Higher-assurance projects can select capabilities without pretending they are universally free.
- Consumers receive new Git-independent archives instead of cloning and later removing provider
  files.
- Repository policy can be tracked while local paths, receipts, and databases remain untracked.
- Existing implementation, tests, and historical evidence remain usable and auditable.
- Multiple projects can pin different provider digests on one machine.

## 7. Negative Consequences — HARD

- Maintainers now own pack schemas, support labels, deterministic packaging, and migration evidence.
- Preview packs can expose preserved implementation that still contains runtime-specific or older
  policy concepts; the new payload is narrower than the retained source.
- Conflict refusal requires an owner or agent to reconcile existing files before apply.
- GitHub protection, required-check configuration, tag signing, and release publication remain
  repository-administrator actions outside the local code change.

## 8. Out-of-Scope — HARD

- Deleting, rewriting, or silently migrating existing bootstrap, hook, memory, executor, plugin,
  specification, archive, or adopter state.
- Automatically modifying arbitrary repositories, Git remotes, commits, branches, or releases.
- Claiming stable support for preview packs or semantic equivalence across every agent runtime.
- Native Windows parity for preserved POSIX implementation paths.
- Hosted control planes, fleet rollout, telemetry, drift scoring, or standing provider authority.

## 9. Verification

- Validate the plane and pack manifests and prove all retained platform exemplars belong to a pack.
- Build the Distribution Plane twice and compare every artifact digest.
- Inspect the core archive and prove it contains exactly the four starter Markdown files.
- Prove composition planning is non-mutating, conflicts never overwrite, changed plans/providers
  fail closed, and a failed apply rolls back its own creations.
- Prove the safety payload has tool-specific path extraction and contains no family/fleet remnants.
- Verify both `yoke` and `mir yoke` entrypoints, asset classification, generated derivatives, plugin
  version parity, full tests, lint, and clean-candidate release readiness.
- Verify the final change deletes no tracked implementation file.

## 10. References

- [ADR-81](adr-81-minimal-starter-support-boundary.md)
- [ADR-80](adr-80-release-runtime-isolation-and-adopter-ownership.md)
- Historical `config/product-planes.json` (removed from the active tree)
- Historical `config/capability-pack.schema.json` (removed from the active tree)
