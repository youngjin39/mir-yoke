---
name: efficiency
description: "Token/context efficiency analysis + AI readiness cartography.\n\nTrigger: token efficiency, session efficiency, Claude usage report, Codex usage report, cost analysis, AI readiness, repo cartography, concise output, terse responses, per-turn token load\n\nAbsorbs: improve-token-efficiency, ai-readiness-cartography"
---

# Efficiency

## Use When
- When analyzing token and context efficiency across Claude Code and Codex activity.
- When auditing a repository with a qualitative AI-readiness review and ROI-ranked follow-up actions.
- When applying or evaluating the terse-output baseline on allowed local instruction surfaces.

## Absorbed legacy skills
- improve-token-efficiency — Analyze repository-level token and context efficiency across Claude Code and Codex local activity, estimate cost drivers, and produce a dashboard-ready report with concrete savings opportunities.
- ai-readiness-cartography — Review seven AI-readiness categories qualitatively, recording strengths, gaps, evidence and ROI-ranked follow-up actions; do not invent numerical scores.

Dashboard-ready describes structured report formatting, not a dashboard implementation.

## Terse-output baseline

Terse-output baseline: use no sycophantic openers or closers; do not restate the request;
lead with the result or answer; offer no unsolicited suggestions beyond the task.
Expand when ambiguity, safety, verification or operational risk needs it.
Preserve exact commands, paths and identifiers.

Inspired by drona23/claude-token-efficient at 0d30a6d.

## Workflow
1. Keep the audit read-only and define the time range, repositories, and evidence sources before collecting data.
2. Measure repeated instruction load, oversized startup context, duplicate tool calls, avoidable file reads, and rework caused by missing repository structure.
3. For AI-readiness, qualitatively review instruction discoverability, modular boundaries, verification entry points, durable state, security boundaries, documentation freshness, and cross-runtime parity.
4. Distinguish observed counts from estimates. State the formula and confidence for every cost or savings estimate.
5. Rank actions by expected saved effort divided by implementation risk, and preserve exact commands, paths, identifiers, and safety warnings.
6. Keep concise output as the baseline, but expand wherever ambiguity would weaken review, verification, or operational safety.

For on-demand instruction-change comparisons, read [per-turn input inventory and always, conditional or historical placement](references/instruction-change-evaluation.md).

For real cache-miss evidence, use [manual prompt-cache diagnosis](references/observed-cache-misses.md).
