---
title: Mir Yoke Public Template Identity and Non-Authority
type: template-adr
created: 2026-08-08
status: accepted
product_role: public-template
provider_runtime: none
standing_consumer_authority: none
amends: [adr-54, adr-75, adr-76, adr-77]
source_decision: Mir Harness ADR-84
schema: docs/templates/_schema/adr.schema.json
---

# ADR-78 — Mir Yoke Public Template Identity and Non-Authority

## 2026-09-06 Current Management Amendment

ADR-86's 2026-09-06 amendment controls Yoke's current primary purpose and management relationship:
Yoke is the Harness-managed central capability supply system for independently owned repositories.
This ADR's public-template identity describes its distribution form and its non-runtime,
non-authority boundary; it does not make Yoke independently managed or a consumer control plane.

## 1. Context

Mir Yoke began as a reusable public harness template. A later centralization period added fleet
catalogs, hash parity, direct deployment, cross-repository reconciliation, watchdog daemons, and
fleet notifications. Those artifacts made historical implementation look like current product
authority even after the project returned to portable bootstrap and preservation-first adoption.

The owner confirmed that Mir Yoke is the template and reference repository itself. It is useful
when starting a project and when an existing repository owner selectively improves a local harness.
It is not the Mir Harness control plane and is not a running agent product.

## 2. Decision Drivers

- Make the public product understandable without private Mir fleet history.
- Preserve useful starter, reference, consumer, and maintainer assets without implicit adoption.
- Keep existing repositories authoritative over their instructions, code, and evidence.
- Retain Git hashes for integrity and provenance without turning them into compliance policy.
- Keep centralization history retrievable while removing its executable authority.

## 3. Considered Alternatives — HARD

1. Restore Mir Yoke as a central fleet baseline and direct-apply source.
2. Split the repository into a template and a hosted agent service.
3. Keep mixed historical and current surfaces and rely on reader interpretation.
4. Establish one public template product with explicit local adoption and exhaustive asset
   classification.

## 4. Decision

Mir Yoke is an independently maintained, public, repository-agnostic template and reference
repository. Its product is versioned files. It is not an agent runtime, daemon, service, fleet
manager, or control plane, and it has no standing authority over any consumer repository.

The provider starts no agent, target scan, scheduler, daemon, rollout, or background service.
Executable files are inert until a maintainer validates this repository or a consumer explicitly
invokes them inside one declared local repository boundary.

Two adoption paths are separate:

1. `mir bootstrap` creates a greenfield baseline after explicit invocation for one project root.
   Phase 1 installs a copied external CLI and removes nothing. Passing Phase 2 finalize performs
   one hash-bound, rollback-capable slim transaction as its last mutation and writes ready last.
2. `mir bootstrap-adoption` assesses an existing repository without writing by default. Its
   explicit `--apply` form may write only the machine-local receipt after every check passes and
   never invokes greenfield slim.

Every tracked release surface has exactly one disposition: `starter`, `reference`,
`optional-consumer-tool`, `template-maintainer-tool`, or `historical`. Unclassified or multiply
classified files block release readiness.

Capability status and check are read-only. Sync, update, attestation, and finalization mutate state
only with their explicit apply flags. Commits and hashes prove source, lock, receipt, cache, and
time-of-check/time-of-use integrity only; they do not prove adoption, compliance, drift, target
selection, or mutation authority.

Central-fleet daemons, target scanners, parity verdicts, direct deployment helpers, notification
workflows, and cross-repository reconciliation leave the active payload. Centralization decisions
and engineering prose remain available through the historical index and Git history.

## 5. Rejected Alternatives — HARD

- Central fleet baseline: conflicts with repository-local ownership and recreates the authority
  failure this decision resolves.
- Hosted runtime: invents a product the owner did not request.
- Mixed unclassified corpus: permits historical tools to regain authority through ambiguity.

## 6. Positive Consequences

- Public adopters receive one stable product explanation and two explicit entry paths.
- Existing repositories can reuse ideas without reconstruction or template conformance.
- Supply-chain integrity remains reproducible without central policy authority.
- Release checks can mechanically detect identity, classification, or historical-boundary drift.

## 7. Negative Consequences — HARD

- Central fleet automation and parity tooling are removed from the public payload.
- The template cannot promise automatic uniformity after adoption.
- Maintainers must keep the classification manifest and release checks current as files change.

## 8. Out-of-Scope — HARD

- Operating Mir Harness fleet inventory, policy, observations, or target-specific prompts.
- Automatically editing, committing, pushing, tagging, or releasing a consumer repository.
- Hosting an agent service or guaranteeing support for every third-party runtime.
- Treating template version lag as consumer drift.

## 9. Verification

- Root identity tests require public-template, provider-non-runtime, and non-authority claims.
- Asset validation maps every tracked candidate file to exactly one classification.
- Adoption and capability tests prove read-only defaults, explicit apply, local-root confinement,
  external CLI isolation, hash-bound greenfield slim, atomic receipts, rollback, and changed-path
  reporting.
- Release readiness runs identity, authority, history, classification, sanitization, derivative,
  focused behavior, full test, and lint checks from a clean candidate tree.

## 10. References

- Mir Harness ADR-84 and the MODE-S Mir Yoke dossier dated 2026-08-08.
- ADR-73 — proportional guidance-first harness.
- ADR-74 — portable bootstrap, capability sources, and memory.
- ADR-77 — preservation-first existing-repository adoption.
