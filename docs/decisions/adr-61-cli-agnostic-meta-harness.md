---
adr: 61
status: accepted
source: mirrored-summary
---

# ADR-61 — CLI-Agnostic Meta-Harness + Global Sub-Agent Execution Policy

## Context

The public template needs a stable reference record for ADR-61 so applied-state
verification can confirm the baseline catalog is complete.

## Decision

The harness is made a CLI-agnostic meta control-plane that sits ABOVE any single agent CLI runtime
(two CLIs are wired today; others are additive, not a rewrite) and preserves its four invariants —
user-intent preservation, orchestration, execution delegation, and verification — regardless of which
CLI runs underneath. Four structural changes deliver this, each small, byte-stable, and
backward-compatible: (1) a global config-driven sub-agent execution policy selects the
delegated-execution backend (force a subprocess backend / follow the user's command / unconstrained /
per-project), defaulting to the current subprocess backend so existing behavior is unchanged; (2) the
dispatch core is neutralized from a single hardcoded backend into a policy value, with a
backend-adapter and a backward-compatible vocabulary alias; (3) a render-target registry seam emits
per-CLI artifacts so adding a third CLI is an additive registry entry rather than a pipeline rewrite
— the structure ships, concrete third-CLI renderers are deferred; (4) no-LLM external monitoring is
extended to deep cross-session observation, and a user-intent conflict surface flags a new goal that
diverges from unfinished prior intent instead of silently overwriting it. Detailed execution history
remains in the upstream control repository.

## Consequences

- The template keeps a stable ADR number map.
- Public consumers can verify baseline completeness.
- The delegated-execution backend is a configuration value, so the harness is not bound to any single
  agent CLI; the default preserves current behavior (backward-compatible).
- Adding a CLI is an additive render-target entry; user-intent conflicts surface for a decision
  rather than being silently overwritten.
