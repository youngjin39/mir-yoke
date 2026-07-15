# Mir Yoke — Harness Template Contract

## Outcome and completion

- Maintain a public, repository-agnostic Claude/Codex harness template that adopters can fit to
  their own product without inheriting private fleet policy or unnecessary ceremony.
- Finish when the requested template outcome works for a clean adopter, the smallest relevant
  evidence passes, and changed scope, residual issues, and risks are explicit.

## Sources

- `setup.sh` owns new-clone profile defaults; after bootstrap, `.mir/repo-profile.toml` is canonical
  for repository identity, role policy, protected paths, and execution boundaries. SessionStart
  supplies compact identity and safety.
- For substantial repository-dependent work, make one task-scoped
  `uv run mir context pull "<query>" [--path <target>] [--risk low|normal|high]`; expand only for
  missing, stale, or conflicting evidence.
- `.mir/memory.db` is canonical memory; `docs/memory-map.md` and `tasks/lessons.md` are generated
  projections; do not hand-edit generated regions.

## Authority and safety

- Read, review, and status requests are non-mutating; change, fix, or build requests authorize only
  in-scope repository edits and relevant verification.
- Get explicit direction before destructive actions, credential or secret access, external writes
  or messages, protected-scope mutation, or material scope expansion.
- Keep the public surface generic and sanitized. Repository-specific workflow, hooks, agents, and
  optional capabilities remain adopter-owned unless a shared correctness or safety fix requires a
  template change.
- Edit canonical sources first: `CLAUDE.md`, `setup.sh` or the adopted `.mir/repo-profile.toml`,
  `.claude/agents/`, and `.claude/skills/`. Regenerate `AGENTS.md`, `.codex/`, and `.agents/`; do not
  hand-edit them.

## Execution and evidence

- Run the smallest check that can fail for changed behavior; use broader verification only when the
  affected risk or coupling requires it.
- Read `.ai-harness/bluebricks.md` only when architecture, delegation, or integration matters. Read
  `.ai-harness/session-closeout.md` only for explicit closeout.

Commands: `uv run pytest`, `uv run ruff check`, `uv run mir --help`.
User-facing language follows the adopter's convention. Internal docs, code, commits, and handoffs
are English.

## Role policy (template summary)

<!-- template:profile:role-policy:begin -->
### Template Harness

- The opened Claude or Codex CLI acts as `control_plane`; both own final scope and verification.
- `codex_first` / `code_tdd_review_plane` is a delegated-lane preference, not a direct-work gate.
- All detailed path, capability, boundary, and gate values remain canonical in `.mir/repo-profile.toml` and are read only when relevant.

<!-- template:profile:role-policy:end -->
