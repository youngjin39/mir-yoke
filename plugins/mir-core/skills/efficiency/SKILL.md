---
name: efficiency
description: "Token/context efficiency analysis + AI readiness cartography.\n\nTrigger: token efficiency, session efficiency, Claude usage report, Codex usage report, cost analysis, AI readiness, repo cartography\n\nAbsorbs: improve-token-efficiency, ai-readiness-cartography"
---

# Efficiency

## Use When
- When analyzing token and context efficiency across Claude Code and Codex activity.
- When auditing a repository against the AI-ready rubric for a scorecard and ROI-ranked follow-up actions.
- When applying or evaluating the terse-output baseline on allowed local instruction surfaces.

## Absorbed legacy skills
- improve-token-efficiency — Analyze repository-level token and context efficiency across Claude Code and Codex local activity, estimate cost drivers, and produce a dashboard-ready report with concrete savings opportunities.
- ai-readiness-cartography — Audit a repository against the AI-ready v2 rubric (100 points across 7 categories) and produce a structured scorecard, dashboard-ready evidence, and ROI-ranked follow-up actions.

## Workflow
1. Keep the audit read-only and define the time range, repositories, and evidence sources before collecting data.
2. Measure repeated instruction load, oversized startup context, duplicate tool calls, avoidable file reads, and rework caused by missing repository structure.
3. For AI-readiness, score instruction discoverability, modular boundaries, verification entry points, durable state, security boundaries, documentation freshness, and cross-runtime parity.
4. Distinguish observed counts from estimates. State the formula and confidence for every cost or savings estimate.
5. Rank actions by expected saved effort divided by implementation risk, and preserve exact commands, paths, identifiers, and safety warnings.
6. Keep concise output as the baseline, but expand wherever ambiguity would weaken review, verification, or operational safety.
