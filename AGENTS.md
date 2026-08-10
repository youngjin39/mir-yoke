<!-- GENERATED FILE: edit CLAUDE.md and rerun scripts/generate_codex_derivatives.sh -->

# Mir Yoke — Harness Template Contract

Mir Yoke is a public template, not an agent runtime, and has no standing authority; adoption is an explicit local action.

## Outcome and completion

- Maintain an agent-guided Claude/Codex harness template fitted to each repository without private fleet policy.
- Finish when it works for a clean adopter and relevant evidence, scope, issues, and risks are clear.

## Sources

- `mir bootstrap` automates macOS, Linux, and WSL; afterward `.mir/repo-profile.toml` owns identity
  and boundaries. Native Windows stops before mutation. Ready requires explicit identity/content.
- For substantial work, run one task-scoped `uv run mir context pull "<query>"`; add path/risk or
  expand only for missing, stale, or conflicting evidence.
- Ready projects require local SQLite+FTS5 and project-specific FTS hits. `.mir/memory.db` is local;
  Phase 2 requires four-layer coverage, zero open gaps, and a passing full review.
- `config/capability-sources.json` and `.mir/capability-lock.json` own Git provenance and hashes;
  remote checks are read-only and activation requires explicit apply.
- Before changing requirements, agents, or skills, run `mir capability check`; review before apply.

## Authority and safety

- Read, review, and status requests are non-mutating; change, fix, or build requests authorize only
  in-scope repository edits and relevant verification.
- Get explicit direction before destructive actions, credential or secret access, external writes
  or messages, protected-scope mutation, or material scope expansion.
- Keep the public surface generic and sanitized. Adopter-specific policy remains adopter-owned.
- Treat shipped assets as a baseline for agent judgment, not a universal installer. Read the target
  contract and state, select applicable controls, and ask before materially expanding scope.
- A full checkout is provider source, not a product payload; R20 blocks product work. Phase 1
  externalizes the CLI; only passing Phase 2 may slim and publish ready. Never delete manually.
- Edit canonical sources first: `CLAUDE.md`, bootstrap/profile, `.claude/agents/`, and plugin skills.
  Regenerate `AGENTS.md` and `.codex/`; project skills use unique names.

## Execution and evidence

- Run the smallest check that can fail for changed behavior; use broader verification only when the
  affected risk or coupling requires it.
- Read `.ai-harness/bluebricks.md` only when architecture, delegation, or integration matters. Read
  `.ai-harness/session-closeout.md` only for explicit closeout.

Commands: `uv run pytest`, `uv run ruff check`, `uv run mir bootstrap --help`, `uv run mir capability
--help`, `uv run mir memory doctor --help`. Artifacts are English; user-facing language is local.

## Role policy (template summary)

<!-- template:profile:role-policy:begin -->
### Template Harness

- The opened Claude or Codex CLI acts as `control_plane`; both own final scope and verification.
- `codex_first` / `code_tdd_review_plane` is a delegated-lane preference, not a direct-work gate.
- All detailed path, capability, boundary, and gate values remain canonical in `.mir/repo-profile.toml` and are read only when relevant.

<!-- template:profile:role-policy:end -->
