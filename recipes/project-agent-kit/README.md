# Project Agent Kit Recipe

This is a supported agent-guided recipe, not a consumer payload or executable installer. It turns
one project-purpose prompt into a repository-owned Claude and Codex working contract that is ready
for later development planning. Mir Yoke is read-only reference material throughout the flow.

Use this recipe only for one explicit empty target directory. An existing repository, a directory
inside another Git worktree, or a target with repository-owned files must use the preservation-first
`starter/` adoption flow instead. The recipe does not copy Mir Yoke's Git history, mutate Mir Yoke,
discover other repositories, or run `yoke plan` or `yoke apply`.

## Required input

The prompt supplies the project purpose and goals. Derive observable success conditions, users,
non-goals, and constraints from that material. If the product stack is absent, select the smallest
conventional stack that can satisfy the stated purpose and record the choice as an assumption. Stop
before mutation when a consequential product decision cannot be derived or the required toolchain
is unavailable.

Record the exact Mir Yoke URL and observed release tag or commit in
`docs/harness-bootstrap.md`. This is provenance only; the target does not track template drift.

## Phase 1 — Preflight

Before writing:

1. resolve and report the absolute target root;
2. prove that the target is empty and is not inside an existing Git worktree;
3. inspect the selected runtime, package manager, linter, builder, and test runner;
4. run `git config --get user.name` and `git config --get user.email` and stop if either is empty;
5. inspect protected paths, credential boundaries, and external systems named by the project; and
6. snapshot the read-only Mir Yoke revision and the target's empty state.

Never invent a Git identity, change global Git configuration, read credentials, configure a remote,
or push. Do not install a global dependency or allow a package manager, compiler, linter, builder,
or test runner to write a cache or home outside the target. Use a preinstalled dependency-free
foundation or redirect every such path to a target-local ignored directory; stop if neither is
possible.

## Phase 2 — Project-owned foundation

Create only the foundation needed to make the future planning session reliable:

- `PROJECT.md` — purpose, goals, users, success conditions, non-goals, selected stack, assumptions,
  and open product decisions;
- `HARNESS.md` — repository outcome, authority, protected and generated paths, work style, and the
  real verification entrypoint;
- `CLAUDE.md` and `AGENTS.md` — thin runtime entrypoints to the same `HARNESS.md` contract;
- a project-specific `README.md`, not the Mir Yoke adoption guide;
- a minimal `.gitignore` for the selected target-local cache and build outputs;
- `docs/harness-bootstrap.md` — source provenance, generated surfaces, selected checks, and
  unresolved assumptions;
- `harness/project-agent-kit.json` — an instance of
  [`project-agent-kit.schema.json`](project-agent-kit.schema.json) recording the exact purpose and
  rendered-prompt hashes, observed provider revision, project slug, toolchain manifest, lockfile,
  domain-neutral compile probe, smoke test, a unique `context_probe` token taken from the purpose,
  canonical/generated reviewer paths, common harness
  paths and commands, and verification argv used by the observer;
- the bounded common harness adapted from `templates/common-harness/`: `harness_a.toml`, the
  canonical handoff, a project-owned thin memory-sync wrapper, and `scripts/mir.sh` rendered with
  the exact observed Mir Yoke revision; and
- the smallest toolchain manifest, lockfile, domain-neutral compile target, and smoke test needed
  for real lint, build, and test commands.

The target must never copy `src/mir/`, `tools/`, or `plugins/`. `scripts/mir.sh` invokes the exact
external provider revision and confines its home, caches, tools, Python installs, and temporary
files below ignored `.mir/runtime/`. Add `.mir/` to `.gitignore`; `.mir/memory.db` is a local index,
never a tracked source of truth.

Before the first commit, run the exact `common_harness.commands` in manifest order:
`memory_init`, `memory_sync`, `memory_doctor`, then `context_pull`. Doctor must report ready and the
pull must use `intent.context_probe` to recover the full project purpose from the indexed
`PROJECT.md`, `HARNESS.md`, `docs/`, and `tasks/` archive. Delete the
database once, rerun those four commands, and prove the same ready state so the ignored database is
rehydratable from tracked sources.

Do not create a development plan, API, UI, domain model, product feature, credential, deployment,
remote, or release configuration. Every placeholder must be resolved before verification.

## Phase 3 — Project-specific reviewer

Follow [`reviewer.md`](reviewer.md). Create one repository-unique code-review skill and one
read-only reviewer agent. Keep Claude sources canonical, generate the Codex surfaces, and provide an
idempotent parity check. Common Mir plugin skills remain optional host capabilities; do not copy or
shadow their common slugs.

## Phase 4 — Verification and Git boundary

Follow [`verification.md`](verification.md). Create `scripts/verify.sh` with real, fail-fast
`lint`, `build`, and `test` steps. Create the tracked `.githooks/pre-commit`, set its executable bit,
invoke `scripts/memory-sync.sh` before the project checks, and configure `core.hooksPath=.githooks`
after Git initialization. The hook records a successful
direct run as `direct:0` and the automatic initial commit invocation as `commit:0` in
`.git/project-agent-kit-pre-commit.log`; no other marker is valid.

After the pre-Git `scripts/verify.sh` check passes:

1. run `git init -b main` in the exact target root;
2. configure only the repository-local hook path;
3. run `PROJECT_AGENT_KIT_HOOK_PHASE=direct .githooks/pre-commit`;
4. stage only the Project Agent Kit foundation;
5. inspect the staged diff;
6. commit with `chore(harness): bootstrap project agent kit`; and
7. prove that `main` has exactly one commit, the worktree is clean, and no remote exists.

The commit must invoke the real pre-commit hook. Never bypass signing or hooks. A configured signing
policy or missing author identity that prevents the commit is a visible blocker, not permission to
weaken Git policy.

## Completion

Report the target root, Mir Yoke revision, created surfaces, exact verification and common-harness
commands with exit status, memory rehydration result, initial commit hash, assumptions, and open
product decisions. Finish with
`READY_FOR_DEVELOPMENT_PLANNING` only when every required gate passed. Product planning and
implementation begin in a later user request.
