<!-- GENERATED FILE: edit CLAUDE.md and rerun scripts/generate_codex_derivatives.sh -->

# Mir Yoke — Minimal Harness Template Contract

Mir Yoke is a public, agent-guided template and reference repository, not an agent runtime. It is
not a universal installer and has no standing authority over consumer repositories. `starter/` is
the only supported consumer payload.

## Outcome and completion

- Maintain the four-file, documentation-only starter and its optional reference corpus.
- Finish when the starter works as current-state-guided material and relevant checks pass.

## Sources

- `starter/HARNESS.md` is the canonical consumer contract template.
- `docs/decisions/adr-81-minimal-starter-support-boundary.md` owns supported scope.
- `config/template-assets.json` classifies the full maintainer checkout.
- `.mir/repo-profile.toml` owns this maintainer repository's local boundaries when present.

## Authority and safety

- Read, review, and status requests are non-mutating; change requests authorize only named scope.
- Get explicit direction before destructive actions, credentials, external writes, protected scope,
  commits, pushes, releases, or material scope expansion.
- Preserve unrelated local changes and keep public material generic and sanitized.
- Consumer repositories own every adapted result. Mir Yoke never discovers or mutates them.
- Advanced memory, plugin, hook, spec, and sub-agent assets are optional reference or maintainer
  material. The supported starter does not require them.
- Edit canonical sources first and regenerate `AGENTS.md`, nested `AGENTS.md`, and `.codex/`.

## Execution and evidence

- Use direct work for bounded changes; scale design, delegation, and review with uncertainty.
- Run the smallest check that can fail for changed behavior.
- For starter changes, run `uv run pytest tests/test_minimal_starter.py -q` and derivative checks.
- Use broader tests only when affected maintainer code or release coupling requires them.

Commands: `uv run pytest`, `uv run ruff check`, `uv run python scripts/verify_codex_sync.py`.
Artifacts are English; user-facing language follows the user.

## Role policy (template summary)

- The opened Claude or Codex session owns final scope and verification for this repository.
- Delegation is optional and proportional, never a direct-work gate.
- A consumer agent reads the target's current state and adapts only the smallest useful baseline.
