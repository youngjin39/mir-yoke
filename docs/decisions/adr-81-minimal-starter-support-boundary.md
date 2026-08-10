---
title: Minimal Starter Support Boundary
type: template-adr
created: 2026-08-10
status: accepted
supported_consumer_payload: starter/
required_runtime: none
amends: [adr-74, adr-75, adr-76, adr-77, adr-79, adr-80]
schema: docs/templates/_schema/adr.schema.json
---

# ADR-81 — Minimal Starter Support Boundary

## 1. Context

Mir Yoke correctly removed central fleet authority, but its greenfield path still required a large
consumer payload, an external CLI, plugins, memory indexing, specification evidence, restart
coordination, and a transactional slim step. That is a product conversion system, not the basic
harness-engineering template the owner intends.

The durable product value is simpler: give an AI agent a safe starting contract, require it to read
the repository's current state, and let it adapt only the material that is useful there.

## 2. Decision

`starter/` is the only supported consumer payload. It contains four Markdown files: one canonical
repository contract, two thin Claude/Codex entrypoints, and one adoption guide. The starter has no
runtime, installer, platform-specific execution path, or standing authority.

The supported workflow is agent-guided:

1. inspect the target repository and existing instructions without mutation;
2. identify purpose, paths, protected surfaces, generated surfaces, and real verification commands;
3. keep, merge, rename, or skip each starter file without overwriting repository-owned content;
4. replace placeholders with observed facts or explicit owner decisions; and
5. verify the target with its own checks and inspect the final diff.

The starter does not require Mir CLI installation, plugins, hooks, a memory database, a spec tree,
sub-agents, receipts, restart phases, or clone-and-slim behavior. Such assets may remain in Mir Yoke
as maintainer code or optional reference material, but they are outside the supported consumer
contract and receive no compatibility promise.

## 3. Consequences

- New projects have one obvious, small entrypoint rather than a provider checkout conversion.
- Existing repositories can use the same material without being reconstructed.
- Operating-system support becomes irrelevant for the core because the payload is Markdown only.
- Advanced automation remains inspectable but cannot be inferred as a readiness prerequisite.
- The public repository may still be large as a reference and maintenance corpus; supported
  consumer scope is measured only by `starter/`.

## 4. Out of scope

- Automated project mutation or target discovery.
- Plugin, memory, agent-catalog, hook, or execution-backend readiness guarantees.
- Cross-repository rollout, drift, notification, daemon, scheduler, commit, push, or release action.
- Compatibility promises for the retained experimental and historical automation corpus.

## 5. Verification

- `starter/` contains exactly four Markdown files and no executable content.
- `HARNESS.md` covers outcome, current-state sources, authority, work style, and verification.
- Claude and Codex entrypoints route to the same repository-owned contract.
- Root authority documents identify `starter/` as the only supported consumer payload and describe
  all advanced machinery as optional reference or maintainer material.
