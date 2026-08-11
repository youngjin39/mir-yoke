# Session Handoff — Core Harness Restoration 0.9 Candidate

## Current state

- The optional public v0.8-compatible `mir` dispatcher and isolated installed-package proof are
  restored with 11 commands; the ADR-82 `yoke` composer remains inactive.
- The standard Project Agent Kit now requires a bounded common harness, pinned thin CLI wrapper,
  SQLite+FTS5 memory configuration, sync wrapper, and resumable handoff. Generated repositories may
  not track `.mir/memory.db`, `src/mir`, provider tools, plugins, or provider Git history.
- The four-file Minimal Starter remains the compatibility minimum.
- The 33 ADR-82 composition files are byte-preserved under
  `reference-templates/advanced-composition/` as inert, remove-on-adoption references.
- ADR-83 has an owner amendment; contracts, spec metadata, CI, release readiness, classification,
  and Claude/Codex derivatives describe the three-layer boundary.
- The evidence observer now runs the complete memory lifecycle twice, deletes and recreates the
  ignored database, recovers the exact normalized project purpose, and behaviorally proves the
  pre-commit hook fails when required memory is absent.
- Public CLI/bootstrap regression runs on both Ubuntu and macOS in CI.

## Verification

- Restored CLI, bootstrap/adoption, memory/context, capability, executor, loop, migration, runtime,
  and Project Agent Kit regression set: 525 passed.
- Behavioral common-harness evidence, restored CLI reachability, contract, and decision regression:
  77 passed.
- Complete materialized release-candidate regression: 759 passed. Repository-wide Ruff, schemas,
  links, public-text
  sanitization, generated derivatives, and diff whitespace all pass.
- Asset classification covers 676 candidate files exactly once with zero missing, duplicate, or
  prohibited paths.
- Independent final restoration review reports READY with zero blocking items.

## Release boundary

- Implementation commit `e5abfad` is complete. The protected lock in the release commit is bound to
  full implementation revision `e5abfadce84be0107395a12509a256b144a2d29a`.
- The owner authorized the implementation commit, protected capability-lock rebind in a separate
  commit, SSH push to `main`, annotated `v0.9.0` tag, and GitHub Release publication.
- Separate Claude and Codex generated-repository executions are post-release owner acceptance. This
  release does not claim that runtime evidence, and the tag workflow does not require it.
- Final clean-tree readiness passed with 759 tests. Release commit `1d17358`, remote `main`, and the
  annotated `v0.9.0` tag were verified over SSH.
- GitHub Release `v0.9.0` was published as a non-draft, non-prerelease release on 2026-08-11:
  <https://github.com/youngjin39/mir-yoke/releases/tag/v0.9.0>.
- No repository-side release work remains. The owner-run external generated-repository acceptance is
  the next independent consumer check.
