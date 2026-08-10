# Migration Guide

This document records breaking changes between major versions of `mir-yoke`. Each entry covers migration steps for existing adopters to upgrade.

## Format

Each section follows the pattern:

```markdown
## v<N+1>.0.0 ← v<N>.x.y

### Breaking changes
- (list of breaking changes)

### Migration steps (per family)
1. (concrete commands or edits)

### Rollback
- (procedure to revert if migration fails)
```

## Current Status

No MAJOR releases yet. Current version: `0.9.0`.

Version 0.9 keeps the complete 0.8 platform source available while adding a smaller default core,
explicit optional capability packs, deterministic distribution artifacts, and preservation-first
composition. Existing adopters do not need to remove or rewrite their installed platform.

The current pre-1.0 platform contract supports automated greenfield bootstrap on macOS, Linux, and
WSL. Native-Windows callers must move automation into WSL or use Mir Yoke as agent-guided reference
material; `setup.ps1` no longer installs or finalizes and exits without repository mutation.

## See Also

- [`CHANGELOG.md`](CHANGELOG.md) — non-breaking change log (PATCH/MINOR)
- [`VERSION`](VERSION) — current semver
