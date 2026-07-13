# Preservation-First Reconciliation

Use this runbook when committed and uncommitted work from multiple branches or worktrees must be combined without losing owner data. It is tool-agnostic and has no dependency on a workspace service.

## 1. Freeze and identify the state

Stop writers that can mutate the repository. For every worktree, record:

- repository root, Git common directory, remotes, branch or detached state, HEAD, upstream, and relevant refs;
- `git status --porcelain=v2 -z --branch`, including staged, unstaged, untracked, rename, submodule, and conflict state;
- worktree linkage from `git worktree list --porcelain`; and
- repository-local instructions, generated-source ownership, and known verification baselines.

Stop if repository identity, HEAD, refs, or status changes before preservation completes.

## 2. Create an access-restricted backup

Create the backup outside all source worktrees under an owner-only directory (`umask 077`; directory mode 0700 and files 0600). Record hashes for every artifact without copying secret contents into logs.

The backup must contain:

1. A Git bundle covering the recorded committed refs and objects.
2. `git diff --binary --full-index` for unstaged changes.
3. `git diff --cached --binary --full-index` for staged changes.
4. A null-safe archive and manifest for every untracked owner file. Record path, type, mode, size, SHA-256, symlink target, and executable bit.
5. Any selected ignored owner material required for restoration. List inclusions and exclusions explicitly; do not silently archive caches or credentials.
6. The porcelain-v2 status, refs, submodule state, artifact hashes, commands, tool versions, and backup root in a machine-readable manifest.

Counts alone are insufficient. Every preserved path needs an identity and content fingerprint.

### Recursive submodule contract

Treat every initialized or declared submodule as a nested preservation boundary, not as a single superproject gitlink. For each submodule, recursively record its configured URL, repository identity, HEAD, relevant refs, upstream/remote relationship, porcelain-v2 status, and the gitlink recorded by its parent. Preserve unpushed committed objects in a submodule-local Git bundle; preserve staged and unstaged changes as separate `--binary --full-index` patches; and archive untracked plus explicitly selected ignored owner material with the same path/type/mode/size/SHA-256 manifest used for the superproject.

The disposable proof must initialize the recorded submodule graph recursively, restore each submodule's refs and HEAD, replay its staged and unstaged patches in order, restore its archived files, and compare its full state before comparing the parent gitlinks. Fail closed if any dirty or unpushed submodule cannot be bundled, archived, replayed, or proven equal. A clean parent status does not waive this requirement.

## 3. Prove restoration before integration

Create a disposable clone or worktree from the recorded HEAD. Verify the bundle, apply the staged patch to the index and worktree, apply the unstaged patch to the worktree, and restore archived files with their recorded types and modes.

Compare the disposable state with the source preimage:

- HEAD and relevant refs;
- porcelain-v2 status;
- staged and unstaged binary/full-index diffs;
- untracked and selected ignored path/type/mode/size/SHA-256 manifests; and
- symlink targets, executable bits, and recursively restored submodule URL/HEAD/refs/status, patches, archives, and parent gitlink state.

Any mismatch is a failed backup. Repair the preservation procedure and repeat the disposable restore before touching the live state.

## 4. Integrate semantically

Classify each change as branch-only, compatible on both sides, generated, or a true semantic conflict. Resolve canonical source files before generated projections, then run the declared generator and inspect its complete output. Preserve unrelated owner work and record an explicit disposition for every accepted, superseded, or rejected commit and patch.

Prefer a normal merge or a clean fast-forward that retains ancestry. When lineage cannot be retained, record patch-equivalence evidence. Never select `ours` or `theirs` wholesale merely to clear conflicts.

## 5. Compare verification baselines

Run focused tests and repository guards, then compare the full verification result with the frozen pre-change baseline. Store stable fingerprints such as failing test node IDs, lint rule/path tuples, and generated-diff identities. Acceptance requires no new failure family, not an unsupported claim that all historical failures disappeared.

Require no unmerged paths, no active merge/rebase/cherry-pick state, a clean scoped diff check, credential/debug scans, and an independent review appropriate to the risk.

## 6. Close without force

Remove a disposable worktree only when Git reports it clean and normal `git worktree remove` succeeds. Delete a temporary branch only with normal merged-branch deletion. If either operation would require force, retain and label the worktree/branch or archive its evidence for later owner disposition. Do not reset, force-delete, rewrite shared refs, push, or discard unknown files as cleanup.

Retain the verified backup until the owner accepts the combined state and the repository's retention policy permits removal.

## Stop conditions

Stop and preserve the current evidence when:

- any writer reappears or recorded identity, HEAD, refs, index, or worktree status drifts;
- the backup omits an unexplained path or the disposable restore is not byte/mode/state equivalent;
- a semantic conflict lacks an evidence-backed disposition;
- generated output changes undeclared surfaces;
- a required command fails or a new baseline failure family appears;
- credentials or debug artifacts are detected;
- cleanup would require force or would discard unknown owner material; or
- no deterministic preservation lane exists. In that case use `ESCALATE_HUMAN`, not repeated model retries.
