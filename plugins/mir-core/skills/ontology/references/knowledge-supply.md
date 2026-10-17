# Consuming Memory Keeper context packs

Start with local authoritative sources and `ontology_check.py lookup`. For external context,
use the supported stdlib [consumer client](../scripts/mk_query.py) from the installed skill:

```sh
python3 scripts/mk_query.py --repo "$PROJECT_ROOT" --soft query "bounded question" --k 3
python3 scripts/mk_query.py --repo "$PROJECT_ROOT" feedback "federation:42" used
```

The client reads `$MIR_KNOWLEDGE_SUPPLY_CONFIG`, else `~/.mir/knowledge-supply.json`. The file
must be host-local, outside the consumer repository, and contain only launch configuration:

```json
{"memory_keeper":{"command":["python3","-m","mir.federation.mcp_server","--binding","federation"],"cwd":"<absolute-host-local-checkout>","timeout_sec":30}}
```

Replace the placeholder locally; use the host's existing interpreter/environment. Do not commit
this file, host paths, private names or credentials. Repository-local configuration is refused.
In a 1.1.0 mapping, `knowledge_supply` may declare
`{"memory_keeper":"connected","binding":"on_demand_stdio"}`; this labels transport, not access.
The contract also accepts `resident_stdio`; this client always owns an on-demand child.

It sends MCP `initialize`, `notifications/initialized`, then `tools/call federation_serve` over
newline-delimited JSON-RPC stdio. It prints the JSON ContextPack, closes the child and always reaps
it; on timeout it kills the owned process group on POSIX. Same-host stdio is the supported
transport; remote access is unsupported. `--client-name` overrides the default
`<repo-dir-name>-agent` telemetry label and grants no authentication or authority.

Missing config, spawn/transport/MCP errors and deadlines print
`{"status":"unavailable","reason":"..."}`. An empty pack prints
`{"status":"empty","reason":"..."}`. Both exit 0 with `--soft`, else 2; local work can continue.
Structured refusal objects pass through unchanged. A personal-namespace MCP error is unavailable;
the client never retries through a broader binding. Feedback is explicit and has MK-side effects.

This guide follows the MK federation MCP server, serve and assembly interfaces.

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

### Agent handoff and delegation

For a handoff or brief to another agent, the parent sends and the child checks this minimum packet,
using only task-relevant mapping entries and sources:

- **Qualified target:** namespace + local id, including the project-owned sub-namespace if used.
- **Status per axis:** lifecycle, temporal, epistemic and verification, preserving local meanings
  and keeping what an actor knew or believed at a given time separate from what is true.
- **Current pins:** repository root, HEAD, source path@revision or content hash, and map/contract
  id, version and digest. Identify which source each pin covers.
- **Evidence:** claim, source and provenance (direct retrieval or inherited evidence), observation
  time, method and conclusion scope. Retain source revision/hash and citations.
- **Explicit unknowns:** missing pins, unavailable or conflicting evidence, and unresolved meanings.
- **Authority:** what the child may / may not do under the current owner instructions and policy.
  A parent's ability to perform an action does not itself authorize the child to perform it.

The child marks each item `verified-in-repo` or `parent-supplied`; record the checked source and
observation time for the former, and preserve the parent's attribution and time for the latter.
Missing fields stay explicit unknowns, not assumed current facts. Recheck affected claims when
HEAD, a pinned source or the map/contract changed; do not relabel inherited evidence as verified
without a local check. Verify only what the task needs and current authority permits.
