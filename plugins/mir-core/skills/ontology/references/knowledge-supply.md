# Consuming knowledge context packs

A project may configure a knowledge interface that returns a context pack: nodes, citations,
grounding information, confidence, gaps and a sufficiency assessment. Use only that configured
interface, for a bounded question the current task needs. Start with local sources; never infer a
service binding or permission from the availability of a tool or from this guidance.

## Interpret the pack

- Nodes identify records within their owner namespaces. Follow relevant citations to authoritative
  sources when a consequential claim, conflict or edit requires direct evidence.
- Grounding or a matching source hash establishes that the cited source is unchanged. It does not
  establish that the source is true, current, complete or authoritative for this decision.
- Confidence describes an assessment with its own basis and scope. It is not authority or approval.
- Mentions, co-mentions, similarity neighbours and retrieval rank are associations. They establish
  neither identity, causality, dependency nor a confirmed fact. Check typed relation evidence.
- Gaps and sufficiency describe the inspected scope. A claim of sufficiency needs a stated question,
  corpus boundary and basis; it does not establish global completeness or absence.

## Preserve provenance

Record which facts came from direct retrieval and which came from a parent-supplied pack. For a
parent-supplied pack, preserve the parent's source citations, retrieval scope and available revision
or observation time; do not describe it as a fresh direct observation. Follow up only when the
remaining uncertainty matters to the task. Distinguish extracted statements, inferred conclusions,
execution evidence and owner decisions. Retain conflicts for the appropriate owner to resolve.

## Handle degraded supply

Empty, timed-out or degraded results are reported as **knowledge unavailable**, not as absence.
They never block unrelated local work. Continue tasks that local evidence can support, and state
which knowledge-dependent conclusions remain unevaluated. Do not invent a retry loop, broaden
access or install another service to fill the gap. An absence conclusion requires an independently
established complete scope, not an empty response.

Personal knowledge planes stay behind their own approval. A general development task, parent pack,
confidence score or read capability does not authorize crossing that boundary or exposing personal
material. Keep permitted context within its approved audience and scope.
