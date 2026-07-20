# Graph Engineering — Structuring Guide

This is not a concept explainer. It specifies how a harness structures a recurring multi-step
flow when it fixes one in place. Intent: whenever a fixed mechanism is built — a pipeline, an
orchestration preset, an automated flow — it is built as an explicit graph (named stages,
explicit transitions, owned state, per-stage verification) instead of an implicit model-driven
habit.

## Promotion criteria — when to fix a flow

Promote a flow from runtime model judgment to a fixed structure only when all three hold:

1. The same multi-step flow has run 2–3+ times with the same stage order.
2. Stage boundaries are stable — per-stage inputs and outputs no longer change between runs.
3. Every stage produces a verifiable artifact (file, test result, rendered output, API response).

Keep exploratory, one-off, or still-evolving work model-driven. Premature fixing buys no
reproducibility and costs flexibility and maintenance.

## Required structure for a fixed flow

A promoted flow must declare all six, in its own repository-owned mechanism:

1. **Stages (nodes)** — named units of work, one owner each (script, agent, or tool call),
   single responsibility per stage.
2. **Transitions (edges)** — what decides "next": on-success, on-failure, and conditional
   branches written down, not re-decided per run. Stages with irreversible external effects
   (publish, upload, send, delete) sit behind an explicit approval gate or a dry-run default.
   Any cycle (retry/refine loop) declares a budget — max iterations, tokens, or wall-time —
   and budget exhaustion is a failure edge, not a silent continue.
3. **State** — where inter-stage data lives (files, DB, task doc), who writes it, and its
   declared shape (schema, typed object, or documented file contract). No hidden state that
   exists only in conversation context.
4. **Per-stage verification** — the smallest check that can fail for that stage's output; a
   failing check blocks the success transition.
5. **Resume point** — a rerun starts from the failed stage, not from scratch; declared state
   must be sufficient to resume. Side-effecting stages must be idempotent or guarded by an
   already-done check, so a resume never double-publishes.
6. **Run record** — each run leaves a trace: stages executed, verdicts, artifacts produced.

## Maturity ladder

Place every recurring flow on this ladder; move it up only when the promotion criteria hold.

- **L0 model-driven** — the agent decides each step at runtime. Correct for exploration.
- **L1 documented preset** — stage list exists as a doc/skill/preset; execution still relies on
  model judgment. A stage list without transitions and verification is L1 — do not call it fixed.
- **L2 orchestrated** — stages dispatched to role-scoped subagents or workflow scripts;
  transitions and verification explicit. Independent items may fan out in parallel and fan
  back in; latency then scales with the slowest branch, not total work.
- **L3 code-fixed** — control flow lives in code (script, CLI, state machine); the model runs
  inside stages, if at all.

Higher is not universally better; pick the lowest level that delivers the reproducibility the
flow needs. Creative or content stage *bodies* usually stay model-driven while stage *order*
and verification move to L2–L3.

## Anti-patterns

- Graphing exploratory work that has not stabilized.
- Stage lists relabeled as pipelines (L1 presented as L2+).
- Inter-stage state carried only in chat context.
- One giant stage that hides the real transitions.
- Happy-path-only graphs with no failure edge.
- Unbounded cycles — a retry/refine loop with no declared budget.

## Local mapping

Each harness maps these requirements onto its own primitives — workflow scripts, orchestration
presets, Python pipeline modules, Makefiles, CLI runners. The six structure requirements are
the contract; the mechanism is repository-owned and is never overwritten by a central template.
