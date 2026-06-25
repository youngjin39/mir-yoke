# ops-self-evolution (example-harness module)

A **skills-only** example module for an operations / platform-ops repository where
the agent has real write authority and must govern its own changes. It ships two
skills — one that gates *task execution*, one that gates the agent's own
*self-improvement* — plus no executable code and no provider-specific wiring.

> Opt-in. This module is illustrative. Copy the skills you need into your own
> `.claude/skills/` directory and point them at your repo's own rules docs.

## What it provides

| Skill | Purpose |
|-------|---------|
| `harness/skills/execution-governance/SKILL.md` | Tier-based write gates, a 4-step promotion flow, a circuit breaker, and evidence-only completion — applied during any task that writes files. |
| `harness/skills/self-evolution/SKILL.md` | Self-improvement judgment + execution: research scan, long-term-memory reflect, risk-classified change review (Type A/B/C/D), and a 3-tier validation gate for technical claims. |

## execution-governance

The skill enforces graduated write authority instead of treating every file the same:

- **Tier 0 (free)** — proceed.
- **Tier 1 (review)** — diff preview + stated reason before writing.
- **Tier 2 (promotion required)** — a 4-step `PLAN -> APPLY -> VERIFY -> RECORD`
  flow with a written promotion record.

It also adds three cross-cutting guards: a **circuit breaker** (stop after the same
action fails twice, analyze, escalate), **evidence-only completion** (never claim
"done" without command output / a passing test / a reviewed diff), and an
**ambiguity gate** (run a clarification pass when a request has zero specificity).

The skill is the generic pattern; it expects *you* to keep a `GOVERNANCE.md` in your
repo that says which paths sit in which tier. Nothing is hard-coded to a specific
repo layout.

## self-evolution

The skill governs changes the agent proposes to *itself* (its harness, skills, or
tooling), routed through five sub-functions — `research`, `reflect`, `review`,
`validate`, `snapshot` — and two gates:

- **Type A/B/C/D classification** — trivial fixes apply immediately; user-visible
  and behavioral changes need approval / a cooling period; structural changes need
  a design doc plus the 4-step promotion above.
- **3-tier validation** — every technical claim must clear **T1 source exists ->
  T2 reproducible -> T3 valuable** before it is trusted or ingested into your
  long-term memory store.

Like the other skill, it reads a `SELF-EVOLUTION.md` you keep in your own repo as
the source of truth and refers generically to "your long-term memory store" — wire
it to whatever memory backend you use.

## Adapting it

1. Copy `harness/skills/execution-governance/` and/or `harness/skills/self-evolution/`
   into your repo's `.claude/skills/` directory.
2. Write a `GOVERNANCE.md` (tier-to-path map) and/or `SELF-EVOLUTION.md` (your
   change-type rules) that the skills point at.
3. Replace the generic "verification skill", "memory store", and "lint/validation
   check" references with your repo's actual verify gate, memory backend, and
   test/lint command.
4. Tune the tiers, the circuit-breaker threshold, and the cooling period to your
   risk tolerance.
