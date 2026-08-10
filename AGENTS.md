<!-- GENERATED FILE: edit CLAUDE.md and rerun scripts/generate_codex_derivatives.sh -->

# Mir Yoke — Local Harness Platform Contract

Mir Yoke is a public, agent-guided local project-harness platform and reference implementation, not
an agent runtime. It is not a universal installer and has no standing authority over consumer
repositories. `starter/` is the only required and default consumer payload; optional packs are
explicit opt-ins.

## Outcome and completion

- Maintain the four-file documentation-only core, declared capability packs, profiles,
  deterministic distribution, and preserved platform implementation.
- Finish when the affected product-plane contracts and smallest relevant checks pass.

## Sources

- `starter/HARNESS.md` is the canonical consumer contract template.
- `docs/decisions/adr-82-product-planes-capability-packs-and-composition.md` owns product planes,
  pack support, and composition; ADR-81 owns the minimum core.
- `config/product-planes.json` and `packs/*/pack.json` own machine-readable product boundaries.
- `config/template-assets.json` classifies the full maintainer checkout.
- `.mir/repo-profile.toml` owns this maintainer repository's local boundaries when present.

## Authority and safety

- Read, review, and status requests are non-mutating; change requests authorize only named scope.
- Get explicit direction before destructive actions, credentials, external writes, protected scope,
  commits, pushes, releases, or material scope expansion.
- Preserve unrelated local changes and keep public material generic and sanitized.
- Consumer repositories own every adapted result. Mir Yoke never discovers or mutates them.
- Advanced memory, plugin, hook, spec, and sub-agent assets remain implemented, but are optional
  pack sources. The starter does not require them and profiles remain advisory.
- Composition planning is read-only. Apply must reject conflicts and may write only the accepted
  plan plus ignored local state and receipts.
- Edit canonical sources first and regenerate `AGENTS.md`, nested `AGENTS.md`, and `.codex/`.

## Execution and evidence

- Use direct work for bounded changes; scale design, delegation, and review with uncertainty.
- Run the smallest check that can fail for changed behavior.
- For core changes, run `uv run pytest tests/test_minimal_starter.py -q` and derivative checks.
- For distribution changes, run product-plane, builder, composer, CLI, and pack-focused tests.
- Use broader tests only when affected maintainer code or release coupling requires them.

Commands: `uv run pytest`, `uv run ruff check`, `uv run yoke --help`,
`uv run python scripts/verify_codex_sync.py`.
Artifacts are English; user-facing language follows the user.

## Role policy (template summary)

- The opened Claude or Codex session owns final scope and verification for this repository.
- Delegation is optional and proportional, never a direct-work gate.
- A consumer agent reads the target's current state and adapts only the smallest useful core or
  explicitly selected pack set.
