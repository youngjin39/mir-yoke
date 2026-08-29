---
title: Harness Upgrade Guidance and Runtime Hygiene
type: template-adr
created: 2026-08-28
status: accepted
amends: [adr-74, adr-83]
schema: docs/templates/_schema/adr.schema.json
---

# ADR-84 — Harness Upgrade Guidance and Runtime Hygiene

## 1. Context

Mir Yoke has a clear four-file Starter, a supported empty-target Project Agent Kit, and an optional
installed CLI. It does not yet give an existing repository one current, topic-oriented path for
evaluating harness engineering, repository governance, context and token efficiency, memory,
embeddings, agents, skills, hooks, and Claude/Codex generated parity. The retained
`docs/harness-engineering/` corpus predates the current public-template authority boundary and is
classified as history, so it cannot fill that role without reintroducing obsolete centralization
claims.

The audit also found concrete runtime hygiene gaps:

- default `mir context pull` omits active durable facts unless history is requested;
- mirrored or superseded decision summaries can enter current-only context as active documents;
- vector search has no explicit late-enable backfill path and accepts a configurable dimension that
  the current physical table does not support;
- Codex `apply_patch` places the unified patch in `tool_input.command`, while several shared hooks
  inspect only older fields;
- generated Codex configuration still emits a deprecated hook feature alias and grants
  `danger-full-access` by default; and
- Codex supports `SessionEnd`, but the generated maintainer hook surface still treats it as
  Claude-only.

## 2. Decision

### 2.1 Current upgrade guide

Add one current, reference-only harness upgrade guide under `docs/operations/` and link it from the
root README. It will route readers by concern, identify canonical sources and checks, and explain
when to adopt or omit agents, skills, hooks, memory, and embeddings. It will not turn the historical
phase corpus into current authority, create a new consumer payload, or add a provider-side target
writer.

The three supported layers remain unchanged:

1. existing repositories compare and adapt the four-file Starter;
2. explicit empty targets may use the Project Agent Kit; and
3. owners may separately install and invoke the optional CLI or plugins.

### 2.2 Context and memory correctness

Default `context pull` will union active durable facts with current document chunks. Facts are
queried even when no document archive is registered. Obvious instruction-override,
credential-exfiltration, raw credential-value, and role-tag patterns are quarantined before
rendering; notices contain fact ids, never the unsafe body. Rendered facts retain subject identity
and content-item provenance ids. `--history` will widen both facts and documents. Fact ranking is
deterministic. Human and JSON fact rendering each have a 2,048-byte
UTF-8-safe limit; one final fact may be truncated with an explicit suffix, and later facts are
omitted. Profile, notice, and chunk budgets remain separate and visible.

Document indexing will treat normalized frontmatter statuses `superseded`, `deprecated`,
`rejected`, `archived`, and `historical` plus `source: mirrored-summary` as history.
Each archive may also declare repository-logical `historical_glob` patterns. Mir Yoke maintainers
should classify `docs/harness-engineering/**` and `docs/governance/**` in their local
maintainer configuration; the public example uses only the generic `docs/history/**` shape.
A metadata version bump will force existing local indexes to recompute that classification. When
file content is unchanged,
this is a metadata-only update: chunk ids, FTS rows, vector rows, and `vec_indexed_at` are
preserved. Semantic-status migration never deletes or regenerates embeddings. Tracked Markdown
remains the portable source of truth; SQLite remains a rebuildable local index.

### 2.3 Embedding boundary

SQLite+FTS5 remains the required baseline and vector mode remains off by default. The current
installed CLI will add `mir context sync --reindex-missing-vectors` for enabling vectors after an
FTS-only index already exists. Ordinary sync does not silently backfill. The explicit operation
refuses to start unless embedding is enabled and sqlite-vec is available, exits nonzero on any
failed or incomplete archive, and reports `vector_coverage=<indexed>/<eligible>` per archive.
Eligible means every stored external chunk in that registered archive. Documents whose vector row
count already equals their chunk count and whose vector timestamp is present remain untouched.
Each missing document is replaced in one SQLite transaction; successful documents remain committed
if a later document fails, so rerunning the command resumes from missing coverage. Enabling
embeddings requires an operator-authored complete fingerprint. The shared vector table persists
that fingerprint and rejects a different one before any additional vector is written or compared
during hybrid retrieval.

The current physical vector table supports 1024 dimensions only. Configuration will fail loudly
for another dimension until versioned physical tables are implemented. Missing-vector backfill is
not a model-change migration. A changed model, runtime,
quantization, normalization, pooling rule, or query/document instruction still requires a fresh or
versioned index as described by the embedding lifecycle guidance.

### 2.4 Claude/Codex runtime hygiene

`config/project-hooks.json` remains the canonical hook registration. Shared hook adapters will
normalize current Codex `apply_patch` input from `tool_input.command` in addition to compatible
legacy fields. Tests will use a real unified-patch fixture.

Generated root configuration will omit `sandbox_mode`, `sandbox_workspace_write`, and
`default_permissions`, because legacy sandbox settings and permission profiles do not compose and
a public template must not override the operator's user-level or managed selection. Write-capable
generated agents will inherit that selection. Mechanically read-only roles retain
`sandbox_mode = "read-only"`. ADR-85 supersedes the concurrency portion of this decision: generated
project configuration omits the root `[agents]` table and `features.multi_agent`, leaving native
agent routing and enablement to operator-owned policy while retaining the current `features.hooks`
key.

The maintainer `SessionEnd` hook will be generated for Codex with a three-second runtime timeout
override while Claude retains its existing timeout. A regression will prove the maintained closeout
path completes within that Codex limit. `UserPromptSubmit` remains intentionally Claude-only in
this change even though Codex supports the event; its per-prompt retrieval policy needs a separate
cross-runtime efficiency decision. `StopFailure` also remains runtime-specific. Generated Codex
guidance will explain project trust and per-hook review; a hook is not an enforcement claim before
the user trusts the project and the current hook hash. The generator script owns the canonical
template for generated `.codex/README.md`.

### 2.5 Agents and skills

The existing three namespaced plugins and thirteen on-demand skills remain the portable shared
capability set. No new umbrella skill is added because `design`, `governance`, `efficiency`,
`bluebricks`, `testing`, `code-review`, and `verify` already cover the upgrade workflow
through progressive disclosure.

The maintainer agent pack remains optional and outside the Starter. This decision does not update
capability-lock-bound Claude agent model pins because `.mir/capability-lock.json` is protected and
the current instruction does not explicitly authorize that protected update. The upgrade guide
will recommend dynamic model selection unless a repository records a justified role-specific pin.

## 3. Source and generation boundaries

- Author product authority in this ADR, `README.md`, `ARCHITECTURE.md`, and current bluebrick docs.
- Author the upgrade procedure under `docs/operations/`.
- Author hook registrations in `config/project-hooks.json` and hook behavior in canonical scripts.
- Author Claude agents in `.claude/agents/*.md` only when their capability lock can be reconciled.
- Generate `AGENTS.md`, `.codex/config.toml`, `.codex/agents/*.toml`, `.codex/hooks.json`, and
  `.codex/README.md` with `scripts/generate_codex_derivatives.sh`.
- Do not edit generated memory projections or `.mir/capability-lock.json` in this change.

## 4. Consequences

- Existing repositories gain a current, selectable upgrade path without receiving a fixed payload.
- Fresh sessions can retrieve current durable facts without opting into history.
- Historical decision summaries no longer pollute default context after reindexing.
- Default facts retain subject/provenance while unsafe instruction or credential values are omitted.
- Late vector enablement has a fingerprint-bound explicit path while model changes remain fail-closed.
- Shared Claude/Codex hooks inspect the current Codex patch wire format.
- Generated root and write-capable Codex agent configuration defer to the operator-selected
  permission policy; mechanically read-only roles remain explicitly read-only. Generated
  configuration uses `features.hooks` but, as amended by ADR-85, omits project-owned approval and
  native-agent routing defaults; deprecated sandbox/profile mixing, `max_threads`, and
  `features.codex_hooks` aliases are absent.

## 5. Out of scope

- Reactivating fleet rollout, drift enforcement, daemons, notifications, or `yoke` composition.
- Expanding the four-file Starter or copying Mir CLI source into Project Agent Kit targets.
- Implementing multi-model sidecar indexes, automatic model migration, destructive vector rebuilds,
  or a shared vector service.
- Editing the protected capability lock, committing, pushing, tagging, or publishing a release.
- Rewriting historical ADRs or the historical harness phase corpus as current instructions.

## 6. Verification

- Public-template identity, asset classification, link integrity, and current authority tests.
- Default active-fact retrieval, subject/provenance rendering, unsafe-value quarantine, history
  expansion, semantic document status, fingerprint-bound missing-vector backfill, vector coverage,
  and unsupported-dimension regressions.
- Codex patch wire-format tests for path safety, credential inspection, and durable-memory sync.
- Hook rendering tests for timeout overrides, `SessionEnd`, nested paths, and generated parity.
- Generated Codex configuration assertions for least privilege and non-deprecated keys.
- Full tests, Ruff, schema checks, sanitization, link checks, and clean-candidate readiness.
- `config/template-assets.json` classifies this ADR as current authority rather than historical
  catch-all material.
