# Session Handoff — Project Agent Kit 0.9 Candidate

## Completed Work

- Implemented ADR-83 as a 0.9 candidate: four-file Starter, separate Project Agent Kit recipe,
  portable plugin provider, and retained reference corpus.
- Added the short-prompt route, purpose-preserving project brief, repository-unique read-only
  reviewer, Claude-to-Codex generation contract, real lint/build/test hook, and verified one-commit
  Git boundary before development planning.
- Added a public target-contract schema and a two-phase clean-room observer. The observer binds the
  concrete purpose and provider revision, validates before execution, uses a credential-free
  target-local environment, mutation-probes parity/lint/build/test/manifest/lock inputs, preserves
  Git identity and signing policy, content-hashes bounded outside state, and sanitizes public logs.
- Removed active product planes, capability packs, profiles, distribution/composer code, and the
  `yoke` CLI while retaining superseded ADR-82 and Git history as audit evidence.
- Generalized common plugins so repository-local Mir files and services are optional context rather
  than hidden prerequisites.

## Decisions

- ADR-83 is current authority; ADR-81 continues to own the four-file minimum Starter and ADR-82 is
  superseded history.
- Mir Yoke is read-only reference. The target agent owns all Project Agent Kit writes under the
  current user's explicit target authorization.
- Clean-room Claude and Codex runs are release-claim gates, not substitutes for target ownership.

## Approval State

- Independent final re-review found no fix-now blocker and classified the implementation as an
  approval candidate.
- `.mir/capability-lock.json` is protected and intentionally not rebound before an approved commit;
  its tree-digest test is the only expected local regression failure.
- Claude and Codex clean-room empty-target runs remain unevaluated until a publishable revision
  exists. No commit, push, tag, release, or consumer write has occurred.

## Next Actions

- Obtain owner approval for the implementation commit and protected lock-rebind sequence.
- After explicit commit approval, create the implementation commit, rebind the protected capability
  lock to that commit, verify, and create the separate lock commit.
- Before a 0.9 release claim, run the same short prompt independently in clean Claude and Codex
  empty targets and verify one clean initial commit in each.

## Modified Files

- Product authority: root contracts, ADR-83/index, ADR-81 amendment, and superseded ADR-82 metadata.
- Supported guidance: `recipes/project-agent-kit/` and four-file `starter/`.
- Provider boundary: portable common plugin skills and Claude/Codex marketplace versions.
- Maintenance: classification, release checks, generated derivatives, focused contract tests, and
  removal of active composition artifacts.
- Durable state: profile, intent, plan, TDD ledger, and this handoff.

## Verification Results

- Focused observer, schema, supported-surface, identity, security, and spec contracts: 92 passed.
- Regenerated asset classification covers 635 candidate files exactly once with zero unclassified,
  duplicate, or prohibited paths.
- Full regression passed 741 tests with only the protected capability-lock digest test intentionally
  deselected pending the approval-gated commit/rebind sequence.
- Actual isolated Claude and Codex plugin installation/activation passed with identical package
  digests. Ruff, diff whitespace, and Claude/Codex derivative parity pass.

## Key Risks

- The protected capability lock still describes the pre-candidate plugin trees until the approved
  two-commit rebind sequence.
- Observer-backed synthetic tests prove the evidence mechanism, not one-prompt reproducibility;
  actual Claude and Codex clean-room runs remain a release gate.
- The repository contains a large intentional inverse diff because active ADR-82 composition was
  removed. Review deleted paths before approval.

<!-- mir:runtime-snapshot:begin -->
## Runtime Snapshot (Generated)

### Active Plan Items
- No open plan items.

### Working Tree
- Working tree dirty (88 paths; inspect git status --short).
<!-- mir:runtime-snapshot:end -->
