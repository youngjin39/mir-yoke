# Embedding Lifecycle Operations (self-managed)

Status: adopted template guidance (2026-07-25). Companion to
`docs/architecture/embedding-index-lifecycle-shape.md` (the target DB shape)
and `BOOTSTRAP.md` Step 2 f (the consent-gated setup flow). That pair covers
*what* the index looks like and *how* it gets enabled; this document covers
*how to operate it afterwards* — in this repository, with no central service
doing it for you.

## Ownership — who manages what

- **This repository owns execution**: adapter code, backfill, shadow
  evaluation, cutover, rollback, retention, garbage collection, and the
  evidence for all of it. Nobody else runs these steps.
- **A central control plane (if this repo belongs to an operator fleet) owns
  governance only**: a model catalog, compatibility policy, and
  target-specific directives. It never gains a write path into this
  repository; status flows upstream as redacted aggregate evidence.
- **Standalone repositories**: this whole document is yours; skip the
  upstream-relay notes.

## Day-one invariants (recap)

1. A vector is valid only with its complete encoder fingerprint — model
   identity/revision, dimension, normalization, pooling, instructions. A model
   name alone is not an identity.
2. Cache and skip decisions key on `(document_fingerprint, content_hash)`.
3. Never compare vectors or mix raw distances across fingerprints;
   cross-model comparison fuses independent rankings (e.g. RRF).
4. Exactly one `active` version per logical index; cutover and rollback are
   atomic pointer changes; rollback never re-embeds; GC is explicit and last.

## Runbooks

### R1 — Enable on a fresh environment
1. Probe the endpoint (any OpenAI-compatible `/v1/embeddings` server).
2. Get explicit user consent before installing any server or model.
3. Validate with one test call: the response dimension must be 1024 and the
   L2 norm must be approximately 1.0. The current physical vector table
   supports 1024 dimensions only; another configured dimension fails before
   indexing.
4. Fill `[memory.embedding]` in `harness_a.toml`, then `mir context sync`.
   `fingerprint` is required when embeddings are enabled and must encode the complete identity
   above, not only the model name.

### R2 — Enable late (embedding arrived after content)
Chunks indexed without vectors are **not auto-backfilled**. After enabling,
ensure sqlite-vec is available, then run:

```sh
mir context sync --reindex-missing-vectors
```

This explicit operation never falls back to FTS. It reports
`vector_coverage=indexed/eligible` per archive, leaves fully covered documents
untouched, and replaces each missing document in its own SQLite transaction.
If a later document fails, fix the backend and rerun the command; successful
documents remain covered. The shared vector table persists the active encoder fingerprint and
rejects a different fingerprint before another vector is written or used for hybrid retrieval.
Verify coverage reaches 100% of eligible chunks
before trusting hybrid retrieval. Ordinary `mir context sync` does not
backfill vectors.

### R3 — Model or runtime change
A new model — or the same model under a new runtime or quantization — is a
**new fingerprint**. Never overwrite in place:
1. Build a candidate index next to the active one; backfill resumably.
2. Run a shadow comparison against the active index before cutover. This gate
   is load-bearing: GPU OOM can silently corrupt embeddings while per-vector
   checks still pass; only corpus-level agreement catches it.
3. Cut over with an atomic pointer change; keep the previous version intact.

### R4 — Rollback
Flip the pointer back to the previous version. Rollback never requires
re-embedding. GC of retired versions is a separate, explicit, last step
(retention ceiling: candidate + active + previous).

### R5 — New machine or environment
Start a fresh index and re-embed. Never copy a vector DB produced by a
different runtime or quantization — same model name, different runtime is a
different fingerprint.

## Verification gates — record these numbers

| Gate | Expectation |
|---|---|
| Test call | dimension == 1024, L2 norm ~= 1.0 |
| Backfill coverage | 100% of eligible chunks |
| Shadow agreement | same model: ~= 1.0; new model: ranking overlap (RRF), never raw distances |
| FTS fallback | search still returns results with embedding disabled |

## Evidence

Per lifecycle run, record: date, encoder fingerprint(s), chunk counts,
coverage, shadow agreement, and the go/no-go decision — e.g. under
`tasks/reports/`. Fleet members relay redacted aggregates upstream when
asked; the fleet reads evidence, it never executes here.

## Tooling

The current CLI supports baseline SQLite+FTS5 indexing and the explicit
missing-vector backfill above. Versioned sidecar indexes, automatic model
migration, and destructive vector rebuilds are not current CLI behavior.
