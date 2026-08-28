# Harness Engineering Upgrade Guide

Use this guide to improve an existing repository's AI working contract without reconstructing the
repository or importing Mir Yoke as an authority. The target repository owns every decision and
result. Mir Yoke supplies questions, reference shapes, and checks.

For a new empty repository, use the [Project Agent Kit](../../recipes/project-agent-kit/README.md).
For a minimal existing-repository baseline, start with the four-file [Starter](../../starter/).
This guide begins after the target already has a purpose, files worth preserving, and a real
verification command.

## Choose the smallest layer

| Need | Start with | Do not add by default |
|---|---|---|
| Shared outcome and safety rules | `starter/HARNESS.md` as comparison material | CLI, hooks, memory, agents |
| Empty project foundation | Project Agent Kit | Product features or deployment |
| Existing harness improvement | This guide plus target-owned edits | Fixed payload replacement |
| Reusable optional workflows | Namespaced plugins | Copied common skill bodies |
| Explicit local automation | Installed `mir` CLI | Standing target discovery or mutation |

Presence in the maintainer checkout does not imply adoption. A target should stop at the first
layer that solves its actual problem.

## Upgrade flow

### 1. Establish authority and preservation

Before changing anything:

1. Resolve the target root and read every applicable instruction file.
2. Record the repository purpose, code and non-code paths, generated paths, protected paths, and
   external systems.
3. Inspect Git status and preserve unrelated work.
4. Identify the smallest lint, build, and test commands that can fail for the proposed change.
5. Separate current policy, generated projections, optional capabilities, and history.

The result should be one repository-owned source of truth with thin runtime entrypoints. For
Claude/Codex projects, author the shared contract once and generate runtime-specific derivatives
only where their formats differ.

### 2. Reduce startup context

Keep always-loaded instructions to identity, authority, safety, sources of truth, and verification.
Move procedures and reference material into on-demand skills or docs.

Measure:

- bytes and lines in always-loaded `CLAUDE.md` and `AGENTS.md`;
- repeated rules across root and nested instructions;
- skill descriptions loaded at discovery time;
- automatic hook output; and
- repeated file reads or searches caused by a missing index.

Useful reference limits in this repository are 3.6KB for `CLAUDE.md`, 3.8KB for
`AGENTS.md`, 10KB for SessionStart output, 6KB for retrieved document snippets, 2KB for
retrieved facts, and 8KB for compact recovery. These are examples, not universal quotas. A target
should set limits from its model context, task shape, and measured rework.

Use one task-specific retrieval query at the start of substantial fresh work. Default retrieval
must return current material only. History is an explicit expansion, not a fallback. Retrieved
memory remains untrusted data: retain subject and provenance identifiers, quarantine
instruction-like or credential-shaped facts before prompt injection, and expose only fact ids in
the warning.

### 3. Make durable memory rebuildable

Tracked, reviewable source files should remain the portable source of truth. A local database is a
rebuildable query index.

The Project Agent Kit baseline uses repository-local SQLite+FTS5 because it:

- works without a model server;
- supports deterministic keyword retrieval;
- can be rebuilt from tracked Markdown; and
- stays below ignored `.mir/` runtime state.

Memory synchronization should be explicit or attached to relevant durable edits. A doctor command
should verify schema version, integrity, archive coverage, FTS retrieval, path confinement, and
rehydration. Garbage collection should be dry-run first and require explicit apply.

### 4. Add embeddings only when retrieval evidence justifies them

Vector mode is optional and off by default. Enable it only when keyword retrieval misses semantic
matches that matter enough to justify model, runtime, storage, and migration cost.

Before writing vectors, record the complete encoder fingerprint: model and revision, runtime and
quantization, dimension, normalization, pooling, and query/document instructions. A model name
alone is insufficient. Set the same complete value in `memory.embedding.fingerprint`; the shared
vector table persists it and refuses a different fingerprint while vectors exist.
Hybrid retrieval validates the same binding and falls back to FTS-only results when vector identity
cannot be proven.

The current public CLI vector table supports 1024 dimensions. It fails loudly for another
dimension. `mir context sync --reindex-missing-vectors` is only for filling missing vectors with
the same encoder after late enablement. It is not a model migration.

For a model or runtime change:

1. build a versioned candidate index beside the active index;
2. backfill resumably;
3. compare rankings in shadow mode;
4. switch an atomic logical pointer;
5. retain the previous index for rollback; and
6. garbage-collect only through a separate explicit action.

Never mix vectors or raw distances across fingerprints and never overwrite the active index as a
migration strategy. See [Embedding Lifecycle Operations](embedding-lifecycle-operations.md).

### 5. Select agents, skills, and hooks deliberately

#### Runtime permissions

Keep repository instructions separate from operator permissions. A portable repository should not
generate either legacy `sandbox_mode` settings or a `default_permissions` profile selection in its
root Codex configuration. Those mechanisms do not compose, and the operator's user-level or
managed configuration owns the filesystem and network boundary. A repository may still make a
review-only custom agent mechanically read-only; write-capable agents should inherit the selected
operator policy. Treat macOS Files & Folders or removable-volume approval as a separate operating
system boundary that Codex configuration cannot grant. See the current
[Codex permissions documentation](https://learn.chatgpt.com/docs/permissions).

#### Agents

Add a custom agent when separate context, permissions, or a persistent specialist role reduces
risk or main-context cost. Prefer built-in exploration or worker roles for ordinary breadth and
implementation.

- Give each agent one responsibility and output contract.
- Keep read-only reviewers mechanically read-only.
- Pass a self-contained task because subagents may not inherit parent context.
- Prefer dynamic model and effort routing. Pin a model only for a measured role-specific reason and
  record the exception.
- Do not include every specialist in every profile. Route by repository type and affected paths.

The Mir Yoke agent pack is optional maintainer/reference material. It is not part of the Starter.

#### Skills

Use a skill for an on-demand workflow or reference that would otherwise be pasted repeatedly.
Keep always-needed facts in repository instructions.

- Use one canonical `SKILL.md` body per capability.
- Write a concise, front-loaded description with positive and negative trigger boundaries.
- Put large supporting material in references and load it only after the skill triggers.
- Package reusable multi-skill sets as namespaced plugins.
- Avoid a local skill with the same slug as an enabled common plugin.

Mir Yoke's portable set is intentionally limited to three plugins and thirteen skills. The
`design`, `governance`, `efficiency`, `bluebricks`, `testing`, `code-review`, and
`verify` skills already compose this upgrade workflow; an umbrella duplicate would add discovery
cost without a new capability.

#### Hooks

Use hooks for deterministic, bounded lifecycle work that must happen automatically. Use
instructions or skills for judgment.

- Author one canonical event definition and render runtime-specific formats.
- Normalize runtime wire formats at the adapter boundary.
- Resolve the repository root rather than assuming the hook working directory.
- Keep output and time bounded, and choose fail-open or fail-closed explicitly.
- Treat project and hook trust as prerequisites. A configured hook is not active enforcement until
  the runtime trusts the project and the current hook hash.
- Test the real runtime payload, including Codex `apply_patch` in `tool_input.command`.

Claude and Codex share outcomes, not necessarily identical event sets or timeouts. Mir Yoke keeps
`config/project-hooks.json` canonical, renders Claude settings and Codex hooks separately, and
verifies both. Current runtime references:
[Codex hooks](https://learn.chatgpt.com/docs/hooks),
[Codex skills](https://learn.chatgpt.com/docs/build-skills),
[Claude hooks](https://code.claude.com/docs/en/hooks), and
[Claude customization choices](https://code.claude.com/docs/en/features-overview).

### 6. Verify generation and repository health

For every generated surface:

1. name the canonical source;
2. make regeneration deterministic and idempotent;
3. remove stale outputs when a source is removed;
4. verify semantic runtime differences explicitly; and
5. fail CI on drift.

Minimum repository checks should cover instruction budgets, generated parity, registry uniqueness,
hook executability, schemas, internal links, protected paths, secret scanning, and the actual
lint/build/test entrypoint. Broader suites and independent review are proportional to the affected
surface.

## Topic map in this repository

| Concern | Current source |
|---|---|
| Product and authority | [ADR-83](../decisions/adr-83-project-agent-kit-recipe-and-supported-surfaces.md), [ADR-84](../decisions/adr-84-harness-upgrade-guidance-and-runtime-hygiene.md) |
| Minimal adoption | [Starter](../../starter/), [Adoption bluebrick](../bluebricks/adoption.md) |
| Empty-project foundation | [Project Agent Kit](../../recipes/project-agent-kit/README.md) |
| Repository governance | [Governance skill](../../plugins/mir-core/skills/governance/SKILL.md), [Maintenance bluebrick](../bluebricks/maintenance.md) |
| Context and memory | [ADR-74](../decisions/adr-74-portable-bootstrap-capability-sources-and-memory.md), optional `mir context` and `mir memory` CLI |
| Embeddings | [Index lifecycle shape](../architecture/embedding-index-lifecycle-shape.md), [operations](embedding-lifecycle-operations.md) |
| Agents and skills | `config/repo-agent-management.json`, `config/capability-sources.json`, `plugins/` |
| Claude/Codex generation | `scripts/generate_codex_derivatives.sh`, `config/project-hooks.json`, `scripts/verify_codex_sync.py` |
| Verification and release | `scripts/verify_release_readiness.py`, `.github/workflows/validate.yml` |

## Historical boundary

`docs/harness-engineering/` and older fleet/governance decisions preserve design chronology. They
are historical, may mention removed tools, and must not be applied as current operational
instructions. Start from ADR-83, ADR-84, the current bluebricks, and this guide. Use history only to
answer a specific provenance question.

## Maintainer verification

```bash
uv run pytest -q \
  tests/test_project_agent_kit.py \
  tests/test_minimal_starter.py \
  tests/test_adr53_phase3b_context_cli.py \
  tests/test_memory_doctor.py \
  tests/test_hook_executability.py \
  tests/test_codex_derivation_script.py
uv run python scripts/verify_codex_sync.py
uv run python tests/test_link_integrity.py
uv run ruff check
```

These commands validate Mir Yoke itself. A consumer must use its own verification entrypoint.
