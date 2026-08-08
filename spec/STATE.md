<!-- Derived projection. Update graph and node files first. -->

# MIR YOKE SPEC STATE
scope: Mir Yoke public template product boundary and implementation verification
features: 4 (done 4 / building 0 / planned 0 / deprecated 0)
requirements: 20 (ready 20 / incomplete 0 / blocked 0)
use cases: 6
tasks: 8 (done 8 / blocked 0)
gaps: 0 (blocking 0)
mode: S · domain: AI_SYSTEM · updated: 2026-08-08

## Reading order

1. `index.yaml`
2. `views/features.md`
3. Target feature and requirement shards plus matching `graph.yaml` edges
4. `tasks.yaml`, `checks.yaml`, and `gaps.yaml` before closeout

## Verification gate

- READY: all requirements pass ARR-1 through ARR-8.
- READY: L1, L2, L3, and L4 contain zero TBD cells.
- READY: every requirement and use case is allocated and has a verification target.
- READY: the protected capability lock reproduces the implementation commit and managed agents.
- SCOPE: implementation changes Mir Yoke only; this dossier grants no cross-repository write.
- COMPLETE: the clean candidate release proof passes from preserved Git ancestry.

## Notes

- Mir Yoke has no provider runtime. Runtime and data views explicitly record this boundary.
- Existing `template-repo/*.md` runbooks are historical unless this spec links them.
- Root Mir Harness `spec/` is intentionally unaffected.
- Graph-bound tests and implementation anchors are present for the changed product boundary.
