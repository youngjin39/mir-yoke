# Project Agent Kit Verification Contract

## Real project checks

`scripts/verify.sh` is the single repository-owned verification entrypoint. It executes explicit
`lint`, `build`, and `test` commands in that order and fails on the first non-zero exit. Each command
must exist and exercise the selected toolchain foundation.

A placeholder, `true`, `echo skip`, `--if-present`, missing-command fallback, or empty test selector
is not successful evidence. If a real command cannot run, the Project Agent Kit is incomplete.
The release observer confirms that lint and build fail when the declared compile probe is absent,
build fails when either the manifest or lockfile is absent, test fails when the smoke test is absent,
and parity fails independently for each canonical and generated reviewer surface.

The initial foundation may contain only manifests, a lockfile, a domain-neutral compile target, and
a smoke test. Those artifacts exist to make lint, build, and test real before product planning; they
must not encode an API, UI, domain model, or product feature.

## Git hook

Track `.githooks/pre-commit` and make it executable. It resolves the repository root and invokes
`scripts/verify.sh` without bypass flags or environment-specific absolute paths. After
`git init -b main`, set the local repository configuration to `core.hooksPath=.githooks` and verify
that exact value.

The hook accepts only `PROJECT_AGENT_KIT_HOOK_PHASE=direct`; an unset phase means `commit`. It writes
the marker only after `scripts/verify.sh` succeeds, using `git rev-parse --git-path` to locate
`.git/project-agent-kit-pre-commit.log`. Run it directly once with the explicit direct phase and then
prove it runs again during the initial commit. The final marker contains exactly `direct:0` and
`commit:0`, in that order. A successful commit with the hook disabled is not evidence.

## Completion checks

- no unresolved template placeholder or Mir Yoke product identity remains in target-owned files,
  except the exact source URL and revision provenance in `docs/harness-bootstrap.md` and the
  machine-readable `harness/project-agent-kit.json` provider field;
- the Claude-to-Codex generator is idempotent and its parity check passes;
- `harness/project-agent-kit.json` validates against the recipe-owned schema and binds the exact
  purpose and rendered prompt to one manifest, lockfile, domain-neutral compile probe, smoke test,
  both canonical/generated reviewer surfaces, and argv lists for parity, lint, build, and test;
- the Claude reviewer denies Write and Edit and the Codex reviewer uses a read-only sandbox;
- lint, build, and test each execute a real command and pass;
- protected and secret paths contain no generated content or captured credential;
- no global dependency was installed, every toolchain cache/home is target-local and ignored, and
  the inspected outside paths retain their before-state;
- `git config --get user.name` and `git config --get user.email` are non-empty;
- `core.hooksPath=.githooks` and `.githooks/pre-commit` is executable;
- `main` has exactly one commit named `chore(harness): bootstrap project agent kit`;
- the final worktree is a clean worktree;
- the repository has no remote and the workflow performs no push; and
- Mir Yoke and every outside path declared or touched by the bootstrap toolchain retain their
  before-state.

Maintainer clean-room observation uses only bounded, non-secret outside directories. Before running
target commands it validates the tracked foundation, rejects symlinks and extra product files, and
uses a credential-free environment with target-local home/cache/temp directories and offline package
manager flags. It content-hashes each declared outside directory and requires a preconfigured
publishable Git identity; it never changes the identity or signing policy.

Mir Yoke maintainers may claim one-prompt reproducibility only after the same published prompt
completes clean-room runs in separate empty directories under both Claude and Codex. Static contract
tests do not replace those release-time runs. Use `scripts/observe_project_agent_kit.py` to store each
run under `release-evidence/project-agent-kit/<version>/{claude,codex}/`. The release validator binds
the concrete rendered prompt to its template and the four recipe contracts, recomputes the observed
Git bundle and logs, and rejects any failed or missing invariant.
