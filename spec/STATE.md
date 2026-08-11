<!-- Derived projection. Update graph and node files first. -->

# MIR YOKE ADVANCED AUTOMATION SPEC SNAPSHOT
status: superseded-reference
superseded_by: ADR-81
scope: pre-ADR-81 bootstrap, capability, and release implementation evidence
features: 4 (done 4 / building 0 / planned 0 / deprecated 0)
requirements: 20 (ready 20 / incomplete 0 / blocked 0)
use cases: 6
tasks: 10 (done 10 / doing 0 / blocked 0)
gaps: 0 (blocking 0)
mode: S · domain: AI_SYSTEM · updated: 2026-08-10

## Reading order

1. `index.yaml`
2. `views/features.md`
3. Target feature and requirement shards plus matching `graph.yaml` edges
4. `tasks.yaml`, `checks.yaml`, and `gaps.yaml` before closeout

## Authority boundary

- This tree is not the current supported consumer contract.
- ADR-81 defines `starter/` as the only supported consumer payload.
- Counts and completion states below preserve historical implementation evidence only.
- No bootstrap, capability, memory, plugin, hook, spec, or receipt requirement in this snapshot is
  a starter readiness requirement.

## Historical verification record

- READY: all requirements pass ARR-1 through ARR-8.
- READY: L1, L2, L3, and L4 contain zero TBD cells.
- READY: every requirement and use case is allocated and has a verification target.
- READY: the protected capability lock is bound to the final implementation commit.
- SCOPE: this historical implementation changed Mir Yoke only and granted no cross-repository write.
- READY: the clean-candidate release proof covers focused contracts, the full suite, lint,
  derivatives, sanitization, links, schemas, and asset classification.
- HISTORY: the 0.8 installed-CLI proof remains in Git history. ADR-83 removed that public
  entrypoint; the current tree instead verifies that no target-writing console script is published.

## Notes

- Mir Yoke has no provider runtime. Runtime and data views explicitly record this boundary.
- Existing `template-repo/*.md` runbooks are historical unless this spec links them.
- Root Mir Harness `spec/` is intentionally unaffected.
- Graph-bound tests and implementation anchors that remain current are present for the historical
  product boundary.
