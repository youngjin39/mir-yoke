# ADR-49 — Opus 4.8 Alignment, Task-Weight Model-Tier Routing, and Runtime Orchestration Prompt Codification

## Decision

The public template adopts three aligned, advisory changes:

- **Opus 4.8 is a drop-in upgrade.** No harness structural change is required when agents reference model *aliases* (for example `model: opus`) instead of hard-pinned version strings. The effort tiers `low | medium | high | xhigh | max` are available; `xhigh` is the recommended tier for coding and agentic lanes. Stale example version strings in schema and documentation surfaces are refreshed to the current model.
- **Optional `effort` frontmatter field.** Add an optional `effort` field to the agent frontmatter schema with the enum `low | medium | high | xhigh | max`. It is *not* required, so existing agents validate unchanged. Coding/agentic and reasoning-heavy review lanes may opt into a higher effort tier; all others fall back to the model default.
- **Task-weight → model-tier routing (advisory) + governed runtime prompts.** Extend the existing `tiny / normal / heavy` task classification into an advisory task-weight → model-tier / effort recommendation, and codify the two runtime-override orchestration prompts (a control-plane variant and an execution-plane variant) as a maintained, symmetric template instead of ad-hoc pasted session text.

### Advisory routing guidance

| Task class | Sub-agent model | Execution-plane reasoning effort | Typical use |
|---|---|---|---|
| `tiny`   | `haiku`  | `low`–`medium`  | trivial bounded single-file edits, lookups, formatting |
| `normal` | `sonnet` | `medium`–`high` | standard bounded implementation or review slice |
| `heavy`  | `opus`   | `xhigh`         | multi-file, ambiguous, architecture, final verification |

The model column applies to control-plane (Claude-backed) sub-agents; for execution-plane sub-agents only the reasoning-effort column applies. Routing is **advisory**: the orchestrator selects a tier from the existing escalation signals, records the choice (and any override) in the plan or handoff, and the choice is audited after the fact. There is **no hook that blocks dispatch** on tier mismatch.

## Why

- Captures the Opus 4.8 capability gains with zero structural churn by relying on model aliases.
- Reuses the single `tiny / normal / heavy` classifier — one classifier, two outputs (gate strictness and model tier) — rather than introducing a parallel classification.
- Keeps tier choice **opt-in per consuming repository**, because the right tier map is repository-specific; a single uniform map is not forced onto every consumer.
- Turns the previously ad-hoc, pasted runtime prompts into a version-controlled, symmetric, shareable contract.
- Stays inside the advisory orchestration boundary: routing is a prompt-level self-check plus post-hoc audit, never a hook block.

## Consequence

Template consumers inherit:

- an optional `effort` field they may set on coding/agentic lanes (and a schema-bump posture when a new effort tier appears, since the field is an enum);
- an advisory routing table that maps task weight to a model tier and reasoning effort, with overrides recorded in the plan or handoff;
- canonical control-plane and execution-plane runtime-override prompt variants, both stating explicitly that the prompt is an **overlay** on top of the standing harness gates (design-first gate, test ledger, verification evidence, agent eligibility) and not a replacement for them.

The routing prompts and `model_routing` assignments are opt-in; cosmetic version refresh and `effort`-field availability are low-risk and may be applied directly. Advisory routing is not deterministically enforced and depends on orchestrator discipline plus post-hoc audit.
