# Session Handoff — Mir Yoke v0.9.0 Closed

## Completed Work

- Restored and released the optional v0.8-compatible public `mir` CLI while keeping the removed
  ADR-82 `yoke` composer inactive.
- Made the standard Project Agent Kit include a project-owned common harness, rehydratable
  SQLite+FTS5 memory, project-specific reviewer, real lint/build/test hook, and one verified initial
  commit without copying Mir runtime source.
- Preserved the 33 superseded composition files as inert references and kept the four-file Minimal
  Starter unchanged.
- Clarified the canonical short prompt in `409d09e`: concrete purpose and goals are required, and
  development planning plus product implementation remain outside bootstrap.
- Removed all merged agent branches locally and remotely; `main` is the only branch.

## Decisions

- `v0.9.0` remains an immutable published tag. Later `main` documentation and prompt refinements do
  not rewrite that release.
- The provider is read-only guidance for Project Agent Kit creation. Generated repositories own
  their harness and memory sources and never copy `src/mir/`, provider tools, plugins, or Git
  history.
- Detailed completion history remains in `tasks/tdd.json`, ADRs, Git history, and the GitHub Release;
  active state stays limited to resume-critical facts.

## Unresolved Issues

- No repository-side blocker remains.
- Real Claude and Codex runs in separate empty target repositories are unevaluated owner-run
  post-release acceptance. A target has not been supplied, so no runtime success claim is made.
- The temporary restore worktree initially lacked `.mir/memory.db` and a bootstrap receipt, so its
  context pull and pinned `scripts/mir.sh` intent wrapper were unavailable; the repository-owned
  intent-store script ran directly through `uv`. After returning to the canonical worktree, context
  pull succeeded in FTS5-only mode. The bootstrap receipt remains absent.

## Next Actions

- No active repository action. End the session.
- Optional manual action: when the owner supplies a target, run the short prompt with Claude and
  Codex and record observed acceptance without changing the `v0.9.0` claim.
- Optional release decision: publish a future patch release only if the owner wants the post-tag
  prompt wording pinned in a release rather than consumed from default `main`.

## Modified Files

- Prompt contract and evidence: `README.md`, `recipes/project-agent-kit/`,
  `release-evidence/project-agent-kit/fixture/`, `config/adopter-payload.json`, and focused tests.
- Closeout state: `tasks/intent.json`, `tasks/plan.md`, `tasks/checklist.md`, `tasks/tdd.json`,
  `tasks/change_log.md`, and this canonical handoff.

## Verification Results

- Prompt, Project Agent Kit evidence, classification, release-readiness contract, identity, and
  decision tests: 56 passed.
- Intent-store and closeout-hook contracts: 6 passed.
- Prompt test Ruff and diff whitespace checks: passed.
- Published release inspection: `v0.9.0` is non-draft and non-prerelease.
- Git inspection: SSH origin; local and remote branch inventories contain only `main`.

## Key Risks

- `v0.9.0` predates the clarified prompt commit. The behavior is available on default `main`, while
  consumers pinning the tag receive the earlier semantically similar wording.
- External Claude/Codex acceptance remains unverified until the owner provides target repositories.
- Final context pull reported profile freshness `review_required` because the selected handoff and
  plan changed after the stored profile baseline; no external memory archives are configured.

<!-- mir:runtime-snapshot:begin -->
## Runtime Snapshot (Generated)

### Active Plan Items
- No open plan items.

### Working Tree
- Working tree clean.
<!-- mir:runtime-snapshot:end -->
