---
title: Fleet Rollout Report Contract
status: approved
date: 2026-05-28
owner: codex
related:
  - ../phase-9-fleet-catalog.md
  - ../phase-10-rollout-pipeline.md
  - ../../decisions/adr-48-central-fleet-management-and-direct-apply-2026-05-28.md
---

# Fleet Rollout Report Contract

## 0. Purpose

your-harness must maintain a per-repository rollout report after every direct-apply cycle.

The report is not optional.
It is the user-facing management surface for:

- current harness state
- applied patch summary
- enabled harness features
- managed agent status
- verification result
- AI/readiness score

## 1. Required Fields

Each report must include:

1. repository slug
2. repository path
3. repository type
4. inspection timestamp
5. current harness surfaces present
6. minimum patch plan summary
7. applied patch summary
8. enabled harness features
9. enabled or managed agent summary
10. verification commands
11. verification results
12. AI/readiness score
13. open exceptions or risks
14. rollback note

## 2. Suggested Output Shape

```text
Repository: <slug>
Type: <type>
Inspected at: <timestamp>
Current harness surfaces:
- ...
Minimum patch plan:
- ...
Applied patch summary:
- ...
Enabled harness features:
- ...
Managed agents:
- ...
Verification:
- command: ...
- result: ...
AI/readiness score: <score>
Open exceptions:
- ...
Rollback:
- ...
```

## 3. Storage Rule

Suggested location:

- `tasks/reports/<slug>_harness_rollout_<date>.md`

Catalog linkage:

- `config/fleet-harness-state.json` should point to the latest report indirectly through timestamped state and verification notes.

## 4. Management Rule

your-harness must keep the latest report understandable without reading the full git diff.

The report should answer:

- what was there before
- what your-harness changed
- what was verified
- what still remains risky

## 5. AI Score Rule

`AI/readiness score` should reflect rollout usefulness, not vanity.

Recommended factors:

- harness surface coverage
- agent surface availability
- verification automation coverage
- rollout drift level
- reporting completeness

## 6. Exit Rule

A direct-apply wave is not complete for a repository until its report exists.
