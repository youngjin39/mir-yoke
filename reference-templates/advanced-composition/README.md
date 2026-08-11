# Advanced Composition Reference Template

This directory preserves the 33-file implementation introduced by ADR-82 at commit
`27b09a3d0da8ee4d82f8cad4e93773b1660ac1b8` as inspectable prior art.

## Boundaries

- `source/` mirrors each preserved file at its original repository-relative path.
- The snapshot is reference material, not an active Mir Yoke product surface or supported
  consumer payload.
- Nothing under this directory is imported, dispatched, installed, or composed by the current
  runtime.
- Active top-level `packs/` and `profiles/` directories, `src/mir/core/distribution/`, and the
  `mir yoke` dispatcher remain intentionally absent.
- Adopters may inspect and selectively adapt the ideas, but this snapshot grants no authority to
  write to an external repository.

Do not edit files under `source/` in place. Preserve the historical snapshot exactly and document
new composition guidance outside the snapshot.
