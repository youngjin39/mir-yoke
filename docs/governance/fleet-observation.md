---
title: Fleet Observation Design
keywords: [fleet, observation, facts, checks, scorecards, autonomous-fix, advisory, import]
created: 2026-05-20
last_used: 2026-06-07
---

# Fleet Observation Design

How a meta-harness inspects the repositories it manages without
becoming intrusive.

The model is a 3-layer read-only pipeline (Facts → Checks →
Scorecards), inspired by Backstage Tech Insights, with the
autonomous-fix and advisory lanes layered on top.

## Layered model

### Layer 1 — Facts (measurement)

Eight measurement axes, each a small Python module that emits typed
`Fact` records into the repository's profile. All measure paths use
a `ReadOnlyPath` wrapper so they cannot mutate the inspected
repository — write attempts on the measurement side fail loudly.

| Axis | Sample facts |
|---|---|
| `harness` | `harness.hooks.<name>.exists`, `harness.hooks.<name>.sha256`, `harness.codex_hooks_json.triggers`, `harness.rollout_class.value` |
| `agent` | `agent.count`, `agent.<name>.frontmatter.execution_backend`, `agent.execution_backend.{claude,codex}_count` |
| `context` | `context.claude_md.size_bytes`, `context.claude_md.section_count`, `context.claude_md.max_section_size_bytes`, `context.claude_md.line_count` |
| `token` | `token.cache_hit_rate`, `token.cache_read.sum`, `token.cache_creation.sum`, `token.average_per_session`, `token.cache_read_to_creation_ratio` |
| `skill` | `skill.count`, `skill.<name>.frontmatter.parsed`, `skill.<name>.compatibility`, `skill.<name>.allowed_tools` |
| `tool` | `tool.count`, `tool.<name>.is_package`, `mcp.json.exists`, `mcp.server.count` |
| `migration` | `migration.current_stage` (read from the repository's local profile) |
| `usage` | `hook.<name>.last_invoked_at`, `hook.<name>.invocation_count_7d`, `usage.invocations_log.exists` |

### Layer 2 — Checks (evaluation)

A YAML registry holds the active checks. Each check carries:
- `severity` ∈ {`deny`, `auto-fix`, `warn`, `violation`}
- `fact_query` — a small DSL like
  `agent.<name>.frontmatter.execution_backend in [claude, codex]`
- `applies_to` filter (management mode, archetype)
- `scorecard_group` ∈ {`harness_structure`, `agent_structure`,
  `context_efficiency`, `token_efficiency`}
- `weight` used by the scorecard layer

Checks read Layer 1 facts; they never measure on their own. A
failing check produces a `CheckResult` with a `finding` string.

### Layer 3 — Scorecards

Per-group weighted ratios collapse the check results into three
integer score slots (0-100):
- `ai_readiness_score`
- `token_efficiency_score`
- `context_efficiency_score`

Score slots are deliberately **fixed at three**. New measurement
axes extend the fact namespace and the check registry; they do not
create new score slots. This keeps the dashboard surface stable.

## Bucket decision

Each `CheckResult` is routed to one of four buckets:

| bucket | meaning | lane |
|---|---|---|
| 1 | deny — hard invariant violation | autonomous fix lane |
| 2 | auto-fix — low-impact deterministic patch | autonomous fix lane |
| 3 | warn — hook-risk or self-modification candidate | advisory lane |
| 4 | violation — soft advisory | advisory lane |

Routing is **archetype × management-mode aware**. A `deny` check
on `harness_structure` is downgraded from bucket 1 to bucket 3 when
the target is not a control repository or a self-hosted variant —
this is principle 1's autonomy guard.

## Autonomous fix lane (S2)

When a check lands in bucket 1 or 2 and the target is not a
control repository, the meta-harness can apply a deterministic
patch. The safety net is five-layered:

1. Family-level lockfile (`flock LOCK_EX`) so two fix attempts
   never overlap.
2. Patch attempts run in a temp git worktree, not the working
   tree.
3. Each patch carries an explicit manifest of paths it owns;
   `git clean -fd` is restricted to the manifest.
4. The worktree HEAD is captured before any cherry-pick; revert is
   automatic on failure.
5. Verify gate (e.g. profile schema validation) blocks commit when
   the patched state cannot be re-validated.

The patch is generated as a Codex CLI invocation: the meta-harness
produces the patch text; an external Codex subprocess applies the
file edits inside the temp worktree. The patch generator never
edits files directly — it only constructs the prompt.

## Advisory lane (S3)

Bucket 3 and 4 findings produce an advisory handoff document
(`tasks/handoffs/fleet-advisory-<date>.md`). The handoff is
mandatory before any sub-agent is spawned to act on the advisory.
Hook-risk findings stay in this lane permanently; they never
graduate to autonomous fix.

## Import lane (S4)

When a new agent / skill / hook arrives from outside the fleet, it
flows through a wave-based rollout:

- **Wave 0 canary** — apply to a single high-fit recipient.
- **Wave 1 fan-out** — apply to remaining fits if the canary
  is clean.
- **Rollback** — automatic on canary failure.

The input spec is JSON-Schema validated with `additionalProperties:
false`; an unknown frontmatter key halts the import rather than
silently accepting an undeclared surface.

Family-to-family transplant uses the optional `source_family_slug`
field; the scoring layer adds bonuses when the source and target
share archetype or management mode.

## Pattern catalogue

The fleet catalogue lives at `docs/patterns/` (one markdown file
per pattern) and `docs/patterns/INDEX.md` (auto-generated index).
Each pattern carries a frontmatter that records its source
repository, license, target archetypes, and adoption notes — the
metadata that the import lane reads when scoring a transplant.

## Self-protection

The meta-harness manages its own repository as the 16th fleet
target, but with strict self-protection:

- Autonomous fix is refused on the self-target (bucket 1 / 2 is
  re-routed to ASK semantic).
- Profile persist requires an explicit `--allow-self` flag.
- Archive operations require `--confirm` even on self.

This prevents the harness from rewriting its own enforcement
surfaces while keeping its measurement pipeline honest.
