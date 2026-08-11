<!-- Derived projection. Update graph and node files first. -->

# MIR YOKE ADVANCED AUTOMATION SPEC SNAPSHOT
status: superseded-reference
superseded_by: ADR-83
scope: pre-ADR-81 bootstrap, capability, and release implementation evidence
features: 4 (done 4 / building 0 / planned 0 / deprecated 0)
requirements: 20 (ready 20 / incomplete 0 / blocked 0)
use cases: 6 · tasks: 10 (done 10) · gaps: 0 (blocking 0)
mode: S · domain: AI_SYSTEM · updated: 2026-08-10

## Reading order

1. `index.yaml`, then `views/features.md`
2. Target feature and requirement shards plus matching `graph.yaml` edges
3. `tasks.yaml`, `checks.yaml`, and `gaps.yaml` before closeout

## Authority boundary

- ADR-83 defines the current three-layer contract; ADR-81 still owns the four-file Starter.
- The standard Project Agent Kit creates project-owned common harness and memory files without
  copying Mir CLI implementation; the optional installed CLI gains no authority from installation.
- Counts preserve historical detail. Nothing here expands Starter or Kit readiness.

## Historical verification record

- READY: 20/20 requirements pass ARR-1 through ARR-8; L1-L4 contain zero TBD cells.
- READY: every requirement and use case is allocated and has a verification target.
- SCOPE: this historical implementation changed Mir Yoke only and granted no cross-repository write.
- READY: historical clean-candidate checks covered tests, lint, derivatives, sanitization, links,
  schemas, and classification.
- SCOPE: this snapshot preserves detailed v0.8 automation requirements; current installed-CLI proof
  comes from package tests, not from the snapshot status.
- SCOPE: ADR-82 composition files remain inert references with no active `yoke` command.
