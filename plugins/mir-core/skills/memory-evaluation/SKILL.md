---
name: memory-evaluation
description: "Evaluate or compare memory quality only when the owner requests a memory-quality evaluation or comparison. Does not activate for ordinary memory lookup, ingestion or cleanup."
---

# Memory evaluation

Inspired by xiaowu0162/LongMemEval-V2 at 2cc8c54.

## Procedure

1. Identify the target-owned memory interface, authority, frozen source history and
   workload. Do not assume an available adapter, shared database, service or writable
   store. Confirm authorized access before examining histories.
2. Build authorized cases across static recall, dynamic tracking, workflow knowledge,
   environment gotchas and premise awareness. Include changed facts, misleading
   premises and environment-specific exceptions. Prefer synthetic or redacted cases
   when real histories contain sensitive information.
3. Keep evaluation answers, category labels and benchmark metadata outside retriever
   inputs. Retain exact source spans separately for assessing retrieved evidence.
4. Compare no-memory and candidate-memory conditions on the same workload and reader
   settings with declared context limits. Report answer quality, evidence support,
   per-category results and query latency together; mark missing adapters or cases
   unevaluated rather than inventing scores.
5. Show individual errors and accuracy/latency trade-offs. Identify uncertainty in
   model-based scoring and retain independent target checks. Main adjudicates the
   recommendation; a judge score is never a hard gate or deployment authority.
6. Record conditions, source/candidate identities, results and remaining unknowns in
   the target's existing evidence log. Reuse its checks rather than creating a second
   cursor or claiming unexecuted comparisons succeeded.

## Boundaries

Invocation authorizes no automatic memory insertion, consolidation, deletion or live
replay. Do not ship upstream harnesses, memory backends, launch wrappers, downloads,
leaderboard utilities, fixed model pins or learning loops. Any runtime adapter needs
separate target-local authorization. Local cases need no benchmark download.
Do not bundle datasets, trajectories, screenshots or questions: dataset redistribution
rights require separate verification from the upstream code license.
