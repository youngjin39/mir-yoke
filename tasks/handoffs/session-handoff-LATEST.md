# Session Handoff — Harness Upgrade Ready to Publish

## Completed Work

- Added ADR-84 and a current, reference-only harness engineering upgrade guide covering governance,
  context/token efficiency, memory, embeddings, agents, skills, hooks, and Claude/Codex parity.
- Corrected default active-fact retrieval, semantic document history, repository-declared history
  globs, metadata-only reclassification, explicit missing-vector backfill, and dimension honesty.
- Normalized current Codex patch input across safety, post-edit, and memory adapters; generated
  operator-owned Codex permissions and bounded SessionEnd parity; documented hook trust.
- Bound vector writes and resumable backfill to one persisted complete encoder fingerprint;
  retained fact subject/provenance and quarantined credential-shaped values.
- Preserved the four-file Starter, Project Agent Kit ownership, optional CLI/plugins, historical
  boundary, protected capability lock, and immutable `v0.9.0` tag.

## Decisions

- The three supported layers remain the Minimal Starter, the standard Project Agent Kit recipe, and
  the separately selected installed CLI. The upgrade guide is reference, not another payload.
- SQLite+FTS5 stays required and vector mode stays off by default. The current vector table supports
  1024 dimensions; missing-vector backfill is not a model migration.
- Retrieved memory is untrusted data. Instruction-like facts are omitted with id-only notices.
- Generated Codex roots and write-capable agents inherit the operator-selected permission policy;
  mechanically read-only roles stay read-only.
- Capability-lock-bound Claude model pins were not changed because the lock is protected.

## Unresolved Issues

- No repository-side blocker remains.
- Real sqlite-vec was unavailable locally. Backfill atomicity and resume were verified with the same
  rowid contract, while actual vec0 acceptance remains covered by the optional environment path.
- Owner-run Claude and Codex empty-target acceptance remains optional and unevaluated.

## Next Actions

- Commit and push the verified `main` change to `origin/main`; the owner authorized this action.
- Do not tag, publish a release, edit the protected capability lock, or run external acceptance.

## Modified Files

- Product guidance and authority docs, current bluebricks, changelog, and asset classification.
- Context/memory/embedding CLI and store, migration 018, examples, operations guide, and regressions.
- Bootstrap permission validation, generated Codex permission inheritance, and hook timeout typing.
- Canonical hook adapters/config, Codex generator and derived surfaces, agent-pack guidance, and
  repository-wide link coverage.
- Plan, intent, checklist, TDD ledger, change log, and this canonical handoff.

## Verification Results

- Clean-candidate release readiness: `ready=true`.
- Focused contracts: 105 passed; installed CLI/policy: 27 passed; full suite: 797 passed.
- All 691 tracked candidate files classify exactly once with zero prohibited or duplicate paths.
- Ruff, schemas, sanitization, links, generated derivative parity, shell syntax, and
  `git diff --check` passed.
- Independent final publication review: `READY`, blocking findings = 0.

## Key Risks

- `v0.9.0` predates both compact lifecycle and ADR-84; no release claim was changed.
- Actual sqlite-vec runtime acceptance and external Claude/Codex generated-target acceptance remain
  unverified optional follow-ups.
- The worktree contains the completed verified change; commit and push are pending.

<!-- mir:runtime-snapshot:begin -->
## Runtime Snapshot (Generated)

### Active Plan Items
- Commit the verified change to `main` and push it to `origin/main`.

### Working Tree
- Working tree dirty (54 paths; inspect git status --short).
<!-- mir:runtime-snapshot:end -->
