---
title: Project Agent Kit Recipe and Supported Surfaces
type: template-adr
created: 2026-08-11
status: accepted
amended: 2026-08-11
amends: [adr-78, adr-81]
supersedes: [adr-82]
schema: docs/templates/_schema/adr.schema.json
---

# ADR-83 — Project Agent Kit Recipe and Supported Surfaces

## 2026-08-11 Owner Amendment

This amendment controls where it conflicts with the original decision below:

1. The four-file Minimal Starter remains the compatibility layer and receives no runtime or memory
   prerequisite.
2. The standard greenfield Project Agent Kit must create a bounded project-owned common harness and
   required SQLite+FTS5 memory component. It must not copy the full Mir package or CLI source.
3. The v0.9 package restores the public v0.8 `mir` command surface as an optional installed operator
   tool. Installation grants no target authority; every state-changing use requires the current
   user's explicit target and operation.
4. ADR-82 remains superseded, but selected composition files are preserved under
   `reference-templates/advanced-composition/` as inert references. No active `yoke` command,
   composer, provider, plan, or apply path returns.
5. The owner pushes the verified tag separately over SSH. The tag workflow does not create or push
   tags; it validates repository state and publishes an idempotent GitHub Release. Separate Claude
   and Codex generated-repository runs are post-release owner acceptance, not a tag blocker or a
   runtime proof claimed by this release. The evidence observer and verifier remain available.

## 1. Context

ADR-81 correctly reduced the minimum consumer payload to four Markdown files. That boundary alone
does not satisfy the owner's primary greenfield workflow: give an AI one project-purpose prompt and
the Mir Yoke URL, then receive a project-owned Claude and Codex agent foundation, code reviewer,
real Git pre-commit verification, and a clean initial commit before development planning.

ADR-82 attempted to close this gap with product planes, capability packs, archives, provider state,
and a target-writing composer. That machinery recreated provider-side project mutation and produced
a fixed payload rather than a purpose-adapted project agent.

## 2. Decision

Mir Yoke exposes three adoption layers:

1. **Minimal Starter** — `starter/` is the only fixed consumer payload and remains exactly four
   Markdown files with no runtime dependency.
2. **Standard Project Agent Kit Recipe** — `recipes/project-agent-kit/` is supported agent guidance
   for one explicit empty target. The target's active AI reads Mir Yoke as reference and creates the
   local result under the user's target authority.
3. **Optional installed CLI** — the v0.9 package publishes the v0.8-compatible `mir` command set for
   owners who explicitly select its automation. It is host-installed, not a Project Agent Kit
   payload, and exposes no active `yoke` composer.

Portable plugins remain optional host capabilities. The retained source, tests, examples,
specifications, history, and ADR-82 reference templates remain inspectable prior art without
automatic adoption claims.

The Project Agent Kit recipe creates a project brief, bounded common harness, required local
SQLite+FTS5 memory, Claude and Codex entrypoints, a repository-unique code-review skill, a read-only
reviewer agent, generated runtime parity, a machine-readable foundation manifest, a real
lint/build/test Git pre-commit gate, and a verified initial commit. It may create only a
domain-neutral toolchain foundation; product planning and implementation remain later work. It
never vendors `src/mir/`, the installed package, or the provider's Git history. Its project-owned
thin wrapper executes the exact recorded provider revision with runtime state confined below
ignored `.mir/`.

In the Project Agent Kit flow, Mir Yoke does not discover a target, apply a plan, write a receipt,
copy its Git history, configure a remote, push, monitor version drift, or own the generated project.
The user's prompt grants the target agent bounded authority for the named empty target and local
`git init` plus the initial commit. Missing Git identity, missing toolchain, an existing Git
boundary, protected scope, or a non-derivable consequential decision stops the flow before an
unsupported completion claim.

Claude project-specific sources are canonical. A target-local generator emits Codex derivatives and
checks parity. Common plugin slugs are never copied into the target; local specializations use a
repository-unique slug.

ADR-82 product planes, capability packs, custom `yoke` build/provider/plan/apply commands, provider
pins, and composer receipts remain absent from the active product. This does not remove the
explicitly invoked v0.8 CLI's machine-local readiness receipts governed by ADR-74 and ADR-80.
Selected ADR-82 files are preserved only under the inert reference-template namespace; Git history
remains the complete recovery record.

## 3. Consequences

- The normal prompt stays short because the published recipe owns the detailed workflow.
- The minimum starter remains portable and documentation-only.
- The standard Kit begins later planning with a repository-owned common harness and working local
  memory without carrying provider runtime source.
- Owners retain the v0.8 public CLI automation through an explicit, independently authorized
  installed tool.
- A purpose-specific Project Agent Kit is generated by the agent that can inspect the actual target,
  not by a provider-side copier.
- Git mutation is explicit, local, verification-gated, and limited to one initial commit.
- Reproducibility is an evaluated user journey rather than a promise that every target receives the
  same files.
- Targets own future maintenance of their harness, reviewer, hook, and generated surfaces.

## 4. Out of scope

- Product planning, feature implementation, remote creation, push, release, or deployment.
- Existing-repository reconstruction or automatic migration.
- Standing provider-side target discovery, composition, rollout, cross-consumer state, composer
  receipts, or drift enforcement.
- Requiring Mir CLI, memory, hooks, plugins, or sub-agents for the four-file starter.
- Treating the optional installed CLI or inert ADR-82 files as implicit authority.

## 5. Verification

- The Starter remains exactly four Markdown files.
- Root documentation routes the short prompt to the Project Agent Kit recipe.
- Recipe tests pin the project-owned common harness, required SQLite+FTS5 memory, and absence of
  copied Mir CLI source.
- Installed-package tests prove the v0.8-compatible `mir` dispatcher outside the source checkout.
- Recipe tests pin target confinement, artifact ownership, reviewer read-only enforcement, real
  lint/build/test commands, Git hook installation, initial-commit conditions, and the planning stop.
- A canonical maintainer observer proves the target was initially empty, runs the declared checks,
  mutation-probes every declared foundation and generated surface, records the original local Git
  and hook state, rejects product files, and publishes only sanitized bounded evidence.
- Optional consumer classification includes only marketplace metadata and `plugins/*`.
- Active contracts contain no product-plane, capability-pack, or `yoke plan/apply` path.
- Plugin packages load from an isolated copy without Mir CLI or repository-local harness files.
- The tag gate runs repository release readiness and publishes the GitHub Release without claiming
  a generated-repository runtime run. The owner later performs separate Claude and Codex acceptance;
  retained tooling may validate the resulting bounded bundles, transcripts, and observations.
