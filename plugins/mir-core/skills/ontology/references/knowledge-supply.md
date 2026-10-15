# Consuming Memory Keeper context packs

Use only the project's configured MK binding for a bounded question; start with local sources.
This guide follows `src/mir/federation/{mcp_server,serve,assemble}.py` in Memory Keeper.
The supported transport is same-host stdio; remote access is unsupported. Generic launch form:

```sh
uv run --project <memory-keeper-checkout> python -m mir.federation.mcp_server --binding federation
```

## Tools

- `federation_serve(query, namespaces?, k?)`: `query` is a nonblank string, at most 8192
  characters. `namespaces` is omitted/null or a nonempty string list drawn from `ns:core`,
  `ns:shared-ops`, `ns:fleet-ops`, `ns:skills` (reserved). `k` is an integer, default 10,
  range 1–100; booleans are rejected. It bounds candidates, not returned node count.
- Personal namespaces are refused by federation. Do not widen access or switch bindings to bypass it.
- `feedback(node_ref, verdict)`: use a received citation's `node_ref`, an existing positive
  signed-64-bit ID (integer or string), or `federation:<id>`. Verdicts are `used`, `confirmed`,
  `contradicted`, `acted_on`. The result is `{node_ref, verdict, issuer}`; the reference is echoed
  as text. Feedback writes MK-internal usage/confirmation/dispute state only, never the consumer
  or source repository. A verdict does not itself prove truth or grant authority.
- `ctx` is injected; client name, issuer, paths, visibility and timeout are not tool arguments.
  Client name labels telemetry; it is not authentication. Serve also records MK query telemetry.

## Read the `mir-context-pack-v1` response

- Check `schema_version` and `query`. Read `nodes` with `citations`, not just the first result.
- Preserve node provenance: `namespace`, `db`/`scope`, `node_id`, `source_slug`, `source_ref`,
  `source_content_hash`, `evidence_id`; citations carry `namespace`, `node_ref`, `source_ref`,
  `evidence_id`. Keep feedback references unchanged and qualify external identities by owner.
- `content`, `title`, `summary`, `when_to_use` provide evidence and usage guidance. Follow relevant
  source citations for consequential claims. A matching `source_content_hash` is not truth.
- `grounding=confirmed` means source-byte/lineage verification, not a true assertion;
  `stale` signals mismatch and `unverifiable` means confirmation is unavailable.
- `confidence` and `confidence_factors` are scoped assessments, not authority or approval.
  `snapshot_age_sec` may be null; age alone is not a universal expiry threshold.
- Read node `status` and `flagged`. Normal MCP retrieval admits active, source-confirmed,
  noncontradicted nodes. Also inspect any `Metadata: status=...; ... valid_to=...` line in
  fleet-derived content: source lifecycle/validity is distinct from the node's own status.
  Expired, superseded or conflicting source claims cannot establish current facts.
- `retrieval_score`, `fts_rank`, `vec_distance` rank associations; they do not establish identity.
- `gaps` describe unmet facets (`facet`, `why_unmet`, `suggested_source`); `sufficiency` reports
  `sufficient`, `grounded_count`, `coverage`, `covered_facets`, `missing_facets`,
  `single_channel_supported`. These assess this query's inspected evidence, not global completeness.
  Read `degradation` (`scope`, `reasons`), `retrieval_summary`, and `next_actions` for limitations;
  `pack_id`, `top_rrf`, `total_tokens_est` identify/rank/size the pack, not its authority.

## Preserve independence and provenance

Record direct retrieval separately from parent-supplied packs; preserve citations, scope and
available hashes/observation times. Do not describe an inherited pack as a fresh observation.
Consumers must bound their wait: the tools have no end-to-end timeout argument. Empty results,
timeout, stale evidence or MK being down do not prove absence. Continue local work; mark only
judgments needing missing external knowledge as lacking evidence. Retain conflicts for the owner.
Do not install services or broaden access to fill gaps. Abandoning a call does not prove it stopped.
The implementation releases the store connection and reader lease after each call, including
failure; the consumer contract's older lifetime-reader statement does not describe current code.
