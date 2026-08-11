# Migration Guide

## 0.9.0 from 0.8.x

### Product boundary

- `starter/` remains the only supported consumer payload.
- New empty repositories may use the supported `recipes/project-agent-kit/` guidance flow.
- Common plugins remain optional host capabilities and are portable outside the Mir Yoke checkout.
- Provider-side bootstrap, copied CLI, memory readiness, product planes, capability packs,
  composition, receipts, and clone-and-slim are no longer active new-project paths.
- The 0.9 package exposes no `mir` or `yoke` console entrypoint. Retained Python modules are
  reference and regression corpus without a public CLI compatibility promise.

### Existing 0.8 adopters

Existing users stay pinned to their chosen 0.8 workflow. Mir Yoke performs no automatic migration,
state deletion, repository rewrite, or target update. Adopt the 0.9 local contract only through an
owner-reviewed repository change.

### New projects

Open one empty target and use the short prompt from `README.md`. The agent creates and verifies a
project-owned foundation, one initial commit, and then stops before development planning.

### Rollback

Discard an uncommitted 0.9 adaptation in the target or restore the target's own prior commit. Mir
Yoke stores no target receipt or external state that needs rollback.

Current version: `0.9.0`. See `CHANGELOG.md` for release details.
