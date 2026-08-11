# Migration Guide

## 0.9.0 from 0.8.x

### Product boundary

- `starter/` remains the only fixed consumer payload and the four-file compatibility layer.
- New empty repositories use the standard `recipes/project-agent-kit/` guidance flow, which now
  requires a bounded project-owned common harness and SQLite+FTS5 memory baseline.
- Common plugins remain optional host capabilities and are portable outside the Mir Yoke checkout.
- The 0.9 package restores the public v0.8 `mir` command surface as an optional installed operator
  tool. It is not copied into Project Agent Kit targets and grants no authority until explicitly
  invoked for the user's named scope.
- ADR-82 product-plane and `yoke` composition sources remain superseded. Preserved files live only
  under `reference-templates/advanced-composition/`; no `yoke` console entrypoint is active.

### Existing 0.8 adopters

Existing users may install v0.9 to retain the public v0.8 `mir` command contract. Mir Yoke performs
no automatic migration, state deletion, repository rewrite, target update, or implicit command.
Adopt the Project Agent Kit or a changed local contract only through an owner-reviewed repository
change.

### New projects

Open one empty target and use the short prompt from `README.md`. The agent creates and verifies a
project-owned common harness and memory foundation, one initial commit, and then stops before
development planning. Do not vendor the Mir CLI source into the target.

### Rollback

Discard an uncommitted Project Agent Kit adaptation in the target or restore the target's own prior
commit. For an explicitly invoked CLI transaction, use that command's recorded rollback/recovery
contract. Installing the CLI does not itself mutate a target.

Current version: `0.9.0`. See `CHANGELOG.md` for release details.
