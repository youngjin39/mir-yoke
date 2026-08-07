# Mir Yoke — Harness Template Contract

## Outcome and completion

- Maintain a public, repository-agnostic Claude/Codex harness template that adopters can fit to
  their own product without inheriting private fleet policy or unnecessary ceremony.
- Finish when the requested template outcome works for a clean adopter, the smallest relevant
  evidence passes, and changed scope, residual issues, and risks are explicit.

## Sources

- `mir bootstrap` owns cross-platform defaults; afterward `.mir/repo-profile.toml` owns identity,
  paths, and boundaries. Require a ready receipt before normal work; incomplete runs may initialize
  or Phase 2 evidence only. Phase 1 requires explicit identity and classified content onboarding.
- For substantial work, run one task-scoped `uv run mir context pull "<query>"`; add path/risk or
  expand only for missing, stale, or conflicting evidence.
- Ready projects require local SQLite+FTS5 and project-specific FTS hits. Tracked content is durable;
  `.mir/memory.db` is local. Generated projections are not hand-edited. Phase 2 requires four-layer
  coverage, AI-ready requirements, zero open gaps, and a passing full review—not non-empty files.
- `config/capability-sources.json` and `.mir/capability-lock.json` own Git provenance and hashes;
  remote checks are read-only and activation requires explicit apply.
- Before changing requirements, agents, or skills, run `mir capability check`; review before apply.

## Authority and safety

- Read, review, and status requests are non-mutating; change, fix, or build requests authorize only
  in-scope repository edits and relevant verification.
- Get explicit direction before destructive actions, credential or secret access, external writes
  or messages, protected-scope mutation, or material scope expansion.
- Keep the public surface generic and sanitized. Adopter-specific policy remains adopter-owned.
- Edit canonical sources first: `CLAUDE.md`, the Python bootstrap coordinator or the adopted
  `.mir/repo-profile.toml`, `.claude/agents/`, and `plugins/*/skills/`. Regenerate `AGENTS.md` and
  `.codex/`. Common skills are namespaced plugins; project skills use unique names.

## Execution and evidence

- Run the smallest check that can fail for changed behavior; use broader verification only when the
  affected risk or coupling requires it.
- Read `.ai-harness/bluebricks.md` only when architecture, delegation, or integration matters. Read
  `.ai-harness/session-closeout.md` only for explicit closeout.

Commands: `uv run pytest`, `uv run ruff check`, `uv run mir bootstrap --help`,
`uv run mir capability --help`, `uv run mir memory doctor --help`. Internal artifacts are English;
user-facing language follows the adopter's convention.

## Role policy (template summary)

<!-- template:profile:role-policy:begin -->
### Template Harness

- The opened Claude or Codex CLI acts as `control_plane`; both own final scope and verification.
- `codex_first` / `code_tdd_review_plane` is a delegated-lane preference, not a direct-work gate.
- All detailed path, capability, boundary, and gate values remain canonical in `.mir/repo-profile.toml` and are read only when relevant.

<!-- template:profile:role-policy:end -->
