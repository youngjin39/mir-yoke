# Manual diagnosis of observed prompt-cache misses

Inspired by bugbug9999/token-diet at 82ac6a7 (ideas only, no license; wording original).

Use when the owner has actual cache-miss evidence, not merely a high token estimate.
This procedure recommends checks to Main and changes no host or provider settings.

1. Record provider, exact model/revision, request time, session identity and reported
   input/cached token fields from authorized redacted telemetry. Missing cache metrics
   mean Unknown, not a demonstrated miss. Separate an initial cold request from a
   formerly warm workload; low cached counts alone do not identify a cause.
2. Compare a hit and miss for equivalent work where records exist. Inventory the
   ordered prompt prefix: global/project instructions, memory, skill metadata, tool
   schema and message order. Record identities or safe hashes, not sensitive content.
   Locate the earliest known change; stable text later in the input may be irrelevant
   if an earlier prefix changed. Model switches and schema changes are hypotheses.
3. Check routing/model changes, instruction edits, dynamic timestamps or injected
   state, tool additions/removals/schema ordering, context compaction and elapsed
   time. Separate observed differences from inferred causes and unavailable fields.
   Consult the applicable provider/model contract before assuming minimum lengths,
   TTL, invalidation rules or prices; no universal TTL or discount is asserted here.
4. If comparison requests are already authorized, hold the workload and model fixed
   and vary one suspected factor. Compare repeated observations under stated cold
   and warm conditions, reporting input/cached counts, latency and known confounders.
   Otherwise report the proposed comparison as unrun. Do not send diagnostic traffic
   merely to keep caches warm: no keep-alive traffic or automatic probing.
5. Report the measured miss, candidate prefix changes, evidence strength, Unknown
   fields and one bounded recommendation. Do not change models, remove necessary
   context, reconfigure tools or promise savings without Main's direction and checks.
